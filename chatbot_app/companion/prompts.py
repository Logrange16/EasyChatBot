"""Public fallback persona and private, local-only overrides."""

import os
from pathlib import Path

from chatbot_app.shared.configuration import load_environment
from chatbot_app.shared.paths import PROJECT_ROOT

DEFAULT_SYSTEM_PROMPT = """
你是一位友善、耐心、尊重用户的聊天伙伴。
使用自然的中文交流，认真倾听，根据话题提供陪伴或实用建议。
尊重用户的个人边界，不编造事实，也不假装拥有现实中的经历。
""".strip()
MAX_PERSONA_LENGTH = 20000


def get_companion_prompt(custom_prompt: str = "") -> str:
    """Use a request override, then a private UTF-8 file, then the public default."""
    if not isinstance(custom_prompt, str):
        raise ValueError("Companion persona must be text.")
    if custom_prompt.strip():
        if len(custom_prompt) > MAX_PERSONA_LENGTH:
            raise ValueError("Companion persona is too long.")
        return custom_prompt.strip()
    load_environment()
    configured = os.getenv("COMPANION_PROMPT_FILE", "").strip()
    path = Path(configured) if configured else Path("data/companion_prompt.md")
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists() and not configured:
        return DEFAULT_SYSTEM_PROMPT
    # Explicit configuration errors should not silently change the persona.
    prompt = path.read_text(encoding="utf-8-sig").strip()
    if not prompt or len(prompt) > MAX_PERSONA_LENGTH:
        raise ValueError("The local companion persona must contain 1 to 20000 characters.")
    return prompt
