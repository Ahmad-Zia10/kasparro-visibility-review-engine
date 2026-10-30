import json
from pathlib import Path

from app.classify.base import PROMPT_VERSION, AnswerToClassify, ModelCall, judge_output


def save_output(path: Path, response_id: str, model: str, output: str, truncated: bool) -> None:
    """Append one received model output so a later run can replay it offline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    line = {
        "response_id": response_id,
        "prompt_version": PROMPT_VERSION,
        "model": model,
        "output": output,
        "truncated": truncated,
    }
    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(line, ensure_ascii=False) + "\n")


def load_outputs(path: Path) -> dict[tuple[str, str], dict]:
    if not path.exists():
        return {}
    saved = {}
    with path.open(encoding="utf-8") as file:
        for line in file:
            if line.strip():
                record = json.loads(line)
                # Later lines win, so a rerun replaces an earlier output.
                saved[record["response_id"], record["prompt_version"]] = record
    return saved


class ReplayClassifier:
    def __init__(self, path: Path) -> None:
        self.saved = load_outputs(path)

    def classify(self, answer: AnswerToClassify) -> ModelCall:
        record = self.saved.get((answer.response_id, PROMPT_VERSION))
        if record is None:
            return ModelCall(
                execution_mode="replay",
                model=None,
                outcome="missing_replay",
                classification=None,
                error=f"no saved output for {answer.response_id} and {PROMPT_VERSION}",
                raw_output=None,
            )
        if record["truncated"]:
            outcome, classification, error = "truncated", None, "output hit the token limit"
        else:
            outcome, classification, error = judge_output(record["output"], answer)
        return ModelCall(
            execution_mode="replay",
            model=record["model"],
            outcome=outcome,
            classification=classification,
            error=error,
            raw_output=record["output"],
        )
