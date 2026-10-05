"""Local configuration and path guards for the Trends CLI."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

SERVICE_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = SERVICE_ROOT / "output"
PLACEHOLDER_VALUES = {"", "replace_with_authorized_key", "changeme", "your_api_key"}


class ConfigurationError(ValueError):
    """Raised before network access when local configuration is unsafe."""


@dataclass(frozen=True)
class Settings:
    youtube_api_key: str
    ollama_host: str
    http_timeout_seconds: float
    google_retries: int
    google_backoff_seconds: float


def _positive_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be a number") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def _positive_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


def _local_ollama_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ConfigurationError("OLLAMA_HOST must be a loopback http:// URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError("OLLAMA_HOST must not include credentials, query, or fragment")
    return value.rstrip("/")


def get_settings(require_youtube_key: bool = True) -> Settings:
    load_dotenv(SERVICE_ROOT / ".env")
    key = os.getenv("YOUTUBE_API_KEY", "").strip()
    if require_youtube_key and key.lower() in PLACEHOLDER_VALUES:
        raise ConfigurationError("YOUTUBE_API_KEY must be set to an authorized non-placeholder value")
    return Settings(
        youtube_api_key=key,
        ollama_host=_local_ollama_url(os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434").strip()),
        http_timeout_seconds=_positive_float("TRENDS_HTTP_TIMEOUT_SECONDS", 30),
        google_retries=_positive_int("TRENDS_GOOGLE_RETRIES", 3),
        google_backoff_seconds=_positive_float("TRENDS_GOOGLE_BACKOFF_SECONDS", 5),
    )


def output_path(filename: str) -> Path:
    candidate = (OUTPUT_DIR / filename).resolve()
    if OUTPUT_DIR.resolve() not in candidate.parents:
        raise ValueError("output path escapes service output directory")
    return candidate
