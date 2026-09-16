"""Synthetic full workflow with real Groq inference and local storage/email fixtures."""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--credential-csv", required=True)
parser.add_argument("--secret-id", default="talyn/groq-api-key")
args = parser.parse_args()
repo = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(repo / "backend/tests"), str(repo / "backend")]
os.environ.pop("TALYN_TEST_DATABASE_URL", None)
import conftest  # noqa: E402
import boto3  # noqa: E402
from pydantic import SecretStr  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app.config import settings  # noqa: E402
from app.adapters import models  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.worker import run_once  # noqa: E402
from test_workflow import prepare, launch, join, start, ANSWER  # noqa: E402

with open(args.credential_csv, encoding="utf-8-sig") as handle:
    credentials = next(csv.DictReader(handle))
session = boto3.Session(
    aws_access_key_id=credentials["Access key ID"],
    aws_secret_access_key=credentials["Secret access key"],
    region_name="ap-south-1",
)
settings().groq_api_key = SecretStr(
    session.client("secretsmanager").get_secret_value(SecretId=args.secret_id)["SecretString"]
)
settings().llm_provider = "groq"
calls = []


def actual(schema, instruction, payload, fixture):
    # Space calls for the free tier; no fixture result is used for inference.
    if calls:
        time.sleep(12)
    result, usage = models.groq_structured(schema, instruction, payload)
    calls.append({"schema": schema.__name__, "usage": usage})
    print("Validated", schema.__name__, flush=True)
    return result, usage


models.structured = actual
Base.metadata.create_all(engine)
with TestClient(app) as manager, TestClient(app) as candidate:
    conftest.manager_login(manager)
    job_id, application_id = prepare(manager)
    join(manager, candidate, launch(manager, job_id, application_id))
    start(candidate)
    for turn in range(9):
        state = candidate.get("/api/candidate/session").json()
        if state["status"] == "completed":
            break
        response = candidate.post(
            "/api/candidate/demo-answer", json={"text": ANSWER, "result_id": f"smoke-{turn}", "final": True}
        )
        assert response.status_code == 200
        response = candidate.post("/api/candidate/turn", json={"turn": state["turn"]})
        assert response.status_code == 200, "Interview turn failed"
    candidate.post("/api/candidate/finish")
    run_once()
    report = candidate.get("/api/candidate/report")
    assert report.status_code == 200, "Candidate report failed"
    manager_report = manager.get(f"/api/applications/{application_id}/report")
    assert manager_report.status_code == 200, "Manager report failed"
result = {
    "provider": "groq",
    "model": settings().groq_model_id,
    "passed": True,
    "boundary": "Real LLM; synthetic candidates, local database/storage/email; not deployed AWS acceptance",
    "calls": calls,
}
(repo / ".local" / "groq-smoke-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
print(json.dumps(result))
