import json

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import func, select

from app.adapters import models
from app.config import settings
from app.db import SessionLocal
from app.errors import WorkflowError, public_job_error
from app.graphs import invoke_recoverable, model_call, preparation_graph
from app.models import AsyncJob, Usage
from app.schemas import FollowupOutput, PlanOutput
from app.worker import process_job
from conftest import manager_login
from test_workflow import JOB


def application(client):
    org = manager_login(client)
    job = client.post("/api/jobs", json=JOB).json()
    candidate = client.post(
        f"/api/jobs/{job['id']}/candidates",
        json={
            "name": "Synthetic Candidate",
            "email": "fixture@example.com",
        },
    ).json()
    return {"org_id": org["id"], "application_id": candidate["id"]}


def test_resume_legacy_checkpoint_without_duplicate_resume_or_lost_sources(client, monkeypatch):
    state = application(client)
    text = "Built API tests with Python and SQL. " * 300
    sources = [{"ref": "synthetic-doc:page:1", "text": text}]
    state.update(
        job=JOB,
        documents=[{"text": text, "sources": sources}],
        claims={"skills": ["Python"], "source_refs": [sources[0]["ref"]]},
        competencies=JOB["criteria"],
        evidence=[{"ref": sources[0]["ref"]}],
        transitions=["document_ingestion", "structured_extraction", "competency_mapping", "candidate_evidence_mapping"],
    )
    instruction = (
        "Generate grounded personalized questions. Retain the given competencies; do not change evaluation standards."
    )
    with pytest.raises(WorkflowError, match="size limit"):
        models.groq_request(
            PlanOutput,
            instruction,
            {
                "job": JOB,
                "claims": state["claims"],
                "sources": state["documents"],
            },
        )
    # Preserve the audit rows for rejected local attempts without charging provider calls.
    with SessionLocal.begin() as db:
        for n in range(12):
            db.add(
                Usage(
                    **{k: state[k] for k in ("org_id", "application_id")},
                    meter="model_calls",
                    quantity=1 if n == 0 else 0,
                    dedupe_key=f"{state['application_id']}:{n}",
                )
            )
    observed = []

    def structured(schema, instruction, payload, fixture):
        observed.append(models.groq_request(schema, instruction, payload))
        return schema.model_validate(fixture), {"inputTokens": 100, "outputTokens": 50}

    monkeypatch.setattr(models, "validate_input", models.groq_request)
    monkeypatch.setattr(models, "structured", structured)
    graph = preparation_graph(InMemorySaver())
    thread = "legacy-" + state["application_id"]
    graph.update_state({"configurable": {"thread_id": thread}}, state, as_node="evidence")
    result = invoke_recoverable(graph, state, thread)
    assert result["transitions"][-1] == "ready_for_transactional_persistence"
    assert any(q["kind"] == "personalized" for q in result["plan"]["questions"])
    assert len(observed) == 1
    sent = json.loads(observed[0]["messages"][1]["content"])["untrusted_data"]
    assert sent["sources"] == [{"sources": sources}]
    assert result == invoke_recoverable(graph, state, thread)
    assert len(observed) == 1
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(Usage.quantity)).where(Usage.meter == "model_calls")) == 2


def test_oversize_input_stops_without_provider_calls_or_retry_budget(client, monkeypatch, caplog):
    state = application(client)
    job = client.post(f"/api/applications/{state['application_id']}/prepare").json()
    monkeypatch.setattr(settings(), "mode", "aws")
    monkeypatch.setattr(settings(), "llm_provider", "groq")
    provider_calls = []
    monkeypatch.setattr(models, "structured", lambda *args: provider_calls.append(args))

    def prepare(*args):
        model_call(state, FollowupOutput, "Assess completeness", {"answer": "PRIVATE_RESUME" * 3000}, {})

    monkeypatch.setattr("app.worker.prepare_application", prepare)
    assert process_job(job["job_id"]) is False
    assert not provider_calls
    with SessionLocal() as db:
        failed = db.get(AsyncJob, job["job_id"])
        assert failed.status == "dead" and failed.attempts == 1
        assert "size limit" in failed.error and len(failed.error) <= 100
        assert db.scalar(select(func.count(Usage.id)).where(Usage.meter == "model_calls")) == 0
    assert "error_code=model_input_too_large" in caplog.text
    assert "PRIVATE_RESUME" not in caplog.text


def test_provider_failures_still_consume_budget_and_never_expose_payload(client, monkeypatch):
    state = application(client)
    monkeypatch.setattr(settings(), "max_model_calls", 1)

    def fail(*args):
        raise RuntimeError("PRIVATE_PROMPT_FROM_PROVIDER")

    monkeypatch.setattr(models, "structured", fail)
    with pytest.raises(RuntimeError) as failed:
        model_call(state, FollowupOutput, "Assess", {}, {})
    assert "PRIVATE_PROMPT" not in public_job_error(failed.value)
    with pytest.raises(WorkflowError, match="allowance exhausted"):
        model_call(state, FollowupOutput, "Assess", {}, {})
    with SessionLocal() as db:
        assert db.scalar(select(func.sum(Usage.quantity)).where(Usage.meter == "model_calls")) == 1
