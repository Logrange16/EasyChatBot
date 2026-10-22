"""Load model settings; TypedDict describes types, while this loader sets defaults."""

import os

from dotenv import load_dotenv
from typing_extensions import TypedDict

from .paths import PROJECT_ROOT


class ModelConfiguration(TypedDict):
    model: str
    api_key: str
    base_url: str


def load_environment() -> None:
    """Load the project .env without overriding existing environment variables."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)


def load_model_configuration() -> ModelConfiguration:
    load_environment()
    api_key = os.getenv("QWEN_API_KEY", "").strip()
    if not api_key:
        raise ValueError("QWEN_API_KEY is missing. Add it to .env or your environment.")
    return {
        "model": os.getenv("QWEN_MODEL", "").strip() or "qwen3.7-flash",
        "api_key": api_key,
        "base_url": os.getenv("QWEN_BASE_URL", "").strip()
        or "https://maas.qianwenaiapi.com/compatible-mode/v1",
    }
