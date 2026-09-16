"""One-off operator acceptance task. Synthetic data only; never a public API endpoint.

Requires separately injected test Cognito credentials. Reads only this run's encrypted
outbox to obtain simulator-only OTPs; secrets and transcripts are never printed.
"""

import asyncio
import hashlib
import io
import json
import os
import re
import subprocess
import tempfile
import time
from datetime import timedelta
from pathlib import Path

import httpx
import websockets
from docx import Document as WordDocument
from sqlalchemy import select

from .adapters import aws
from .config import settings
from .db import SessionLocal
from .models import Application, AsyncJob, EmailDelivery, now
from .security import decrypt


def main():
    if os.environ.get("TALYN_ACCEPTANCE_RUN") != "synthetic" or settings().mode != "aws":
        raise RuntimeError("Only an explicitly configured synthetic acceptance task may run")
    credentials = json.loads(os.environ["TALYN_SMOKE_CREDENTIALS"])
    if not credentials["email"].endswith("@simulator.amazonses.com"):
        raise RuntimeError("Acceptance manager must use the SES simulator")
    base = settings().public_url
    stages = []

    def call(client, method, path, data=None, expected=(200, 201, 202)):
        response = client.request(method, "/api" + path, json=data)
        if response.status_code not in expected:
            raise RuntimeError(f"{method} {path.split('?')[0]} returned HTTP {response.status_code}")
        return response.json()

    def wait_for(fn, timeout=180):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = fn()
            if result:
                return result
            time.sleep(2)
        raise RuntimeError("Bounded acceptance wait expired")

    def passed(name):
        stages.append(name)
        print(json.dumps({"stage": name, "passed": True}), flush=True)

    with (
        httpx.Client(base_url=base, headers={"Origin": base}, timeout=120) as manager,
        httpx.Client(base_url=base, headers={"Origin": base}, timeout=120) as candidate,
    ):
        login = call(
            manager, "POST", "/auth/login", {"email": credentials["email"], "password": credentials["password"]}
        )
        manager.headers["x-csrf-token"] = login["csrf"]
        org = call(manager, "POST", "/organizations", {"name": "Synthetic AWS acceptance " + str(int(time.time()))})
        oid = org["id"]
        passed("cloudfront_https_cognito_login_organization")
        job = call(
            manager,
            "POST",
            "/jobs",
            {
                "title": "Synthetic backend engineer",
                "description": "Build Python services and explain database consistency and performance tradeoffs.",
                "skills": ["Python", "PostgreSQL"],
                "duration_minutes": 5,
                "criteria": [
                    {
                        "name": "Technical reasoning",
                        "description": "Explain tested choices, tradeoffs and measurable outcomes.",
                    }
                ],
            },
        )
        application = call(
            manager,
            "POST",
            f"/jobs/{job['id']}/candidates",
            {"name": "Synthetic Alex", "email": "success@simulator.amazonses.com"},
        )
        aid = application["id"]
        word = WordDocument()
        word.add_paragraph(
            "Synthetic Alex built a Python service using PostgreSQL transactions and idempotency keys. They tested retry failure cases and compared query performance before and after adding an index."
        )
        buffer = io.BytesIO()
        word.save(buffer)
        data = buffer.getvalue()
        document = call(
            manager,
            "POST",
            f"/applications/{aid}/documents",
            {
                "filename": "synthetic.docx",
                "content_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            },
        )
        uploaded = httpx.put(document["upload"]["url"], headers=document["upload"]["headers"], content=data, timeout=60)
        if uploaded.status_code != 200:
            raise RuntimeError("Signed S3 document upload failed")
        call(manager, "POST", f"/documents/{document['id']}/complete")

        def application_state():
            return next(a for a in call(manager, "GET", f"/jobs/{job['id']}/applications") if a["id"] == aid)

        wait_for(lambda: any(d["status"] == "ready" for d in application_state()["documents"]))
        passed("signed_s3_checksum_sqs_document_extraction")
        call(manager, "POST", f"/applications/{aid}/prepare")

        def plan_ready():
            response = manager.get(f"/api/applications/{aid}/plan")
            return response.json() if response.status_code == 200 else None

        plan = wait_for(plan_ready)
        call(
            manager,
            "PUT",
            f"/applications/{aid}/plan",
            {
                "questions": plan["questions"],
                "dimensions": plan["dimensions"],
                "version": plan["version"],
                "approve": True,
            },
        )
        passed("groq_plan_postgres_checkpoints_approval")
        call(
            manager,
            "POST",
            f"/jobs/{job['id']}/campaigns",
            {"application_ids": [aid], "idempotency_key": "acceptance-" + aid},
        )

        def delivery(kind):
            with SessionLocal() as db:
                row = db.scalar(
                    select(EmailDelivery)
                    .where(EmailDelivery.org_id == oid, EmailDelivery.kind == kind)
                    .order_by(EmailDelivery.created_at.desc())
                )
                if row and row.status in {"sent", "delivered"}:
                    return json.loads(decrypt(row.payload_ciphertext))["body"]
            return None

        body = wait_for(lambda: delivery("invitation"))
        token = re.search(r"#invite=([A-Za-z0-9_-]+)", body).group(1)
        challenge = call(candidate, "POST", "/candidate/access/request", {"token": token})
        body = wait_for(lambda: delivery("verification"))
        code = re.search(r"\b\d{6}\b", body).group()
        access = call(
            candidate, "POST", "/candidate/access/verify", {"challenge_id": challenge["challenge_id"], "code": code}
        )
        candidate.headers["x-csrf-token"] = access["csrf"]
        info = call(candidate, "GET", "/candidate/me")
        call(
            candidate,
            "POST",
            "/candidate/consent",
            {
                "policy_version": info["policy_version"],
                "recording": True,
                "transcription": True,
                "ai_evaluation": True,
                "device_check": True,
            },
        )
        state = call(candidate, "POST", "/candidate/start")
        passed("ses_simulator_invitation_otp_and_scoped_consent")

        with tempfile.TemporaryDirectory() as folder:
            clip = Path(folder) / "synthetic.webm"
            frame = Path(folder) / "frame.jpg"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-f",
                    "lavfi",
                    "-i",
                    "testsrc2=size=320x240:rate=10",
                    "-t",
                    "2",
                    "-c:v",
                    "libvpx",
                    str(clip),
                ],
                check=True,
                timeout=30,
            )
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", str(clip), "-frames:v", "1", str(frame)], check=True, timeout=20
            )
            media = clip.read_bytes()
            obj = call(
                candidate,
                "POST",
                "/candidate/recordings",
                {
                    "sequence": 0,
                    "sha256": hashlib.sha256(media).hexdigest(),
                    "size": len(media),
                    "content_type": "video/webm",
                    "start_ms": 0,
                    "end_ms": 2000,
                },
            )
            uploaded = httpx.put(obj["upload"]["url"], headers=obj["upload"]["headers"], content=media, timeout=60)
            if uploaded.status_code != 200:
                raise RuntimeError("Signed S3 recording upload failed")
            call(candidate, "POST", f"/candidate/recordings/{obj['id']}/complete")
            result = candidate.post(
                "/api/candidate/frames", content=frame.read_bytes(), headers={"Content-Type": "image/jpeg"}
            )
            if result.status_code != 202:
                raise RuntimeError("Synthetic frame upload failed")

        speech = aws("polly").synthesize_speech(
            Text="I built a Python service with PostgreSQL transactions and idempotency keys. I compared two approaches, tested retry failures, and measured query latency before adding an index. Duplicate requests were safely ignored, and response time improved by forty percent. I explained the tradeoffs to the team and documented the result.",
            VoiceId="Joanna",
            Engine="neural",
            OutputFormat="pcm",
            SampleRate="16000",
        )
        with speech["AudioStream"] as stream:
            audio = stream.read()

        async def answer():
            url = base.replace("https://", "wss://") + "/api/candidate/audio"
            cookie = "; ".join(f"{c.name}={c.value}" for c in candidate.cookies.jar)
            async with websockets.connect(
                url, origin=base, additional_headers={"Cookie": cookie}, open_timeout=30, max_size=1048576
            ) as socket:
                await socket.send(json.dumps({"type": "start", "sample_rate": 16000, "csrf": access["csrf"]}))
                if json.loads(await socket.recv())["type"] != "ready":
                    raise RuntimeError("Streaming handshake failed")
                finals = []

                async def send():
                    for offset in range(0, len(audio), 3200):
                        await socket.send(audio[offset : offset + 3200])
                        await asyncio.sleep(0.1)
                    await socket.send(json.dumps({"type": "stop"}))

                async def receive():
                    async for message in socket:
                        data = json.loads(message)
                        if data["type"] == "transcript" and data["final"]:
                            finals.append(data["id"])
                        if data["type"] == "stopped":
                            return
                        if data["type"] == "error":
                            raise RuntimeError("Streaming provider returned an error")

                await asyncio.wait_for(asyncio.gather(send(), receive()), 75)
                if not finals:
                    raise RuntimeError("No final transcript arrived")

        for turn in range(4):
            if state["status"] != "active":
                break
            question = call(candidate, "GET", "/candidate/speech")
            if httpx.get(question["url"], timeout=30).status_code != 200:
                raise RuntimeError("Polly S3 playback URL failed")
            asyncio.run(answer())
            state = call(candidate, "POST", "/candidate/turn", {"turn": state["turn"]})
        call(candidate, "POST", "/candidate/finish")
        passed("cloudfront_websocket_pcm_transcribe_polly_interview")

        def frame_processed():
            with SessionLocal() as db:
                job = db.scalar(select(AsyncJob).where(AsyncJob.org_id == oid, AsyncJob.kind == "frame"))
                if job and job.status == "dead":
                    raise RuntimeError("Synthetic Rekognition frame job exhausted retries")
                return job and job.status == "done"

        wait_for(frame_processed)
        passed("rekognition_synthetic_frame_processed")
        wait_for(
            lambda: call(candidate, "POST", "/candidate/recordings/finalize-manifest", {"expected_clips": 1})[
                "finalized"
            ]
        )

        def report_ready():
            response = manager.get(f"/api/applications/{aid}/report")
            return response.json() if response.status_code == 200 else None

        report = wait_for(report_ready)
        feedback = call(candidate, "GET", "/candidate/report")
        call(manager, "PATCH", f"/reports/{report['id']}", {"notes": "SYNTHETIC_PRIVATE_NOTE", "decision": "pending"})
        if "SYNTHETIC_PRIVATE_NOTE" in json.dumps(call(candidate, "GET", "/candidate/report")):
            raise RuntimeError("Audience separation failed")
        if feedback.get("synthetic"):
            raise RuntimeError("AWS acceptance unexpectedly used demo inference")
        passed("groq_evidence_reports_audience_isolation_media_manifest")
        wait_for(lambda: delivery("candidate_report"))
        wait_for(lambda: delivery("manager_report"))
        passed("ses_report_notifications")
        with SessionLocal.begin() as db:
            fixture = db.get(Application, aid)
            fixture.delete_after = now() + timedelta(days=1)
        print(
            json.dumps(
                {
                    "acceptance_passed": True,
                    "stages": stages,
                    "synthetic_application": aid,
                    "limitations": "Generated media via protocol client; browser capture tested separately. OCR, bounce handling and ten live concurrent sessions are not claimed.",
                }
            ),
            flush=True,
        )


if __name__ == "__main__":
    main()
