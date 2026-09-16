import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Application, Candidate, Consent, InterviewSession, Organization, Plan, Question, RubricVersion
from app.security import create_session
from app.config import settings
from conftest import manager_login
from test_workflow import ANSWER, JOB


def test_ten_simultaneous_interviews_and_capacity_guard(client):
    org = manager_login(client)
    job_id = client.post("/api/jobs", json=JOB).json()["id"]
    credentials = []
    for i in range(11):
        with SessionLocal.begin() as db:
            person = Candidate(org_id=org["id"], name=f"Synthetic {i}", email=f"fixture-{i}@example.com")
            db.add(person)
            db.flush()
            application = Application(org_id=org["id"], candidate_id=person.id, job_id=job_id, status="invited")
            db.add(application)
            db.flush()
            plan = Plan(org_id=org["id"], application_id=application.id, approved=True, model_id="synthetic-demo")
            db.add(plan)
            db.flush()
            for index, criterion in enumerate(JOB["criteria"]):
                db.add(
                    Question(
                        org_id=org["id"],
                        plan_id=plan.id,
                        position=index,
                        text="Explain a concrete example and its outcome.",
                        competency=criterion["name"],
                        kind="core",
                        max_followups=0,
                    )
                )
            db.add(RubricVersion(org_id=org["id"], plan_id=plan.id, version=1, dimensions=JOB["criteria"]))
            db.add(
                Consent(
                    org_id=org["id"],
                    application_id=application.id,
                    policy_version="2026-09-v1",
                    recording=False,
                    transcription=True,
                    ai_evaluation=True,
                    device_check=True,
                )
            )
            application.recording_required = False
            auth, token = create_session(
                db,
                kind="candidate",
                subject=person.id,
                email=person.email,
                org_id=org["id"],
                application_id=application.id,
            )
            credentials.append((token, auth.csrf))

    def request(index, method, path, body=None):
        token, csrf = credentials[index]
        with TestClient(app) as c:
            c.cookies.set("talyn_candidate", token)
            return c.request(method, path, json=body, headers={"origin": "http://localhost:3000", "x-csrf-token": csrf})

    latencies = []
    start_time = time.perf_counter()

    def begin(index):
        start = time.perf_counter()
        result = request(index, "POST", "/api/candidate/start")
        latencies.append(time.perf_counter() - start)
        assert result.status_code == 200, result.text
        return result.json()

    with ThreadPoolExecutor(max_workers=10) as pool:
        states = list(pool.map(begin, range(10)))
    assert request(10, "POST", "/api/candidate/start").status_code == 429

    def answer(index):
        start = time.perf_counter()
        assert (
            request(
                index, "POST", "/api/candidate/demo-answer", {"text": ANSWER, "result_id": f"concurrent-{index}"}
            ).status_code
            == 200
        )
        result = request(index, "POST", "/api/candidate/turn", {"turn": states[index]["turn"]})
        assert result.status_code == 200, result.text
        assert result.json()["turn"] == 1
        latencies.append(time.perf_counter() - start)
        assert request(index, "POST", "/api/candidate/finish").status_code == 200

    with ThreadPoolExecutor(max_workers=10) as pool:
        list(pool.map(answer, range(10)))
    elapsed = time.perf_counter() - start_time
    with SessionLocal() as db:
        assert db.get(Organization, org["id"]).active_sessions == 0
        assert (
            len(
                db.scalars(
                    select(InterviewSession).where(
                        InterviewSession.org_id == org["id"], InterviewSession.status == "completed"
                    )
                ).all()
            )
            == 10
        )
    result = {
        "concurrent_interviews": 10,
        "completed": 10,
        "capacity_11th_request": 429,
        "wall_seconds": round(elapsed, 3),
        "request_groups": len(latencies),
        "p95_group_seconds": round(sorted(latencies)[int(len(latencies) * 0.95) - 1], 3),
        "mode": "deterministic local adapters; no live AWS audio or cloud load tested",
        "database": settings().database_url.split(":")[0],
    }
    target = Path(__file__).resolve().parents[2] / ".local" / "concurrency-result.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))
