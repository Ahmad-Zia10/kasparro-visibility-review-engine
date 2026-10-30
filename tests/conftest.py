import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# The app reads settings at import, so test identities go in the environment first.
os.environ.update(
    ANALYST_NAME="test-analyst",
    ANALYST_TOKEN="analyst-token-for-tests",
    REVIEWER_NAME="test-reviewer",
    REVIEWER_TOKEN="reviewer-token-for-tests",
)

from app.auth import Analyst, Reviewer  # noqa: E402
from app.config import settings  # noqa: E402
from app.main import create_app  # noqa: E402


def analyst_only(analyst: Analyst) -> dict[str, str]:
    return {"name": analyst.name}


def reviewer_only(reviewer: Reviewer) -> dict[str, str]:
    return {"name": reviewer.name}


def echo_number(number: int) -> dict[str, int]:
    return {"number": number}


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setattr(settings, "database_path", tmp_path / "test.db")
    app = create_app()
    app.get("/test/analyst-only")(analyst_only)
    app.get("/test/reviewer-only")(reviewer_only)
    app.get("/test/numbers/{number}")(echo_number)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def analyst_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.analyst_token}"}


@pytest.fixture
def reviewer_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {settings.reviewer_token}"}
