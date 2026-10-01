from __future__ import annotations

import logging
import sys
from typing import Any

from app.observability.context import get_trace_context


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("risk_tier")

    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(message)s",
        datefmt="%H:%M:%S",
    )

    handler.setFormatter(formatter)

    logger.addHandler(handler)
    logger.propagate = False

    return logger


LOGGER = _build_logger()


def get_logger() -> logging.Logger:
    return LOGGER


def log_event(
    event: str,
    *,
    agent: str | None = None,
    test_case_id: str | None = None,
    rule_id: str | None = None,
    **fields: Any,
) -> None:
    trace(
        event,
        agent=agent,
        test_case_id=test_case_id,
        rule_id=rule_id,
        **fields,
    )


def trace(
    event: str,
    *,
    agent: str | None = None,
    test_case_id: str | None = None,
    rule_id: str | None = None,
    **fields: Any,
) -> None:

    context = get_trace_context()

    parts: list[str] = []

    if context:
        parts.append(f"trace={context.trace_id}")
        parts.append(f"pipeline={context.pipeline_id}")
        parts.append(f"release={context.release_id}")

    if agent:
        parts.append(f"agent={agent}")

    if test_case_id:
        parts.append(f"test={test_case_id}")

    if rule_id:
        parts.append(f"rule={rule_id}")

    for key, value in fields.items():
        if value is not None:
            parts.append(f"{key}={value}")

    suffix = " | ".join(parts)

    LOGGER.info(
        "[%s] %s",
        event,
        suffix,
    )


def trace_error(
    event: str,
    *,
    agent: str | None = None,
    error: Exception,
    **fields: Any,
) -> None:

    context = get_trace_context()

    parts = []

    if context:
        parts.append(f"trace={context.trace_id}")
        parts.append(f"pipeline={context.pipeline_id}")
        parts.append(f"release={context.release_id}")

    if agent:
        parts.append(f"agent={agent}")

    parts.append(f"error={type(error).__name__}")
    parts.append(f"message={error}")

    for key, value in fields.items():
        parts.append(f"{key}={value}")

    LOGGER.error(
        "[%s] %s",
        event,
        " | ".join(parts),
    )