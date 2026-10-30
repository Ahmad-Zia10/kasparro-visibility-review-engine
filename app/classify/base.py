from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

PROMPT_VERSION = "classify_v1"
PROMPT_PATH = Path(__file__).parent / "prompts" / f"{PROMPT_VERSION}.md"
PROMPT_TEXT = PROMPT_PATH.read_text(encoding="utf-8")

ExecutionMode = Literal["local-model", "replay", "stub"]
Outcome = Literal[
    "ok", "invalid_output", "empty", "timeout", "model_error", "truncated", "missing_replay"
]
Label = Literal["mentioned", "recommended", "negative"]


class Evidence(BaseModel):
    label: Label
    quote: str = Field(min_length=1)


class Classification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mentioned: bool
    recommended: bool
    negative: bool
    competitors: list[str]
    position: int | None = Field(ge=1)
    evidence: list[Evidence]

    @model_validator(mode="after")
    def labels_agree(self) -> "Classification":
        if not self.mentioned and (self.recommended or self.negative or self.position is not None):
            raise ValueError("recommended, negative and position require mentioned")
        labelled = {item.label for item in self.evidence}
        missing = [
            label
            for label in ("mentioned", "recommended", "negative")
            if getattr(self, label) and label not in labelled
        ]
        if missing:
            raise ValueError(f"no evidence for {', '.join(missing)}")
        return self


OUTPUT_SCHEMA = Classification.model_json_schema()


@dataclass(frozen=True)
class AnswerToClassify:
    response_id: str
    question: str
    text: str


@dataclass(frozen=True)
class ModelCall:
    """One classification attempt, kept whether or not it succeeded."""

    execution_mode: ExecutionMode
    model: str | None
    outcome: Outcome
    classification: Classification | None
    error: str | None
    raw_output: str | None
    latency_ms: int = 0
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    prompt_version: str = PROMPT_VERSION


class Classifier(Protocol):
    def classify(self, answer: AnswerToClassify) -> ModelCall: ...


def fence(tag: str, text: str) -> str:
    """Wrap text in a tag, defusing any copy of the closing tag inside it."""
    closing = f"</{tag}>"
    defused = text.replace(closing, "<\\/" + tag + ">")
    return f"<{tag}>\n{defused}\n{closing}"


def build_messages(answer: AnswerToClassify) -> list[dict[str, str]]:
    user = f"{fence('question', answer.question)}\n\n{fence('answer', answer.text)}"
    return [{"role": "system", "content": PROMPT_TEXT}, {"role": "user", "content": user}]


def judge_output(
    output: str, answer: AnswerToClassify
) -> tuple[Outcome, Classification | None, str | None]:
    """Turn raw model text into a classification, or say why it is unusable."""
    if not output.strip():
        return "empty", None, "model returned no text"
    try:
        classification = Classification.model_validate_json(output)
    except ValidationError as error:
        return "invalid_output", None, first_error(error)
    answer_words = " ".join(answer.text.split())
    for item in classification.evidence:
        if " ".join(item.quote.split()) not in answer_words:
            return "invalid_output", None, f"{item.label} quote not found in answer"
    return "ok", classification, None


def first_error(error: ValidationError) -> str:
    problem = error.errors()[0]
    where = ".".join(str(part) for part in problem["loc"])
    return f"{where}: {problem['msg']}" if where else problem["msg"]
