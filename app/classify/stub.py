import json

from app.classify.base import AnswerToClassify, ModelCall, judge_output

NOT_MENTIONED = json.dumps(
    {
        "mentioned": False,
        "recommended": False,
        "negative": False,
        "competitors": [],
        "position": None,
        "evidence": [],
    }
)


class StubClassifier:
    """Canned outputs per response ID, for tests and keyless runs."""

    def __init__(
        self, outputs: dict[str, str] | None = None, timeouts: set[str] | None = None
    ) -> None:
        self.outputs = outputs or {}
        self.timeouts = timeouts or set()

    def classify(self, answer: AnswerToClassify) -> ModelCall:
        if answer.response_id in self.timeouts:
            return ModelCall(
                execution_mode="stub",
                model=None,
                outcome="timeout",
                classification=None,
                error="stub timeout",
                raw_output=None,
            )
        output = self.outputs.get(answer.response_id, NOT_MENTIONED)
        outcome, classification, error = judge_output(output, answer)
        return ModelCall(
            execution_mode="stub",
            model=None,
            outcome=outcome,
            classification=classification,
            error=error,
            raw_output=output,
        )
