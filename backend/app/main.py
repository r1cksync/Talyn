import asyncio
import hashlib
from contextlib import asynccontextmanager

import jwt
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from . import auth, candidate_api, manager_api, realtime
from .adapters import storage
from .checkpoints import setup
from .config import settings
from .db import SessionLocal


@asynccontextmanager
async def lifespan(app):
    setup()
    async def work():
        from .worker import run_once
        while True:
            try:
                await asyncio.to_thread(run_once)
            except Exception:
                pass
            await asyncio.sleep(1)
    task = asyncio.create_task(work()) if settings().mode == "demo" and settings().run_demo_worker else None
    yield
    if task:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


app = FastAPI(title="Talyn API", version="0.1.0", lifespan=lifespan,
              docs_url="/api/docs" if settings().mode == "demo" else None, openapi_url="/api/openapi.json" if settings().mode == "demo" else None)
app.add_middleware(CORSMiddleware, allow_origins=[settings().public_url], allow_credentials=True,
                   allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"])


@app.middleware("http")
async def security_headers(request: Request, call_next):
    length = request.headers.get("content-length")
    try:
        if length and int(length) > 21*1024*1024:
            return Response(status_code=413)
    except ValueError:
        return Response(status_code=400)
    response = await call_next(request)
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), geolocation=()"
    if settings().mode == "aws":
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response


@app.get("/api/health")
def health():
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "mode": settings().mode}


@app.get("/api/config")
def public_config():
    return {"mode": settings().mode, "policy_version": "2026-09-v1"}


def object_claims(token, operation):
    if settings().mode != "demo":
        raise HTTPException(404)
    try:
        claims = jwt.decode(token, settings().session_secret, algorithms=["HS256"])
        if claims["op"] != operation:
            raise ValueError()
        return claims
    except Exception as exc:
        raise HTTPException(403, "Object access expired or invalid") from exc


@app.put("/api/demo/objects/{token}")
async def put_object(token: str, request: Request):
    claims = object_claims(token, "put")
    data = bytearray()
    async for part in request.stream():
        data.extend(part)
        if len(data) > min(claims["size"], 20971520):
            raise HTTPException(413, "Upload exceeds authorized size")
    if len(data) != claims["size"] or hashlib.sha256(data).hexdigest() != claims["sha"]:
        raise HTTPException(422, "Upload checksum or size mismatch")
    storage.put(claims["key"], bytes(data), claims["type"])
    return {"uploaded": True}


@app.get("/api/demo/objects/{token}")
def get_object(token: str):
    claims = object_claims(token, "get")
    path = storage.local_path(claims["key"])
    if not path.is_file():
        raise HTTPException(404)
    return FileResponse(path, media_type=claims["type"])


app.include_router(auth.router)
app.include_router(manager_api.router)
app.include_router(candidate_api.router)
app.include_router(realtime.router)
