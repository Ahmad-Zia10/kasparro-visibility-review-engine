import json
from contextlib import closing
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from app.analyses import service
from app.analyses.worker import process_pending
from app.classify.base import AnswerToClassify, ModelCall
from app.classify.stub import StubClassifier
from app.config import settings
from app.db import connect
from app.main import create_app


class BrokenClassifier(StubClassifier):
    """Raises for one response, as an unexpected bug would."""

    def classify(self, answer: AnswerToClassify) -> ModelCall:
        if answer.response_id == "resp-2":
            raise RuntimeError("unexpected bug")
        return super().classify(answer)


def start_analysis(client: TestClient, headers: dict[str, str]) -> Response:
    dataset = client.post("/datasets", headers=headers).json()
    return client.post("/analyses", headers=headers, json={"dataset_id": dataset["dataset_id"]})


def run_worker(classifier: StubClassifier, limit: int = 100) -> int:
    with closing(connect(settings.database_path)) as conn:
        return process_pending(conn, classifier, limit)


def model_calls(response_id: str) -> list[dict]:
    with closing(connect(settings.database_path)) as conn:
        rows = conn.execute(
            "SELECT execution_mode, outcome FROM model_calls WHERE response_id = ?",
            (response_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def test_every_response_accounted_for(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    started = start_analysis(client, analyst_headers).json()

    run_worker(StubClassifier(timeouts={"resp-2"}))

    analysis = client.get(f"/analyses/{started['analysis_id']}", headers=analyst_headers)
    failed = client.get(
        f"/analyses/{started['analysis_id']}/results/resp-2", headers=analyst_headers
    )
    assert analysis.status_code == 200
    assert analysis.json()["status"] == "complete"
    assert analysis.json()["counts"] == {
        "pending": 0,
        "done": 2,
        "failed": 1,
        "skipped": 0,
        "total": 3,
    }
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["score"] is None
    assert failed.json()["error"] == "stub timeout"


def test_new_run_is_202_with_every_response_pending(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    response = start_analysis(client, analyst_headers)

    body = response.json()
    assert response.status_code == 202
    assert body["status"] == "running"
    assert body["counts"]["pending"] == 3
    assert body["scoring_version"] == "scoring_v1"
    assert body["category_version"] == "categories_v1"
    assert body["prompt_version"] == "classify_v1"


def test_rerun_same_config_returns_existing(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    first = start_analysis(client, analyst_headers)
    run_worker(StubClassifier())

    second = start_analysis(client, analyst_headers)

    assert first.status_code == 202
    assert second.status_code == 200
    assert second.json()["analysis_id"] == first.json()["analysis_id"]
    assert second.json()["counts"]["done"] == 3
    assert second.json()["counts"]["total"] == 3
    assert len(model_calls("resp-1")) == 1


def test_new_scoring_version_creates_new_run(
    client: TestClient,
    analyst_headers: dict[str, str],
    pack_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = start_analysis(client, analyst_headers)
    monkeypatch.setattr(service, "SCORING_VERSION", "scoring_v2")

    second = start_analysis(client, analyst_headers)

    assert second.status_code == 202
    assert second.json()["analysis_id"] != first.json()["analysis_id"]
    assert second.json()["scoring_version"] == "scoring_v2"
    assert second.json()["counts"]["pending"] == 3


def test_resume_after_restart(
    test_settings: None, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    with TestClient(create_app()) as first_app:
        analysis_id = start_analysis(first_app, analyst_headers).json()["analysis_id"]
        run_worker(StubClassifier(), limit=1)

    with TestClient(create_app()) as restarted_app:
        resumed_count = run_worker(StubClassifier())
        response = restarted_app.get(f"/analyses/{analysis_id}", headers=analyst_headers)

    assert resumed_count == 2
    assert response.status_code == 200
    assert response.json()["counts"]["done"] == 3
    assert [len(model_calls(rid)) for rid in ("resp-1", "resp-2", "resp-3")] == [1, 1, 1]


def test_retry_only_touches_failed(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    analysis_id = start_analysis(client, analyst_headers).json()["analysis_id"]
    run_worker(StubClassifier(timeouts={"resp-2"}))
    done_before = client.get(f"/analyses/{analysis_id}/results/resp-1", headers=analyst_headers)

    response = client.post(f"/analyses/{analysis_id}/retry", headers=analyst_headers)

    done_after = client.get(f"/analyses/{analysis_id}/results/resp-1", headers=analyst_headers)
    retried = client.get(f"/analyses/{analysis_id}/results/resp-2", headers=analyst_headers)
    assert response.status_code == 200
    assert response.json()["counts"]["pending"] == 1
    assert done_after.json() == done_before.json()
    assert retried.json()["status"] == "pending"
    assert retried.json()["attempts"] == 1
    assert retried.json()["error"] is None


def test_retry_stops_at_max_attempts(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    analysis_id = start_analysis(client, analyst_headers).json()["analysis_id"]
    always_times_out = StubClassifier(timeouts={"resp-2"})
    run_worker(always_times_out)
    for _ in range(settings.model_max_attempts):
        client.post(f"/analyses/{analysis_id}/retry", headers=analyst_headers)
        run_worker(always_times_out)

    result = client.get(f"/analyses/{analysis_id}/results/resp-2", headers=analyst_headers)

    assert result.json()["status"] == "failed"
    assert result.json()["attempts"] == settings.model_max_attempts
    assert len(model_calls("resp-2")) == settings.model_max_attempts


def test_listing_is_bounded(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    analysis_id = start_analysis(client, analyst_headers).json()["analysis_id"]
    url = f"/analyses/{analysis_id}/results"

    too_many = client.get(url, headers=analyst_headers, params={"limit": 101})
    first_page = client.get(url, headers=analyst_headers, params={"limit": 2})
    last_page = client.get(url, headers=analyst_headers, params={"limit": 2, "offset": 2})

    assert too_many.status_code == 422
    assert too_many.json()["error"] == "invalid_request"
    assert first_page.status_code == 200
    assert first_page.json()["total"] == 3
    assert [item["response_id"] for item in first_page.json()["results"]] == [
        "resp-1",
        "resp-2",
    ]
    assert [item["response_id"] for item in last_page.json()["results"]] == ["resp-3"]


def test_rejected_records_are_skipped_with_reason(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    bad_engine = {
        "response_id": "resp-bad",
        "run_id": "run-test",
        "prompt_id": "test:p1",
        "engine": "bing",
        "answer_text": "text",
        "capture_status": "captured",
    }
    with (pack_dir / "data" / "responses.jsonl").open("a", encoding="utf-8") as file:
        file.write(json.dumps(bad_engine) + "\n")
    analysis_id = start_analysis(client, analyst_headers).json()["analysis_id"]

    processed_count = run_worker(StubClassifier())

    skipped = client.get(f"/analyses/{analysis_id}/results/resp-bad", headers=analyst_headers)
    analysis = client.get(f"/analyses/{analysis_id}", headers=analyst_headers)
    assert processed_count == 3
    assert skipped.status_code == 200
    assert skipped.json()["status"] == "skipped"
    assert "engine" in skipped.json()["reason"]
    assert skipped.json()["attempts"] == 0
    assert analysis.json()["counts"]["skipped"] == 1
    assert analysis.json()["counts"]["total"] == 4


def test_results_and_calls_record_execution_mode(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    started = start_analysis(client, analyst_headers).json()

    run_worker(StubClassifier())

    result = client.get(
        f"/analyses/{started['analysis_id']}/results/resp-1", headers=analyst_headers
    )
    assert started["execution_mode"] == "stub"
    assert result.json()["execution_mode"] == "stub"
    assert model_calls("resp-1") == [{"execution_mode": "stub", "outcome": "ok"}]


def test_worker_skips_runs_of_another_mode(
    client: TestClient,
    analyst_headers: dict[str, str],
    pack_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    start_analysis(client, analyst_headers)
    monkeypatch.setattr(settings, "model_mode", "replay")

    processed_count = run_worker(StubClassifier())

    assert processed_count == 0
    assert model_calls("resp-1") == []


def test_unexpected_error_fails_only_that_response(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    analysis_id = start_analysis(client, analyst_headers).json()["analysis_id"]

    run_worker(BrokenClassifier())

    broken = client.get(f"/analyses/{analysis_id}/results/resp-2", headers=analyst_headers)
    analysis = client.get(f"/analyses/{analysis_id}", headers=analyst_headers)
    assert broken.json()["status"] == "failed"
    assert broken.json()["error"] == "worker error: unexpected bug"
    assert broken.json()["attempts"] == 1
    assert analysis.json()["counts"]["done"] == 2


@pytest.mark.parametrize("path", ["/analyses", "/analyses/an_any/retry"])
def test_reviewer_cannot_start_or_retry(
    client: TestClient, reviewer_headers: dict[str, str], path: str
) -> None:
    response = client.post(path, headers=reviewer_headers, json={"dataset_id": "ds_any"})

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"


def test_reviewer_can_read_results(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
) -> None:
    analysis_id = start_analysis(client, analyst_headers).json()["analysis_id"]

    response = client.get(f"/analyses/{analysis_id}/results", headers=reviewer_headers)

    assert response.status_code == 200
    assert response.json()["total"] == 3


def test_unknown_dataset_is_404(client: TestClient, analyst_headers: dict[str, str]) -> None:
    response = client.post("/analyses", headers=analyst_headers, json={"dataset_id": "ds_none"})

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"


def test_unknown_result_is_404(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    analysis_id = start_analysis(client, analyst_headers).json()["analysis_id"]

    response = client.get(f"/analyses/{analysis_id}/results/resp-none", headers=analyst_headers)

    assert response.status_code == 404
    assert response.json()["error"] == "not_found"
