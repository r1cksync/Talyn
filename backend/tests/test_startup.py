import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url

from app.db import engine


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Requires the isolated PostgreSQL test database")
def test_two_fresh_processes_initialize_without_snapshot_deadlock(tmp_path):
    schema = "startup_" + uuid4().hex
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    url = make_url(os.environ["TALYN_TEST_DATABASE_URL"]).update_query_dict({"options": f"-csearch_path={schema}"})
    database_url = url.render_as_string(hide_password=False)
    env = dict(
        os.environ,
        TALYN_DATABASE_URL=database_url,
        TALYN_CHECKPOINT_URL=database_url.replace("postgresql+psycopg://", "postgresql://"),
        TALYN_DATA_DIR=str(tmp_path),
        TALYN_MODE="demo",
    )
    # Keep the first initializer in setup long enough for the second to wait.
    code = "import time; import app.launch as l; original=l.setup; l.setup=lambda:(time.sleep(1),original()); l.initialize()"
    processes = []
    try:
        for _ in range(2):
            processes.append(
                subprocess.Popen(
                    [sys.executable, "-u", "-c", code],
                    env=env,
                    cwd=Path(__file__).resolve().parents[1],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            )
        for process in processes:
            output, _ = process.communicate(timeout=25)
            assert process.returncode == 0, output
            assert "checkpoints ready" in output
        with engine.connect() as connection:
            assert connection.scalar(text(f'SELECT max(v) FROM "{schema}".checkpoint_migrations')) >= 9
    finally:
        for process in processes:
            if process.poll() is None:
                process.terminate()
                process.communicate(timeout=10)
        # This schema is unique to this test inside the explicitly isolated DB.
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
