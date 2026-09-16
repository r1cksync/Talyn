"""Health and recording requests must stay responsive during database / S3 waits."""

import asyncio
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import timedelta
from threading import Event
from types import SimpleNamespace as N

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.config import settings
from app.db import SessionLocal, engine
from app.main import app
from app.models import InterviewSession, now
from conftest import manager_login
from test_workflow import join, launch, prepare, start


class FakeTranscribe:
    def __init__(self, **kwargs):
        pass

    async def start_stream_transcription(self, **kwargs):
        ended = asyncio.Event()

        async def end_stream():
            ended.set()

        return N(input_stream=N(end_stream=end_stream), output_stream=ended)


class FakeEvents:
    def __init__(self, ended):
        self.ended = ended

    async def handle_events(self):
        await self.ended.wait()


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Requires actual PostgreSQL row locks")
@pytest.mark.parametrize("phase", ["start", "heartbeat", "stop"])
def test_audio_row_lock_does_not_block_http_event_loop(client, monkeypatch, phase):
    import app.realtime as realtime

    manager_login(client)
    job_id, app_id = prepare(client, upload=False)
    with TestClient(app) as candidate:
        join(client, candidate, launch(client, job_id, app_id))
        start(candidate)
        monkeypatch.setattr(settings(), "mode", "aws")
        monkeypatch.setattr(realtime, "TranscribeStreamingClient", FakeTranscribe)
        monkeypatch.setattr(realtime, "TranscriptResultStreamHandler", FakeEvents)
        with SessionLocal() as db:
            sid = db.scalar(select(InterviewSession.id).where(InterviewSession.application_id == app_id))
        with candidate.websocket_connect("/api/candidate/audio") as ws:
            hello = {"type": "start", "sample_rate": 16000, "csrf": candidate.headers["x-csrf-token"]}
            if phase != "start":
                ws.send_json(hello)
                assert ws.receive_json()["type"] == "ready"
            waiting = Event()

            def detect_lock_wait(conn, cursor, statement, parameters, context, executemany):
                if "interview_sessions" in statement and ("FOR UPDATE" in statement or statement.startswith("UPDATE")):
                    waiting.set()

            with SessionLocal() as locked, ThreadPoolExecutor() as pool:
                locked.scalar(select(InterviewSession).where(InterviewSession.id == sid).with_for_update())
                event.listen(engine, "before_cursor_execute", detect_lock_wait)
                try:
                    if phase == "heartbeat":
                        future_time = now() + timedelta(seconds=6)
                        monkeypatch.setattr(realtime, "now", lambda: future_time)
                    ws.send_json(hello if phase == "start" else {"type": "ping" if phase == "heartbeat" else "stop"})
                    assert waiting.wait(3), "Audio handler did not reach the database lock"
                    health = pool.submit(candidate.get, "/api/health")
                    try:
                        responsive = health.result(timeout=1).status_code == 200
                    except TimeoutError:
                        responsive = False
                finally:
                    locked.rollback()
                    event.remove(engine, "before_cursor_execute", detect_lock_wait)
                if phase != "stop":
                    assert ws.receive_json()["type"] == ("ready" if phase == "start" else "pong")
                    ws.send_json({"type": "stop"})
                assert ws.receive_json()["type"] == "stopped"
            assert responsive, "A locked interview row froze unrelated HTTP requests"


def test_slow_frame_storage_does_not_block_health(client, monkeypatch):
    from app.adapters import storage

    manager_login(client)
    job_id, app_id = prepare(client, upload=False)
    with TestClient(app) as candidate:
        join(client, candidate, launch(client, job_id, app_id))
        start(candidate)
        entered, release = Event(), Event()

        def slow_put(*args):
            entered.set()
            assert release.wait(5)

        monkeypatch.setattr(storage, "put", slow_put)
        with ThreadPoolExecutor() as pool:
            frame = pool.submit(
                candidate.post,
                "/api/candidate/frames",
                content=b"\xff\xd8\xfffixture",
                headers={"content-type": "image/jpeg"},
            )
            assert entered.wait(3)
            health = pool.submit(candidate.get, "/api/health")
            try:
                responsive = health.result(timeout=1).status_code == 200
            except TimeoutError:
                responsive = False
            finally:
                release.set()
            assert frame.result(timeout=3).status_code == 202
        assert responsive, "A frame upload froze unrelated HTTP requests"
