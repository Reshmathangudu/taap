from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from app.observability.context import trace_fields


AUDIT_DIR = Path("data/output/audit")
AUDIT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)

_AUDIT_LOCK = Lock()


def _safe_release_filename(
    release_id: str,
) -> str:
    return (
        str(release_id or "UNKNOWN")
        .strip()
        .upper()
        .replace("/", "_")
        .replace("\\", "_")
        .replace(":", "_")
    )


def audit_event(
    event: str,
    *,
    agent: str,
    message: str,
    release_id: str | None = None,
    test_case_id: str | None = None,
    rule_id: str | None = None,
    decision: str | None = None,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:

    trace = trace_fields()

    # Prefer the caller's own release_id over the ContextVar-based
    # TraceContext. TraceContext is only ever populated by the FastAPI
    # trace_requests middleware from the request's path params / an
    # X-Release-ID header — neither exists for the AG-UI /agui/run
    # endpoint's request, and even if it did, contextvars do not cross the
    # OS thread boundary that RiskTierPipelineAgent's run_in_executor
    # introduces. Every specialist tool already has the real release_id as
    # a plain function argument; passing it through here is what actually
    # makes every pipeline run's audit trail land under the right file
    # instead of a shared UNKNOWN_audit.jsonl.
    resolved_release_id = str(
        release_id or trace.get("release_id") or "UNKNOWN"
    )

    record = {
        "timestamp": datetime.now(
            timezone.utc
        ).isoformat(),
        "event": event,
        "agent": agent,
        "message": message,
        **trace,
        # Override whatever (possibly empty) release_id trace_fields()
        # supplied — the caller-supplied/resolved one is authoritative.
        "release_id": resolved_release_id,
    }

    if test_case_id:
        record["test_case_id"] = test_case_id

    if rule_id:
        record["rule_id"] = rule_id

    if decision:
        record["decision"] = decision

    if details:
        record["details"] = details

    path = AUDIT_DIR / (
        f"{_safe_release_filename(resolved_release_id)}_audit.jsonl"
    )

    serialized = json.dumps(
        record,
        ensure_ascii=False,
        default=str,
    )

    with _AUDIT_LOCK:
        # AUDIT_DIR.mkdir() at module import time only ever runs once per
        # process. If the directory is deleted later (e.g. a manual cache
        # cleanup) while this process keeps running, every subsequent
        # write would fail with FileNotFoundError until the process
        # restarts. Recreating it here, right before every write, makes
        # audit logging self-healing instead of depending on process
        # lifetime matching the directory's.
        AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        with path.open(
            "a",
            encoding="utf-8",
        ) as file:
            file.write(serialized + "\n")

    return record