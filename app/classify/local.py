import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from app.classify.base import (
    OUTPUT_SCHEMA,
    AnswerToClassify,
    ModelCall,
    build_messages,
    judge_output,
)
from app.classify.replay import save_output


def post_json(url: str, body: dict, timeout: float) -> dict:
    request = urllib.request.Request(
        url, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=timeout) as reply:
        return json.load(reply)


class LocalClassifier:
    """Classifies with a model served by Ollama on this machine."""

    def __init__(
        self,
        url: str,
        model: str,
        timeout_seconds: float,
        max_output_tokens: int,
        replay_path: Path,
    ) -> None:
        self.url = url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.replay_path = replay_path

    def classify(self, answer: AnswerToClassify) -> ModelCall:
        body = {
            "model": self.model,
            "messages": build_messages(answer),
            "stream": False,
            "format": OUTPUT_SCHEMA,
            "options": {"temperature": 0, "num_predict": self.max_output_tokens},
        }
        started = time.monotonic()
        try:
            reply = post_json(f"{self.url}/api/chat", body, self.timeout_seconds)
        except (TimeoutError, urllib.error.URLError, ValueError) as error:
            return self.failed(error, started)

        output = reply.get("message", {}).get("content", "")
        truncated = reply.get("done_reason") == "length"
        save_output(self.replay_path, answer.response_id, self.model, output, truncated)
        if truncated:
            outcome, classification, error = "truncated", None, "output hit the token limit"
        else:
            outcome, classification, error = judge_output(output, answer)
        return ModelCall(
            execution_mode="local-model",
            model=self.model,
            outcome=outcome,
            classification=classification,
            error=error,
            raw_output=output,
            latency_ms=elapsed_ms(started),
            input_tokens=reply.get("prompt_eval_count"),
            output_tokens=reply.get("eval_count"),
        )

    def failed(self, error: Exception, started: float) -> ModelCall:
        # urlopen wraps a connect timeout in URLError, so check the reason too.
        reason = getattr(error, "reason", error)
        if isinstance(reason, TimeoutError):
            outcome, message = "timeout", f"no reply within {self.timeout_seconds}s"
        else:
            outcome, message = "model_error", f"ollama call failed: {reason}"
        return ModelCall(
            execution_mode="local-model",
            model=self.model,
            outcome=outcome,
            classification=None,
            error=message,
            raw_output=None,
            latency_ms=elapsed_ms(started),
        )


def elapsed_ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)
