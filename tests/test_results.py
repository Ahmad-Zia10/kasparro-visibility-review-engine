from app.analyses.results import build_result, find_span
from app.classify.base import AnswerToClassify
from app.classify.stub import StubClassifier

ANSWER = AnswerToClassify(
    response_id="resp-1",
    question="best tools?",
    text="Options include Kasparro and BrandX.\nKasparro is a good pick for audits.",
)

RECOMMENDED = """{
  "mentioned": true, "recommended": true, "negative": false,
  "competitors": ["BrandX"], "position": null,
  "evidence": [
    {"label": "mentioned", "quote": "Options include Kasparro"},
    {"label": "recommended", "quote": "Kasparro is a good pick"}
  ]
}"""


def test_result_holds_labels_score_and_evidence() -> None:
    call = StubClassifier({"resp-1": RECOMMENDED}).classify(ANSWER)

    result = build_result(call, ANSWER.text, ["https://www.kasparro.com/"])

    assert result.status == "done"
    assert result.labels["kasparro_cited"] is True
    assert result.labels["competitors"] == ["BrandX"]
    assert result.score is not None
    assert result.score["total"] == 100
    assert result.evidence[1] == {
        "label": "recommended",
        "quote": "Kasparro is a good pick",
        "start": 37,
        "end": 60,
    }


def test_failed_result_has_no_score() -> None:
    call = StubClassifier({"resp-1": "{not json"}).classify(ANSWER)

    result = build_result(call, ANSWER.text, ["https://kasparro.com/"])

    assert result.status == "failed"
    assert result.score is None
    assert result.labels is None
    assert result.error


def test_evidence_span_points_at_quote() -> None:
    span = find_span(ANSWER.text, "Kasparro is a good pick")

    assert span == (37, 60)
    assert ANSWER.text[37:60] == "Kasparro is a good pick"


def test_evidence_span_is_null_when_spacing_differs() -> None:
    assert find_span("Options  include Kasparro", "Options include Kasparro") is None


def test_kasparro_is_not_listed_as_its_own_competitor() -> None:
    output = RECOMMENDED.replace('["BrandX"]', '["BrandX", "Kasparro"]')
    call = StubClassifier({"resp-1": output}).classify(ANSWER)

    result = build_result(call, ANSWER.text, [])

    assert result.labels["competitors"] == ["BrandX"]
