import math
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select, update

from .checkpoints import checkpoint_store, thread_id
from .config import settings
from .db import SessionLocal
from .graphs import evaluation_graph, execution_graph, invoke_recoverable, preparation_graph
from .models import (
    Answer,
    Application,
    Candidate,
    Consent,
    Criterion,
    Evaluation,
    Evidence,
    Extraction,
    InterviewSession,
    Job,
    Membership,
    Organization,
    Plan,
    Question,
    Report,
    RubricVersion,
    TranscriptSegment,
    Transition,
    now,
)
from .outbox import audit, enqueue, meter, queue_email
from .schemas import CandidateReport, ManagerReport
from .security import aware, owned


def questions_for(db, application_id, org_id):
    plan = db.scalar(select(Plan).where(Plan.application_id == application_id, Plan.org_id == org_id))
    if not plan:
        raise HTTPException(409, "Interview plan is not ready")
    questions = db.scalars(
        select(Question).where(Question.plan_id == plan.id, Question.org_id == org_id).order_by(Question.position)
    ).all()
    return plan, questions


def question_dict(q):
    return {
        "text": q.text,
        "competency": q.competency,
        "kind": q.kind,
        "expected_evidence": q.expected_evidence,
        "time_limit_seconds": q.time_limit_seconds,
        "max_followups": q.max_followups,
        "source_refs": q.source_refs,
    }


def prepare_application(org_id, application_id):
    from .models import Document

    with SessionLocal() as db:
        app = owned(db, Application, application_id, org_id)
        job = owned(db, Job, app.job_id, org_id)
        docs = db.scalars(select(Document).where(Document.application_id == app.id, Document.org_id == org_id)).all()
        if any(d.status in {"pending", "processing"} for d in docs):
            raise ValueError("Documents are still processing")
        if any(d.status == "error" for d in docs):
            raise ValueError("Resolve document extraction errors before preparing")
        extracts = db.scalars(
            select(Extraction).join(Document).where(Document.application_id == app.id, Extraction.org_id == org_id)
        ).all()
        criteria = db.scalars(select(Criterion).where(Criterion.job_id == job.id, Criterion.org_id == org_id)).all()
        initial = {
            "org_id": org_id,
            "application_id": app.id,
            "job": {
                "title": job.title,
                "description": job.description,
                "skills": job.skills,
                "duration_minutes": job.duration_minutes,
                "criteria": [
                    {"name": c.name, "description": c.description, "weight": c.weight, "anchors": c.anchors}
                    for c in criteria
                ],
            },
            "documents": [
                {"text": e.text, "sources": [{**s, "ref": f"{e.document_id}:{s['ref']}"} for s in e.sources]}
                for e in extracts
            ],
        }
    with checkpoint_store() as saver:
        state = invoke_recoverable(preparation_graph(saver), initial, thread_id(org_id, application_id, "prepare"))
    with SessionLocal.begin() as db:
        app = owned(db, Application, application_id, org_id, lock=True)
        if app.revoked:
            raise ValueError("Application revoked")
        existing = db.scalar(select(Plan).where(Plan.application_id == app.id, Plan.org_id == org_id))
        if existing:
            return
        plan = Plan(
            org_id=org_id,
            application_id=app.id,
            model_id="synthetic-demo" if settings().mode == "demo" else settings().bedrock_model_id,
            warnings=state["plan"]["warnings"],
        )
        db.add(plan)
        db.flush()
        for i, q in enumerate(state["plan"]["questions"]):
            db.add(Question(org_id=org_id, plan_id=plan.id, position=i, **q))
        db.add(RubricVersion(org_id=org_id, plan_id=plan.id, version=1, dimensions=initial["job"]["criteria"]))
        app.status = "prepared"
        audit(db, org_id, "worker", "plan.prepared", plan.id, {"transitions": state["transitions"]})


def start_session(db, auth):
    app = owned(db, Application, auth.application_id, auth.org_id, lock=True)
    plan, _ = questions_for(db, app.id, app.org_id)
    if not plan.approved or app.revoked:
        raise HTTPException(409, "Interview is not available")
    consent = db.scalar(
        select(Consent).where(
            Consent.application_id == app.id,
            Consent.org_id == app.org_id,
            Consent.policy_version == settings().consent_policy,
        )
    )
    if not consent or not all([consent.transcription, consent.ai_evaluation, consent.device_check]):
        raise HTTPException(409, "Complete consent and device checks first")
    if app.recording_required and not consent.recording:
        raise HTTPException(409, "Recording accommodation requires manager approval")
    session = db.scalar(select(InterviewSession).where(InterviewSession.application_id == app.id))
    if session:
        return session
    job = owned(db, Job, app.job_id, app.org_id)
    org = db.scalar(select(Organization).where(Organization.id == app.org_id).with_for_update())
    current_period = now().strftime("%Y-%m")
    if org.usage_period != current_period:
        org.used_minutes, org.usage_period = 0, current_period
        db.flush()
    result = db.execute(
        update(Organization)
        .where(
            Organization.id == app.org_id,
            Organization.active_sessions < Organization.max_concurrent,
            Organization.used_minutes + job.duration_minutes <= Organization.max_minutes,
        )
        .values(
            active_sessions=Organization.active_sessions + 1,
            used_minutes=Organization.used_minutes + job.duration_minutes,
        )
    )
    if not result.rowcount:
        raise HTTPException(429, "Organization interview capacity or monthly minute limit reached")
    session = InterviewSession(
        org_id=app.org_id,
        application_id=app.id,
        status="active",
        started_at=now(),
        deadline_at=now() + timedelta(minutes=job.duration_minutes),
    )
    db.add(session)
    db.flush()
    db.add(
        Transition(
            org_id=app.org_id, session_id=session.id, from_state="ready", to_state="active", reason="candidate_start"
        )
    )
    app.status = "interviewing"
    return session


def session_state(db, session):
    plan, questions = questions_for(db, session.application_id, session.org_id)
    q = questions[session.question_index] if session.question_index < len(questions) else None
    text = session.followup_text or (q.text if q else "Your interview is complete. Thank you.")
    return {
        "id": session.id,
        "status": session.status,
        "question_index": session.question_index,
        "question_count": len(questions),
        "question": {"id": q.id, "text": text, "competency": q.competency} if q else None,
        "turn": session.turn,
        "deadline_at": aware(session.deadline_at).isoformat() if session.deadline_at else None,
        "started_at": aware(session.started_at).isoformat() if session.started_at else None,
        "server_time": now().isoformat(),
        "silence_seconds": settings().silence_seconds,
    }


def reconcile_segment(db, session, *, result_id, text, start_ms, end_ms, final, quality="unknown"):
    _, questions = questions_for(db, session.application_id, session.org_id)
    if session.status != "active" or session.question_index >= len(questions):
        raise HTTPException(409, "Interview is not active")
    if aware(session.deadline_at) <= now():
        raise HTTPException(409, "Interview duration elapsed")
    segment = db.scalar(
        select(TranscriptSegment).where(
            TranscriptSegment.session_id == session.id,
            TranscriptSegment.org_id == session.org_id,
            TranscriptSegment.result_id == result_id,
        )
    )
    if segment and segment.final:
        return segment
    if segment and segment.turn != session.turn:
        raise HTTPException(409, "Transcript belongs to an earlier turn")
    if not segment:
        segment = TranscriptSegment(
            org_id=session.org_id,
            session_id=session.id,
            question_id=questions[session.question_index].id,
            result_id=result_id,
            turn=session.turn,
            revision=0,
        )
        db.add(segment)
    segment.text = text[:10000]
    segment.start_ms, segment.end_ms = max(0, start_ms), max(start_ms, end_ms)
    segment.final, segment.quality = final, quality
    segment.revision += 1
    db.flush()
    return segment


def finish_session(db, session, reason="completed"):
    if session.status != "active":
        return
    session.status, session.completed_at = "completed", now()
    session.connection_id, session.connection_until = None, None
    app = owned(db, Application, session.application_id, session.org_id)
    app.status = "evaluating"
    org = db.get(Organization, app.org_id)
    elapsed = max(1, math.ceil((now() - aware(session.started_at)).total_seconds() / 60))
    job = owned(db, Job, app.job_id, app.org_id)
    elapsed = min(elapsed, job.duration_minutes)
    db.execute(
        update(Organization)
        .where(Organization.id == app.org_id)
        .values(
            active_sessions=func_max_zero(Organization.active_sessions - 1, db),
            used_minutes=func_max_zero(Organization.used_minutes - job.duration_minutes + elapsed, db)
            if org.usage_period == aware(session.started_at).strftime("%Y-%m")
            else Organization.used_minutes,
        )
    )
    app.delete_after = now() + timedelta(days=org.retention_days)
    session.delete_after = app.delete_after
    meter(db, app.org_id, app.id, "interview_minutes", elapsed, "interview:" + session.id)
    db.add(
        Transition(org_id=app.org_id, session_id=session.id, from_state="active", to_state="completed", reason=reason)
    )
    enqueue(db, app.org_id, "evaluate", app.id, "evaluate:" + session.id)


def func_max_zero(expression, db):
    from sqlalchemy import case

    return case((expression < 0, 0), else_=expression)


def complete_turn(org_id, session_id, turn):
    # A durable per-turn graph and an atomic turn compare prevent double advancement.
    with SessionLocal() as db:
        session = owned(db, InterviewSession, session_id, org_id)
        if session.status != "active" or session.turn != turn:
            return session_state(db, session)
        if session.connection_id and aware(session.connection_until) > now():
            raise HTTPException(409, "Finish the audio stream before completing the turn")
        _, questions = questions_for(db, session.application_id, org_id)
        q = questions[session.question_index]
        segments = db.scalars(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.session_id == session.id,
                TranscriptSegment.org_id == org_id,
                TranscriptSegment.turn == turn,
                TranscriptSegment.final.is_(True),
                TranscriptSegment.speaker == "candidate",
            )
            .order_by(TranscriptSegment.start_ms)
        ).all()
        initial = {
            "org_id": org_id,
            "application_id": session.application_id,
            "session_id": session.id,
            "turn": turn,
            "question": question_dict(q),
            "answer": " ".join(s.text for s in segments),
            "followups": session.followups,
            "remaining_seconds": max(0, int((aware(session.deadline_at) - now()).total_seconds())),
        }
        segment_ids = [s.id for s in segments]
        quality = (
            "answered"
            if segments and all(s.quality not in {"poor", "unknown"} for s in segments)
            else "technical_or_missing_audio"
        )
    with checkpoint_store() as saver:
        state = invoke_recoverable(
            execution_graph(saver), initial, thread_id(org_id, initial["application_id"], f"turn-{turn}")
        )
    with SessionLocal.begin() as db:
        session = owned(db, InterviewSession, session_id, org_id, lock=True)
        if session.turn != turn or session.status != "active":
            return session_state(db, session)
        db.add(
            Answer(
                org_id=org_id,
                session_id=session.id,
                question_id=q.id,
                turn=turn,
                segment_ids=segment_ids,
                status=quality,
            )
        )
        session.turn += 1
        if state["action"] == "followup" and aware(session.deadline_at) > now():
            session.followups += 1
            session.followup_text = state["followup"]
        else:
            session.question_index += 1
            session.followups, session.followup_text = 0, ""
        if session.question_index >= len(questions) or aware(session.deadline_at) <= now():
            finish_session(db, session, "deadline" if aware(session.deadline_at) <= now() else "completed")
        db.flush()
        return session_state(db, session)


def evaluate_application(org_id, application_id):
    with SessionLocal() as db:
        app = owned(db, Application, application_id, org_id)
        session = db.scalar(
            select(InterviewSession).where(InterviewSession.application_id == app.id, InterviewSession.org_id == org_id)
        )
        if not session or session.status != "completed" or app.revoked:
            raise ValueError("Interview is not ready for evaluation")
        plan, questions = questions_for(db, app.id, org_id)
        rubric = db.scalar(
            select(RubricVersion).where(
                RubricVersion.plan_id == plan.id, RubricVersion.org_id == org_id, RubricVersion.version == plan.version
            )
        )
        by_id = {q.id: q for q in questions}
        segments = db.scalars(
            select(TranscriptSegment)
            .where(TranscriptSegment.session_id == session.id, TranscriptSegment.org_id == org_id)
            .order_by(TranscriptSegment.start_ms)
        ).all()
        answers = db.scalars(select(Answer).where(Answer.session_id == session.id, Answer.org_id == org_id)).all()
        initial = {
            "org_id": org_id,
            "application_id": app.id,
            "session_id": session.id,
            "rubric": rubric.dimensions,
            "segments": [
                {
                    "id": s.id,
                    "text": s.text,
                    "speaker": s.speaker,
                    "final": s.final,
                    "quality": s.quality,
                    "competency": by_id[s.question_id].competency,
                }
                for s in segments
            ],
            "answers": [{"label": by_id[a.question_id].competency, "status": a.status} for a in answers]
            + [
                {"label": q.competency, "status": "unanswered"}
                for q in questions
                if q.id not in {a.question_id for a in answers}
            ],
        }
    with checkpoint_store() as saver:
        state = invoke_recoverable(evaluation_graph(saver), initial, thread_id(org_id, application_id, "evaluate"))
    manager_report = ManagerReport.model_validate(state["manager_report"])
    candidate_report = CandidateReport.model_validate(state["candidate_report"])
    with SessionLocal.begin() as db:
        app = owned(db, Application, application_id, org_id, lock=True)
        if db.scalar(select(Report.id).where(Report.session_id == initial["session_id"], Report.org_id == org_id)):
            return
        ev = Evaluation(
            org_id=org_id,
            session_id=initial["session_id"],
            dimensions=state["evaluation"]["dimensions"],
            completeness="incomplete" if state["incomplete"] else "complete",
        )
        db.add(ev)
        db.flush()
        for dimension in ev.dimensions:
            for ref in dimension["evidence"]:
                db.add(
                    Evidence(
                        org_id=org_id,
                        evaluation_id=ev.id,
                        dimension=dimension["name"],
                        segment_id=ref["segment_id"],
                        quote=ref["quote"],
                    )
                )
        for audience, report in [("manager", manager_report), ("candidate", candidate_report)]:
            db.add(
                Report(org_id=org_id, session_id=initial["session_id"], audience=audience, content=report.model_dump())
            )
        person = owned(db, Candidate, app.candidate_id, org_id)
        queue_email(
            db,
            org_id,
            person.email,
            "candidate_report",
            f"candidate-report:{app.id}:1",
            "Your Talyn interview feedback is ready",
            "Your AI-generated feedback is ready. Verify your email to view it: "
            f"{settings().public_url}/interview#resume={app.id}\nYour feedback is private to you. No hiring decision is made by Talyn.",
        )
        managers = db.scalars(
            select(Membership).where(Membership.org_id == org_id, Membership.role.in_(["owner", "recruiter"]))
        ).all()
        for member in managers:
            queue_email(
                db,
                org_id,
                member.email,
                "manager_report",
                f"manager-report:{app.id}:1:{member.id}",
                "Interview report ready for review",
                f"An interview report is ready. Sign in to review the evidence and make your own decision: {settings().public_url}/workspace?report={app.id}",
            )
        app.status = "reported"
        audit(db, org_id, "worker", "reports.generated", app.id, {"version": 1, "transitions": state["transitions"]})
