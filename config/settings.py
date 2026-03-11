"""Application settings loaded from environment variables / .env file."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Telegram ──────────────────────────────────────────────────────────────
    telegram_bot_token: str = "CHANGE_ME"

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key: str = "CHANGE_ME"
    openai_model: str = "gpt-4o"
    openai_temperature: float = 0.3

    # ── MetaTrader 5 ──────────────────────────────────────────────────────────
    mt5_path: Optional[str] = None
    mt5_login: Optional[int] = None
    mt5_password: Optional[str] = None
    mt5_server: Optional[str] = None

    # ── Risk management ───────────────────────────────────────────────────────
    default_risk_pct: float = 1.0
    max_risk_pct: float = 3.0
    max_positions: int = 5
    magic_number: int = 234000

    # ── Application ───────────────────────────────────────────────────────────
    log_level: str = "INFO"
    journal_dir: str = "data/journal"

    # ── Access control ────────────────────────────────────────────────────────
    # Stored as a comma-separated string in the env file; parsed to a set of ints.
    allowed_user_ids: str = ""

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(f"log_level must be one of {allowed}")
        return upper

    @property
    def allowed_user_id_set(self) -> set[int]:
        """Return a set of allowed Telegram user IDs (empty = allow all)."""
        if not self.allowed_user_ids.strip():
            return set()
        return {int(uid.strip()) for uid in self.allowed_user_ids.split(",") if uid.strip()}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings singleton."""
    return Settings()
