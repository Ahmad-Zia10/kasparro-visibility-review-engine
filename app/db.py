import sqlite3
import sys
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends

from app.config import settings

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(path: Path) -> sqlite3.Connection:
    # FastAPI may open a connection on one thread and use it on another.
    conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def transaction(conn: sqlite3.Connection) -> Iterator[None]:
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
    except BaseException:
        conn.rollback()
        raise
    conn.commit()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def get_conn() -> Iterator[sqlite3.Connection]:
    """Give each request its own connection and close it afterwards."""
    with closing(connect(settings.database_path)) as conn:
        yield conn


Conn = Annotated[sqlite3.Connection, Depends(get_conn)]


if __name__ == "__main__":
    if sys.argv[1:] != ["init"]:
        sys.exit("usage: python -m app.db init")
    with closing(connect(settings.database_path)) as connection:
        init_db(connection)
