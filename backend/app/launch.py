"""Serialize authoritative migrations before starting a Fargate process."""

import os
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from .checkpoints import setup
from .db import engine


def main():
    with engine.connect() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("SELECT pg_advisory_lock(82470123)"))
        try:
            command.upgrade(Config("alembic.ini"), "head")
            setup()
        finally:
            if engine.dialect.name == "postgresql":
                conn.execute(text("SELECT pg_advisory_unlock(82470123)"))
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
