"""Typed, checkpointed, bounded workflows. Notifications are committed by callers."""

from typing import TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy
from sqlalchemy import func, select

from .adapters import models
from .config import settings
from .db import SessionLocal
from .errors import WorkflowError, retryable_error
from .models import Application, Usage
from .schemas import EvaluationOutput, ExtractedClaims, FollowupOutput, PlanOutput

RETRY = RetryPolicy(max_attempts=2, initial_interval=1, retry_on=retryable_error)


def model_call(state, schema, instruction, payload, fixture):
    # A local input rejection never reaches the provider and must not consume its call allowance.
    models.validate_input(schema, instruction, payload)
    # Reserve a call before invoking the provider. A crashed attempt still consumes budget.
    call_id = str(uuid4())
    with SessionLocal.begin() as db:
        app = db.scalar(
            select(Application)
            .where(Application.id == state["application_id"], Application.org_id == state["org_id"])
            .with_for_update()
        )
        if not app or app.revoked:
            raise ValueError("Application authorization failed")
        count = db.scalar(
            select(func.coalesce(func.sum(Usage.quantity), 0)).where(
                Usage.application_id == app.id, Usage.org_id == app.org_id, Usage.meter == "model_calls"
            )
        )
        if count >= settings().max_model_calls:
            raise WorkflowError("model_budget_exhausted")
        db.add(Usage(org_id=app.org_id, application_id=app.id, meter="model_calls", quantity=1, dedupe_key=call_id))
    result, usage = models.structured(schema, instruction, payload, fixture)
    with SessionLocal.begin() as db:
        for key, name in [("inputTokens", "llm_input_tokens"), ("outputTokens", "llm_output_tokens")]:
            db.add(
                Usage(
                    org_id=state["org_id"],
                    application_id=state["application_id"],
                    meter=name,
                    quantity=usage.get(key, 0),
                    dedupe_key=f"{call_id}:{key}",
                )
            )
    return result.model_dump()


class PrepareState(TypedDict, total=False):
    version: int
    org_id: str
    application_id: str
    job: dict
    documents: list[dict]
    claims: dict
    competencies: list[dict]
    evidence: list[dict]
    plan: dict
    transitions: list[str]


def source_documents(state):
    # Sources already contain all extracted text with citation identifiers. Older
    # checkpoints also contain a duplicate full-text field; do not resend it.
    return [{"sources": document["sources"]} for document in state["documents"]]


def preparation_graph(checkpointer):
    graph = StateGraph(PrepareState)

    def ingest(state):
        return {"version": 1, "transitions": ["document_ingestion"]}

    def extract(state):
        sources = [s for d in state["documents"] for s in d["sources"]]
        fixture = {
            "skills": state["job"]["skills"],
            "projects": [s["text"][:300] for s in sources[:2]],
            "source_refs": [s["ref"] for s in sources[:2]],
        }
        result = model_call(
            state,
            ExtractedClaims,
            "Extract relevant factual claims with provided source references.",
            {"documents": source_documents(state)},
            fixture,
        )
        refs = {s["ref"] for s in sources}
        if any(ref not in refs for ref in result["source_refs"]):
            raise ValueError("Extraction cites unknown source")
        return {"claims": result, "transitions": state["transitions"] + ["structured_extraction"]}

    def competencies(state):
        return {"competencies": state["job"]["criteria"], "transitions": state["transitions"] + ["competency_mapping"]}

    def evidence(state):
        return {
            "evidence": [{"ref": ref} for ref in state["claims"]["source_refs"]],
            "transitions": state["transitions"] + ["candidate_evidence_mapping"],
        }

    def generate(state):
        criteria = state["competencies"]
        # Core questions are deterministic and shared across candidates for this job.
        core = [
            {
                "text": f"Describe a concrete example of {c['name'].lower()}. Explain your approach, tradeoffs, and outcome.",
                "competency": c["name"],
                "kind": "core",
                "expected_evidence": [c["description"]],
                "time_limit_seconds": min(240, max(60, state["job"]["duration_minutes"] * 60 // (len(criteria) + 1))),
                "max_followups": 1,
                "source_refs": [],
            }
            for c in criteria[:6]
        ]
        while len(core) < 2:
            core.append(
                {
                    **core[0],
                    "kind": "situational",
                    "text": f"How would you approach an unfamiliar {criteria[0]['name'].lower()} problem under a tight deadline?",
                }
            )
        docs = state["documents"]
        if docs and state["claims"]["source_refs"]:
            first_ref = state["claims"]["source_refs"][0]
            source_text = next(
                (s["text"] for d in docs for s in d["sources"] if s["ref"] == first_ref), "your project"
            )[:250]
            personalized = {
                "text": f"Your resume describes ‘{source_text}’. What was your contribution, and how did you verify the outcome?",
                "competency": criteria[0]["name"],
                "kind": "personalized",
                "expected_evidence": ["Candidate contribution and verifiable outcome"],
                "time_limit_seconds": 180,
                "max_followups": 1,
                "source_refs": [first_ref],
            }
            fixture = {"questions": core[:1] + [personalized], "warnings": []}
            result = model_call(
                state,
                PlanOutput,
                "Generate grounded personalized questions. Retain the given competencies; do not change evaluation standards.",
                {"job": state["job"], "claims": state["claims"], "sources": source_documents(state)},
                fixture,
            )
            additions = [q for q in result["questions"] if q["kind"] == "personalized"][:2]
        else:
            additions = []
        return {
            "plan": {
                "questions": core + additions,
                "warnings": [] if docs else ["No resume supplied; using shared job questions."],
            },
            "transitions": state["transitions"] + ["question_generation"],
        }

    def align(state):
        names = {c["name"] for c in state["competencies"]}
        refs = {s["ref"] for d in state["documents"] for s in d["sources"]}
        for question in state["plan"]["questions"]:
            if question["competency"] not in names or any(ref not in refs for ref in question["source_refs"]):
                raise ValueError("Question does not align with rubric or source evidence")
        return {"transitions": state["transitions"] + ["rubric_alignment"]}

    def quality(state):
        PlanOutput.model_validate(state["plan"])
        return {"transitions": state["transitions"] + ["quality_checks"]}

    def ready(state):
        return {"transitions": state["transitions"] + ["ready_for_transactional_persistence"]}

    for name, node in [
        ("ingestion", ingest),
        ("extraction", extract),
        ("competencies", competencies),
        ("evidence", evidence),
        ("generation", generate),
        ("alignment", align),
        ("quality", quality),
        ("persistence_boundary", ready),
    ]:
        graph.add_node(name, node, retry_policy=RETRY)
    order = [
        START,
        "ingestion",
        "extraction",
        "competencies",
        "evidence",
        "generation",
        "alignment",
        "quality",
        "persistence_boundary",
        END,
    ]
    for left, right in zip(order, order[1:]):
        graph.add_edge(left, right)
    return graph.compile(checkpointer=checkpointer)


class ExecuteState(TypedDict, total=False):
    version: int
    org_id: str
    application_id: str
    session_id: str
    turn: int
    question: dict
    answer: str
    remaining_seconds: int
    followups: int
    followup: str
    action: str
    transitions: list[str]


def execution_graph(checkpointer):
    graph = StateGraph(ExecuteState)

    def validate(state):
        return {
            "version": 1,
            "transitions": ["session_validation", "question_selection", "question_delivery", "answer_collection"],
        }

    def assess(state):
        if state["followups"] >= state["question"]["max_followups"] or state["remaining_seconds"] < 45:
            return {"action": "next", "followup": ""}
        # Empty/missing audio is a technical/completeness condition, never a negative competency score.
        if not state["answer"].strip():
            return {"action": "next", "followup": ""}
        result = model_call(
            state,
            FollowupOutput,
            "Assess answer completeness. Ask at most one short, same-difficulty, job-relevant clarification when evidence is missing.",
            {
                "question": state["question"]["text"],
                "answer": state["answer"],
                "competency": state["question"]["competency"],
            },
            {
                "needs_followup": len(state["answer"].split()) < 25,
                "question": "Could you give a specific example of your own contribution and the result?",
            },
        )
        return {
            "action": "followup" if result["needs_followup"] and result["question"] else "next",
            "followup": result["question"] if result["needs_followup"] else "",
        }

    def progress(state):
        return {
            "transitions": state["transitions"] + ["answer_completeness_assessment", state["action"], "progress_update"]
        }

    graph.add_node("validate", validate)
    graph.add_node("assess", assess, retry_policy=RETRY)
    graph.add_node("progress", progress)
    graph.add_edge(START, "validate")
    graph.add_edge("validate", "assess")
    graph.add_edge("assess", "progress")
    graph.add_edge("progress", END)
    return graph.compile(checkpointer=checkpointer)


class EvaluateState(TypedDict, total=False):
    version: int
    org_id: str
    application_id: str
    session_id: str
    segments: list[dict]
    rubric: list[dict]
    answers: list[dict]
    evaluation: dict
    incomplete: list[str]
    manager_report: dict
    candidate_report: dict
    transitions: list[str]


def verify_evidence(evaluation, segments, rubric):
    by_id = {s["id"]: s for s in segments if s["final"] and s["speaker"] == "candidate"}
    if {d["name"] for d in evaluation["dimensions"]} != {r["name"] for r in rubric}:
        raise ValueError("Evaluation dimensions differ from approved rubric")
    if len(evaluation["dimensions"]) != len(rubric):
        raise ValueError("Duplicate evaluation dimension")
    for dimension in evaluation["dimensions"]:
        valid = []
        for evidence in dimension["evidence"]:
            source = by_id.get(evidence["segment_id"])
            if not source or evidence["quote"] not in source["text"] or source["competency"] != dimension["name"]:
                raise ValueError("Unverifiable transcript evidence")
            if source["quality"] not in {"poor", "unknown"}:
                valid.append(evidence)
        if dimension["insufficient_evidence"] or not valid:
            dimension["score"] = None
            dimension["insufficient_evidence"] = True
        elif dimension["score"] is None:
            dimension["insufficient_evidence"] = True
    return evaluation


def evaluation_graph(checkpointer):
    graph = StateGraph(EvaluateState)

    def finalize(state):
        return {
            "version": 1,
            "segments": [s for s in state["segments"] if s["final"]],
            "transitions": ["finalize_transcript", "associate_answers"],
        }

    def assess(state):
        dimensions = []
        for criterion in state["rubric"]:
            sources = [
                s for s in state["segments"] if s["competency"] == criterion["name"] and s["speaker"] == "candidate"
            ]
            valid = [s for s in sources if s["quality"] not in {"poor", "unknown"}]
            dimensions.append(
                {
                    "name": criterion["name"],
                    "score": 3 if valid else None,
                    "explanation": "Synthetic rubric demonstration based on the cited answer."
                    if valid
                    else "Insufficient reliable evidence to score.",
                    "evidence": [{"segment_id": s["id"], "quote": s["text"][:300]} for s in valid[:2]],
                    "missing_evidence": [] if valid else ["A complete, reliable answer is needed."],
                    "insufficient_evidence": not valid,
                }
            )
        fixture = {
            "dimensions": dimensions,
            "summary": "Synthetic interview report for workflow demonstration.",
            "strengths": ["Provided concrete examples in recorded answers."]
            if any(d["score"] for d in dimensions)
            else [],
            "further_assessment": ["Discuss tradeoffs and measurable outcomes in a follow-up conversation."],
        }
        result = model_call(
            state,
            EvaluationOutput,
            "Assess each approved rubric dimension. Cite exact segment IDs and substrings. Never penalize missing audio. No hiring decision.",
            {"rubric": state["rubric"], "transcript": state["segments"], "answers": state["answers"]},
            fixture,
        )
        return {"evaluation": result, "transitions": state["transitions"] + ["assess_rubric"]}

    def verify(state):
        return {
            "evaluation": verify_evidence(state["evaluation"], state["segments"], state["rubric"]),
            "transitions": state["transitions"] + ["verify_evidence"],
        }

    def completeness(state):
        incomplete = [a["label"] + ": " + a["status"] for a in state["answers"] if a["status"] != "answered"]
        if any(s["quality"] in {"poor", "unknown"} for s in state["segments"]):
            incomplete.append("Some transcription has low or unknown confidence; affected evidence is not scored.")
        return {"incomplete": incomplete, "transitions": state["transitions"] + ["assess_completeness"]}

    def reports(state):
        data = state["evaluation"]
        common = {"synthetic": settings().mode == "demo", "ai_generated": True}
        return {
            "manager_report": {**common, **data, "incomplete_sections": state["incomplete"]},
            "candidate_report": {
                **common,
                "competencies": [r["name"] for r in state["rubric"]],
                "strengths": data["strengths"],
                "suggestions": data["further_assessment"],
                "feedback": "This AI-generated feedback summarizes job-related answer evidence. " + data["summary"],
            },
            "transitions": state["transitions"] + ["generate_separate_reports", "notification_outbox_boundary"],
        }

    for name, fn in [
        ("finalize", finalize),
        ("assess", assess),
        ("verify", verify),
        ("completeness", completeness),
        ("reports", reports),
    ]:
        graph.add_node(name, fn, retry_policy=RETRY)
    order = [START, "finalize", "assess", "verify", "completeness", "reports", END]
    for left, right in zip(order, order[1:]):
        graph.add_edge(left, right)
    return graph.compile(checkpointer=checkpointer)


def invoke_recoverable(graph, initial, thread):
    config = {"configurable": {"thread_id": thread}, "recursion_limit": 24}
    snapshot = graph.get_state(config)
    if snapshot.values and not snapshot.next:
        return snapshot.values
    return graph.invoke(None if snapshot.values else initial, config=config)
