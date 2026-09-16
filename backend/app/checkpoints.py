import sqlite3
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver

from .config import settings


@contextmanager
def checkpoint_store():
    conf = settings()
    if conf.mode == "demo" and not conf.checkpoint_url:
        with sqlite3.connect(conf.data_dir / "checkpoints.db", check_same_thread=False, timeout=30) as conn:
            yield SqliteSaver(conn)
    else:
        url = conf.checkpoint_url or conf.resolve_database().replace("postgresql+psycopg://", "postgresql://")
        with PostgresSaver.from_conn_string(url) as saver:
            yield saver


def setup():
    with checkpoint_store() as saver:
        saver.setup()


def thread_id(org_id, application_id, workflow, version=1):
    return f"{org_id}:{application_id}:{workflow}:v{version}"
