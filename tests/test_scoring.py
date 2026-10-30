import ast
from pathlib import Path

import pytest

from app import scoring
from app.scoring import Labels, score


def labels(**changes: object) -> Labels:
    base = {
        "mentioned": True,
        "recommended": True,
        "negative": False,
        "position": 2,
        "kasparro_cited": True,
    }
    return Labels(**(base | changes))


def test_score_components_and_weights() -> None:
    result = score(labels())

    assert result.components == {
        "included": 1.0,
        "recommended": 1.0,
        "position": 0.5,
        "kasparro_cited": 1.0,
        "negative": 0.0,
    }
    assert result.total == pytest.approx(25 + 40 + 20 * 0.5 + 15)
    assert result.used == ["included", "recommended", "position", "kasparro_cited", "negative"]


def test_null_position_redistributes_weight() -> None:
    result = score(labels(position=None, kasparro_cited=False))

    assert result.components["position"] is None
    assert "position" not in result.used
    assert result.total == pytest.approx((25 + 40) * 100 / 80)


def test_mention_only_is_not_recommendation() -> None:
    result = score(labels(recommended=False, position=None, kasparro_cited=False))

    assert result.total == pytest.approx(25 * 100 / 80)


def test_negative_penalty_clamps_at_zero() -> None:
    result = score(labels(recommended=False, negative=True, position=10, kasparro_cited=False))

    assert result.components["negative"] == 1.0
    assert result.total == 0


def test_absent_scores_zero() -> None:
    result = score(labels(mentioned=False, recommended=False, position=None, kasparro_cited=False))

    assert result.total == 0


def test_scoring_has_no_model_dependency() -> None:
    tree = ast.parse(Path(scoring.__file__).read_text(encoding="utf-8"))

    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }

    assert not any(name and name.startswith("app") for name in imported)
