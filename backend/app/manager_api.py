import csv
import io
import json
import secrets
from datetime import timedelta
from pathlib import PurePath

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .adapters import aws, storage
from .config import settings
from .db import get_db
from .models import (
    Application,
    AsyncJob,
    AuthSession,
    Campaign,
    Candidate,
    Criterion,
    Document,
    EmailDelivery,
    Extraction,
    InterviewSession,
    Invitation,
    Job,
    Membership,
    Organization,
    Plan,
    Question,
    RecordingManifest,
    RecordingObject,
    Report,
    RubricVersion,
    TranscriptSegment,
    Usage,
    VideoObservation,
    now,
)
from .outbox import audit, enqueue, queue_email
from .schemas import (
    CampaignInput,
    CandidateInput,
    DocumentInput,
    ExplanationInput,
    JobInput,
    MemberInput,
    NoteInput,
    OrgInput,
    OrgSettingsInput,
    PlanEdit,
)
from .security import decrypt, digest, manager, membership, owned
from .services import question_dict, questions_for

router = APIRouter(prefix="/api", tags=["manager"])


def as_dict(row, fields):
    return {f: getattr(row, f) for f in fields.split()}


@router.post("/organizations", status_code=201)
def create_org(data: OrgInput, auth=Depends(manager), db: Session = Depends(get_db)):
    org = Organization(
        name=data.name,
        retention_days=settings().retention_days,
        max_minutes=settings().max_monthly_minutes,
        max_concurrent=settings().max_concurrent,
    )
    db.add(org)
    db.flush()
    db.add(Membership(org_id=org.id, subject=auth.subject, email=auth.email, role="owner"))
    auth.org_id = org.id
    audit(db, org.id, auth.subject, "organization.created", org.id)
    return as_dict(org, "id name retention_days max_minutes max_concurrent")


@router.post("/organizations/{org_id}/select")
def select_org(org_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, org_id)
    auth.org_id = org_id
    return {"org_id": org_id}


@router.get("/organization")
def get_org(auth=Depends(manager), db: Session = Depends(get_db)):
    member = membership(db, auth)
    org = db.get(Organization, member.org_id)
    members = db.scalars(select(Membership).where(Membership.org_id == org.id)).all()
    usage = db.execute(
        select(Usage.meter, func.sum(Usage.quantity)).where(Usage.org_id == org.id).group_by(Usage.meter)
    ).all()
    return {
        **as_dict(org, "id name retention_days max_minutes max_concurrent used_minutes active_sessions"),
        "role": member.role,
        "members": [as_dict(m, "id email role") for m in members],
        "usage": {key: value for key, value in usage},
    }


@router.patch("/organization")
def update_org(data: OrgSettingsInput, auth=Depends(manager), db: Session = Depends(get_db)):
    member = membership(db, auth, owner=True)
    org = db.get(Organization, member.org_id)
    org.retention_days = data.retention_days
    audit(db, org.id, auth.subject, "retention.updated", org.id, data.model_dump())
    return {"retention_days": org.retention_days}


@router.post("/organization/members", status_code=201)
def add_member(data: MemberInput, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, owner=True)
    if settings().mode == "aws":
        users = aws("cognito-idp").list_users(
            UserPoolId=settings().cognito_pool_id, Filter=f'email = "{str(data.email)}"', Limit=2
        )["Users"]
        if len(users) != 1:
            raise HTTPException(400, "The colleague must register and verify their email first")
        attributes = {a["Name"]: a["Value"] for a in users[0]["Attributes"]}
        if attributes.get("email_verified") != "true":
            raise HTTPException(400, "Email verification required")
        subject = attributes["sub"]
    else:
        session = db.scalar(
            select(AuthSession).where(AuthSession.email == str(data.email), AuthSession.kind == "manager")
        )
        if not session:
            raise HTTPException(400, "This demo colleague must sign in first")
        subject = session.subject
    if db.scalar(select(Membership).where(Membership.org_id == auth.org_id, Membership.subject == subject)):
        raise HTTPException(409, "Already a member")
    member = Membership(org_id=auth.org_id, subject=subject, email=str(data.email), role=data.role)
    db.add(member)
    db.flush()
    audit(db, auth.org_id, auth.subject, "membership.created", member.id)
    return as_dict(member, "id email role")


@router.get("/jobs")
def jobs(auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth)
    rows = db.scalars(select(Job).where(Job.org_id == auth.org_id).order_by(Job.created_at.desc())).all()
    return [as_dict(j, "id title description seniority skills duration_minutes status created_at") for j in rows]


@router.post("/jobs", status_code=201)
def create_job(data: JobInput, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    if len({c.name for c in data.criteria}) != len(data.criteria):
        raise HTTPException(422, "Criteria names must be unique")
    job = Job(org_id=auth.org_id, **data.model_dump(exclude={"criteria"}))
    db.add(job)
    db.flush()
    for criterion in data.criteria:
        db.add(Criterion(org_id=auth.org_id, job_id=job.id, **criterion.model_dump()))
    audit(db, auth.org_id, auth.subject, "job.created", job.id)
    return as_dict(job, "id title status")


@router.get("/jobs/{job_id}")
def job_detail(job_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth)
    job = owned(db, Job, job_id, auth.org_id)
    criteria = db.scalars(select(Criterion).where(Criterion.job_id == job.id, Criterion.org_id == auth.org_id)).all()
    return {
        **as_dict(job, "id title description seniority skills duration_minutes status"),
        "criteria": [as_dict(c, "name description weight anchors") for c in criteria],
    }


def add_candidate(db, org_id, job_id, data):
    email = str(data.email).lower()
    person = db.scalar(select(Candidate).where(Candidate.org_id == org_id, Candidate.email == email))
    if not person:
        person = Candidate(org_id=org_id, email=email, name=data.name)
        db.add(person)
        db.flush()
    app = db.scalar(
        select(Application).where(
            Application.org_id == org_id, Application.job_id == job_id, Application.candidate_id == person.id
        )
    )
    if not app:
        org = db.get(Organization, org_id)
        app = Application(
            org_id=org_id,
            job_id=job_id,
            candidate_id=person.id,
            delete_after=now() + timedelta(days=org.retention_days),
        )
        db.add(app)
        db.flush()
    return app


@router.post("/jobs/{job_id}/candidates", status_code=201)
def create_candidate(job_id: str, data: CandidateInput, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    owned(db, Job, job_id, auth.org_id)
    app = add_candidate(db, auth.org_id, job_id, data)
    audit(db, auth.org_id, auth.subject, "candidate.added", app.id)
    return {"id": app.id}


@router.post("/jobs/{job_id}/import")
async def import_candidates(job_id: str, request: Request, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    owned(db, Job, job_id, auth.org_id)
    body = await request.body()
    if len(body) > 262144:
        raise HTTPException(413, "CSV exceeds 256 KB")
    try:
        rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
        if not rows or len(rows) > 100 or set(rows[0]) != {"name", "email"}:
            raise ValueError("Expected name,email columns and 1–100 rows")
        candidates = [CandidateInput.model_validate(r) for r in rows]
    except Exception as exc:
        raise HTTPException(422, "Use UTF-8 CSV with name,email columns and 1–100 valid rows") from exc
    ids = [add_candidate(db, auth.org_id, job_id, c).id for c in candidates]
    audit(db, auth.org_id, auth.subject, "candidates.imported", job_id, {"count": len(ids)})
    return {"count": len(ids), "application_ids": ids}


@router.get("/jobs/{job_id}/applications")
def applications(job_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth)
    owned(db, Job, job_id, auth.org_id)
    apps = db.scalars(
        select(Application)
        .where(Application.job_id == job_id, Application.org_id == auth.org_id)
        .order_by(Application.created_at)
    ).all()
    result = []
    for app in apps:
        candidate = owned(db, Candidate, app.candidate_id, auth.org_id)
        docs = db.scalars(
            select(Document).where(Document.application_id == app.id, Document.org_id == auth.org_id)
        ).all()
        plan = db.scalar(select(Plan).where(Plan.application_id == app.id, Plan.org_id == auth.org_id))
        jobs = db.scalars(select(AsyncJob).where(AsyncJob.org_id == auth.org_id, AsyncJob.target_id == app.id)).all()
        result.append(
            {
                **as_dict(app, "id status accommodation recording_required revoked"),
                "name": candidate.name,
                "email": candidate.email,
                "documents": [as_dict(d, "id filename status error purpose") for d in docs],
                "plan_approved": bool(plan and plan.approved),
                "jobs": [as_dict(j, "id kind status attempts error") for j in jobs],
            }
        )
    return result


@router.post("/applications/{application_id}/documents", status_code=201)
def upload_document(application_id: str, data: DocumentInput, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    app = owned(db, Application, application_id, auth.org_id)
    if app.status not in {"new", "preparing"}:
        raise HTTPException(409, "Documents are locked after plan preparation")
    extension = ".pdf" if data.content_type == "application/pdf" else ".docx"
    if PurePath(data.filename).suffix.lower() != extension or data.size > settings().max_document_bytes:
        raise HTTPException(422, "File extension/type or size invalid")
    count = db.scalar(
        select(func.count(Document.id)).where(Document.application_id == app.id, Document.org_id == auth.org_id)
    )
    if count >= 4:
        raise HTTPException(409, "Maximum four documents per application")
    key = f"{auth.org_id}/{app.id}/documents/{secrets.token_hex(16)}{extension}"
    doc = Document(org_id=auth.org_id, application_id=app.id, object_key=key, **data.model_dump())
    db.add(doc)
    db.flush()
    return {"id": doc.id, "upload": storage.upload_url(key, data.content_type, data.size, data.sha256)}


@router.post("/documents/{document_id}/complete")
def complete_document(document_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    doc = owned(db, Document, document_id, auth.org_id)
    if doc.status == "pending":
        doc.status = "processing"
        enqueue(db, auth.org_id, "extract", doc.id, "extract:" + doc.id)
    return {"status": doc.status}


@router.delete("/documents/{document_id}")
def remove_failed_document(document_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    doc = owned(db, Document, document_id, auth.org_id)
    if doc.status not in {"pending", "error"}:
        raise HTTPException(409, "Only pending or failed documents can be removed")
    enqueue(db, auth.org_id, "delete_document", doc.id, "delete-document:" + doc.id)
    return {"status": "deletion_queued"}


@router.get("/documents/{document_id}/extraction")
def extraction(document_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth)
    doc = owned(db, Document, document_id, auth.org_id)
    result = db.scalar(select(Extraction).where(Extraction.document_id == doc.id, Extraction.org_id == auth.org_id))
    return {
        "status": doc.status,
        "error": doc.error,
        "sources": result.sources if result else [],
        "warnings": result.warnings if result else [],
    }


@router.post("/applications/{application_id}/prepare", status_code=202)
def prepare(application_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    app = owned(db, Application, application_id, auth.org_id)
    if app.status not in {"new", "preparing"}:
        raise HTTPException(409, "Application is already prepared")
    docs = db.scalars(select(Document).where(Document.application_id == app.id, Document.org_id == auth.org_id)).all()
    if any(d.status != "ready" for d in docs):
        raise HTTPException(409, "Resolve or remove unfinished document uploads first")
    job = enqueue(db, auth.org_id, "prepare", app.id, "prepare:" + app.id)
    app.status = "preparing"
    return {"job_id": job.id, "status": job.status}


@router.get("/applications/{application_id}/plan")
def plan_detail(application_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth)
    owned(db, Application, application_id, auth.org_id)
    plan, questions = questions_for(db, application_id, auth.org_id)
    rubric = db.scalar(
        select(RubricVersion).where(
            RubricVersion.plan_id == plan.id, RubricVersion.org_id == auth.org_id, RubricVersion.version == plan.version
        )
    )
    return {
        **as_dict(plan, "id version approved warnings model_id"),
        "questions": [question_dict(q) for q in questions],
        "dimensions": rubric.dimensions,
    }


@router.put("/applications/{application_id}/plan")
def edit_plan(application_id: str, data: PlanEdit, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    app = owned(db, Application, application_id, auth.org_id, lock=True)
    if app.status not in {"prepared", "approved"}:
        raise HTTPException(409, "Plan cannot change after invitation launch")
    plan, questions = questions_for(db, app.id, auth.org_id)
    if plan.version != data.version:
        raise HTTPException(409, "Plan changed. Reload before editing.")
    names = {d.name for d in data.dimensions}
    job_names = set(
        db.scalars(select(Criterion.name).where(Criterion.job_id == app.job_id, Criterion.org_id == auth.org_id))
    )
    if (
        names != job_names
        or len(names) != len(data.dimensions)
        or any(q.competency not in names for q in data.questions)
    ):
        raise HTTPException(422, "Preserve job competency names across candidates")
    for d in data.dimensions:
        if set(d.anchors) != {"1", "2", "3", "4", "5"}:
            raise HTTPException(422, "Define scoring anchors 1–5")
    db.execute(delete(Question).where(Question.plan_id == plan.id, Question.org_id == auth.org_id))
    for i, q in enumerate(data.questions):
        db.add(Question(org_id=auth.org_id, plan_id=plan.id, position=i, **q.model_dump()))
    plan.version += 1
    plan.approved = data.approve
    db.add(
        RubricVersion(
            org_id=auth.org_id,
            plan_id=plan.id,
            version=plan.version,
            dimensions=[d.model_dump() for d in data.dimensions],
            approved_by=auth.subject if data.approve else None,
        )
    )
    app.status = "approved" if data.approve else "prepared"
    audit(db, auth.org_id, auth.subject, "plan.updated", plan.id, {"version": plan.version, "approved": plan.approved})
    return {"version": plan.version, "approved": plan.approved}


@router.post("/jobs/{job_id}/campaigns", status_code=201)
def launch(job_id: str, data: CampaignInput, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    owned(db, Job, job_id, auth.org_id)
    existing = db.scalar(
        select(Campaign).where(Campaign.org_id == auth.org_id, Campaign.idempotency_key == data.idempotency_key)
    )
    if existing:
        return {"id": existing.id, "status": existing.status}
    apps = [owned(db, Application, identifier, auth.org_id, lock=True) for identifier in set(data.application_ids)]
    if any(a.job_id != job_id or a.status != "approved" for a in apps):
        raise HTTPException(409, "Select approved, uninvited candidates for this job")
    campaign = Campaign(org_id=auth.org_id, job_id=job_id, idempotency_key=data.idempotency_key)
    db.add(campaign)
    db.flush()
    for app in apps:
        person = owned(db, Candidate, app.candidate_id, auth.org_id)
        token = secrets.token_urlsafe(48)
        invitation = Invitation(
            org_id=auth.org_id,
            campaign_id=campaign.id,
            application_id=app.id,
            token_hash=digest(token),
            expires_at=now() + timedelta(days=7),
        )
        db.add(invitation)
        db.flush()
        queue_email(
            db,
            auth.org_id,
            person.email,
            "invitation",
            "invite:" + invitation.id,
            "Your Talyn interview invitation",
            f"You are invited to an AI-assisted interview. Review disclosures and accommodations before starting. "
            f"Verify your email to continue: {settings().public_url}/interview#invite={token}\nThis link expires in 7 days.",
        )
        app.status = "invited"
    audit(db, auth.org_id, auth.subject, "campaign.launched", campaign.id, {"count": len(apps)})
    return {"id": campaign.id, "status": campaign.status, "invitations": len(apps)}


@router.post("/applications/{application_id}/revoke")
def revoke(application_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    app = owned(db, Application, application_id, auth.org_id, lock=True)
    app.revoked = True
    for invitation in db.scalars(
        select(Invitation).where(Invitation.application_id == app.id, Invitation.org_id == auth.org_id)
    ):
        invitation.revoked = True
    for session in db.scalars(
        select(AuthSession).where(AuthSession.application_id == app.id, AuthSession.org_id == auth.org_id)
    ):
        session.revoked = True
    active = db.scalar(
        select(InterviewSession).where(
            InterviewSession.application_id == app.id, InterviewSession.org_id == auth.org_id
        )
    )
    if active and active.status == "active":
        from .services import finish_session

        finish_session(db, active, "revoked")
        active.status = "cancelled"
    app.status = "cancelled"
    audit(db, auth.org_id, auth.subject, "application.revoked", app.id)
    return {"revoked": True}


@router.post("/applications/{application_id}/accommodation")
def approve_accommodation(application_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    app = owned(db, Application, application_id, auth.org_id)
    app.recording_required = False
    audit(db, auth.org_id, auth.subject, "accommodation.recording_waived", app.id)
    return {"recording_required": False}


@router.get("/reports")
def list_reports(auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth)
    rows = db.execute(
        select(Application, Candidate, Job)
        .join(Candidate, Candidate.id == Application.candidate_id)
        .join(Job, Job.id == Application.job_id)
        .where(
            Application.org_id == auth.org_id,
            Candidate.org_id == auth.org_id,
            Job.org_id == auth.org_id,
            Application.status == "reported",
        )
        .order_by(Application.created_at.desc())
    ).all()
    return [
        {"id": app.id, "name": candidate.name, "email": candidate.email, "job_title": job.title}
        for app, candidate, job in rows
    ]


@router.get("/applications/{application_id}/report")
def report_detail(application_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth)
    app = owned(db, Application, application_id, auth.org_id)
    session = db.scalar(
        select(InterviewSession).where(
            InterviewSession.application_id == app.id, InterviewSession.org_id == auth.org_id
        )
    )
    if not session:
        raise HTTPException(404, "Interview has not started")
    report = db.scalar(
        select(Report)
        .where(Report.session_id == session.id, Report.org_id == auth.org_id, Report.audience == "manager")
        .order_by(Report.version.desc())
    )
    if not report:
        raise HTTPException(404, "Report is not ready")
    segments = db.scalars(
        select(TranscriptSegment)
        .where(
            TranscriptSegment.session_id == session.id,
            TranscriptSegment.org_id == auth.org_id,
            TranscriptSegment.final.is_(True),
        )
        .order_by(TranscriptSegment.start_ms)
    ).all()
    observations = db.scalars(
        select(VideoObservation)
        .where(
            VideoObservation.session_id == session.id,
            VideoObservation.org_id == auth.org_id,
            VideoObservation.visible.is_(True),
        )
        .order_by(VideoObservation.start_ms)
    ).all()
    clips = db.scalars(
        select(RecordingObject)
        .where(
            RecordingObject.session_id == session.id,
            RecordingObject.org_id == auth.org_id,
            RecordingObject.verified.is_(True),
        )
        .order_by(RecordingObject.sequence)
    ).all()
    manifest = db.scalar(
        select(RecordingManifest).where(
            RecordingManifest.session_id == session.id, RecordingManifest.org_id == auth.org_id
        )
    )
    audit(db, auth.org_id, auth.subject, "report.viewed", report.id)
    return {
        **report.content,
        **as_dict(report, "id version manager_notes decision"),
        "application_id": app.id,
        "transcript": [as_dict(s, "id text speaker start_ms end_ms quality question_id") for s in segments],
        "observations": [
            as_dict(o, "id kind start_ms end_ms confidence sample_count dismissed explanation") for o in observations
        ],
        "recordings": [
            {
                **as_dict(c, "sequence start_ms end_ms content_type"),
                "url": storage.download_url(c.object_key, c.content_type),
            }
            for c in clips
        ],
        "manifest": as_dict(manifest, "finalized expected_clips missing_sequences gaps") if manifest else None,
    }


@router.patch("/reports/{report_id}")
def annotate_report(report_id: str, data: NoteInput, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    report = owned(db, Report, report_id, auth.org_id, lock=True)
    if report.audience != "manager":
        raise HTTPException(404)
    latest = db.scalar(
        select(func.max(Report.version)).where(
            Report.session_id == report.session_id, Report.org_id == auth.org_id, Report.audience == "manager"
        )
    )
    if report.version != latest:
        raise HTTPException(409, "Reload the latest report")
    new = Report(
        org_id=auth.org_id,
        session_id=report.session_id,
        audience="manager",
        version=latest + 1,
        content=report.content,
        manager_notes=data.notes,
        decision=data.decision,
    )
    db.add(new)
    db.flush()
    audit(db, auth.org_id, auth.subject, "report.annotated", new.id, {"version": new.version})
    return {"id": new.id, "version": new.version}


@router.patch("/observations/{observation_id}/dismiss")
def dismiss_observation(
    observation_id: str, data: ExplanationInput, auth=Depends(manager), db: Session = Depends(get_db)
):
    membership(db, auth, write=True)
    observation = owned(db, VideoObservation, observation_id, auth.org_id)
    observation.dismissed = True
    audit(db, auth.org_id, auth.subject, "observation.dismissed", observation.id, {"reason": data.explanation})
    return {"dismissed": True}


@router.get("/deliveries")
def deliveries(auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth)
    rows = db.scalars(
        select(EmailDelivery)
        .where(EmailDelivery.org_id == auth.org_id)
        .order_by(EmailDelivery.created_at.desc())
        .limit(200)
    ).all()
    return [
        {
            **as_dict(d, "id recipient kind status attempts error created_at"),
            **({"preview": json.loads(decrypt(d.payload_ciphertext))} if settings().mode == "demo" else {}),
        }
        for d in rows
    ]


@router.post("/background-jobs/{job_id}/retry")
def retry_job(job_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, write=True)
    job = owned(db, AsyncJob, job_id, auth.org_id)
    if job.status != "dead":
        raise HTTPException(409, "Only dead-letter jobs can be manually retried")
    job.status, job.attempts, job.error, job.published_at = "pending", 0, "", None
    job.available_at = now()
    audit(db, auth.org_id, auth.subject, "job.retried", job.id)
    return {"status": job.status}


@router.delete("/applications/{application_id}", status_code=202)
def delete_application(application_id: str, auth=Depends(manager), db: Session = Depends(get_db)):
    membership(db, auth, owner=True)
    app = owned(db, Application, application_id, auth.org_id)
    if app.status == "interviewing":
        raise HTTPException(409, "Cancel the active interview first")
    app.revoked, app.status = True, "deleting"
    enqueue(db, auth.org_id, "delete", app.id, "delete:" + app.id)
    audit(db, auth.org_id, auth.subject, "application.deletion_requested", app.id)
    return {"status": "deletion_queued"}
