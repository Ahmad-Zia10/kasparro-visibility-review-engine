from dataclasses import asdict, dataclass
from typing import Literal

from app.citations import is_kasparro_url
from app.classify.base import ModelCall
from app.scoring import Labels, score


@dataclass(frozen=True)
class ResultRow:
    status: Literal["done", "failed"]
    labels: dict | None
    score: dict | None
    evidence: list[dict]
    error: str | None


def build_result(call: ModelCall, answer_text: str, citation_urls: list[str]) -> ResultRow:
    """Turn one classifier call and the response's citations into a stored result."""
    if call.classification is None:
        # R27: a failure keeps its reason and gets no score, never a zero.
        return ResultRow(status="failed", labels=None, score=None, evidence=[], error=call.error)
    found = call.classification
    labels = Labels(
        mentioned=found.mentioned,
        recommended=found.recommended,
        negative=found.negative,
        position=found.position,
        kasparro_cited=any(is_kasparro_url(url) for url in citation_urls),
    )
    evidence = []
    for item in found.evidence:
        span = find_span(answer_text, item.quote)
        start, end = span if span else (None, None)
        evidence.append({"label": item.label, "quote": item.quote, "start": start, "end": end})
    return ResultRow(
        status="done",
        labels=asdict(labels) | {"competitors": clean_competitors(found.competitors)},
        score=asdict(score(labels)),
        evidence=evidence,
        error=None,
    )


def clean_competitors(names: list[str]) -> list[str]:
    """Drop Kasparro itself; the model sometimes lists the brand as its own competitor."""
    return [name for name in names if not name.lower().startswith("kasparro")]


def find_span(answer_text: str, quote: str) -> tuple[int, int] | None:
    """Character offsets of the quote in the answer, or None if not found exactly."""
    start = answer_text.find(quote)
    if start == -1:
        return None
    return start, start + len(quote)
