from app.findings import aggregate, build_diagnostics, build_remedies

CATEGORIES = {
    "p1": {"category": "comparison", "branded": True},
    "p2": {"category": "tool_discovery", "branded": False},
}


def result(
    response_id: str, prompt_id: str, engine: str, status: str = "done", **labels: object
) -> dict:
    found = {
        "mentioned": False,
        "recommended": False,
        "negative": False,
        "kasparro_cited": False,
        "competitors": ["BrandX"],
    } | labels
    evidence = [
        {"label": label, "quote": f"{label} quote {response_id}"}
        for label in ("mentioned", "recommended", "negative")
        if found[label]
    ]
    return {
        "response_id": response_id,
        "prompt_id": prompt_id,
        "engine": engine,
        "status": status,
        "labels": found if status == "done" else None,
        "score": {"total": 50.0} if status == "done" else None,
        "evidence": evidence if status == "done" else [],
    }


ROWS = [
    result("r1", "p1", "chatgpt", mentioned=True, recommended=True),
    result("r2", "p1", "gemini", mentioned=True, negative=True),
    result("r3", "p1", "aimode", status="failed"),
    result("r4", "p2", "chatgpt"),
    result("r5", "p2", "gemini"),
    result("r6", "p2", "aimode", status="skipped"),
]


def test_aggregates_report_denominators() -> None:
    aggregates = aggregate(ROWS, CATEGORIES)

    overall = aggregates["overall"]
    branded = aggregates["by_question_type"]["branded"]
    assert (overall["n_eligible"], overall["n_successful"]) == (5, 4)
    assert (overall["n_failed"], overall["n_skipped"]) == (1, 1)
    assert overall["mentioned"] == {"count": 2, "rate": 0.5}
    assert branded["mentioned"] == {"count": 2, "rate": 1.0}
    assert aggregates["by_engine"]["aimode"]["mentioned"]["rate"] is None
    assert aggregates["same_prompt"]["n_compared"] == 0


def test_diagnostic_cites_existing_response_ids() -> None:
    aggregates = aggregate(ROWS, CATEGORIES)

    diagnostics = build_diagnostics(aggregates, ROWS, CATEGORIES)

    known = {row["response_id"] for row in ROWS}
    assert [item["id"] for item in diagnostics] == ["D1", "D2", "D3"]
    for diagnostic in diagnostics:
        assert diagnostic["evidence"]
        assert {item["response_id"] for item in diagnostic["evidence"]} <= known
    assert diagnostics[2]["evidence"] == [
        {"response_id": "r2", "engine": "gemini", "excerpt": "negative quote r2"}
    ]


def test_remedy_has_all_required_fields() -> None:
    diagnostics = build_diagnostics(aggregate(ROWS, CATEGORIES), ROWS, CATEGORIES)

    remedies = build_remedies(diagnostics)

    required = {
        "priority",
        "diagnostic",
        "problem",
        "evidence",
        "action",
        "expected_benefit",
        "effort",
        "uncertainty",
        "validation",
    }
    assert [remedy["priority"] for remedy in remedies] == [1, 2, 3]
    for remedy in remedies:
        assert set(remedy) == required
        assert all(remedy[field] not in ("", None) for field in required - {"evidence"})
        assert "rank" not in remedy["expected_benefit"].lower()
