from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass
from uuid import uuid4


@dataclass
class TraceContext:
    trace_id: str
    pipeline_id: str
    release_id: str


_CURRENT_TRACE: ContextVar[TraceContext | None] = ContextVar(
    "risk_tier_trace",
    default=None,
)


def create_trace_context(release_id: str) -> TraceContext:
    release = str(release_id or "").strip().upper()

    return TraceContext(
        trace_id=f"TRACE-{uuid4().hex[:8].upper()}",
        pipeline_id=f"PIPE-{release}-{uuid4().hex[:6].upper()}",
        release_id=release,
    )


def set_trace_context(context: TraceContext):
    return _CURRENT_TRACE.set(context)


def get_trace_context() -> TraceContext | None:
    return _CURRENT_TRACE.get()


def reset_trace_context(token) -> None:
    _CURRENT_TRACE.reset(token)

def trace_fields() -> dict[str, str]:
    context = get_trace_context()

    if context is None:
        return {}

    return {
        "trace_id": context.trace_id,
        "pipeline_id": context.pipeline_id,
        "release_id": context.release_id,
    }