import json

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import Job
from conftest import manager_login
from test_workflow import JOB


def test_job_is_committed_before_success_reaches_the_client():
    observed = []

    async def inspect_response(scope, receive, send):
        async def inspect(message):
            if scope.get("path") == "/api/jobs" and scope.get("method") == "POST":
                if message["type"] == "http.response.body" and message.get("body"):
                    created = json.loads(message["body"])
                    with SessionLocal() as independent:
                        observed.append(independent.scalar(select(Job.id).where(Job.id == created["id"])))
            await send(message)

        await app(scope, receive, inspect)

    with TestClient(inspect_response) as client:
        manager_login(client)
        response = client.post("/api/jobs", json=JOB)
        assert response.status_code == 201
        assert observed == [response.json()["id"]], "Success must follow the durable database commit"
