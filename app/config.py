"""Configuration loaded from environment variables."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _get_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


class Settings:
    def __init__(self) -> None:
        # --- AI provider ---
        self.openai_api_key: str = (
            os.getenv("GROQ_API_KEY", "").strip()
            or os.getenv("OPENAI_API_KEY", "").strip()
        )
        self.openai_base_url: str = os.getenv(
            "OPENAI_BASE_URL", "https://api.openai.com/v1"
        ).rstrip("/")
        self.openai_model: str = os.getenv(
            "OPENAI_MODEL", "openai/gpt-oss-120b"
        ).strip()
        self.openai_timeout: float = float(os.getenv("OPENAI_TIMEOUT", "60"))

        # --- Firebase Auth ---
        # Path can be absolute or relative to project root.
        self.firebase_credentials_path: str = os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS", ""
        ).strip()

        # --- DB ---
        default_db = BASE_DIR / "not.db"
        self.db_path: str = os.getenv("DB_PATH", str(default_db))

        # --- Limits ---
        self.max_message_chars: int = _get_int("MAX_MESSAGE_CHARS", 8000)
        self.max_history_messages: int = _get_int("MAX_HISTORY_MESSAGES", 40)
        self.max_conversation_messages: int = _get_int("MAX_CONVERSATION_MESSAGES", 500)

        # --- Rate limiting ---
        self.rate_limit_requests: int = _get_int("RATE_LIMIT_REQUESTS", 30)
        self.rate_limit_window: int = _get_int("RATE_LIMIT_WINDOW", 60)

        # --- CORS ---
        cors_raw = os.getenv("CORS_ORIGINS", "*").strip()
        self.cors_origins: list[str] = (
            ["*"] if cors_raw == "*" else [o.strip() for o in cors_raw.split(",") if o.strip()]
        )

        # --- Optional legacy shared token (kept for backwards-compat) ---
        self.access_token: str = os.getenv("ACCESS_TOKEN", "").strip()

        # --- System prompt ---
        self.system_prompt: str = os.getenv(
            "SYSTEM_PROMPT",
            (
                "You are NOT, a helpful, intelligent, friendly AI assistant. "
                "Communicate naturally, understand context, answer accurately, and assist "
                "with programming, learning, research, and everyday tasks. Support English, "
                "Urdu, Roman Urdu, and other languages when possible. Respond in the user's "
                "preferred language. Never claim to have performed an action that you did "
                "not actually perform."
            ),
        )

    @property
    def api_key_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def auth_configured(self) -> bool:
        return bool(self.firebase_credentials_path)


@lru_cache
def get_settings() -> Settings:
    return Settings()