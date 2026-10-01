from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.logging_config import get_logger
from app.tracing.cost import estimate_cost_usd
from app.tracing.ids import (
    new_agent_run_id,
    new_run_id,
    new_trace_id,
    safe_name,
    short_dir_token,
)
from app.tracing.writer import append_jsonl, append_log_line, write_json, write_text

logger = get_logger(__name__)

_LOCK = threading.Lock()
_ACTIVE_RUNS: dict[str, "RunTrace"] = {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _logs_base_dir() -> Path:
    try:
        from app.config import get_settings

        return Path(get_settings().logs_dir)
    except Exception:
        return Path("logs")


def _tracing_enabled() -> bool:
    try:
        from app.config import get_settings

        return bool(get_settings().tracing_enabled)
    except Exception:
        return True


@dataclass
class AgentTrace:
    """
    One agent's execution within one run. Created by start_agent_trace(),
    mutated by record_*() calls, closed by finish_agent_trace(). Never
    raises on its own — every method here that touches disk goes through
    app.tracing.writer, which swallows and logs its own failures.
    """

    run: "RunTrace"
    agent_name: str
    agent_run_id: str
    parent_agent_run_id: str | None
    dir_path: Path
    started_at: datetime
    tool_seq: dict[str, int] = field(default_factory=dict)
    tool_count: int = 0
    tool_names: list[str] = field(default_factory=list)
    llm_call: bool = False
    model: str | None = None
    tokens: dict[str, int | None] = field(
        default_factory=lambda: {
            "prompt": None, "completion": None, "total": None,
            "cached": None, "reasoning": None,
        }
    )
    estimated_cost_usd: float | None = None
    last_output: Any = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def next_tool_sequence(self, tool_name: str) -> int:
        with self.lock:
            current = self.tool_seq.get(tool_name, 0) + 1
            self.tool_seq[tool_name] = current
            return current

    @property
    def execution_id(self) -> str:
        """Alias of agent_run_id — the exact term the observability spec uses."""
        return self.agent_run_id

    @property
    def parent_execution_id(self) -> str | None:
        """Alias of parent_agent_run_id."""
        return self.parent_agent_run_id


@dataclass
class RunTrace:
    """
    One top-level run (a full pipeline execution, or one conversational ADK
    invocation). Holds every finished AgentTrace's compact summary in
    `agents`, plus a reference to every still-running one in `open_agents`
    (needed so peek_run_totals sees real token usage the moment
    record_token_usage() sets it — an agent transferred to via
    transfer_to_agent can start running, and the deterministic pipeline it
    triggers can peek this run, before the transferring agent's OWN
    after_agent_callback ever fires and moves it into `agents`; without
    open_agents that peek would see nothing yet). Also accumulates the
    flat cross-cutting indexes (tool_invocations, cache_events, errors)
    finish_run() rolls up into tools_summary.json/errors.json.
    """

    run_id: str
    trace_id: str
    release_id: str
    kind: str
    dir_path: Path
    started_at: datetime
    trace_parent_run_id: str | None = None
    agents: list[dict[str, Any]] = field(default_factory=list)
    open_agents: dict[str, "AgentTrace"] = field(default_factory=dict)
    tool_invocations: list[dict[str, Any]] = field(default_factory=list)
    cache_events: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    final_response: Any = None
    last_agent_run_id: str | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)

    def register_open_agent(self, agent_trace: "AgentTrace") -> None:
        with self.lock:
            self.open_agents[agent_trace.agent_run_id] = agent_trace

    def unregister_open_agent(self, agent_run_id: str) -> None:
        with self.lock:
            self.open_agents.pop(agent_run_id, None)

    def record_agent_summary(self, summary: dict[str, Any]) -> None:
        with self.lock:
            self.agents.append(summary)

    def record_tool_invocation(self, entry: dict[str, Any]) -> None:
        with self.lock:
            self.tool_invocations.append(entry)

    def record_cache_event(self, entry: dict[str, Any]) -> None:
        with self.lock:
            self.cache_events.append(entry)

    def record_error(self, entry: dict[str, Any]) -> None:
        with self.lock:
            self.errors.append(entry)

    def set_final_response(self, data: Any) -> None:
        with self.lock:
            self.final_response = data

    def set_last_agent(self, agent_run_id: str) -> None:
        with self.lock:
            self.last_agent_run_id = agent_run_id

    def get_last_agent(self) -> str | None:
        with self.lock:
            return self.last_agent_run_id

    def snapshot_agents(self) -> list[dict[str, Any]]:
        """Finished agent summaries plus a live snapshot of every agent
        still running right now — see the class docstring for why both are
        needed."""
        with self.lock:
            finished = list(self.agents)
            open_traces = list(self.open_agents.values())
        return finished + [_agent_trace_snapshot(t) for t in open_traces]

    @property
    def parent_execution_id(self) -> str | None:
        """Alias of trace_parent_run_id, for symmetry with per-agent naming."""
        return self.trace_parent_run_id


def _agent_trace_snapshot(agent_trace: "AgentTrace") -> dict[str, Any]:
    """
    Live equivalent of the summary dict finish_agent_trace() appends via
    record_agent_summary(), computed for an AgentTrace that is still
    running. status is reported as RUNNING and finished_at is None —
    tool_calls/llm_call/model/tokens reflect whatever has actually been
    recorded so far, which is exactly what a same-moment peek needs.
    """
    now = _now()
    return {
        "agent_name": agent_trace.agent_name,
        "agent_run_id": agent_trace.agent_run_id,
        "execution_id": agent_trace.agent_run_id,
        "parent_agent_run_id": agent_trace.parent_agent_run_id,
        "parent_execution_id": agent_trace.parent_agent_run_id,
        "status": "RUNNING",
        "started_at": _iso(agent_trace.started_at),
        "finished_at": None,
        "duration_ms": (now - agent_trace.started_at).total_seconds() * 1000,
        "tool_calls": agent_trace.tool_count,
        "tools": list(agent_trace.tool_names),
        "llm_call": agent_trace.llm_call,
        "model": agent_trace.model,
        "tokens": dict(agent_trace.tokens),
        "estimated_cost_usd": agent_trace.estimated_cost_usd,
        "error": None,
    }


def _register_run(
    run_id: str,
    release_id: str,
    kind: str,
    trace_parent_run_id: str | None = None,
) -> RunTrace:
    # Inherit the parent's trace_id when one exists, rather than minting a
    # fresh one — this is what actually threads one trace_id across an ADK
    # query-run -> pipeline-run boundary (e.g. a chat turn that stages and
    # transfers to the deterministic pipeline). Falls back to a fresh id
    # for a genuinely new causal chain (no parent, or parent already closed
    # and evicted from the active-runs registry).
    trace_id: str | None = None
    if trace_parent_run_id:
        with _LOCK:
            parent = _ACTIVE_RUNS.get(trace_parent_run_id)
        if parent is not None:
            trace_id = parent.trace_id
    if trace_id is None:
        trace_id = new_trace_id()

    now = _now()
    safe_release = safe_name(release_id or "UNKNOWN")
    date_segment = now.strftime("%Y-%m-%d")
    # short_dir_token only affects the on-disk folder name — run_id itself
    # (used everywhere else: run_metadata.json, event_stream.jsonl, dict
    # keys) is untouched, so ADK's long invocation_id is still fully
    # recoverable from the file contents even though the folder name for
    # it is hashed short (see short_dir_token's docstring).
    dir_path = _logs_base_dir() / safe_release / date_segment / short_dir_token(run_id)
    run_trace = RunTrace(
        run_id=run_id,
        trace_id=trace_id,
        release_id=str(release_id or "UNKNOWN"),
        kind=kind,
        dir_path=dir_path,
        started_at=now,
        trace_parent_run_id=trace_parent_run_id,
    )
    with _LOCK:
        _ACTIVE_RUNS[run_id] = run_trace

    if _tracing_enabled():
        write_json(
            dir_path / "run_metadata.json",
            {
                "run_id": run_id,
                "trace_id": trace_id,
                "execution_id": run_id,
                "parent_execution_id": trace_parent_run_id,
                "release_id": run_trace.release_id,
                "kind": kind,
                "started_at": _iso(now),
                "logs_schema_version": 1,
            },
        )

    record_event(run_trace, "RUN_STARTED", release_id=run_trace.release_id, kind=kind)
    return run_trace


def start_run(
    release_id: str,
    kind: str,
    trace_parent_run_id: str | None = None,
) -> RunTrace:
    """Start a fresh top-level run (the deterministic pipeline path calls this)."""
    return _register_run(
        run_id=new_run_id(),
        release_id=release_id,
        kind=kind,
        trace_parent_run_id=trace_parent_run_id,
    )


def get_or_create_run(run_id: str, release_id: str, kind: str) -> RunTrace:
    """
    Look up an already-started run by id, or lazily create one.

    Used by the ADK conversational path, where the root agent's
    before_agent_callback is the first thing that ever needs a RunTrace —
    there is no separate explicit start_run() call site for that path.
    run_id there is the ADK invocation_id, which is stable across an entire
    turn (including any transfer_to_agent hop to a specialist).
    """
    with _LOCK:
        existing = _ACTIVE_RUNS.get(run_id)
    if existing is not None:
        return existing
    return _register_run(run_id=run_id, release_id=release_id, kind=kind)


def get_active_run(run_id: str) -> RunTrace | None:
    """Direct, read-only accessor into the in-memory active-runs registry."""
    with _LOCK:
        return _ACTIVE_RUNS.get(run_id)


def record_event(
    run: RunTrace,
    event_type: str,
    agent_run_id: str | None = None,
    parent_agent_run_id: str | None = None,
    **fields: Any,
) -> None:
    """
    Append one entry to this run's event_stream.jsonl — the single,
    centralized event-stream writer every instrumentation point (agent
    lifecycle, tool calls, LLM calls, A2A messages, cache hits/misses)
    calls, so there is one event mechanism, not duplicated logic per
    component. Never raises (goes through app.tracing.writer).
    """
    if not _tracing_enabled():
        return
    entry = {
        "ts": _iso(_now()),
        "run_id": run.run_id,
        "trace_id": run.trace_id,
        "event_type": event_type,
        "agent_run_id": agent_run_id,
        "execution_id": agent_run_id,
        "parent_agent_run_id": parent_agent_run_id,
        "parent_execution_id": parent_agent_run_id,
    }
    if fields:
        entry["fields"] = fields
    append_jsonl(run.dir_path / "event_stream.jsonl", entry)


def start_agent_trace(
    run: RunTrace,
    agent_name: str,
    input_data: Any,
    parent_agent_run_id: str | None = None,
) -> AgentTrace:
    if parent_agent_run_id is None:
        parent_agent_run_id = run.get_last_agent()

    agent_run_id = new_agent_run_id(agent_name)
    dir_path = run.dir_path / safe_name(agent_name)
    started_at = _now()

    agent_trace = AgentTrace(
        run=run,
        agent_name=agent_name,
        agent_run_id=agent_run_id,
        parent_agent_run_id=parent_agent_run_id,
        dir_path=dir_path,
        started_at=started_at,
    )

    if _tracing_enabled():
        write_json(
            dir_path / "input.json",
            {
                "agent_name": agent_name,
                "agent_run_id": agent_run_id,
                "execution_id": agent_run_id,
                "parent_agent_run_id": parent_agent_run_id,
                "parent_execution_id": parent_agent_run_id,
                "run_id": run.run_id,
                "trace_id": run.trace_id,
                "release_id": run.release_id,
                "started_at": _iso(started_at),
                "input": input_data,
            },
        )
        append_log_line(
            dir_path / "execution.log",
            f"{_iso(started_at)} | START | agent={agent_name} | agent_run_id={agent_run_id} "
            f"| parent_agent_run_id={parent_agent_run_id}",
        )

    run.set_last_agent(agent_run_id)
    run.register_open_agent(agent_trace)
    record_event(
        run, "AGENT_STARTED",
        agent_run_id=agent_run_id, parent_agent_run_id=parent_agent_run_id,
        agent_name=agent_name,
    )
    return agent_trace


def record_agent_progress(agent_trace: AgentTrace, text: str) -> None:
    """AGENT_PROGRESS event — a sub-step within one agent's turn, distinct
    from AGENT_STARTED/FINISHED. Purely observational, no file write beyond
    the event stream (the human-readable execution.log already carries
    finer-grained lines from record_tool_call/etc.)."""
    record_event(
        agent_trace.run, "AGENT_PROGRESS",
        agent_run_id=agent_trace.agent_run_id,
        parent_agent_run_id=agent_trace.parent_agent_run_id,
        agent_name=agent_trace.agent_name, text=text,
    )


def record_model_name(agent_trace: AgentTrace, model: str | None) -> None:
    """Pure in-memory setter (no I/O) — captured early in before_model_callback
    so the model name is available when after_model_callback writes usage."""
    agent_trace.model = model


def record_system_prompt(agent_trace: AgentTrace, prompt: str) -> None:
    agent_trace.llm_call = True
    if _tracing_enabled():
        write_text(agent_trace.dir_path / "system_prompt.txt", prompt or "")


def record_llm_context(agent_trace: AgentTrace, contents: Any) -> None:
    if _tracing_enabled():
        write_json(agent_trace.dir_path / "llm_context.json", contents)


def record_llm_request(agent_trace: AgentTrace, model: str | None, system_instruction: Any, contents: Any) -> None:
    """
    The full structured LLM request (requirement 3's "LLM request", distinct
    from the human-readable system_prompt.txt/llm_context.json pair those
    already produce) — and the matching LLM_REQUEST event-stream entry
    (requirement 8).
    """
    agent_trace.llm_call = True
    if _tracing_enabled():
        write_json(
            agent_trace.dir_path / "llm_request.json",
            {"model": model, "system_instruction": system_instruction, "contents": contents},
        )
    record_event(
        agent_trace.run, "LLM_REQUEST",
        agent_run_id=agent_trace.agent_run_id,
        parent_agent_run_id=agent_trace.parent_agent_run_id,
        agent_name=agent_trace.agent_name, model=model,
    )


def record_llm_response(
    agent_trace: AgentTrace,
    model: str | None,
    output_text: Any,
    tokens: dict[str, int | None],
) -> None:
    """The full structured LLM response, and the matching LLM_RESPONSE event."""
    if _tracing_enabled():
        write_json(
            agent_trace.dir_path / "llm_response.json",
            {"model": model, "output": output_text, "tokens": tokens},
        )
    record_event(
        agent_trace.run, "LLM_RESPONSE",
        agent_run_id=agent_trace.agent_run_id,
        parent_agent_run_id=agent_trace.parent_agent_run_id,
        agent_name=agent_trace.agent_name, model=model, tokens=tokens,
    )


def record_token_usage(
    agent_trace: AgentTrace,
    model: str | None,
    prompt_tokens: int | None,
    completion_tokens: int | None,
    total_tokens: int | None,
    output_text: Any = None,
    cached_tokens: int | None = None,
    reasoning_tokens: int | None = None,
) -> None:
    agent_trace.llm_call = True
    agent_trace.model = model
    agent_trace.tokens = {
        "prompt": prompt_tokens,
        "completion": completion_tokens,
        "total": total_tokens,
        "cached": cached_tokens,
        "reasoning": reasoning_tokens,
    }
    agent_trace.estimated_cost_usd = estimate_cost_usd(model, prompt_tokens, completion_tokens)
    if output_text is not None:
        agent_trace.last_output = output_text

    if _tracing_enabled():
        write_json(
            agent_trace.dir_path / "token_usage.json",
            {
                "llm_call": True,
                "model": model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "cached_tokens": cached_tokens,
                "reasoning_tokens": reasoning_tokens,
                "estimated_cost_usd": agent_trace.estimated_cost_usd,
            },
        )


def record_tool_call(
    agent_trace: AgentTrace,
    tool_name: str,
    docstring: str | None,
    args: Any,
    response: Any,
    status: str,
    duration_ms: float,
    error: str | None = None,
) -> None:
    agent_trace.tool_count += 1
    agent_trace.tool_names.append(tool_name)
    timestamp = _iso(_now())

    agent_trace.run.record_tool_invocation(
        {
            "tool_name": tool_name,
            "agent_name": agent_trace.agent_name,
            "agent_run_id": agent_trace.agent_run_id,
            "execution_id": agent_trace.agent_run_id,
            "status": status,
            "duration_ms": duration_ms,
            "timestamp": timestamp,
        }
    )
    if status != "SUCCESS":
        agent_trace.run.record_error(
            {
                "scope": "tool",
                "agent_name": agent_trace.agent_name,
                "agent_run_id": agent_trace.agent_run_id,
                "tool_name": tool_name,
                "error": error,
                "timestamp": timestamp,
            }
        )

    record_event(
        agent_trace.run, "TOOL_FINISHED" if status == "SUCCESS" else "TOOL_FAILED",
        agent_run_id=agent_trace.agent_run_id,
        parent_agent_run_id=agent_trace.parent_agent_run_id,
        agent_name=agent_trace.agent_name, tool_name=tool_name,
        duration_ms=duration_ms, status=status, error=error,
    )

    if not _tracing_enabled():
        return

    sequence = agent_trace.next_tool_sequence(tool_name)
    tool_dir = agent_trace.dir_path / "tool_calls" / f"{safe_name(tool_name)}_{sequence:03d}"

    write_json(tool_dir / "input.json", args)
    write_json(tool_dir / "response.json", response)
    write_text(tool_dir / "docstring.txt", docstring or "")
    write_json(
        tool_dir / "meta.json",
        {
            "tool_name": tool_name,
            "calling_agent": agent_trace.agent_name,
            "agent_run_id": agent_trace.agent_run_id,
            "sequence": sequence,
            "timestamp": timestamp,
            "duration_ms": duration_ms,
            "status": status,
            "error": error,
        },
    )
    append_log_line(
        agent_trace.dir_path / "execution.log",
        f"{timestamp} | TOOL_CALL | tool={tool_name} | seq={sequence} | status={status} "
        f"| duration_ms={duration_ms:.1f}" + (f" | error={error}" if error else ""),
    )


def record_tool_started(agent_trace: AgentTrace, tool_name: str) -> None:
    """TOOL_STARTED event — emitted separately from record_tool_call (which
    fires once, after the call completes) so the event stream has a real
    started/finished pair with two different timestamps."""
    record_event(
        agent_trace.run, "TOOL_STARTED",
        agent_run_id=agent_trace.agent_run_id,
        parent_agent_run_id=agent_trace.parent_agent_run_id,
        agent_name=agent_trace.agent_name, tool_name=tool_name,
    )


def record_a2a(
    run: RunTrace,
    event_type: str,
    source_agent: str,
    destination_agent: str,
    payload: Any,
    message_type: str | None = None,
) -> None:
    """
    Logs one agent-to-agent communication moment (requirement 5). event_type
    is A2A_REQUEST or A2A_RESPONSE. payload is masked the same way every
    other trace file is — never logs secrets/credentials.
    """
    record_event(
        run, event_type,
        source_agent=source_agent, destination_agent=destination_agent,
        message_type=message_type, payload=payload,
    )


def record_cache_event(
    run: RunTrace,
    hit: bool,
    cache_name: str,
    key: str,
    **extra: Any,
) -> None:
    """Logs a CACHE_HIT/CACHE_MISS moment (part of requirements 8/14) and
    rolls it into this run's cache_statistics (see finish_run)."""
    event_type = "CACHE_HIT" if hit else "CACHE_MISS"
    timestamp = _iso(_now())
    run.record_cache_event(
        {"cache_name": cache_name, "key": key, "hit": hit, "timestamp": timestamp}
    )
    record_event(run, event_type, cache_name=cache_name, key=key, **extra)


def abandon_open_agent_traces(run: RunTrace, reason: str) -> list[str]:
    """
    Force-closes every AgentTrace still open on this run, with
    status="ABANDONED" — used when an invocation ends (successfully via a
    clean early exit, or via an unhandled exception) without the affected
    agent's own after_agent_callback ever having fired, which otherwise
    leaves a permanently half-written trace folder (no output.json) and a
    RunTrace that's never closed. Returns the agent_run_ids closed this
    way, so a caller can also purge any of its own bookkeeping keyed by
    the same ids (see app/observability/agent_logging.py's
    _active_agent_traces).
    """
    with run.lock:
        open_traces = list(run.open_agents.values())
    closed_ids: list[str] = []
    for agent_trace in open_traces:
        try:
            finish_agent_trace(agent_trace, status="ABANDONED", error=reason)
            closed_ids.append(agent_trace.agent_run_id)
        except Exception:
            logger.exception(
                "tracing: failed to abandon open agent trace %s", agent_trace.agent_run_id
            )
    return closed_ids


def finish_agent_trace(
    agent_trace: AgentTrace,
    output_data: Any = None,
    status: str = "SUCCESS",
    error: Exception | str | None = None,
) -> None:
    finished_at = _now()
    duration_ms = (finished_at - agent_trace.started_at).total_seconds() * 1000
    error_text = str(error) if error is not None else None
    final_output = output_data if output_data is not None else agent_trace.last_output

    if _tracing_enabled():
        write_json(
            agent_trace.dir_path / "output.json",
            {
                "agent_name": agent_trace.agent_name,
                "agent_run_id": agent_trace.agent_run_id,
                "execution_id": agent_trace.agent_run_id,
                "parent_execution_id": agent_trace.parent_agent_run_id,
                "status": status,
                "started_at": _iso(agent_trace.started_at),
                "finished_at": _iso(finished_at),
                "duration_ms": duration_ms,
                "error": error_text,
                "output": final_output,
            },
        )

        if not agent_trace.llm_call:
            write_json(
                agent_trace.dir_path / "token_usage.json",
                {
                    "llm_call": False,
                    "reason": "deterministic business-logic stage, no model invoked",
                    "model": None,
                    "prompt_tokens": None,
                    "completion_tokens": None,
                    "total_tokens": None,
                    "cached_tokens": None,
                    "reasoning_tokens": None,
                    "estimated_cost_usd": None,
                },
            )

        append_log_line(
            agent_trace.dir_path / "execution.log",
            f"{_iso(finished_at)} | END | agent={agent_trace.agent_name} | status={status} "
            f"| duration_ms={duration_ms:.1f}" + (f" | error={error_text}" if error_text else ""),
        )

    agent_trace.run.record_agent_summary(
        {
            "agent_name": agent_trace.agent_name,
            "agent_run_id": agent_trace.agent_run_id,
            "execution_id": agent_trace.agent_run_id,
            "parent_agent_run_id": agent_trace.parent_agent_run_id,
            "parent_execution_id": agent_trace.parent_agent_run_id,
            "status": status,
            "started_at": _iso(agent_trace.started_at),
            "finished_at": _iso(finished_at),
            "duration_ms": duration_ms,
            "tool_calls": agent_trace.tool_count,
            "tools": list(agent_trace.tool_names),
            "llm_call": agent_trace.llm_call,
            "model": agent_trace.model,
            "tokens": dict(agent_trace.tokens),
            "estimated_cost_usd": agent_trace.estimated_cost_usd,
            "error": error_text,
        }
    )
    agent_trace.run.unregister_open_agent(agent_trace.agent_run_id)

    if status != "SUCCESS":
        agent_trace.run.record_error(
            {
                "scope": "agent",
                "agent_name": agent_trace.agent_name,
                "agent_run_id": agent_trace.agent_run_id,
                "error": error_text,
                "timestamp": _iso(finished_at),
            }
        )

    record_event(
        agent_trace.run,
        "AGENT_FINISHED" if status == "SUCCESS" else "AGENT_FAILED",
        agent_run_id=agent_trace.agent_run_id,
        parent_agent_run_id=agent_trace.parent_agent_run_id,
        agent_name=agent_trace.agent_name, status=status,
        duration_ms=duration_ms, error=error_text,
    )


def _compute_totals(agents: list[dict[str, Any]]) -> dict[str, Any]:
    total_tool_calls = sum(a["tool_calls"] for a in agents)
    total_llm_calls = sum(1 for a in agents if a["llm_call"])

    tools_invoked: list[str] = []
    for a in agents:
        for name in a.get("tools", []):
            if name not in tools_invoked:
                tools_invoked.append(name)

    token_totals: dict[str, int | None] = {
        "prompt": None, "completion": None, "total": None,
        "cached": None, "reasoning": None,
    }
    for key in token_totals:
        values = [a["tokens"].get(key) for a in agents if a.get("tokens", {}).get(key) is not None]
        if values:
            token_totals[key] = sum(values)

    cost_values = [a.get("estimated_cost_usd") for a in agents if a.get("estimated_cost_usd") is not None]
    total_cost = sum(cost_values) if cost_values else None

    return {
        "tool_calls": total_tool_calls,
        "llm_calls": total_llm_calls,
        "tools_invoked": tools_invoked,
        "tokens": token_totals,
        "estimated_cost_usd": total_cost,
    }


def peek_run_totals(run_id: str) -> dict[str, Any] | None:
    """
    Best-effort, read-only snapshot of another run's current totals — used
    by the deterministic pipeline path to fold its triggering ADK turn's
    real LLM token usage into the pipeline's own execution_summary.json.

    Includes agents that are still mid-turn (see RunTrace.snapshot_agents):
    the Master Orchestrator's own agent turn is very often still open —
    not yet through its after_agent_callback — at the exact moment
    transfer_to_agent hands control to the sub-agent that starts the
    pipeline, even though its real token usage was already recorded the
    moment its model call returned (confirmed against google-adk's actual
    flow: tool-call dispatch for a turn always happens in a later
    _run_one_step_async iteration than the _call_llm_async call that
    produced it, so after_model_callback for that response is guaranteed
    to have already run). Without including open agents here, this would
    always see zero tokens, not just sometimes.

    Returns None if run_id isn't currently registered (already popped via
    finish_run(..., close=True) elsewhere, or never existed).
    """
    run = get_active_run(run_id)
    if run is None:
        return None
    return _compute_totals(run.snapshot_agents())


def finish_run(
    run_trace: RunTrace,
    status: str = "SUCCESS",
    error: Exception | str | None = None,
    close: bool = True,
    orchestration: dict[str, Any] | None = None,
) -> None:
    """
    Write execution_summary.json (and the other run-level rollup files)
    for this run.

    close=True (the default, used by the deterministic pipeline path's
    one-shot execute() wrapper, and by RiskTierTracingPlugin's
    after_run_callback/on_run_error_callback for the ADK conversational
    path) also removes the run from the in-memory active-runs registry.
    The per-agent-turn checkpoint (close=False, still called from
    log_after_agent_callback) keeps writing an up-to-date
    execution_summary.json after every agent turn, since a single ADK
    invocation can span several agents (transfer_to_agent) with no
    other single "the whole invocation is done" moment visible from
    inside an agent callback — RiskTierTracingPlugin's after_run_callback
    is what actually closes it once the whole invocation ends.

    orchestration, when given (see peek_run_totals), is folded into this
    run's own totals — its tokens/llm_calls are added on top of whatever
    this run's own agents produced.
    """
    finished_at = _now()
    duration_ms = (finished_at - run_trace.started_at).total_seconds() * 1000

    if close:
        with _LOCK:
            _ACTIVE_RUNS.pop(run_trace.run_id, None)

    if not _tracing_enabled():
        return

    agents = run_trace.snapshot_agents()
    totals = _compute_totals(agents)

    if orchestration:
        orch_tokens = orchestration.get("tokens") or {}
        for key in ("prompt", "completion", "total", "cached", "reasoning"):
            value = orch_tokens.get(key)
            if value is not None:
                totals["tokens"][key] = (totals["tokens"].get(key) or 0) + value
        totals["llm_calls"] = totals.get("llm_calls", 0) + orchestration.get("llm_calls", 0)
        orch_cost = orchestration.get("estimated_cost_usd")
        if orch_cost is not None:
            totals["estimated_cost_usd"] = (totals.get("estimated_cost_usd") or 0) + orch_cost

    with run_trace.lock:
        cache_events = list(run_trace.cache_events)
        tool_invocations = list(run_trace.tool_invocations)
        errors = list(run_trace.errors)
        final_response = run_trace.final_response

    cache_hits = sum(1 for e in cache_events if e["hit"])
    cache_misses = sum(1 for e in cache_events if not e["hit"])
    cache_by_name: dict[str, dict[str, int]] = {}
    for e in cache_events:
        bucket = cache_by_name.setdefault(e["cache_name"], {"hits": 0, "misses": 0})
        bucket["hits" if e["hit"] else "misses"] += 1
    cache_statistics = {"hits": cache_hits, "misses": cache_misses, "by_cache_name": cache_by_name}

    summary = {
        "run_id": run_trace.run_id,
        "trace_id": run_trace.trace_id,
        "execution_id": run_trace.run_id,
        "parent_execution_id": run_trace.trace_parent_run_id,
        "release_id": run_trace.release_id,
        "kind": run_trace.kind,
        "trace_parent_run_id": run_trace.trace_parent_run_id,
        "started_at": _iso(run_trace.started_at),
        "finished_at": _iso(finished_at),
        "duration_ms": duration_ms,
        "status": status,
        "error": str(error) if error is not None else None,
        "execution_order": [a["agent_name"] for a in agents],
        "parallelism": "sequential",
        "agents": agents,
        "orchestration": orchestration,
        "totals": totals,
        "cache_statistics": cache_statistics,
    }

    write_json(run_trace.dir_path / "execution_summary.json", summary)
    write_json(
        run_trace.dir_path / "token_usage_summary.json",
        {"run_id": run_trace.run_id, "totals": totals, "agents": [
            {
                "agent_name": a["agent_name"], "agent_run_id": a["agent_run_id"],
                "llm_call": a["llm_call"], "model": a["model"], "tokens": a["tokens"],
                "estimated_cost_usd": a.get("estimated_cost_usd"),
            }
            for a in agents
        ]},
    )
    write_json(run_trace.dir_path / "errors.json", {"run_id": run_trace.run_id, "errors": errors})
    write_json(
        run_trace.dir_path / "tools_summary.json",
        {"run_id": run_trace.run_id, "tools": tool_invocations},
    )
    if final_response is not None:
        write_json(
            run_trace.dir_path / "final_response.json",
            {"run_id": run_trace.run_id, "release_id": run_trace.release_id, "summary": final_response},
        )

    record_event(
        run_trace, "RUN_FINISHED" if status == "SUCCESS" else "RUN_ERROR",
        status=status, duration_ms=duration_ms,
        error=str(error) if error is not None else None,
    )
