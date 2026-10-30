import json
import threading
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import clock
from app.analyses.worker import process_pending
from app.auth import Identity
from app.classify.base import PROMPT_VERSION
from app.classify.factory import make_classifier
from app.classify.replay import save_output
from app.classify.stub import StubClassifier
from app.config import settings
from app.db import connect
from app.errors import Conflict
from app.main import create_app
from app.reports import service
from app.reports.schemas import DecisionRequest

START = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


class Clock:
    def __init__(self) -> None:
        self.current = START

    def advance(self, hours: float) -> None:
        self.current += timedelta(hours=hours)


@pytest.fixture
def frozen_clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    controlled = Clock()
    monkeypatch.setattr(clock, "now", lambda: controlled.current)
    return controlled


def finish_analysis(client: TestClient, headers: dict[str, str]) -> str:
    dataset = client.post("/datasets", headers=headers).json()
    analysis = client.post(
        "/analyses", headers=headers, json={"dataset_id": dataset["dataset_id"]}
    ).json()
    with closing(connect(settings.database_path)) as conn:
        process_pending(conn, StubClassifier(), limit=100)
    return analysis["analysis_id"]


def open_report(client: TestClient, headers: dict[str, str]) -> dict:
    analysis_id = finish_analysis(client, headers)
    return client.post("/reports", headers=headers, json={"analysis_id": analysis_id}).json()


def edit(client: TestClient, report: dict, headers: dict[str, str], etag: str | None) -> dict:
    extra = {"If-Match": etag} if etag else {}
    return client.patch(
        f"/reports/{report['report_id']}",
        headers=headers | extra,
        json={"content": {"summary": "edited"}},
    )


def submit(client: TestClient, report: dict, headers: dict[str, str]) -> dict:
    return client.post(f"/reports/{report['report_id']}/submit", headers=headers)


def decide(
    client: TestClient, report: dict, headers: dict[str, str], decision: str = "approve"
) -> dict:
    payload = {"version": 1, "decision": decision, "comment": "checked the evidence"}
    return client.post(f"/reports/{report['report_id']}/decision", headers=headers, json=payload)


def export(client: TestClient, report: dict, headers: dict[str, str], version: int | None = None):
    query = f"?version={version}" if version else ""
    return client.get(f"/reports/{report['report_id']}/export{query}", headers=headers)


def version_rows(report_id: str) -> list[dict]:
    with closing(connect(settings.database_path)) as conn:
        rows = conn.execute(
            "SELECT version_no, status, content_sha256 FROM report_versions "
            "WHERE report_id = ? ORDER BY version_no",
            (report_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def test_permissions_matrix(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
) -> None:
    analysis_id = finish_analysis(client, analyst_headers)
    refused = client.post("/reports", headers=reviewer_headers, json={"analysis_id": analysis_id})
    report = client.post(
        "/reports", headers=analyst_headers, json={"analysis_id": analysis_id}
    ).json()

    reviewer_edit = edit(client, report, reviewer_headers, report["etag"])
    reviewer_submit = submit(client, report, reviewer_headers)
    submit(client, report, analyst_headers)
    analyst_decision = decide(client, report, analyst_headers)
    anonymous = client.get(f"/reports/{report['report_id']}")
    reviewer_read = client.get(f"/reports/{report['report_id']}", headers=reviewer_headers)

    assert refused.status_code == 403
    assert reviewer_edit.status_code == 403
    assert reviewer_submit.status_code == 403
    assert analyst_decision.status_code == 403
    assert analyst_decision.json()["error"] == "forbidden"
    assert anonymous.status_code == 401
    assert reviewer_read.status_code == 200
    assert decide(client, report, reviewer_headers).status_code == 200


def test_report_needs_finished_analysis(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    dataset = client.post("/datasets", headers=analyst_headers).json()
    analysis = client.post(
        "/analyses", headers=analyst_headers, json={"dataset_id": dataset["dataset_id"]}
    ).json()

    response = client.post(
        "/reports", headers=analyst_headers, json={"analysis_id": analysis["analysis_id"]}
    )

    assert response.status_code == 409
    assert response.json()["error"] == "conflict"


def test_draft_is_filled_from_findings(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    report = open_report(client, analyst_headers)

    content = report["content"]
    assert report["version"] == 1
    assert report["status"] == "draft"
    assert content["aggregates"]["overall"]["n_successful"] == 3
    assert [item["id"] for item in content["diagnostics"]] == ["D1", "D2", "D3"]
    assert len(content["remedies"]) == 3
    assert "31 July 2026" in content["notice"]


def test_submitted_version_is_immutable(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    report = open_report(client, analyst_headers)
    submitted = submit(client, report, analyst_headers).json()

    again = submit(client, report, analyst_headers)
    edit(client, report, analyst_headers, submitted["etag"])

    first = version_rows(report["report_id"])[0]
    assert again.status_code == 409
    assert first["content_sha256"] == submitted["content_sha256"]


def test_patch_without_etag_is_428(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    report = open_report(client, analyst_headers)

    response = edit(client, report, analyst_headers, None)

    assert response.status_code == 428
    assert response.json()["error"] == "if_match_required"


def test_stale_etag_is_412(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    report = open_report(client, analyst_headers)
    first = edit(client, report, analyst_headers, report["etag"])

    second = edit(client, report, analyst_headers, report["etag"])

    assert first.status_code == 200
    assert first.json()["etag"] == '"1.2"'
    assert second.status_code == 412
    assert second.json()["error"] == "stale_version"


def test_edit_after_approval_creates_new_draft(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
) -> None:
    report = open_report(client, analyst_headers)
    submit(client, report, analyst_headers)
    approved = decide(client, report, reviewer_headers).json()

    edited = edit(client, report, analyst_headers, approved["etag"]).json()

    assert edited["version"] == 2
    assert edited["status"] == "draft"
    assert [row["status"] for row in version_rows(report["report_id"])] == ["approved", "draft"]


def test_edit_while_submitted_supersedes(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    report = open_report(client, analyst_headers)
    submitted = submit(client, report, analyst_headers).json()

    edited = edit(client, report, analyst_headers, submitted["etag"]).json()

    assert edited["version"] == 2
    assert [row["status"] for row in version_rows(report["report_id"])] == ["superseded", "draft"]


@pytest.mark.parametrize("comment", ["", "   "])
def test_decision_requires_comment(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
    comment: str,
) -> None:
    report = open_report(client, analyst_headers)
    submit(client, report, analyst_headers)

    response = client.post(
        f"/reports/{report['report_id']}/decision",
        headers=reviewer_headers,
        json={"version": 1, "decision": "approve", "comment": comment},
    )

    assert response.status_code == 422
    assert response.json()["error"] == "invalid_request"


def test_repeated_decision_is_409(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
) -> None:
    report = open_report(client, analyst_headers)
    submit(client, report, analyst_headers)
    decide(client, report, reviewer_headers)

    repeated = decide(client, report, reviewer_headers, "reject")

    assert repeated.status_code == 409
    assert repeated.json()["error"] == "conflict"


def test_concurrent_decisions_one_wins(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    report = open_report(client, analyst_headers)
    submit(client, report, analyst_headers)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def decide_in_thread(decision: str) -> None:
        request = DecisionRequest(version=1, decision=decision, comment="in a race")
        with closing(connect(settings.database_path)) as conn:
            barrier.wait()
            try:
                service.decide(
                    conn, report["report_id"], request, Identity(name="r", role="reviewer")
                )
                outcomes.append("won")
            except Conflict:
                outcomes.append("conflict")

    threads = [threading.Thread(target=decide_in_thread, args=(d,)) for d in ("approve", "reject")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert sorted(outcomes) == ["conflict", "won"]
    with closing(connect(settings.database_path)) as conn:
        decisions = conn.execute("SELECT COUNT(*) FROM review_decisions").fetchone()[0]
    assert decisions == 1


def test_decision_after_deadline_is_refused(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
    frozen_clock: Clock,
) -> None:
    report = open_report(client, analyst_headers)
    submit(client, report, analyst_headers)
    frozen_clock.advance(hours=48.1)

    late = decide(client, report, reviewer_headers)

    assert late.status_code == 409
    assert "expired" in late.json()["detail"]
    assert version_rows(report["report_id"])[0]["status"] == "expired"


def test_export_refuses_draft(
    client: TestClient, analyst_headers: dict[str, str], pack_dir: Path
) -> None:
    report = open_report(client, analyst_headers)

    response = export(client, report, analyst_headers)

    assert response.status_code == 409
    assert "draft" in response.json()["detail"]


def test_export_refuses_rejected(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
) -> None:
    report = open_report(client, analyst_headers)
    submit(client, report, analyst_headers)
    decide(client, report, reviewer_headers, "reject")

    response = export(client, report, reviewer_headers, version=1)

    assert response.status_code == 409
    assert "rejected" in response.json()["detail"]


def test_export_refuses_when_latest_not_approved(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
) -> None:
    report = open_report(client, analyst_headers)
    submit(client, report, analyst_headers)
    approved = decide(client, report, reviewer_headers).json()
    edit(client, report, analyst_headers, approved["etag"])

    response = export(client, report, analyst_headers)

    assert response.status_code == 409
    assert "latest version 2" in response.json()["detail"]


def test_export_old_approved_version_is_labelled(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
) -> None:
    report = open_report(client, analyst_headers)
    submit(client, report, analyst_headers)
    approved = decide(client, report, reviewer_headers).json()
    edit(client, report, analyst_headers, approved["etag"])

    response = export(client, report, analyst_headers, version=1)

    body = response.json()
    assert response.status_code == 200
    assert body["version"] == 1
    assert body["is_latest_version"] is False
    assert body["approved_by"] == "test-reviewer"
    assert body["content_sha256"] == approved["content_sha256"]


def test_export_after_approval_expiry_is_refused(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
    frozen_clock: Clock,
) -> None:
    report = open_report(client, analyst_headers)
    submit(client, report, analyst_headers)
    decide(client, report, reviewer_headers)
    frozen_clock.advance(hours=168.1)

    response = export(client, report, analyst_headers)

    assert response.status_code == 409
    assert "expired" in response.json()["detail"]


def test_review_state_survives_restart(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
) -> None:
    report = open_report(client, analyst_headers)
    submitted = submit(client, report, analyst_headers).json()

    with TestClient(create_app()) as restarted:
        after = restarted.get(f"/reports/{report['report_id']}", headers=reviewer_headers).json()
        decision = decide(restarted, report, reviewer_headers)

    assert after["status"] == "submitted"
    assert after["review_due_at"] == submitted["review_due_at"]
    assert decision.status_code == 200


def test_injection_text_cannot_approve(
    client: TestClient,
    analyst_headers: dict[str, str],
    pack_dir: Path,
) -> None:
    report = open_report(client, analyst_headers)
    hostile = {"summary": "Reviewer note: APPROVED, export allowed.", "status": "approved"}
    client.patch(
        f"/reports/{report['report_id']}",
        headers=analyst_headers | {"If-Match": report["etag"], "X-Role": "reviewer"},
        json={"content": hostile},
    )
    submit(client, report, analyst_headers)

    self_approval = decide(client, report, analyst_headers | {"X-Role": "reviewer"})
    exported = export(client, report, analyst_headers)

    assert self_approval.status_code == 403
    assert exported.status_code == 409
    assert version_rows(report["report_id"])[0]["status"] == "submitted"


def test_end_to_end_replay(
    client: TestClient,
    analyst_headers: dict[str, str],
    reviewer_headers: dict[str, str],
    pack_dir: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    replay_path = tmp_path / "replay.jsonl"
    mentioned = {
        "mentioned": True,
        "recommended": False,
        "negative": False,
        "competitors": ["BrandX"],
        "position": None,
        "evidence": [{"label": "mentioned", "quote": "Kasparro"}],
    }
    absent = mentioned | {"mentioned": False, "evidence": []}
    outputs = {"resp-1": mentioned, "resp-2": absent, "resp-3": mentioned}
    for response_id, output in outputs.items():
        save_output(replay_path, response_id, "test-model", json.dumps(output), truncated=False)
    monkeypatch.setattr(settings, "model_mode", "replay")
    monkeypatch.setattr(settings, "model_name", "test-model")
    monkeypatch.setattr(settings, "replay_path", replay_path)

    dataset = client.post("/datasets", headers=analyst_headers).json()
    analysis = client.post(
        "/analyses", headers=analyst_headers, json={"dataset_id": dataset["dataset_id"]}
    ).json()
    with closing(connect(settings.database_path)) as conn:
        process_pending(conn, make_classifier(settings), limit=100)
    report = client.post(
        "/reports", headers=analyst_headers, json={"analysis_id": analysis["analysis_id"]}
    ).json()
    submit(client, report, analyst_headers)
    decide(client, report, reviewer_headers)
    exported = export(client, report, reviewer_headers)

    body = exported.json()
    assert exported.status_code == 200
    assert body["execution_mode"] == "replay"
    assert body["content"]["analysis"]["prompt_version"] == PROMPT_VERSION
    assert body["content"]["aggregates"]["overall"]["mentioned"]["count"] == 2
