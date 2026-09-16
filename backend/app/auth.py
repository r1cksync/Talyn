import secrets

import boto3
import jwt
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import get_db
from .models import Membership
from .schemas import Credentials, VerifyRegistration
from .security import create_session, manager, rate_limit, set_cookie

router = APIRouter(prefix="/api/auth", tags=["authentication"])


def auth_origin(request):
    if request.headers.get("origin") != settings().public_url:
        raise HTTPException(403, "Origin rejected")


def cognito():
    return boto3.client("cognito-idp", region_name=settings().region)


@router.post("/register", status_code=202)
def register(data: Credentials, request: Request, db: Session = Depends(get_db)):
    auth_origin(request)
    rate_limit(db, "register:" + request.client.host, 5, 3600)
    if settings().mode == "demo":
        return {"message": "Synthetic demo uses the demo sign-in button. No account or email was created."}
    try:
        cognito().sign_up(
            ClientId=settings().cognito_client_id,
            Username=str(data.email).lower(),
            Password=data.password,
            UserAttributes=[{"Name": "email", "Value": str(data.email).lower()}],
        )
    except Exception as exc:
        raise HTTPException(400, "Registration could not be completed. Check your details or sign in.") from exc
    return {"message": "Check your email for the verification code."}


@router.post("/verify")
def verify(data: VerifyRegistration, request: Request, db: Session = Depends(get_db)):
    auth_origin(request)
    rate_limit(db, "verify:" + request.client.host, 10, 600)
    if settings().mode != "aws":
        raise HTTPException(400, "Use demo sign in")
    try:
        cognito().confirm_sign_up(
            ClientId=settings().cognito_client_id, Username=str(data.email).lower(), ConfirmationCode=data.code
        )
    except Exception as exc:
        raise HTTPException(400, "Verification code invalid or expired") from exc
    return {"verified": True}


def login_response(db, response, subject, email):
    membership = db.scalar(select(Membership).where(Membership.subject == subject))
    session, token = create_session(
        db, kind="manager", subject=subject, email=email, org_id=membership.org_id if membership else None
    )
    set_cookie(response, "manager", token)
    return {"csrf": session.csrf, "org_id": session.org_id, "email": email, "mode": settings().mode}


@router.post("/login")
def login(data: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    auth_origin(request)
    rate_limit(db, "login:" + request.client.host, 15, 300)
    if settings().mode != "aws":
        raise HTTPException(400, "Use demo sign in")
    try:
        result = cognito().initiate_auth(
            ClientId=settings().cognito_client_id,
            AuthFlow="USER_PASSWORD_AUTH",
            AuthParameters={"USERNAME": str(data.email).lower(), "PASSWORD": data.password},
        )
        token = result["AuthenticationResult"]["IdToken"]
        issuer = f"https://cognito-idp.{settings().region}.amazonaws.com/{settings().cognito_pool_id}"
        key = jwt.PyJWKClient(issuer + "/.well-known/jwks.json").get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=["RS256"], audience=settings().cognito_client_id, issuer=issuer)
        if claims.get("token_use") != "id" or not claims.get("email_verified"):
            raise ValueError("Email must be verified")
    except Exception as exc:
        raise HTTPException(401, "Unable to sign in. Verify your email and credentials.") from exc
    return login_response(db, response, claims["sub"], claims["email"])


@router.post("/demo")
def demo(request: Request, response: Response, db: Session = Depends(get_db)):
    auth_origin(request)
    if settings().mode != "demo":
        raise HTTPException(404)
    subject = "demo-" + secrets.token_hex(12)
    return login_response(db, response, subject, "manager@example.test")


@router.get("/me")
def me(auth=Depends(manager), db: Session = Depends(get_db)):
    memberships = db.scalars(select(Membership).where(Membership.subject == auth.subject)).all()
    return {
        "csrf": auth.csrf,
        "email": auth.email,
        "org_id": auth.org_id,
        "mode": settings().mode,
        "memberships": [{"org_id": m.org_id, "role": m.role} for m in memberships],
    }


@router.post("/logout")
def logout(response: Response, auth=Depends(manager)):
    auth.revoked = True
    response.delete_cookie("talyn_manager", path="/api")
    return {"ok": True}
