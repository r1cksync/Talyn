import hashlib
import subprocess

import pytest
from fastapi.testclient import TestClient
from langgraph.graph import END, START, StateGraph
from typing import TypedDict
from sqlalchemy import select

from app.adapters import storage
from app.checkpoints import checkpoint_store
from app.db import SessionLocal
from app.graphs import invoke_recoverable
from app.main import app
from app.models import AsyncJob, RecordingObject
from app.worker import process_job, run_once
from conftest import manager_login
from test_workflow import join, launch, prepare, start


def test_clip_checksum_missing_sequence_and_decodable_playback(client, tmp_path):
    import imageio_ffmpeg

    manager_login(client)
    job_id, app_id = prepare(client, upload=False)
    with TestClient(app) as candidate:
        join(client, candidate, launch(client, job_id, app_id))
        start(candidate)
        fixture = tmp_path / "synthetic.webm"
        subprocess.run(
            [
                imageio_ffmpeg.get_ffmpeg_exe(),
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=160x120:rate=10",
                "-t",
                "1",
                "-c:v",
                "libvpx",
                str(fixture),
            ],
            check=True,
        )
        data = fixture.read_bytes()
        created = candidate.post(
            "/api/candidate/recordings",
            json={
                "sequence": 0,
                "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data),
                "content_type": "video/webm",
                "start_ms": 0,
                "end_ms": 1000,
            },
        )
        assert created.status_code == 201, created.text
        obj = created.json()
        assert candidate.put(obj["upload"]["url"], content=b"wrong checksum").status_code == 422
        assert candidate.put(obj["upload"]["url"], content=data).status_code == 200
        assert candidate.post(f"/api/candidate/recordings/{obj['id']}/complete").status_code == 200
        run_once()
        candidate.post("/api/candidate/finish")
        result = candidate.post("/api/candidate/recordings/finalize-manifest", json={"expected_clips": 2}).json()
        assert not result["finalized"] and result["missing_sequences"] == [1]
        result = candidate.post("/api/candidate/recordings/finalize-manifest", json={"expected_clips": 1}).json()
        assert result["finalized"]
        with SessionLocal() as db:
            recording = db.get(RecordingObject, obj["id"])
            assert recording.verified
            download = storage.download_url(recording.object_key, recording.content_type)
        assert candidate.get(download).content == data


def test_graph_recovers_from_failed_node_with_fresh_checkpointer():
    class State(TypedDict, total=False):
        first: int
        result: int

    calls = {"first": 0, "second": 0}

    def first(state):
        calls["first"] += 1
        return {"first": 42}

    def second(state):
        calls["second"] += 1
        if calls["second"] == 1:
            raise RuntimeError("Synthetic process interruption")
        return {"result": state["first"] + 1}

    def graph(saver):
        builder = StateGraph(State)
        builder.add_node("a", first)
        builder.add_node("b", second)
        builder.add_edge(START, "a")
        builder.add_edge("a", "b")
        builder.add_edge("b", END)
        return builder.compile(checkpointer=saver)

    import uuid

    thread = "recovery-test:" + str(uuid.uuid4())
    with checkpoint_store() as saver:
        with pytest.raises(RuntimeError):
            invoke_recoverable(graph(saver), {}, thread)
    with checkpoint_store() as saver:
        result = invoke_recoverable(graph(saver), {}, thread)
    assert result["result"] == 43
    assert calls == {"first": 1, "second": 2}


def test_outbox_replay_does_not_resend_delivered_message(client, monkeypatch):
    from app.outbox import queue_email
    import app.worker as worker

    org = manager_login(client)
    with SessionLocal.begin() as db:
        delivery = queue_email(
            db, org["id"], "alex@example.com", "test", "durable-deduplication-key", "Synthetic test", "Synthetic body"
        )
        identifier = db.scalar(select(AsyncJob.id).where(AsyncJob.target_id == delivery.id))
    calls = []
    monkeypatch.setattr(worker, "deliver_email", lambda *args: calls.append(args) or "test-provider-id")
    assert process_job(identifier)
    with SessionLocal.begin() as db:
        job = db.get(AsyncJob, identifier)
        job.status, job.locked_until = "pending", None
    assert process_job(identifier)
    assert len(calls) == 1 and calls[0][0] == "alex@example.com"


def test_background_job_cannot_cross_tenant_boundary(client):
    from app.outbox import enqueue

    manager_login(client)
    job_id, app_id = prepare(client, upload=False)
    with TestClient(app) as other:
        other_org = manager_login(other, "Unrelated tenant")
    with SessionLocal.begin() as db:
        job = enqueue(db, other_org["id"], "prepare", app_id, "invalid-tenant-job")
        identifier = job.id
    assert not process_job(identifier)
    with SessionLocal() as db:
        assert db.get(AsyncJob, identifier).status == "pending"


def test_websocket_rejects_missing_session_and_wrong_origin(client, monkeypatch):
    from starlette.websockets import WebSocketDisconnect
    from app.config import settings

    monkeypatch.setattr(settings(), "mode", "aws")
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/candidate/audio", headers={"origin": "https://evil.example"}):
            pass
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/api/candidate/audio", headers={"origin": "http://localhost:3000"}):
            pass


def test_pcm_websocket_finalization_and_reconnection(client, monkeypatch):
    """Exercise the actual route with a deterministic Transcribe event source."""
    import asyncio
    from types import SimpleNamespace as N
    import app.realtime as realtime
    from app.config import settings
    from app.models import InterviewSession, TranscriptSegment

    packets = []

    class Input:
        def __init__(self):
            self.ended = asyncio.Event()

        async def send_audio_event(self, audio_chunk):
            packets.append(audio_chunk)

        async def end_stream(self):
            self.ended.set()

    class Transcribe:
        def __init__(self, **kwargs):
            pass

        async def start_stream_transcription(self, **kwargs):
            assert kwargs["media_sample_rate_hz"] == 16000 and kwargs["media_encoding"] == "pcm"
            input_stream = Input()
            return N(input_stream=input_stream, output_stream=input_stream)

    class Events:
        def __init__(self, output):
            self.output = output

        async def handle_events(self):
            await self.output.ended.wait()
            for partial, text in [(True, "I tested"), (False, "I tested transaction failures.")]:
                event = N(
                    transcript=N(
                        results=[
                            N(
                                result_id="provider-result",
                                is_partial=partial,
                                start_time=0.0,
                                end_time=0.1,
                                alternatives=[N(transcript=text, items=[N(confidence=0.99)])],
                            )
                        ]
                    )
                )
                await self.handle_transcript_event(event)

    manager_login(client)
    job_id, app_id = prepare(client, upload=False)
    with TestClient(app) as candidate:
        join(client, candidate, launch(client, job_id, app_id))
        start(candidate)
        monkeypatch.setattr(settings(), "mode", "aws")
        monkeypatch.setattr(realtime, "TranscribeStreamingClient", Transcribe)
        monkeypatch.setattr(realtime, "TranscriptResultStreamHandler", Events)
        offsets = []
        for _ in range(2):
            with candidate.websocket_connect("/api/candidate/audio") as ws:
                ws.send_json({"type": "start", "sample_rate": 16000, "csrf": candidate.headers["x-csrf-token"]})
                ready = ws.receive_json()
                assert ready["type"] == "ready"
                offsets.append(ready["offset_ms"])
                ws.send_bytes(bytes(3200))
                ws.send_json({"type": "stop"})
                assert ws.receive_json()["final"] is False
                assert ws.receive_json()["final"] is True
                assert ws.receive_json()["type"] == "stopped"
                with SessionLocal() as db:
                    session = db.scalar(select(InterviewSession).where(InterviewSession.application_id == app_id))
                    assert session.connection_id is None
        assert len(packets) == 2 and offsets[1] >= offsets[0]
        with SessionLocal() as db:
            rows = db.scalars(select(TranscriptSegment).where(TranscriptSegment.session_id == session.id)).all()
            assert len(rows) == 2 and all(row.final and row.text == "I tested transaction failures." for row in rows)
