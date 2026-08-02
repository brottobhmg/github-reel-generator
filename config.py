"""Centralized application configuration.

All settings are loaded from environment variables (via a ``.env`` file) so that
no secrets or infrastructure endpoints are hardcoded in the source code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load variables from the local `.env` file (gitignored) if present.
load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent


def _get_bool(name: str, default: bool = False) -> bool:
    """Parse an environment variable as a boolean."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Immutable application settings."""

    # ── LLM providers ────────────────────────────────────────
    nvidia_nim_api_key: str = field(
        default_factory=lambda: os.getenv("NVIDIA_NIM_API_KEY", "")
    )
    groq_api_key: str = field(
        default_factory=lambda: os.getenv("GROQ_API_KEY", "")
    )
    openrouter_api_key: str = field(
        default_factory=lambda: os.getenv("OPENROUTER_API_KEY", "")
    )

    # ── Telegram ─────────────────────────────────────────────
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", "")
    )

    # ── Backend API ──────────────────────────────────────────
    api_url: str = field(
        default_factory=lambda: os.getenv("API_URL", "http://localhost:8000")
    )
    poll_interval: int = field(
        default_factory=lambda: int(os.getenv("POLL_INTERVAL", "30"))
    )

    # ── Pipeline ─────────────────────────────────────────────
    load_delay: float = field(
        default_factory=lambda: float(os.getenv("LOAD_DELAY", "8.0"))
    )

    # ── Paths ────────────────────────────────────────────────
    output_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT / "output"
    )
    videos_dir: Path = field(
        default_factory=lambda: PROJECT_ROOT / "videos"
    )
    repos_file: Path = field(
        default_factory=lambda: PROJECT_ROOT / "repos"
    )

    # ── Debug ────────────────────────────────────────────────
    debug: bool = field(
        default_factory=lambda: _get_bool("DEBUG", False)
    )

    # ── LLM model lists ──────────────────────────────────────
    nim_models: tuple[str, ...] = (
        "nvidia/nemotron-3-super-120b-a12b",
        "openai/gpt-oss-120b",
        "stepfun/step-3.5-flash",
    )
    openrouter_models: tuple[str, ...] = (
        "nvidia/nemotron-3-super-120b-a12b:free",
        "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
        "nvidia/nemotron-3-ultra-550b-a55b:free",
    )
    nim_timeout: float = 40.0
    openrouter_timeout: float = 40.0

    @property
    def has_llm_keys(self) -> bool:
        """True if at least one LLM provider key is configured."""
        return bool(
            self.nvidia_nim_api_key
            or self.groq_api_key
            or self.openrouter_api_key
        )


settings = Settings()
