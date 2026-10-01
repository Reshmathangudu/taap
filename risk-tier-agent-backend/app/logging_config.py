from __future__ import annotations

import logging
import sys


def _configure(logger: logging.Logger) -> logging.Logger:
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
    )

    logger.addHandler(handler)
    logger.propagate = False

    return logger


def get_logger(name: str) -> logging.Logger:
    """
    Return a configured per-module logger.

    Callers typically do `logger = get_logger(__name__)` and then use the
    standard logging.Logger API, including `extra={...}` for structured
    fields (e.g. logger.info("message", extra={"release_id": ...})).
    """
    return _configure(logging.getLogger(name))
