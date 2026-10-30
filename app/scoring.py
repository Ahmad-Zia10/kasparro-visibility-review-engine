from dataclasses import dataclass

SCORING_VERSION = "scoring_v1"
WEIGHTS = {"included": 25, "recommended": 40, "position": 20, "kasparro_cited": 15}
NEGATIVE_PENALTY = 30


@dataclass(frozen=True)
class Labels:
    mentioned: bool
    recommended: bool
    negative: bool
    position: int | None
    kasparro_cited: bool


@dataclass(frozen=True)
class Score:
    total: float
    components: dict[str, float | None]
    used: list[str]


def score(labels: Labels) -> Score:
    """Score one response from 0 to 100 under scoring_v1."""
    components = {
        "included": float(labels.mentioned),
        "recommended": float(labels.recommended),
        "position": None if labels.position is None else 1 / labels.position,
        "kasparro_cited": float(labels.kasparro_cited),
        "negative": float(labels.negative),
    }
    used = [name for name in WEIGHTS if components[name] is not None]
    # A null component's weight is shared out so the positive parts still reach 100.
    used_weight = sum(WEIGHTS[name] for name in used)
    positive = sum(WEIGHTS[name] * components[name] for name in used) * 100 / used_weight
    total = positive - NEGATIVE_PENALTY * components["negative"]
    return Score(total=min(max(total, 0), 100), components=components, used=[*used, "negative"])
