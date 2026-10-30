import json
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.db import connect


def append_line(path: Path, line: str) -> None:
    with path.open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def stored_responses() -> dict[str, dict]:
    with closing(connect(settings.database_path)) as conn:
        rows = conn.execute("SELECT response_id, model_version, raw_json FROM responses").fetchall()
    return {row["response_id"]: dict(row) for row in rows}


def test_import_preserves_original_ids(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    response = client.post("/datasets", headers=analyst_headers)

    body = response.json()
    assert response.status_code == 201
    assert body["prompt_count"] == 2
    assert body["response_count"] == 3
    assert body["citation_count"] == 3
    assert body["rejected"] == []
    stored = stored_responses()
    assert set(stored) == {"resp-1", "resp-2", "resp-3"}
    assert json.loads(stored["resp-1"]["raw_json"])["provider_timestamp"] == (
        "2026-07-31 04:00:00 +00:00"
    )


def test_missing_model_version_stays_null(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    client.post("/datasets", headers=analyst_headers)

    stored = stored_responses()
    assert stored["resp-1"]["model_version"] == "model-test-1"
    assert stored["resp-2"]["model_version"] is None


def test_one_bad_record_keeps_valid_ones(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    data = pack_dir / "data"
    append_line(data / "prompts.jsonl", "{not valid json")
    bad_engine = {
        "response_id": "resp-bad",
        "run_id": "run-test",
        "prompt_id": "test:p1",
        "engine": "bing",
        "answer_text": "text",
        "capture_status": "captured",
    }
    append_line(data / "responses.jsonl", json.dumps(bad_engine))
    orphan = {
        "citation_id": "CIT-orphan",
        "response_id": "resp-missing",
        "prompt_id": "test:p1",
        "engine": "chatgpt",
        "order": 1,
        "citation_type": "inline_hyperlink",
        "url": "https://example.org/",
    }
    append_line(data / "citations.jsonl", json.dumps(orphan))

    response = client.post("/datasets", headers=analyst_headers)

    body = response.json()
    rejected = {(item["file"], item["line"]): item for item in body["rejected"]}
    assert response.status_code == 201
    assert (body["prompt_count"], body["response_count"], body["citation_count"]) == (2, 3, 3)
    assert set(rejected) == {("prompts.jsonl", 3), ("responses.jsonl", 4), ("citations.jsonl", 4)}
    assert rejected[("prompts.jsonl", 3)]["record_id"] is None
    assert rejected[("responses.jsonl", 4)]["record_id"] == "resp-bad"
    assert "engine" in rejected[("responses.jsonl", 4)]["reason"]
    assert rejected[("citations.jsonl", 4)]["reason"] == "unknown response_id resp-missing"


def test_unreadable_file_is_422(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    (pack_dir / "data" / "citations.jsonl").unlink()

    response = client.post("/datasets", headers=analyst_headers)

    assert response.status_code == 422
    assert response.json() == {
        "error": "unreadable_pack",
        "detail": "cannot read citations.jsonl",
    }


def test_reimport_is_idempotent(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    first = client.post("/datasets", headers=analyst_headers)

    second = client.post("/datasets", headers=analyst_headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()
    assert len(stored_responses()) == 3


def test_reviewer_cannot_import(
    client: TestClient, reviewer_headers: dict[str, str], pack_dir: Path
) -> None:
    response = client.post("/datasets", headers=reviewer_headers)

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"


def test_reviewer_can_read_dataset(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
) -> None:
    imported = client.post("/datasets", headers=analyst_headers).json()

    response = client.get(f"/datasets/{imported['dataset_id']}", headers=reviewer_headers)

    assert response.status_code == 200
    assert response.json() == imported


def test_get_unknown_dataset_is_404(client: TestClient, reviewer_headers: dict[str, str]) -> None:
    response = client.get("/datasets/ds_unknown", headers=reviewer_headers)

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
