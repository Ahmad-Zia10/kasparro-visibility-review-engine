from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Identity(BaseModel):
    name: str
    role: Literal["analyst", "reviewer"]


class Settings(BaseSettings):
    # Empty values in .env fall back to the defaults below.
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)

    analyst_name: str
    # Minimum length stops an empty token from matching a missing header.
    analyst_token: str = Field(min_length=16)
    reviewer_name: str
    reviewer_token: str = Field(min_length=16)
    database_path: Path = Path("kasparro.db")
    pack_dir: Path = Path("pack")
    model_mode: Literal["local", "replay", "stub"] = "replay"
    model_name: str = "qwen2.5:3b"
    ollama_url: str = "http://localhost:11434"
    model_timeout_seconds: float = Field(default=180, gt=0)
    model_max_output_tokens: int = Field(default=800, gt=0)
    model_max_attempts: int = Field(default=3, ge=1)
    replay_path: Path = Path("eval/results/replay_cache/classify_v1.jsonl")

    def identities(self) -> dict[str, Identity]:
        """Map each configured token to the identity it grants."""
        return {
            self.analyst_token: Identity(name=self.analyst_name, role="analyst"),
            self.reviewer_token: Identity(name=self.reviewer_name, role="reviewer"),
        }


settings = Settings()
