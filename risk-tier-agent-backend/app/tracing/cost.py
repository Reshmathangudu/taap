from __future__ import annotations

from app.logging_config import get_logger

logger = get_logger(__name__)


def estimate_cost_usd(
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
) -> float | None:
    """
    Best-effort USD cost estimate for one LLM call, via LiteLLM's own
    pricing table (litellm is already a dependency of this app — see
    app/services/llm_service.py — so this adds no new import cost).

    Returns None whenever a real number isn't available: no model/token
    counts, an unrecognized model, or any other lookup failure — cost is
    "if available" (requirement 6), never estimated by guesswork, and
    this must never raise into the real LLM call it's observing.
    """
    if not model or prompt_tokens is None or completion_tokens is None:
        return None

    try:
        import litellm

        prompt_cost, completion_cost = litellm.cost_per_token(
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
        return float(prompt_cost) + float(completion_cost)
    except Exception:
        logger.debug("tracing: cost estimation unavailable for model %s", model, exc_info=True)
        return None
