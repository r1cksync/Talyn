import asyncio
import json
import secrets
from datetime import timedelta

from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select, update

from .config import settings
from .db import SessionLocal
from .models import Application, InterviewSession, now
from .outbox import meter
from .security import aware, session_from_token
from .services import reconcile_segment

router = APIRouter()


@router.websocket("/api/candidate/audio")
async def audio_stream(ws: WebSocket):
    if ws.headers.get("origin") != settings().public_url or settings().mode != "aws":
        await ws.close(code=1008)
        return
    stream = None
    consumer = None
    connection_id = secrets.token_hex(16)
    sid, oid, aid = None, None, None
    started = now()
    try:
        with SessionLocal() as db:
            auth = session_from_token(db, ws.cookies.get("talyn_candidate"), "candidate")
            app = db.get(Application, auth.application_id)
            if not app or app.revoked or app.org_id != auth.org_id:
                raise ValueError("Access revoked")
            session = db.scalar(
                select(InterviewSession).where(
                    InterviewSession.application_id == app.id, InterviewSession.org_id == auth.org_id
                )
            )
            if not session or session.status != "active" or aware(session.deadline_at) <= now():
                raise ValueError("No active interview")
            sid, oid, aid = session.id, session.org_id, session.application_id
            csrf, expires = auth.csrf, aware(auth.expires_at)
        await ws.accept()
        hello = await asyncio.wait_for(ws.receive_json(), 10)
        if (
            hello.get("type") != "start"
            or hello.get("sample_rate") != 16000
            or not secrets.compare_digest(hello.get("csrf", ""), csrf)
        ):
            raise ValueError("Invalid stream handshake")
        with SessionLocal.begin() as db:
            session = db.scalar(select(InterviewSession).where(InterviewSession.id == sid).with_for_update())
            if session.connection_id and aware(session.connection_until) > now():
                raise ValueError("Another audio stream is active")
            session.connection_id, session.connection_until = connection_id, now() + timedelta(seconds=30)
            offset_ms = max(0, int((now() - aware(session.started_at)).total_seconds() * 1000))
            turn = session.turn
        client = TranscribeStreamingClient(region=settings().region)
        stream = await client.start_stream_transcription(
            language_code="en-US",
            media_sample_rate_hz=16000,
            media_encoding="pcm",
            enable_partial_results_stabilization=True,
            partial_results_stability="medium",
        )

        class Handler(TranscriptResultStreamHandler):
            async def handle_transcript_event(self, event):
                for result in event.transcript.results:
                    if not result.alternatives:
                        continue
                    alternative = result.alternatives[0]
                    confidence = [
                        float(i.confidence)
                        for i in alternative.items or []
                        if getattr(i, "confidence", None) is not None
                    ]
                    quality = "good" if confidence and sum(confidence) / len(confidence) >= 0.7 else "poor"

                    def persist():
                        with SessionLocal.begin() as db:
                            live = db.get(InterviewSession, sid)
                            application = db.get(Application, aid)
                            if (
                                not live
                                or live.connection_id != connection_id
                                or live.turn != turn
                                or application.revoked
                            ):
                                return None
                            segment = reconcile_segment(
                                db,
                                live,
                                result_id=f"{connection_id}:{result.result_id}",
                                text=alternative.transcript,
                                start_ms=offset_ms + int(result.start_time * 1000),
                                end_ms=offset_ms + int(result.end_time * 1000),
                                final=not result.is_partial,
                                quality=quality,
                            )
                            return {
                                "type": "transcript",
                                "result_id": segment.result_id,
                                "id": segment.id,
                                "text": segment.text,
                                "final": segment.final,
                                "revision": segment.revision,
                                "turn": segment.turn,
                                "start_ms": segment.start_ms,
                                "end_ms": segment.end_ms,
                            }

                    message = await asyncio.to_thread(persist)
                    if message:
                        await ws.send_json(message)

        consumer = asyncio.create_task(Handler(stream.output_stream).handle_events())
        await ws.send_json({"type": "ready", "offset_ms": offset_ms, "turn": turn})
        byte_count = 0
        last_check = now()
        while True:
            message = await asyncio.wait_for(ws.receive(), 25)
            if message["type"] == "websocket.disconnect":
                break
            if "bytes" in message and message["bytes"] is not None:
                data = message["bytes"]
                byte_count += len(data)
                elapsed = max(1, (now() - started).total_seconds())
                if len(data) % 2 or len(data) > 6400 or byte_count > (elapsed + 3) * 32000:
                    raise ValueError("Invalid PCM framing or stream rate")
                await stream.input_stream.send_audio_event(audio_chunk=data)
            else:
                control = json.loads(message.get("text") or "{}")
                if control.get("type") == "stop":
                    break
                if control.get("type") == "ping":
                    await ws.send_json({"type": "pong", "server_time": now().isoformat()})
            if (now() - last_check).total_seconds() >= 5:
                with SessionLocal.begin() as db:
                    live = db.get(InterviewSession, sid)
                    app = db.get(Application, aid)
                    auth_check = session_from_token(db, ws.cookies.get("talyn_candidate"), "candidate")
                    if (
                        app.revoked
                        or auth_check.revoked
                        or live.status != "active"
                        or aware(live.deadline_at) <= now()
                        or expires <= now()
                    ):
                        break
                    live.connection_until = now() + timedelta(seconds=30)
                last_check = now()
        await stream.input_stream.end_stream()
        await asyncio.wait_for(consumer, 15)
        # Commit release before acknowledging stop so the HTTP turn request can proceed.
        with SessionLocal.begin() as db:
            db.execute(
                update(InterviewSession)
                .where(InterviewSession.id == sid, InterviewSession.connection_id == connection_id)
                .values(connection_id=None, connection_until=None)
            )
        await ws.send_json({"type": "stopped"})
    except (WebSocketDisconnect, asyncio.TimeoutError):
        pass
    except Exception:
        try:
            await ws.send_json(
                {
                    "type": "error",
                    "message": "Audio connection ended. Reconnect to continue; saved captions are preserved.",
                }
            )
        except Exception:
            pass
    finally:
        if stream:
            try:
                await stream.input_stream.end_stream()
            except Exception:
                pass
        if consumer and not consumer.done():
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)
        if sid:
            with SessionLocal.begin() as db:
                db.execute(
                    update(InterviewSession)
                    .where(InterviewSession.id == sid, InterviewSession.connection_id == connection_id)
                    .values(connection_id=None, connection_until=None)
                )
                meter(
                    db,
                    oid,
                    aid,
                    "transcription_seconds",
                    (now() - started).total_seconds(),
                    "transcribe:" + connection_id,
                )
        try:
            await ws.close()
        except Exception:
            pass
