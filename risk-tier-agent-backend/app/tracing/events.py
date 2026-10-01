"""
The chronological event-stream vocabulary, written by tracer.record_event()
to each run's event_stream.jsonl. Plain string constants only (no logic
here) so both app/tracing/tracer.py and any caller can import them without
a circular dependency.
"""

from __future__ import annotations

RUN_STARTED = "RUN_STARTED"
RUN_FINISHED = "RUN_FINISHED"
RUN_ERROR = "RUN_ERROR"

AGENT_STARTED = "AGENT_STARTED"
AGENT_PROGRESS = "AGENT_PROGRESS"
AGENT_FINISHED = "AGENT_FINISHED"
AGENT_FAILED = "AGENT_FAILED"

TOOL_STARTED = "TOOL_STARTED"
TOOL_FINISHED = "TOOL_FINISHED"
TOOL_FAILED = "TOOL_FAILED"

LLM_REQUEST = "LLM_REQUEST"
LLM_RESPONSE = "LLM_RESPONSE"

A2A_REQUEST = "A2A_REQUEST"
A2A_RESPONSE = "A2A_RESPONSE"

CACHE_HIT = "CACHE_HIT"
CACHE_MISS = "CACHE_MISS"

ALL_EVENT_TYPES = frozenset(
    {
        RUN_STARTED, RUN_FINISHED, RUN_ERROR,
        AGENT_STARTED, AGENT_PROGRESS, AGENT_FINISHED, AGENT_FAILED,
        TOOL_STARTED, TOOL_FINISHED, TOOL_FAILED,
        LLM_REQUEST, LLM_RESPONSE,
        A2A_REQUEST, A2A_RESPONSE,
        CACHE_HIT, CACHE_MISS,
    }
)
