import hashlib
import secrets
from datetime import timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import EmailStr
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .adapters import speak, storage
from .config import settings
from .db import get_db
from .models import (
    Application,
    Candidate,
    Consent,
    EmailChallenge,
    InterviewSession,
    Invitation,
    Job,
    RecordingManifest,
    RecordingObject,
    Report,
    TranscriptSegment,
    VideoObservation,
    now,
)
from .outbox import audit, enqueue, meter, queue_email
from .schemas import (
    AccommodationInput,
    ChallengeInput,
    ClipInput,
    ConsentInput,
    DemoAnswer,
    ExplanationInput,
    InviteInput,
    ManifestInput,
    StrictModel,
    TurnInput,
)
from .security import aware, candidate, create_session, digest, owned, rate_limit, secret_digest, set_cookie
from .services import complete_turn, finish_session, reconcile_segment, session_state, start_session

router = APIRouter(prefix="/api/candidate", tags=["candidate"])


def origin(request):
    if request.headers.get("origin") != settings().public_url:
        raise HTTPException(403, "Origin rejected")


def issue_challenge(db, invite):
    # Challenges are short-lived and throttled; only hashes are stored in the challenge table.
    code = f"{secrets.randbelow(1000000):06d}"
    challenge = EmailChallenge(
        org_id=invite.org_id,
        invitation_id=invite.id,
        code_hash=secret_digest(code),
        expires_at=now() + timedelta(minutes=10),
    )
    db.add(challenge)
    db.flush()
    app = owned(db, Application, invite.application_id, invite.org_id)
    person = owned(db, Candidate, app.candidate_id, invite.org_id)
    queue_email(
        db,
        invite.org_id,
        person.email,
        "verification",
        "verify:" + challenge.id,
        "Your Talyn verification code",
        f"Your code is {code}. It expires in 10 minutes. Do not share this code.",
    )
    return {"challenge_id": challenge.id, "message": "If access is valid, a code will arrive in your email."}


@router.post("/access/request", status_code=202)
def request_access(data: InviteInput, request: Request, db: Session = Depends(get_db, scope="function")):
    origin(request)
    rate_limit(db, "invite-ip:" + request.client.host, 15, 600)
    rate_limit(db, "invite-token:" + digest(data.token), 3, 600)
    invite = db.scalar(select(Invitation).where(Invitation.token_hash == digest(data.token)))
    if not invite or invite.revoked or invite.consumed_at or aware(invite.expires_at) <= now():
        raise HTTPException(410, "Invitation is expired or already used. Use email verification to resume.")
    app = owned(db, Application, invite.application_id, invite.org_id)
    if app.revoked:
        raise HTTPException(410, "Interview access has been revoked")
    return issue_challenge(db, invite)


class ResumeInput(StrictModel):
    application_id: str
    email: EmailStr


@router.post("/access/resume", status_code=202)
def request_resume(data: ResumeInput, request: Request, db: Session = Depends(get_db, scope="function")):
    origin(request)
    rate_limit(db, "resume-ip:" + request.client.host, 10, 600)
    rate_limit(db, "resume-app:" + data.application_id, 3, 600)
    app = db.get(Application, data.application_id)
    if app and not app.revoked and (not app.delete_after or aware(app.delete_after) > now()):
        person = owned(db, Candidate, app.candidate_id, app.org_id)
        invite = db.scalar(
            select(Invitation).where(
                Invitation.application_id == app.id,
                Invitation.org_id == app.org_id,
                Invitation.revoked.is_(False),
                Invitation.consumed_at.is_not(None),
            )
        )
        if person.email.lower() == str(data.email).lower() and invite:
            return issue_challenge(db, invite)
    return {"challenge_id": secrets.token_hex(18), "message": "If access is valid, a code will arrive in your email."}


@router.post("/access/verify")
def verify_access(
    data: ChallengeInput, request: Request, response: Response, db: Session = Depends(get_db, scope="function")
):
    origin(request)
    rate_limit(db, "challenge-ip:" + request.client.host, 20, 600)
    challenge = db.scalar(select(EmailChallenge).where(EmailChallenge.id == data.challenge_id).with_for_update())
    if not challenge or challenge.consumed or challenge.attempts >= 5 or aware(challenge.expires_at) <= now():
        raise HTTPException(401, "Verification code expired or invalid")
    challenge.attempts += 1
    correct = secrets.compare_digest(challenge.code_hash, secret_digest(data.code))
    db.commit()
    if not correct:
        raise HTTPException(401, "Verification code expired or invalid")
    invite = owned(db, Invitation, challenge.invitation_id, challenge.org_id, lock=True)
    app = owned(db, Application, invite.application_id, invite.org_id)
    if invite.revoked or app.revoked:
        raise HTTPException(401, "Access revoked")
    if invite.consumed_at:
        if aware(challenge.created_at) <= aware(invite.consumed_at):
            raise HTTPException(401, "Invitation already exchanged; request a resume code")
    elif aware(invite.expires_at) <= now():
        raise HTTPException(401, "Invitation expired")
    result = db.execute(
        update(EmailChallenge)
        .where(EmailChallenge.id == challenge.id, EmailChallenge.consumed.is_(False))
        .values(consumed=True)
    )
    if not result.rowcount:
        raise HTTPException(401, "Verification code already used")
    if not invite.consumed_at:
        invite.consumed_at = now()
    person = owned(db, Candidate, app.candidate_id, invite.org_id)
    session, token = create_session(
        db,
        kind="candidate",
        subject=person.id,
        email=person.email,
        org_id=invite.org_id,
        application_id=invite.application_id,
    )
    set_cookie(response, "candidate", token)
    audit(db, invite.org_id, person.id, "candidate.verified", app.id)
    return {"csrf": session.csrf, "application_id": app.id}


@router.get("/me")
def candidate_info(auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    app = owned(db, Application, auth.application_id, auth.org_id)
    job = owned(db, Job, app.job_id, auth.org_id)
    person = owned(db, Candidate, app.candidate_id, auth.org_id)
    session = db.scalar(
        select(InterviewSession).where(InterviewSession.application_id == app.id, InterviewSession.org_id == app.org_id)
    )
    return {
        "csrf": auth.csrf,
        "application_id": app.id,
        "name": person.name,
        "job_title": job.title,
        "duration_minutes": job.duration_minutes,
        "recording_required": app.recording_required,
        "accommodation": app.accommodation,
        "mode": settings().mode,
        "llm_provider": settings().llm_provider,
        "policy_version": settings().consent_policy,
        "frame_interval_seconds": settings().frame_interval_seconds,
        "session": session_state(db, session) if session else None,
    }


@router.post("/consent")
def consent(data: ConsentInput, auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    app = owned(db, Application, auth.application_id, auth.org_id)
    if data.policy_version != settings().consent_policy:
        raise HTTPException(409, "Reload and review the current data-processing disclosure")
    if not data.transcription or not data.ai_evaluation or not data.device_check:
        raise HTTPException(422, "Transcription, AI disclosure acknowledgment, and device check are required")
    if app.recording_required and not data.recording:
        raise HTTPException(409, "Request a recording accommodation before continuing")
    existing = db.scalar(
        select(Consent).where(
            Consent.application_id == app.id,
            Consent.org_id == auth.org_id,
            Consent.policy_version == data.policy_version,
        )
    )
    if existing:
        return {"accepted": True}
    db.add(Consent(org_id=auth.org_id, application_id=app.id, **data.model_dump()))
    audit(db, auth.org_id, auth.subject, "consent.accepted", app.id, {"policy_version": data.policy_version})
    return {"accepted": True}


@router.post("/accommodation", status_code=202)
def accommodation(data: AccommodationInput, auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    app = owned(db, Application, auth.application_id, auth.org_id)
    app.accommodation = data.request
    audit(db, auth.org_id, auth.subject, "accommodation.requested", app.id)
    return {"status": "Requested. Contact the hiring team to agree on adjustments before starting."}


@router.post("/start")
def start(auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    return session_state(db, start_session(db, auth))


def current_session(db, auth, active=False):
    session = db.scalar(
        select(InterviewSession)
        .where(InterviewSession.application_id == auth.application_id, InterviewSession.org_id == auth.org_id)
        .with_for_update()
    )
    if not session or active and session.status != "active":
        raise HTTPException(409, "Interview is not active")
    return session


@router.get("/session")
def get_session(auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth)
    return session_state(db, session)


@router.get("/transcript")
def get_transcript(auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth)
    segments = db.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.session_id == session.id, TranscriptSegment.org_id == auth.org_id)
        .order_by(TranscriptSegment.start_ms)
    ).all()
    return [
        {
            "id": s.id,
            "result_id": s.result_id,
            "text": s.text,
            "final": s.final,
            "revision": s.revision,
            "start_ms": s.start_ms,
            "end_ms": s.end_ms,
            "turn": s.turn,
        }
        for s in segments
    ]


@router.post("/demo-answer")
def demo_answer(data: DemoAnswer, auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    if settings().mode != "demo":
        raise HTTPException(404)
    session = current_session(db, auth, active=True)
    offset = int((now() - aware(session.started_at)).total_seconds() * 1000)
    segment = reconcile_segment(
        db,
        session,
        result_id=data.result_id,
        text=data.text,
        start_ms=max(0, offset - 2000),
        end_ms=offset,
        final=data.final,
        quality="synthetic",
    )
    return {"id": segment.id, "final": segment.final, "revision": segment.revision}


@router.post("/turn")
def turn(data: TurnInput, auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth)
    sid, oid = session.id, auth.org_id
    db.commit()  # Do not hold a row lock across a model call.
    return complete_turn(oid, sid, data.turn)


@router.post("/finish")
def finish(auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth)
    finish_session(db, session, "candidate_finished")
    return session_state(db, session)


@router.get("/speech")
def speech(auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth, active=True)
    state = session_state(db, session)
    text = state["question"]["text"]
    key = f"{auth.org_id}/{auth.application_id}/speech/{hashlib.sha256(text.encode()).hexdigest()}.mp3"
    if settings().mode == "demo":
        return {"demo": True, "text": text}
    try:
        data = storage.read(key, 1024 * 1024)
    except Exception:
        data = speak(text)
        storage.put(key, data, "audio/mpeg")
        meter(db, auth.org_id, auth.application_id, "speech_characters", len(text), "speech:" + key)
    return {"url": storage.download_url(key, "audio/mpeg"), "text": text}


@router.post("/recordings", status_code=201)
def recording_upload(data: ClipInput, auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth)
    consent = db.scalar(
        select(Consent).where(Consent.application_id == auth.application_id, Consent.org_id == auth.org_id)
    )
    if not consent or not consent.recording:
        raise HTTPException(403, "Recording consent required")
    if (
        session.status not in {"active", "completed"}
        or data.end_ms <= data.start_ms
        or data.end_ms - data.start_ms > 35000
    ):
        raise HTTPException(422, "Clip must contain at most 35 seconds of independently playable video")
    elapsed = int((now() - aware(session.started_at)).total_seconds() * 1000)
    if session.completed_at:
        elapsed = int((aware(session.completed_at) - aware(session.started_at)).total_seconds() * 1000)
    if data.end_ms > elapsed + 5000 or data.end_ms > 3660000:
        raise HTTPException(422, "Recording timestamps exceed the interview timeline")
    if session.completed_at and now() - aware(session.completed_at) > timedelta(hours=24):
        raise HTTPException(409, "Recording upload window closed")
    manifest = db.scalar(
        select(RecordingManifest).where(
            RecordingManifest.session_id == session.id, RecordingManifest.org_id == auth.org_id
        )
    )
    if manifest and manifest.finalized:
        raise HTTPException(409, "Recording manifest is finalized")
    existing = db.scalar(
        select(RecordingObject).where(
            RecordingObject.session_id == session.id,
            RecordingObject.org_id == auth.org_id,
            RecordingObject.sequence == data.sequence,
        )
    )
    if existing:
        if existing.sha256 != data.sha256 or existing.size != data.size:
            raise HTTPException(409, "Sequence already registered with different content")
        obj = existing
    else:
        key = f"{auth.org_id}/{auth.application_id}/recordings/{data.sequence:05d}-" + secrets.token_hex(12)
        obj = RecordingObject(org_id=auth.org_id, session_id=session.id, object_key=key, **data.model_dump())
        db.add(obj)
        db.flush()
    return {
        "id": obj.id,
        "verified": obj.verified,
        "upload": storage.upload_url(obj.object_key, obj.content_type, obj.size, obj.sha256),
    }


@router.post("/recordings/{recording_id}/complete")
def recording_complete(recording_id: str, auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth)
    obj = owned(db, RecordingObject, recording_id, auth.org_id)
    if obj.session_id != session.id:
        raise HTTPException(404)
    if not obj.verified:
        enqueue(db, auth.org_id, "verify_recording", obj.id, "recording:" + obj.id)
    return {"status": "verified" if obj.verified else "verifying"}


@router.post("/recordings/finalize-manifest")
def finalize_manifest(data: ManifestInput, auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth)
    rows = db.scalars(
        select(RecordingObject)
        .where(RecordingObject.session_id == session.id, RecordingObject.org_id == auth.org_id)
        .order_by(RecordingObject.sequence)
    ).all()
    by_seq = {r.sequence: r for r in rows}
    missing = [i for i in range(data.expected_clips) if i not in by_seq or not by_seq[i].verified]
    if any(r.sequence >= data.expected_clips for r in rows):
        raise HTTPException(422, "Manifest cannot omit registered clips")
    gaps = [{"start_ms": a.end_ms, "end_ms": b.start_ms} for a, b in zip(rows, rows[1:]) if b.start_ms - a.end_ms > 500]
    manifest = db.scalar(
        select(RecordingManifest).where(
            RecordingManifest.session_id == session.id, RecordingManifest.org_id == auth.org_id
        )
    )
    if manifest and manifest.finalized:
        return {"finalized": True, "missing_sequences": manifest.missing_sequences, "gaps": manifest.gaps}
    if not manifest:
        manifest = RecordingManifest(org_id=auth.org_id, session_id=session.id)
        db.add(manifest)
    manifest.expected_clips, manifest.missing_sequences, manifest.gaps = data.expected_clips, missing, gaps
    manifest.finalized = not missing and session.status == "completed"
    return {"finalized": manifest.finalized, "missing_sequences": missing, "gaps": gaps}


@router.get("/recordings/status")
def recordings_status(auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth)
    rows = db.scalars(
        select(RecordingObject).where(RecordingObject.session_id == session.id, RecordingObject.org_id == auth.org_id)
    ).all()
    return {
        "next_sequence": max([r.sequence for r in rows], default=-1) + 1,
        "clips": [{"id": r.id, "sequence": r.sequence, "verified": r.verified} for r in rows],
    }


@router.post("/frames", status_code=202)
# Parse the body before entering the worker thread; DB and S3 calls are synchronous.
def frame(
    data: bytes = Body(media_type="image/jpeg"),
    auth=Depends(candidate),
    db: Session = Depends(get_db, scope="function"),
):
    session = current_session(db, auth, active=True)
    consent = db.scalar(
        select(Consent).where(Consent.application_id == auth.application_id, Consent.org_id == auth.org_id)
    )
    if not consent or not consent.recording:
        raise HTTPException(403, "Recording consent required")
    rate_limit(db, "frame:" + session.id, 1, settings().frame_interval_seconds)
    if len(data) > 262144 or not data.startswith(b"\xff\xd8\xff"):
        raise HTTPException(422, "A JPEG frame under 256 KB is required")
    offset = max(0, int((now() - aware(session.started_at)).total_seconds() * 1000))
    key = f"{auth.org_id}/{auth.application_id}/frames/{offset}.jpg"
    storage.put(key, data, "image/jpeg")
    enqueue(db, auth.org_id, "frame", session.id, f"frame:{session.id}:{offset}")
    meter(db, auth.org_id, auth.application_id, "sampled_frames", 1, "sample:" + key)
    return {"queued": True}


@router.get("/observations")
def observations(auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth)
    rows = db.scalars(
        select(VideoObservation).where(
            VideoObservation.org_id == auth.org_id,
            VideoObservation.session_id == session.id,
            VideoObservation.visible.is_(True),
        )
    ).all()
    return [
        {"id": o.id, "kind": o.kind, "start_ms": o.start_ms, "end_ms": o.end_ms, "explanation": o.explanation}
        for o in rows
    ]


@router.patch("/observations/{observation_id}/explanation")
def explain_observation(
    observation_id: str,
    data: ExplanationInput,
    auth=Depends(candidate),
    db: Session = Depends(get_db, scope="function"),
):
    session = current_session(db, auth)
    observation = owned(db, VideoObservation, observation_id, auth.org_id)
    if observation.session_id != session.id:
        raise HTTPException(404)
    observation.explanation = data.explanation
    return {"saved": True}


@router.get("/report")
def candidate_report(auth=Depends(candidate), db: Session = Depends(get_db, scope="function")):
    session = current_session(db, auth)
    report = db.scalar(
        select(Report)
        .where(Report.session_id == session.id, Report.org_id == auth.org_id, Report.audience == "candidate")
        .order_by(Report.version.desc())
    )
    if not report:
        raise HTTPException(404, "Your feedback is being prepared")
    from .schemas import CandidateReport

    return {"version": report.version, **CandidateReport.model_validate(report.content).model_dump()}
