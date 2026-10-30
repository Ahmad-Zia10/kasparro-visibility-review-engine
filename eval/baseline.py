"""Keyword baseline: labels from word lists, for comparison with the model."""

import re

RECOMMEND_WORDS = ("recommend", "worth", "good choice", "legitimate", "best", "strong")
NEGATIVE_WORDS = (
    "not widely",
    "no evidence",
    "couldn't find",
    "can't independently",
    "not publicly",
    "overpriced",
    "harder to justify",
    "skeptical",
    "lack of",
    "unproven",
)


def keyword_labels(text: str) -> dict:
    """Mentioned if the name appears; the other labels look only at sentences naming Kasparro."""
    sentences = [s.lower() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if "kasparro" in s.lower()]
    mentioned = bool(sentences)
    return {
        "mentioned": mentioned,
        "recommended": any(word in s for s in sentences for word in RECOMMEND_WORDS),
        "negative": any(word in s for s in sentences for word in NEGATIVE_WORDS),
        "position": None,
    }
