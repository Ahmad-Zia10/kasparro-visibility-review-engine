from eval.grader import check_claims, check_scores, expected_score, label_metrics


def labels(**values: object) -> dict:
    return {"mentioned": False, "recommended": False, "negative": False, "position": None} | values


def test_grader_precision_recall_on_known_input() -> None:
    pairs = [
        (labels(mentioned=True), labels(mentioned=True)),
        (labels(mentioned=True), labels()),
        (labels(), labels(mentioned=True)),
        (labels(), labels()),
        (labels(mentioned=True), None),
    ]

    metrics = label_metrics(pairs)

    assert (metrics["n_cases"], metrics["n_graded"], metrics["n_failed"]) == (5, 4, 1)
    assert metrics["mentioned"]["precision"] == 0.5
    assert metrics["mentioned"]["recall"] == 0.5
    assert metrics["mentioned"]["agreement"] == 0.5


def test_unsupported_claim_is_flagged() -> None:
    evidence = {"r1": [{"label": "negative", "quote": "few public reviews"}]}
    diagnostics = [
        {"id": "D1", "evidence": [{"response_id": "r1", "excerpt": "few public reviews"}]},
        {"id": "D2", "evidence": [{"response_id": "r1", "excerpt": "Kasparro doubled revenue"}]},
        {"id": "D3", "evidence": [{"response_id": "r9", "excerpt": "anything"}]},
    ]

    problems = check_claims(diagnostics, evidence)

    assert problems == [
        "D2: excerpt not in evidence of r1",
        "D3: unknown response r9",
    ]


def test_score_arithmetic_check_catches_error() -> None:
    found = labels(mentioned=True, recommended=True, kasparro_cited=False)
    right = {"response_id": "r1", "labels": found, "score": {"total": expected_score(found)}}
    wrong = {"response_id": "r2", "labels": found, "score": {"total": 99.0}}

    assert expected_score(found) == 81.25
    assert check_scores([right, wrong]) == ["r2"]
