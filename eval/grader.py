"""Deterministic grading: label agreement, score arithmetic and diagnostic evidence."""

LABELS = ("mentioned", "recommended", "negative")


def label_metrics(pairs: list[tuple[dict, dict | None]]) -> dict:
    """Per-label precision, recall and agreement; a None prediction is a failure, not a guess."""
    graded = [(expected, predicted) for expected, predicted in pairs if predicted is not None]
    metrics = {"n_cases": len(pairs), "n_graded": len(graded), "n_failed": len(pairs) - len(graded)}
    for label in (*LABELS, "position"):
        metrics[label] = compare(graded, label)
    return metrics


def compare(graded: list[tuple[dict, dict]], label: str) -> dict:
    agree = sum(expected[label] == predicted[label] for expected, predicted in graded)
    result = {"agreement": ratio(agree, len(graded))}
    if label == "position":
        return result
    true_pos = sum(bool(e[label]) and bool(p[label]) for e, p in graded)
    false_pos = sum(not e[label] and bool(p[label]) for e, p in graded)
    false_neg = sum(bool(e[label]) and not p[label] for e, p in graded)
    result["precision"] = ratio(true_pos, true_pos + false_pos)
    result["recall"] = ratio(true_pos, true_pos + false_neg)
    result["counts"] = {"tp": true_pos, "fp": false_pos, "fn": false_neg}
    return result


def ratio(part: int, whole: int) -> float | None:
    return round(part / whole, 3) if whole else None


def expected_score(labels: dict) -> float:
    """scoring_v1 written out again by hand, so a bug in app/scoring.py shows up."""
    parts = {
        "included": (25, float(labels["mentioned"])),
        "recommended": (40, float(labels["recommended"])),
        "kasparro_cited": (15, float(labels["kasparro_cited"])),
    }
    if labels["position"] is not None:
        parts["position"] = (20, 1 / labels["position"])
    weight = sum(w for w, _ in parts.values())
    positive = sum(w * v for w, v in parts.values()) * 100 / weight
    return min(max(positive - 30 * labels["negative"], 0), 100)


def check_scores(results: list[dict]) -> list[str]:
    """Response IDs whose stored score differs from the hand-written formula."""
    return [
        row["response_id"]
        for row in results
        if row["score"] is not None
        and abs(row["score"]["total"] - expected_score(row["labels"])) > 0.01
    ]


def check_claims(diagnostics: list[dict], evidence_by_id: dict[str, list[dict]]) -> list[str]:
    """Diagnostic evidence problems: unknown response IDs, or excerpts not stored."""
    problems = []
    for diagnostic in diagnostics:
        if not diagnostic["evidence"]:
            problems.append(f"{diagnostic['id']}: no evidence")
        for item in diagnostic["evidence"]:
            stored = evidence_by_id.get(item["response_id"])
            if stored is None:
                problems.append(f"{diagnostic['id']}: unknown response {item['response_id']}")
            elif (item["excerpt"] or "").startswith("competitors named:"):
                continue
            elif item["excerpt"] not in {quote["quote"] for quote in stored}:
                problems.append(
                    f"{diagnostic['id']}: excerpt not in evidence of {item['response_id']}"
                )
    return problems
