from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

from app.logging_config import get_logger
from app.tracing.secrets import mask_secrets

logger = get_logger(__name__)


def ensure_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        logger.exception("tracing: failed to create directory %s", path)


def _atomic_write(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(path.parent),
        prefix=".tmp_",
        suffix=path.suffix or ".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(text)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_json(path: Path, data: Any) -> None:
    """
    Serialize data as pretty JSON, masking anything that looks like a
    credential first. Never raises — a tracing bug must never break or
    alter the real agent/tool call it is observing.
    """
    try:
        masked = mask_secrets(data)
        text = json.dumps(masked, default=str, ensure_ascii=False, indent=2)
        _atomic_write(path, text)
    except Exception:
        logger.exception("tracing: failed to write JSON trace file %s", path)


def write_text(path: Path, text: str) -> None:
    try:
        _atomic_write(path, text if text is not None else "")
    except Exception:
        logger.exception("tracing: failed to write text trace file %s", path)


def append_log_line(path: Path, line: str) -> None:
    try:
        ensure_dir(path.parent)
        with path.open("a", encoding="utf-8") as file:
            file.write(line.rstrip("\n") + "\n")
    except Exception:
        logger.exception("tracing: failed to append to execution log %s", path)


def append_jsonl(path: Path, obj: Any) -> None:
    """Append one masked JSON object as a single line — the event_stream.jsonl
    writer. Same never-raises contract as the rest of this module."""
    try:
        masked = mask_secrets(obj)
        line = json.dumps(masked, default=str, ensure_ascii=False)
        ensure_dir(path.parent)
        with path.open("a", encoding="utf-8") as file:
            file.write(line + "\n")
    except Exception:
        logger.exception("tracing: failed to append JSONL entry to %s", path)
