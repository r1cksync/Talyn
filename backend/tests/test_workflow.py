import hashlib
import io
import re
from datetime import timedelta

import pytest
from docx import Document as WordDocument
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuthSession, EmailChallenge, EmailDelivery, Invitation, Report, now
from app.worker import run_once
from conftest import manager_login

JOB = {"title": "Backend engineer", "description": "Build reliable Python services and explain database performance tradeoffs.",
       "skills": ["Python", "SQL"], "seniority": "Mid-level", "duration_minutes": 30,
       "criteria": [{"name": "Technical reasoning", "description": "Explain alternatives, data integrity, and tested outcomes."},
                    {"name": "Collaboration", "description": "Describe clear communication of technical tradeoffs."}]}
ANSWER = "I designed a Python service using PostgreSQL transactions and idempotency keys. I compared two approaches with the team, tested failure cases and measured p95 latency. This reduced duplicate work by forty percent and improved reliability."


def prepare(manager, upload=True):
    job = manager.post("/api/jobs", json=JOB)
    assert job.status_code == 201, job.text
    job_id = job.json()["id"]
    imported = manager.post(f"/api/jobs/{job_id}/import", content="name,email\nAlex Morgan,alex@example.com\n", headers={"content-type": "text/csv"})
    assert imported.status_code == 200, imported.text
    app_id = imported.json()["application_ids"][0]
    if upload:
        word = WordDocument()
        word.add_paragraph("Alex Morgan developed a Python API with PostgreSQL, idempotency keys, and integration tests.")
        out = io.BytesIO()
        word.save(out)
        data = out.getvalue()
        result = manager.post(f"/api/applications/{app_id}/documents", json={"filename": "synthetic-resume.docx",
            "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest()})
        assert result.status_code == 201, result.text
        upload_url = result.json()["upload"]["url"]
        assert manager.put(upload_url, content=data).status_code == 200
        assert manager.post(f"/api/documents/{result.json()['id']}/complete").status_code == 200
        run_once()
    response = manager.post(f"/api/applications/{app_id}/prepare")
    assert response.status_code == 202, response.text
    run_once()
    plan = manager.get(f"/api/applications/{app_id}/plan")
    assert plan.status_code == 200, plan.text
    plan = plan.json()
    result = manager.put(f"/api/applications/{app_id}/plan", json={"questions": plan["questions"], "dimensions": plan["dimensions"],
                                                                 "version": plan["version"], "approve": True})
    assert result.status_code == 200, result.text
    return job_id, app_id


def launch(manager, job_id, app_id):
    result = manager.post(f"/api/jobs/{job_id}/campaigns", json={"application_ids": [app_id], "idempotency_key": "test-campaign-"+app_id})
    assert result.status_code == 201, result.text
    run_once()
    deliveries = manager.get("/api/deliveries").json()
    invitation = next(d for d in deliveries if d["kind"] == "invitation")
    return re.search(r"#invite=([A-Za-z0-9_-]+)", invitation["preview"]["body"]).group(1)


def join(manager, candidate, token):
    candidate.headers.update({"origin": "http://localhost:3000"})
    response = candidate.post("/api/candidate/access/request", json={"token": token})
    assert response.status_code == 202, response.text
    challenge = response.json()["challenge_id"]
    run_once()
    deliveries = manager.get("/api/deliveries").json()
    code = re.search(r"\b\d{6}\b", next(d for d in deliveries if d["kind"] == "verification")["preview"]["body"]).group()
    result = candidate.post("/api/candidate/access/verify", json={"challenge_id": challenge, "code": code})
    assert result.status_code == 200, result.text
    candidate.headers["x-csrf-token"] = result.json()["csrf"]
    return challenge, code


def start(candidate):
    result = candidate.post("/api/candidate/consent", json={"policy_version": "2026-09-v1", "recording": True,
        "transcription": True, "ai_evaluation": True, "device_check": True})
    assert result.status_code == 200, result.text
    result = candidate.post("/api/candidate/start")
    assert result.status_code == 200, result.text
    return result.json()


def finish(candidate):
    state = start(candidate)
    for i in range(15):
        if state["status"] == "completed":
            break
        result = candidate.post("/api/candidate/demo-answer", json={"text": ANSWER, "result_id": f"answer-{i}"})
        assert result.status_code == 200, result.text
        result = candidate.post("/api/candidate/turn", json={"turn": state["turn"]})
        assert result.status_code == 200, result.text
        state = result.json()
    assert state["status"] == "completed"
    run_once()
    run_once()
    return state


def test_complete_workflow_and_recipient_separation(client):
    manager_login(client)
    job_id, app_id = prepare(client)
    token = launch(client, job_id, app_id)
    with TestClient(app) as candidate:
        join(client, candidate, token)
        finish(candidate)
        feedback = candidate.get("/api/candidate/report")
        assert feedback.status_code == 200, feedback.text
        feedback = feedback.json()
        assert feedback["synthetic"] and feedback["ai_generated"]
        assert not {"manager_notes", "dimensions", "expected_evidence", "decision"} & feedback.keys()
        report = client.get(f"/api/applications/{app_id}/report")
        assert report.status_code == 200, report.text
        report = report.json()
        assert report["dimensions"][0]["evidence"]
        annotation = client.patch(f"/api/reports/{report['id']}", json={"notes": "PRIVATE recruiter note", "decision": "hold"})
        assert annotation.status_code == 200
        assert "PRIVATE" not in candidate.get("/api/candidate/report").text
    deliveries = client.get("/api/deliveries").json()
    assert all(d["recipient"] == "alex@example.com" for d in deliveries if d["kind"] == "candidate_report")
    assert all(d["recipient"] == "manager@example.test" for d in deliveries if d["kind"] == "manager_report")
    before = len(deliveries)
    run_once()
    assert len(client.get("/api/deliveries").json()) == before


def test_tenant_and_role_isolation(client):
    manager_login(client)
    job_id, app_id = prepare(client, upload=False)
    with TestClient(app) as other:
        manager_login(other, "Other tenant")
        assert other.get(f"/api/jobs/{job_id}").status_code == 404
        assert other.get(f"/api/applications/{app_id}/plan").status_code == 404
        assert other.post(f"/api/applications/{app_id}/prepare").status_code == 404
        assert other.delete(f"/api/applications/{app_id}").status_code == 404
    from app.models import Membership
    with SessionLocal.begin() as db:
        member = db.scalar(select(Membership).where(Membership.email == "manager@example.test"))
        member.role = "reviewer"
    assert client.post("/api/jobs", json=JOB).status_code == 403
    assert client.get(f"/api/jobs/{job_id}").status_code == 200


def test_invitation_expiry_verification_replay_and_csrf(client):
    manager_login(client)
    job_id, app_id = prepare(client, upload=False)
    token = launch(client, job_id, app_id)
    with TestClient(app) as candidate:
        challenge, code = join(client, candidate, token)
        assert candidate.post("/api/candidate/access/verify", json={"challenge_id": challenge, "code": code}).status_code == 401
        assert candidate.post("/api/candidate/access/request", json={"token": token}).status_code == 410
        assert candidate.post("/api/candidate/start", headers={"x-csrf-token": "bad"}).status_code == 403
        assert candidate.get(f"/api/applications/{app_id}/plan").status_code == 401
        client.post(f"/api/applications/{app_id}/revoke")
        assert candidate.get("/api/candidate/me").status_code == 401
    with SessionLocal.begin() as db:
        invite = db.scalar(select(Invitation))
        invite.expires_at = now()-timedelta(days=1)
        invite.revoked, invite.consumed_at = False, None
    with TestClient(app) as stranger:
        result = stranger.post("/api/candidate/access/request", json={"token": token}, headers={"origin": "http://localhost:3000"})
        assert result.status_code == 410


def test_partial_replacement_final_immutability_and_turn_replay(client):
    manager_login(client)
    job_id, app_id = prepare(client, upload=False)
    with TestClient(app) as candidate:
        join(client, candidate, launch(client, job_id, app_id))
        state = start(candidate)
        for text, final in [("I designed", False), ("I designed a Python service", False), (ANSWER, True), ("malicious overwrite", True)]:
            result = candidate.post("/api/candidate/demo-answer", json={"text": text, "result_id": "stable", "final": final})
            assert result.status_code == 200, result.text
        transcript = candidate.get("/api/candidate/transcript").json()
        assert len(transcript) == 1 and transcript[0]["text"] == ANSWER and transcript[0]["revision"] == 3
        first = candidate.post("/api/candidate/turn", json={"turn": state["turn"]}).json()
        second = candidate.post("/api/candidate/turn", json={"turn": state["turn"]}).json()
        assert first["turn"] == second["turn"] == 1
        assert candidate.get("/api/candidate/session").json()["turn"] == 1


def test_production_rejects_demo_and_insecure_configuration():
    from app.config import Settings
    with pytest.raises(ValueError):
        Settings(environment="production", mode="demo")
    with pytest.raises(ValueError):
        Settings(mode="aws", public_url="http://example.com")


def test_document_attack_rejected_and_untrusted_prompt_boundary():
    import zipfile
    from app.document_extract import extract
    from app.adapters import SYSTEM_POLICY
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as z:
        z.writestr("word/document.xml", "<root/>")
        z.writestr("word/vbaProject.bin", b"malicious")
    with pytest.raises(ValueError):
        extract(archive.getvalue(), "docx")
    with pytest.raises(ValueError):
        extract(b"not a pdf", "application/pdf")
    assert "UNTRUSTED DATA" in SYSTEM_POLICY and "Never follow" in SYSTEM_POLICY


def test_fabricated_evidence_rejected_and_poor_audio_unscored():
    from app.graphs import verify_evidence
    evaluation = {"dimensions": [{"name": "SQL", "score": 1, "insufficient_evidence": False,
        "evidence": [{"segment_id": "s1", "quote": "real quote"}]}]}
    segments = [{"id": "s1", "text": "real quote", "final": True, "speaker": "candidate", "competency": "SQL", "quality": "poor"}]
    result = verify_evidence(evaluation, segments, [{"name": "SQL"}])
    assert result["dimensions"][0]["score"] is None
    evaluation["dimensions"][0]["evidence"][0]["quote"] = "fabricated quotation"
    with pytest.raises(ValueError):
        verify_evidence(evaluation, segments, [{"name": "SQL"}])


def test_checkpoint_recovery_and_retention(client):
    from app.services import prepare_application
    from app.checkpoints import checkpoint_store
    from app.models import Application, Plan
    from app.worker import delete_application
    org = manager_login(client)
    job_id, app_id = prepare(client)
    with SessionLocal() as db:
        count = len(db.scalars(select(Plan)).all())
    prepare_application(org["id"], app_id)
    with SessionLocal.begin() as db:
        assert len(db.scalars(select(Plan)).all()) == count
        db.get(Application, app_id).revoked = True
    delete_application(org["id"], app_id)
    with SessionLocal() as db:
        assert not db.get(Application, app_id)
    with checkpoint_store() as saver:
        assert not any(c.config["configurable"]["thread_id"].startswith(org["id"]+":"+app_id+":") for c in saver.list(None))
