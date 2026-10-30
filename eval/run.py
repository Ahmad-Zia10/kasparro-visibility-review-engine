"""Rerun the evaluation and write eval/results/report.md and report.json.

python -m eval.run           grade saved outputs (replay, no model needed)
python -m eval.run --local   classify cases with no saved output using Ollama first
"""

import json
import sys
from pathlib import Path

from app.analyses.results import build_result, clean_competitors
from app.classify.base import PROMPT_VERSION, AnswerToClassify
from app.classify.local import LocalClassifier
from app.classify.replay import ReplayClassifier, load_outputs
from app.config import settings
from app.findings import aggregate, build_diagnostics
from eval.baseline import keyword_labels
from eval.grader import check_claims, check_scores, label_metrics

CASES_DIR = Path("eval/cases")
RESULTS_DIR = Path("eval/results")
CASE_FILES = ("labels_v1.jsonl", "edge_cases.jsonl")


def load_cases() -> list[dict]:
    return [
        json.loads(line)
        for name in CASE_FILES
        for line in (CASES_DIR / name).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def load_pack() -> tuple[dict, dict, dict]:
    data = settings.pack_dir / "data"
    read = lambda name: [json.loads(line) for line in (data / name).open(encoding="utf-8")]  # noqa: E731
    prompts = {row["prompt_id"]: row["text"] for row in read("prompts.jsonl")}
    responses = {row["response_id"]: row for row in read("responses.jsonl")}
    citations: dict[str, list[str]] = {}
    for row in read("citations.jsonl"):
        citations.setdefault(row["response_id"], []).append(row["url"])
    return prompts, responses, citations


def answer_for(case: dict, prompts: dict, responses: dict) -> AnswerToClassify:
    response = responses.get(case["response_id"])
    if response is None:
        return AnswerToClassify(case["response_id"], "(synthetic edge case)", case["answer_text"])
    text = response["answer_markdown"] or response["answer_text"]
    return AnswerToClassify(case["response_id"], prompts[response["prompt_id"]], text)


def classify(answers: list[AnswerToClassify], use_local: bool) -> dict:
    saved = load_outputs(settings.replay_path)
    local = LocalClassifier(
        settings.ollama_url,
        settings.model_name,
        settings.model_timeout_seconds,
        settings.model_max_output_tokens,
        settings.replay_path,
    )
    calls = {}
    for answer in answers:
        if use_local and (answer.response_id, PROMPT_VERSION) not in saved:
            local.classify(answer)
    replay = ReplayClassifier(settings.replay_path)
    for answer in answers:
        calls[answer.response_id] = replay.classify(answer)
    return calls


def predicted_labels(call) -> dict | None:
    if call.classification is None:
        return None
    found = call.classification
    return {
        "mentioned": found.mentioned,
        "recommended": found.recommended,
        "negative": found.negative,
        "position": found.position,
    }


def build_report(cases: list[dict], use_local: bool) -> dict:
    prompts, responses, citations = load_pack()
    answers = {case["response_id"]: answer_for(case, prompts, responses) for case in cases}
    calls = classify(list(answers.values()), use_local)
    report = {"prompt_version": PROMPT_VERSION, "model": settings.model_name, "splits": {}}
    for split in ("tune", "final", "all"):
        chosen = [c for c in cases if split == "all" or c["split"] == split]
        report["splits"][split] = {
            "model": label_metrics(
                [(c, predicted_labels(calls[c["response_id"]])) for c in chosen]
            ),
            "baseline": label_metrics(
                [(c, keyword_labels(answers[c["response_id"]].text)) for c in chosen]
            ),
        }
    report["failures"] = {
        rid: call.error for rid, call in calls.items() if call.classification is None
    }
    results = []
    for case in cases:
        row = build_result(
            calls[case["response_id"]],
            answers[case["response_id"]].text,
            citations.get(case["response_id"], []),
        )
        results.append(
            {
                "response_id": case["response_id"],
                "prompt_id": case["prompt_id"] or "",
                "engine": case["engine"] or "synthetic",
                "status": row.status,
                "labels": row.labels,
                "score": row.score,
                "evidence": row.evidence,
            }
        )
    report["score_mismatches"] = check_scores(results)
    report["claim_problems"] = claim_check(results)
    report["competitor_fix"] = competitor_fix(calls)
    return report


def claim_check(results: list[dict]) -> dict:
    evidence = {row["response_id"]: row["evidence"] for row in results}
    diagnostics = build_diagnostics(aggregate(results, {}), results, {})
    unsupported = {
        "id": "X1",
        "evidence": [{"response_id": results[0]["response_id"], "excerpt": "an invented quote"}],
    }
    return {
        "real_diagnostics": check_claims(diagnostics, evidence),
        "planted_unsupported_claim": check_claims([unsupported], evidence),
    }


def competitor_fix(calls: dict) -> dict:
    raw = [c.classification.competitors for c in calls.values() if c.classification]
    return {
        "lists_naming_kasparro_before_fix": sum(
            any(name.lower().startswith("kasparro") for name in names) for names in raw
        ),
        "lists_naming_kasparro_after_fix": sum(
            any(name.lower().startswith("kasparro") for name in clean_competitors(names))
            for names in raw
        ),
    }


def write_markdown(report: dict, path: Path) -> None:
    claims = report["claim_problems"]
    lines = [
        "# Evaluation report",
        "",
        f"Prompt `{report['prompt_version']}`, model `{report['model']}`. "
        "Outputs are replayed from "
        "the saved local-model run, so this checks those outputs only; replay itself does not "
        "establish model quality.",
        "",
    ]
    for split, sides in report["splits"].items():
        model = sides["model"]
        lines += [
            f"## Split: {split}",
            "",
            f"Cases {model['n_cases']}, graded {model['n_graded']}, failed {model['n_failed']}, "
            "skipped 0.",
            "",
            "| Label | Model agreement | Model P / R | Baseline agreement | Baseline P / R |",
            "|---|---|---|---|---|",
        ]
        for label in ("mentioned", "recommended", "negative", "position"):
            m, b = model[label], sides["baseline"][label]
            lines.append(
                f"| {label} | {m['agreement']} | {m.get('precision')} / {m.get('recall')} "
                f"| {b['agreement']} | {b.get('precision')} / {b.get('recall')} |"
            )
        lines.append("")
    lines += [
        "## Checks",
        "",
        f"- Failed classifications: {report['failures'] or 'none'}",
        f"- Score arithmetic mismatches against the hand-written formula: "
        f"{report['score_mismatches'] or 'none'}",
        f"- Diagnostic evidence problems: {claims['real_diagnostics'] or 'none'}",
        f"- Planted unsupported claim flagged: {claims['planted_unsupported_claim']}",
        f"- Competitor lists naming Kasparro, before / after the fix: "
        f"{report['competitor_fix']['lists_naming_kasparro_before_fix']} / "
        f"{report['competitor_fix']['lists_naming_kasparro_after_fix']}",
        "- Repeat runs (R69): not run. One local call takes 60 to 140 seconds on this CPU.",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str]) -> None:
    report = build_report(load_cases(), use_local="--local" in argv)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_markdown(report, RESULTS_DIR / "report.md")


if __name__ == "__main__":
    main(sys.argv[1:])
