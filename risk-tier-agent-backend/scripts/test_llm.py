from __future__ import annotations

from app.config import get_settings
from app.services.llm_service import test_litellm_connection


def main() -> None:
    settings = get_settings()
    print(f"Testing model: {settings.llm_model}")
    print(test_litellm_connection())


if __name__ == "__main__":
    main()
