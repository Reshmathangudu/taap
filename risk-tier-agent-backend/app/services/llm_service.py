from __future__ import annotations
 
from functools import lru_cache
from typing import Any
 
from google.adk.models.lite_llm import LiteLlm
from litellm import completion
 
from app.config import get_settings
from app.utils.retry import retry, RetryException
 
 
@lru_cache(maxsize=1)
def get_adk_litellm_model() -> LiteLlm:
    """
    Create the LiteLLM-backed model used by every Google ADK agent.
 
    Google ADK remains the agent framework.
    LiteLLM translates ADK model calls to the selected provider.
    """
 
    settings = get_settings()
    api_key = settings.require_openai_key()
 
    return LiteLlm(
        model=settings.llm_model,
        api_key=api_key,
    )
 
 
@retry(
    max_attempts=3,
    initial_delay=2,
    backoff=2,
    max_delay=20,
)
def _completion_with_retry(
    model: str,
    api_key: str,
    prompt: str,
    timeout: int,
) -> Any:
    """
    Internal LiteLLM completion with retry support.
    Retries transient API/network failures automatically.
    """
 
    return completion(
        model=model,
        api_key=api_key,
        messages=[
            {
                "role": "user",
                "content": prompt,
            }
        ],
        timeout=timeout,
    )
 
 
def test_litellm_connection(
    prompt: str = "Reply with exactly: LiteLLM connection successful",
) -> str:
    """
    Verify LiteLLM/OpenAI connectivity.
 
    Uses automatic retry before failing.
    """
 
    settings = get_settings()
    api_key = settings.require_openai_key()
 
    try:
 
        response: Any = _completion_with_retry(
            model=settings.llm_model,
            api_key=api_key,
            prompt=prompt,
            timeout=settings.llm_timeout_seconds,
        )
 
        content = response.choices[0].message.content
 
        if not content:
            raise RuntimeError("LiteLLM returned an empty response.")
 
        return str(content).strip()
 
    except RetryException as ex:
        raise RuntimeError(
            "Unable to connect to LiteLLM/OpenAI after multiple retry attempts."
        ) from ex