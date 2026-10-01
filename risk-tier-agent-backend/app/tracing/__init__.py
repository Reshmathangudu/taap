"""
End-to-end execution tracing and observability.

Writes a full, file-based trace tree under settings.logs_dir for every
run — pipeline or conversational — so a run can be reconstructed after the
fact from logs alone: run/trace identifiers threaded through the whole
call chain, exactly what input each agent received, the real system
prompt/request/response exchanged with the LLM (when one was involved),
every tool call's real input/response/docstring, every agent-to-agent
message, cache hits/misses, real token usage (including cached/reasoning
tokens and an estimated cost when available), a chronological event
stream, and a final per-run summary.

This is a strict superset of app.observability's stdout/audit-JSONL
logging, not a replacement for it — that package stays as the lightweight,
always-on structured-event layer; this package is the detailed,
file-per-run/agent/tool layer built on top of the same integration points
(app/observability/agent_logging.py's ADK callbacks,
app/tracing/adk_plugin.py's whole-invocation hooks, and
RiskTierMasterOrchestrator._run_stage for the deterministic pipeline path).

Every public function here is best-effort: a tracing failure is logged and
swallowed, never raised, so it can never break or alter the real agent/tool
call it is observing.
"""

from app.tracing import events
from app.tracing.secrets import mask_secrets
from app.tracing.tracer import (
    AgentTrace,
    RunTrace,
    abandon_open_agent_traces,
    finish_agent_trace,
    finish_run,
    get_active_run,
    get_or_create_run,
    peek_run_totals,
    record_a2a,
    record_agent_progress,
    record_cache_event,
    record_event,
    record_llm_context,
    record_llm_request,
    record_llm_response,
    record_model_name,
    record_system_prompt,
    record_token_usage,
    record_tool_call,
    record_tool_started,
    start_agent_trace,
    start_run,
)

__all__ = [
    "AgentTrace",
    "RunTrace",
    "events",
    "mask_secrets",
    "start_run",
    "get_or_create_run",
    "get_active_run",
    "peek_run_totals",
    "start_agent_trace",
    "record_model_name",
    "record_system_prompt",
    "record_llm_context",
    "record_llm_request",
    "record_llm_response",
    "record_token_usage",
    "record_tool_call",
    "record_tool_started",
    "record_agent_progress",
    "record_a2a",
    "record_cache_event",
    "record_event",
    "finish_agent_trace",
    "abandon_open_agent_traces",
    "finish_run",
]
