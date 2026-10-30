from fastapi.testclient import TestClient


def test_analyst_token_is_accepted(client: TestClient, analyst_headers: dict[str, str]) -> None:
    response = client.get("/test/analyst-only", headers=analyst_headers)

    assert response.status_code == 200
    assert response.json() == {"name": "test-analyst"}


def test_missing_token_is_401(client: TestClient) -> None:
    response = client.get("/test/analyst-only")

    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


def test_unknown_token_is_401(client: TestClient) -> None:
    response = client.get(
        "/test/analyst-only", headers={"Authorization": "Bearer not-a-real-token"}
    )

    assert response.status_code == 401
    assert response.json()["error"] == "unauthenticated"


def test_wrong_role_is_403(
    client: TestClient, analyst_headers: dict[str, str], reviewer_headers: dict[str, str]
) -> None:
    as_reviewer = client.get("/test/analyst-only", headers=reviewer_headers)
    as_analyst = client.get("/test/reviewer-only", headers=analyst_headers)

    assert as_reviewer.status_code == 403
    assert as_reviewer.json()["error"] == "forbidden"
    assert as_analyst.status_code == 403
    assert as_analyst.json()["error"] == "forbidden"


def test_role_header_is_ignored(client: TestClient, reviewer_headers: dict[str, str]) -> None:
    headers = {**reviewer_headers, "X-Role": "analyst", "X-Actor": "test-analyst"}

    response = client.get("/test/analyst-only", headers=headers)

    assert response.status_code == 403
    assert response.json()["error"] == "forbidden"


def test_error_body_shape(client: TestClient) -> None:
    response = client.get("/test/analyst-only")

    assert response.status_code == 401
    assert response.json() == {
        "error": "unauthenticated",
        "detail": "missing or unknown bearer token",
    }


def test_validation_error_body_shape(client: TestClient) -> None:
    response = client.get("/test/numbers/not-a-number")

    body = response.json()
    assert response.status_code == 422
    assert set(body) == {"error", "detail"}
    assert body["error"] == "invalid_request"
    assert "number" in body["detail"]
