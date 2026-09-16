import base64
import hashlib
import hmac
import secrets
import time
from datetime import timedelta, timezone

from cryptography.fernet import Fernet
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import AuthSession, Membership, RateBucket, now


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def secret_digest(value: str) -> str:
    return hmac.new(settings().session_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def aware(value):
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value


def cipher():
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(settings().session_secret.encode()).digest()))


def encrypt(value: str):
    return cipher().encrypt(value.encode()).decode()


def decrypt(value: str):
    return cipher().decrypt(value.encode()).decode()


def rate_limit(db: Session, key: str, limit=15, seconds=60):
    window = int(time.time()) // seconds
    key = digest(key + str(window))
    bucket = db.scalar(select(RateBucket).where(RateBucket.key == key))
    if not bucket:
        bucket = RateBucket(key=key, window=window, count=0)
        db.add(bucket)
        db.flush()
    db.execute(update(RateBucket).where(RateBucket.id == bucket.id).values(count=RateBucket.count + 1))
    db.refresh(bucket)
    # Rate counters must survive rejected requests.
    db.commit()
    if bucket.count > limit:
        raise HTTPException(429, "Too many attempts. Please try again later.")


def create_session(db, *, kind, subject, email="", org_id=None, application_id=None):
    token = secrets.token_urlsafe(48)
    session = AuthSession(
        token_hash=digest(token),
        kind=kind,
        subject=subject,
        email=email,
        org_id=org_id,
        application_id=application_id,
        csrf=secrets.token_urlsafe(24),
        expires_at=now() + timedelta(hours=8 if kind == "manager" else 2),
    )
    db.add(session)
    db.flush()
    return session, token


def set_cookie(response, kind, token):
    response.set_cookie(
        "talyn_" + kind,
        token,
        httponly=True,
        secure=settings().mode == "aws",
        samesite="lax",
        max_age=28800 if kind == "manager" else 7200,
        path="/api",
    )


def session_from_token(db, token, kind):
    if not token:
        raise HTTPException(401, "Sign in to continue")
    auth = db.scalar(
        select(AuthSession).where(
            AuthSession.token_hash == digest(token), AuthSession.kind == kind, AuthSession.revoked.is_(False)
        )
    )
    if not auth or aware(auth.expires_at) <= now():
        raise HTTPException(401, "Session expired. Verify access again.")
    return auth


def check_csrf(request: Request, auth):
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        if request.headers.get("origin") != settings().public_url:
            raise HTTPException(403, "Origin rejected")
        if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), auth.csrf):
            raise HTTPException(403, "CSRF token rejected")


def manager(request: Request, db: Session = Depends(get_db, scope="function")):
    auth = session_from_token(db, request.cookies.get("talyn_manager"), "manager")
    check_csrf(request, auth)
    return auth


def candidate(request: Request, db: Session = Depends(get_db, scope="function")):
    from .models import Application

    auth = session_from_token(db, request.cookies.get("talyn_candidate"), "candidate")
    app = db.get(Application, auth.application_id)
    if not app or app.org_id != auth.org_id or app.revoked:
        raise HTTPException(401, "Interview access revoked")
    check_csrf(request, auth)
    return auth


def membership(db, auth, org_id=None, write=False, owner=False):
    org_id = org_id or auth.org_id
    member = db.scalar(select(Membership).where(Membership.org_id == org_id, Membership.subject == auth.subject))
    if not member:
        raise HTTPException(403, "Organization membership required")
    if owner and member.role != "owner" or write and member.role == "reviewer":
        raise HTTPException(403, "Your organization role cannot perform this action")
    return member


def owned(db, model, identifier, org_id, lock=False):
    query = select(model).where(model.id == identifier, model.org_id == org_id)
    if lock:
        query = query.with_for_update()
    result = db.scalar(query)
    if not result:
        raise HTTPException(404, "Record not found")
    return result
