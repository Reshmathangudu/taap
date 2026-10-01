from __future__ import annotations

import inspect
import json
import threading
import time
from typing import Any

from app import tracing
from app.observability.logger import log_event

# Keyed by (invocation_id, tool.name) — set in the before_tool_callback,
# popped in the matching after_tool_callback to log how long the tool took.
# ADK calls a given (invocation, tool) pair sequentially, never concurrently
# with itself, so this simple dict is safe without extra locking.
_tool_started_at: dict[tuple[str, str], float] = {}

# RiskTierPipelineAgent (app/agents/pipeline_stream_agent.py) is a plain
# BaseAgent that drives RiskTierMasterOrchestrator.execute() directly in a
# background thread — it makes no LLM call and no ADK tool call of its own.
# execute() does its own, more detailed tracing (see master_orchestrator.py's
# _run_stage), so tracing it again here would just produce a second, mostly
# empty logs/<release>/<run_id>/ tree for the same logical run. Skipped by name.
_SKIP_AGENT_TRACE_NAMES = {"risk_tier_pipeline"}

# Per (invocation_id, agent_name) -> AgentTrace, so the tool/model callbacks
# (which only ever receive a callback_context/tool_context, never a direct
# Python reference) can find the trace that log_before_agent_callback
# opened for this turn. Guarded by a lock since ADK's background pipeline
# path can run on a different thread than the main event loop.
_active_agent_traces: dict[tuple[str, str], tracing.AgentTrace] = {}
_active_agent_traces_lock = threading.Lock()


def _compact(value: Any, limit: int = 300) -> str:
    """Render a tool's args short enough for one terminal line.

    Some tool payloads (e.g. create_jira_issue's description, or a full
    release's cached blocks) can be tens of KB — this keeps the log line
    readable without hiding which tool ran or with roughly what shape of
    input it got.
    """
    try:
        text = json.dumps(value, default=str, ensure_ascii=False)
    except Exception:
        text = str(value)
    if len(text) > limit:
        text = text[:limit] + "…"
    return text


def _to_jsonable(obj: Any) -> Any:
    """Best-effort conversion of an ADK/google-genai pydantic object (Content,
    Part, GenerateContentConfig, ...) into plain JSON-safe data, for the
    detailed trace files (llm_context.json, system_prompt.txt). Falls back to
    str() for anything unexpected — never raises."""
    try:
        if obj is None or isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return {key: _to_jsonable(val) for key, val in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_to_jsonable(item) for item in obj]
        model_dump = getattr(obj, "model_dump", None)
        if callable(model_dump):
            try:
                return model_dump(exclude_none=True, mode="json")
            except Exception:
                return model_dump(exclude_none=True)
        return str(obj)
    except Exception:
        return str(obj)


def _extract_text_from_jsonable(value: Any) -> list[str]:
    """Pull every `parts[].text` out of a Content-shaped dict/list, if any."""
    texts: list[str] = []
    items = value if isinstance(value, list) else [value]
    for item in items:
        if not isinstance(item, dict):
            continue
        for part in item.get("parts") or []:
            if isinstance(part, dict) and part.get("text"):
                texts.append(part["text"])
    return texts


def _extract_system_prompt_text(system_instruction: Any) -> str:
    if system_instruction is None:
        return ""
    if isinstance(system_instruction, str):
        return system_instruction
    jsonable = _to_jsonable(system_instruction)
    texts = _extract_text_from_jsonable(jsonable)
    if texts:
        return "\n".join(texts)
    return json.dumps(jsonable, default=str, ensure_ascii=False, indent=2)


def _extract_response_output(llm_response: Any) -> Any:
    content = getattr(llm_response, "content", None)
    if content is None:
        return None
    jsonable = _to_jsonable(content)
    texts = _extract_text_from_jsonable(jsonable)
    if texts:
        return "\n".join(texts)
    return jsonable


def _resolve_tool_docstring(tool: Any) -> str:
    func = getattr(tool, "func", None)
    docstring = inspect.getdoc(func) if func is not None else None
    if docstring:
        return docstring
    return getattr(tool, "description", None) or ""


def _get_agent_trace(invocation_id: str, agent_name: str) -> tracing.AgentTrace | None:
    with _active_agent_traces_lock:
        return _active_agent_traces.get((invocation_id, agent_name))


def pop_active_agent_trace(invocation_id: str, agent_name: str) -> tracing.AgentTrace | None:
    """
    Public counterpart to _get_agent_trace, for app.tracing.adk_plugin's
    on_agent_error_callback: when an agent's turn ends via an unhandled
    exception, ADK never calls after_agent_callback (confirmed in
    google/adk/agents/base_agent.py), so log_after_agent_callback's own
    pop-and-close never runs — this lets the plugin close that specific
    agent's trace itself and remove the now-stale bookkeeping entry.
    """
    with _active_agent_traces_lock:
        return _active_agent_traces.pop((invocation_id, agent_name), None)


def discard_active_agent_traces_for_invocation(invocation_id: str) -> list[tracing.AgentTrace]:
    """
    Whole-invocation sweep for app.tracing.adk_plugin's after_run_callback/
    on_run_error_callback: removes every bookkeeping entry for this
    invocation_id regardless of which agent(s) it belongs to. Used
    alongside tracing.abandon_open_agent_traces(), which closes the actual
    AgentTrace objects on disk — this just stops this module's own
    _active_agent_traces dict from pointing at now-closed traces.
    """
    with _active_agent_traces_lock:
        keys = [key for key in _active_agent_traces if key[0] == invocation_id]
        return [_active_agent_traces.pop(key) for key in keys]


def log_before_agent_callback(callback_context: Any) -> None:
    """
    before_agent_callback: logs the moment ADK hands control to an agent —
    the root Master Orchestrator on turn start, or a specialist sub-agent
    right after the Master transfers to it. Also opens a detailed
    app.tracing AgentTrace for this agent's turn (input.json + the
    tool_calls/ tree), using the ADK invocation_id as the tracing run_id —
    it is stable across the whole turn, including any transfer_to_agent hop.

    Safe to combine with another before_agent_callback on the same agent by
    passing a list, e.g. before_agent_callback=[log_before_agent_callback,
    scope_guard_before_agent_callback] — returning None here never
    short-circuits the invocation, so callbacks after it in the list still
    run normally.
    """
    agent_name = callback_context.agent_name
    invocation_id = callback_context.invocation_id

    log_event(
        "AGENT_START",
        agent=agent_name,
        invocation=invocation_id,
    )

    if agent_name not in _SKIP_AGENT_TRACE_NAMES:
        try:
            state = dict(callback_context.state)
        except Exception:
            state = {}
        release_id = str(state.get("release_id") or "UNKNOWN")

        try:
            run = tracing.get_or_create_run(run_id=invocation_id, release_id=release_id, kind="query")
            agent_trace = tracing.start_agent_trace(run, agent_name=agent_name, input_data=state)
            with _active_agent_traces_lock:
                _active_agent_traces[(invocation_id, agent_name)] = agent_trace
        except Exception:
            pass

    return None


def log_after_agent_callback(callback_context: Any) -> None:
    """after_agent_callback: logs the moment an agent finishes its turn, and
    closes its app.tracing AgentTrace (output.json, token_usage.json)."""
    agent_name = callback_context.agent_name
    invocation_id = callback_context.invocation_id

    log_event(
        "AGENT_END",
        agent=agent_name,
        invocation=invocation_id,
    )

    with _active_agent_traces_lock:
        agent_trace = _active_agent_traces.pop((invocation_id, agent_name), None)
    if agent_trace is not None:
        try:
            tracing.finish_agent_trace(agent_trace, status="SUCCESS")
        except Exception:
            pass
        try:
            # Checkpoint, not close: ADK has no single "the whole
            # invocation is done" callback, so every agent-turn boundary
            # rewrites this run's run_summary.json with whatever has
            # accumulated so far. close=False keeps the run queryable via
            # tracing.peek_run_totals() afterward — e.g. the deterministic
            # pipeline path (master_orchestrator.py's execute()) reads this
            # run's totals when it was reached via stage_pipeline_run +
            # transfer_to_agent, to fold the real orchestration LLM call's
            # token usage into its own run_summary.json.
            tracing.finish_run(agent_trace.run, status="SUCCESS", close=False)
        except Exception:
            pass

    return None


def log_before_model_callback(callback_context: Any, llm_request: Any) -> None:
    """
    before_model_callback: captures the FINAL resolved system prompt and
    full message contents about to be sent to the LLM — after all of ADK's
    own instruction-building/context-injection, not the agent's static
    instruction= field. Never mutates llm_request and always returns None,
    so the real model call is never altered or skipped.
    """
    agent_trace = _get_agent_trace(callback_context.invocation_id, callback_context.agent_name)
    if agent_trace is None:
        return None

    try:
        config = getattr(llm_request, "config", None)
        system_instruction = getattr(config, "system_instruction", None) if config is not None else None
        model = getattr(llm_request, "model", None)
        contents = _to_jsonable(getattr(llm_request, "contents", None))

        tracing.record_system_prompt(agent_trace, _extract_system_prompt_text(system_instruction))
        tracing.record_llm_context(agent_trace, contents)
        tracing.record_model_name(agent_trace, model)
        tracing.record_llm_request(
            agent_trace, model=model, system_instruction=_to_jsonable(system_instruction), contents=contents
        )
    except Exception:
        pass

    return None


def log_after_model_callback(callback_context: Any, llm_response: Any) -> None:
    """
    after_model_callback: captures REAL provider-reported token usage from
    llm_response.usage_metadata (never estimated) plus the model's output
    text for this turn. Only acts once usage_metadata is populated — ADK
    only attaches it to the final/aggregated response for a turn, not to
    intermediate streaming chunks. Always returns None.
    """
    agent_trace = _get_agent_trace(callback_context.invocation_id, callback_context.agent_name)
    if agent_trace is None:
        return None

    usage = getattr(llm_response, "usage_metadata", None)
    if usage is None:
        return None

    try:
        output_text = _extract_response_output(llm_response)
        tokens = {
            "prompt": getattr(usage, "prompt_token_count", None),
            "completion": getattr(usage, "candidates_token_count", None),
            "total": getattr(usage, "total_token_count", None),
            "cached": getattr(usage, "cached_content_token_count", None),
            "reasoning": getattr(usage, "thoughts_token_count", None),
        }
        tracing.record_token_usage(
            agent_trace,
            model=agent_trace.model,
            prompt_tokens=tokens["prompt"],
            completion_tokens=tokens["completion"],
            total_tokens=tokens["total"],
            output_text=output_text,
            cached_tokens=tokens["cached"],
            reasoning_tokens=tokens["reasoning"],
        )
        tracing.record_llm_response(agent_trace, model=agent_trace.model, output_text=output_text, tokens=tokens)
    except Exception:
        pass

    return None


def log_before_tool_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
) -> None:
    """
    before_tool_callback: logs every tool call made by whichever agent this
    callback is attached to (root or any specialist sub-agent), and records
    the call's start time for both the stdout elapsed-time log and the
    app.tracing tool_calls/ trace entry written in log_after_tool_callback.

    ADK auto-registers a synthetic "transfer_to_agent" tool on any agent
    that has sub_agents — a Master Orchestrator -> sub-agent handoff is an
    LLM-issued call to that tool, so it shows up here too, with
    args["agent_name"] naming the sub-agent being transferred to. Logged as
    its own AGENT_TRANSFER event (not a generic TOOL_CALL) so the terminal
    reads as "master handed off to X", not "master called a tool named
    transfer_to_agent". It is still traced as a tool call in app.tracing so
    the transfer is visible in that agent's tool_calls/ tree too.
    """
    _tool_started_at[(tool_context.invocation_id, tool.name)] = time.perf_counter()

    if tool.name == "transfer_to_agent":
        log_event(
            "AGENT_TRANSFER",
            agent=tool_context.agent_name,
            to=args.get("agent_name", "?"),
            invocation=tool_context.invocation_id,
        )
    else:
        log_event(
            "TOOL_CALL",
            agent=tool_context.agent_name,
            tool=tool.name,
            args=_compact(args),
            invocation=tool_context.invocation_id,
        )
        agent_trace = _get_agent_trace(tool_context.invocation_id, tool_context.agent_name)
        if agent_trace is not None:
            try:
                tracing.record_tool_started(agent_trace, tool.name)
            except Exception:
                pass
    return None


def log_after_tool_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: Any,
) -> None:
    """after_tool_callback: logs completion + elapsed time of a tool call,
    and writes the full tool_calls/<tool_name>_NNN/ trace entry (docstring,
    real input args, real response) for whichever agent made the call."""
    started_at = _tool_started_at.pop((tool_context.invocation_id, tool.name), None)
    elapsed_ms = (time.perf_counter() - started_at) * 1000 if started_at is not None else -1.0

    if tool.name != "transfer_to_agent":
        log_event(
            "TOOL_RESULT",
            agent=tool_context.agent_name,
            tool=tool.name,
            elapsed_ms=f"{elapsed_ms:.1f}",
            invocation=tool_context.invocation_id,
        )

    agent_trace = _get_agent_trace(tool_context.invocation_id, tool_context.agent_name)
    if agent_trace is not None:
        try:
            tracing.record_tool_call(
                agent_trace,
                tool_name=tool.name,
                docstring=_resolve_tool_docstring(tool),
                args=args,
                response=tool_response,
                status="SUCCESS",
                duration_ms=max(elapsed_ms, 0.0),
            )
        except Exception:
            pass

    return None


def log_on_tool_error_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    error: Exception,
) -> None:
    """
    on_tool_error_callback: when a tool call raises, ADK does NOT call
    after_tool_callback at all (confirmed in
    google/adk/flows/llm_flows/functions.py) — it calls this instead, which
    is the only reachable place to ever see a failed tool call. Always
    returns None so the real exception continues to propagate unchanged;
    this callback only ever observes.
    """
    started_at = _tool_started_at.pop((tool_context.invocation_id, tool.name), None)
    elapsed_ms = (time.perf_counter() - started_at) * 1000 if started_at is not None else -1.0

    log_event(
        "TOOL_ERROR",
        agent=tool_context.agent_name,
        tool=tool.name,
        error=str(error),
        invocation=tool_context.invocation_id,
    )

    agent_trace = _get_agent_trace(tool_context.invocation_id, tool_context.agent_name)
    if agent_trace is not None:
        try:
            tracing.record_tool_call(
                agent_trace,
                tool_name=tool.name,
                docstring=_resolve_tool_docstring(tool),
                args=args,
                response=None,
                status="FAILED",
                duration_ms=max(elapsed_ms, 0.0),
                error=str(error),
            )
        except Exception:
            pass

    return None
