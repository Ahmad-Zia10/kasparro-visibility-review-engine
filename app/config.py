from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Identity(BaseModel):
    name: str
    role: Literal["analyst", "reviewer"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    analyst_name: str
    # Minimum length stops an empty token from matching a missing header.
    analyst_token: str = Field(min_length=16)
    reviewer_name: str
    reviewer_token: str = Field(min_length=16)
    database_path: Path = Path("kasparro.db")

    def identities(self) -> dict[str, Identity]:
        """Map each configured token to the identity it grants."""
        return {
            self.analyst_token: Identity(name=self.analyst_name, role="analyst"),
            self.reviewer_token: Identity(name=self.reviewer_name, role="reviewer"),
        }


settings = Settings()
