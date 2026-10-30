from app.classify.base import Classifier
from app.classify.local import LocalClassifier
from app.classify.replay import ReplayClassifier
from app.classify.stub import StubClassifier
from app.config import Settings


def make_classifier(settings: Settings) -> Classifier:
    """Pick the classifier named by MODEL_MODE."""
    if settings.model_mode == "local":
        return LocalClassifier(
            url=settings.ollama_url,
            model=settings.model_name,
            timeout_seconds=settings.model_timeout_seconds,
            max_output_tokens=settings.model_max_output_tokens,
            replay_path=settings.replay_path,
        )
    if settings.model_mode == "replay":
        return ReplayClassifier(settings.replay_path)
    return StubClassifier()
