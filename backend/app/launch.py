"""Serialize authoritative migrations before starting a Fargate process."""

import os
import sys
import time

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from .checkpoints import setup
from .db import engine


def initialize():
    print("Initializing Talyn database and checkpoints", flush=True)
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            # A blocking lock query holds an old MVCC snapshot, which can block
            # the lock owner's CREATE INDEX CONCURRENTLY in checkpoint setup.
            conn = conn.execution_options(isolation_level="AUTOCOMMIT")
            deadline = time.monotonic() + 120
            while not conn.scalar(text("SELECT pg_try_advisory_lock(82470123)")):
                if time.monotonic() >= deadline:
                    raise RuntimeError("Timed out waiting for database initialization")
                time.sleep(0.5)
        try:
            command.upgrade(Config("alembic.ini"), "head")
            setup()
        finally:
            if engine.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_unlock(82470123)"))
    print("Talyn database and checkpoints ready", flush=True)


def main():
    initialize()
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        os.execvp("python", ["python", "-m", "app.worker"])
    os.execvp(
        "python",
        [
            "python",
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "--no-access-log",
            "--timeout-graceful-shutdown",
            "100",
            "--timeout-keep-alive",
            "125",
        ],
    )


if __name__ == "__main__":
    main()
