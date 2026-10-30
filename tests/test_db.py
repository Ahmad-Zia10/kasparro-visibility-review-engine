import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.db import connect, transaction


@pytest.fixture
def conn(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    connection = connect(tmp_path / "test.db")
    connection.execute("CREATE TABLE notes (body TEXT NOT NULL)")
    yield connection
    connection.close()


def test_transaction_commits_on_success(conn: sqlite3.Connection) -> None:
    with transaction(conn):
        conn.execute("INSERT INTO notes (body) VALUES ('kept')")

    bodies = [row["body"] for row in conn.execute("SELECT body FROM notes")]
    assert bodies == ["kept"]


def test_transaction_rolls_back_on_error(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValueError), transaction(conn):
        conn.execute("INSERT INTO notes (body) VALUES ('lost')")
        raise ValueError("simulated failure")

    count = conn.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
    assert count == 0
