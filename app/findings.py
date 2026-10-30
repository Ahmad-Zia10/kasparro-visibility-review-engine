"""Deterministic findings over stored results: aggregates, diagnostics and remedies."""

from collections import defaultdict
from statistics import mean

MAX_EXAMPLES = 5
SNAPSHOT_NOTE = (
    "Archived answers captured on 31 July 2026 (India, English). "
    "A historical snapshot, not a current ranking."
)


def aggregate(rows: list[dict], categories: dict[str, dict]) -> dict:
    """Group results overall, by engine, by category and by branded question."""
    groups: dict[str, dict[str, list[dict]]] = {
        "by_engine": defaultdict(list),
        "by_category": defaultdict(list),
        "by_question_type": defaultdict(list),
    }
    for row in rows:
        category = categories.get(row["prompt_id"], {})
        groups["by_engine"][row["engine"]].append(row)
        groups["by_category"][category.get("category", "uncategorised")].append(row)
        branded = "branded" if category.get("branded") else "unbranded"
        groups["by_question_type"][branded].append(row)
    return {
        "overall": summarise(rows),
        **{
            name: {key: summarise(members) for key, members in sorted(grouped.items())}
            for name, grouped in groups.items()
        },
        "same_prompt": compare_engines(rows),
    }


def summarise(rows: list[dict]) -> dict:
    """Counts with their denominators; rates are over successful results only."""
    done = [row for row in rows if row["status"] == "done"]
    summary = {
        "n_eligible": sum(row["status"] != "skipped" for row in rows),
        "n_successful": len(done),
        "n_failed": sum(row["status"] == "failed" for row in rows),
        "n_skipped": sum(row["status"] == "skipped" for row in rows),
    }
    for label in ("mentioned", "recommended", "negative", "kasparro_cited"):
        count = sum(bool(row["labels"][label]) for row in done)
        summary[label] = {"count": count, "rate": rate(count, len(done))}
    scores = [row["score"]["total"] for row in done]
    summary["mean_score"] = round(mean(scores), 1) if scores else None
    return summary


def rate(count: int, total: int) -> float | None:
    return round(count / total, 3) if total else None


def compare_engines(rows: list[dict]) -> dict:
    """Prompts where every engine answered successfully, and where they disagree on mention."""
    by_prompt: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        by_prompt[row["prompt_id"]].append(row)
    complete = {
        prompt_id: members
        for prompt_id, members in by_prompt.items()
        if len(members) == 3 and all(row["status"] == "done" for row in members)
    }
    disagree = sorted(
        prompt_id
        for prompt_id, members in complete.items()
        if len({row["labels"]["mentioned"] for row in members}) > 1
    )
    return {
        "n_prompts": len(by_prompt),
        "n_compared": len(complete),
        "n_mention_disagreement": len(disagree),
        "examples": disagree[:MAX_EXAMPLES],
    }


def build_diagnostics(
    aggregates: dict, rows: list[dict], categories: dict[str, dict]
) -> list[dict]:
    done = [row for row in rows if row["status"] == "done"]
    return [
        branded_gap(aggregates, done, categories),
        engine_gap(aggregates, done),
        negative_framing(aggregates, done),
    ]


def branded_gap(aggregates: dict, done: list[dict], categories: dict[str, dict]) -> dict:
    types = aggregates["by_question_type"]
    branded, unbranded = types.get("branded"), types.get("unbranded")
    absent = [
        row
        for row in done
        if not categories.get(row["prompt_id"], {}).get("branded")
        and not row["labels"]["mentioned"]
    ]
    return {
        "id": "D1",
        "title": "Kasparro appears when the question names it, rarely otherwise",
        "pattern": (
            f"Mentioned in {count_text(branded, 'mentioned')} successful answers to branded "
            f"questions and {count_text(unbranded, 'mentioned')} to unbranded ones."
        ),
        "possible_explanation": (
            "Engines may not associate Kasparro with the AI-visibility category, so it is only "
            "surfaced when the user already knows the name. Not tested here."
        ),
        "test_evidence": (
            "Unbranded answers that list other tools without Kasparro; compare against the "
            "competitor names they give."
        ),
        "evidence": [
            {
                "response_id": row["response_id"],
                "engine": row["engine"],
                "excerpt": "competitors named: " + ", ".join(row["labels"]["competitors"][:4]),
            }
            for row in absent
            if row["labels"]["competitors"]
        ][:MAX_EXAMPLES],
    }


def engine_gap(aggregates: dict, done: list[dict]) -> dict:
    engines = aggregates["by_engine"]
    ranked = sorted(
        (name for name in engines if engines[name]["recommended"]["rate"] is not None),
        key=lambda name: engines[name]["recommended"]["rate"],
    )
    low, high = (ranked[0], ranked[-1]) if ranked else (None, None)
    examples = [
        row
        for row in done
        if row["engine"] == low and row["labels"]["mentioned"] and not row["labels"]["recommended"]
    ]
    return {
        "id": "D2",
        "title": "Engines differ in whether a mention becomes a recommendation",
        "pattern": (
            f"Recommendation rate is lowest on {low} "
            f"({count_text(engines.get(low), 'recommended')}) and highest on {high} "
            f"({count_text(engines.get(high), 'recommended')})."
        ),
        "possible_explanation": (
            "Engines draw on different sources; one may find less third-party material that "
            "supports recommending Kasparro. Not tested here."
        ),
        "test_evidence": f"Answers on {low} that mention Kasparro without recommending it.",
        "evidence": [quote_of(row, "mentioned") for row in examples][:MAX_EXAMPLES],
    }


def negative_framing(aggregates: dict, done: list[dict]) -> dict:
    overall = aggregates["overall"]
    negative = [row for row in done if row["labels"]["negative"]]
    return {
        "id": "D3",
        "title": "Some answers frame Kasparro as unproven or hard to verify",
        "pattern": (
            f"{overall['negative']['count']} of {overall['mentioned']['count']} answers that "
            "mention Kasparro also say something unfavourable."
        ),
        "possible_explanation": (
            "Answers may lack independent reviews or case studies to cite. A citation only shows "
            "a link was returned; the pages were not inspected."
        ),
        "test_evidence": "Quoted unfavourable passages, one per answer.",
        "evidence": [quote_of(row, "negative") for row in negative][:MAX_EXAMPLES],
    }


def count_text(summary: dict | None, label: str) -> str:
    if not summary:
        return "0/0"
    return f"{summary[label]['count']}/{summary['n_successful']}"


def quote_of(row: dict, label: str) -> dict:
    quote = next((item["quote"] for item in row["evidence"] if item["label"] == label), None)
    return {"response_id": row["response_id"], "engine": row["engine"], "excerpt": quote}


def build_remedies(diagnostics: list[dict]) -> list[dict]:
    """Three remedies, in priority order, each tied to a diagnostic. None promises a ranking."""
    d1, d2, d3 = diagnostics
    return [
        {
            "priority": 1,
            "diagnostic": d1["id"],
            "problem": d1["pattern"],
            "evidence": [item["response_id"] for item in d1["evidence"]],
            "action": (
                "Investigate which sources the unbranded answers draw on, and whether Kasparro is "
                "listed in the comparison pages and directories those sources come from."
            ),
            "expected_benefit": "Shows whether category association is the gap.",
            "effort": "low: one analyst day reading cited pages",
            "uncertainty": "High. Engines change; presence in sources may not lead to inclusion.",
            "validation": "Rerun the 25 unbranded prompts after a change and compare mentions.",
        },
        {
            "priority": 2,
            "diagnostic": d3["id"],
            "problem": d3["pattern"],
            "evidence": [item["response_id"] for item in d3["evidence"]],
            "action": (
                "Publish verifiable proof that answers can cite: named case studies, method "
                "documentation and independent reviews, only where they are true."
            ),
            "expected_benefit": "Gives engines something to cite instead of a lack of evidence.",
            "effort": "medium: depends on customer permission for case studies",
            "uncertainty": "Medium. Engines may not pick up new pages, or may weigh them lightly.",
            "validation": "Track the negative count on the branded prompts across repeated runs.",
        },
        {
            "priority": 3,
            "diagnostic": d2["id"],
            "problem": d2["pattern"],
            "evidence": [item["response_id"] for item in d2["evidence"]],
            "action": (
                "Compare the citations of the lowest-recommending engine with the others to see "
                "which source types it relies on; decide only after that comparison."
            ),
            "expected_benefit": "Targets effort at the engine where the gap is largest.",
            "effort": "low: uses citations already captured",
            "uncertainty": "High. Based on one snapshot and a small local model's labels.",
            "validation": "Repeat the run on a later snapshot and check whether the gap persists.",
        },
    ]
