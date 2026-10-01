from __future__ import annotations

from functools import lru_cache
from pathlib import Path


PROMPTS_DIRECTORY = Path(__file__).resolve().parent


@lru_cache(maxsize=None)
def load_prompt(file_name: str) -> str:
    path = PROMPTS_DIRECTORY / file_name
    if not path.exists():
        raise FileNotFoundError(f"Prompt file was not found: {path}")
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Prompt file is empty: {path}")
    return prompt
