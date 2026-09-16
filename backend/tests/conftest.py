import os
import tempfile
from pathlib import Path

_root = Path(tempfile.mkdtemp(prefix="talyn-tests-"))
os.environ["TALYN_DATABASE_URL"] = "sqlite:///" + str(_root / "test.db").replace("\\", "/")
os.environ["TALYN_DATA_DIR"] = str(_root)
os.environ["TALYN_MODE"] = "demo"
os.environ["TALYN_RUN_DEMO_WORKER"] = "false"
os.environ["TALYN_PUBLIC_URL"] = "http://localhost:3000"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from app.db import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def manager_login(client, organization="Synthetic Studio"):
    result = client.post("/api/auth/demo", headers={"origin": "http://localhost:3000"})
    assert result.status_code == 200, result.text
    client.headers.update({"origin": "http://localhost:3000", "x-csrf-token": result.json()["csrf"]})
    org = client.post("/api/organizations", json={"name": organization})
    assert org.status_code == 201, org.text
    return org.json()
