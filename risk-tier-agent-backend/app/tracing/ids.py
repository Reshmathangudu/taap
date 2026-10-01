from __future__ import annotations

import hashlib
import re
from uuid import uuid4

_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9_.-]+")


def safe_name(name: str) -> str:
    """Sanitize a string for use as a single filesystem path segment."""
    cleaned = _UNSAFE_CHARS.sub("_", str(name or "").strip())
    return cleaned or "unknown"


def short_dir_token(value: str, max_len: int = 16) -> str:
    """
    A short, collision-resistant directory-name form of an identifier that
    may be much longer than this project's own tracing ids — notably
    ADK's own invocation_id ('e-<uuid4>', 38 chars), used as-is for the
    tracing run_id on the conversational path. A deeply nested logs/ tree
    under a long OneDrive-synced project path can then exceed Windows'
    260-char MAX_PATH. Used ONLY for the directory segment: the real
    run_id/invocation_id value is unchanged everywhere else (JSON content,
    dict keys, event stream), so lookups by the full id are unaffected.
    """
    cleaned = safe_name(value)
    if len(cleaned) <= max_len:
        return cleaned
    digest = hashlib.sha1(cleaned.encode("utf-8")).hexdigest()[:10]
    return f"R-{digest}"


def new_run_id() -> str:
    return f"RUN-{uuid4().hex[:10].upper()}"


def new_trace_id() -> str:
    """
    One trace_id per causal chain, not per run: a pipeline run triggered
    from within an ADK conversational turn inherits that turn's trace_id
    (see tracer.get_active_run/_register_run) rather than minting a fresh
    one, so the whole chain — routing decision plus the pipeline it
    triggered — shares one identifier end to end.
    """
    return f"TRACE-{uuid4().hex[:10].upper()}"


def new_agent_run_id(agent_name: str) -> str:
    return f"{safe_name(agent_name)}-{uuid4().hex[:8].upper()}"
