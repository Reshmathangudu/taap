from __future__ import annotations

from typing import Any

from google.adk.plugins.base_plugin import BasePlugin

from app.logging_config import get_logger
from app.tracing import tracer

logger = get_logger(__name__)


class RiskTierTracingPlugin(BasePlugin):
    """
    Closes the two gaps the per-agent ADK callbacks in
    app/observability/agent_logging.py cannot reach on their own:

    1. A crashed agent turn. When an agent's own turn raises, ADK returns
       from run_async() *before* after_agent_callback ever fires
       (confirmed in google/adk/agents/base_agent.py) — log_after_agent_
       callback's pop-and-close never runs, so that AgentTrace stays open
       forever with no output.json.
    2. A clean early exit. scope_guard_before_agent_callback (already
       wired on root_agent) short-circuits an out-of-scope query by
       returning Content, which sets ctx.end_invocation and makes
       run_async() return immediately — again before after_agent_callback.
       Since log_before_agent_callback already opened an AgentTrace by
       then, every out-of-scope query used to leave a permanently
       half-written trace folder and a run that was never closed.

    Wiring this plugin (via ADKAgent.from_app(App(..., plugins=[...])) in
    app/api/api.py) gives access to the invocation-wide hooks that catch
    both cases — after_run_callback fires once the whole invocation ends,
    successfully or via a clean early exit; on_run_error_callback fires on
    an unhandled exception; on_agent_error_callback narrows the same
    exception case to the one agent that actually raised, so that failure
    is attributed correctly instead of swept generically at run-end.
    """

    def __init__(self) -> None:
        super().__init__(name="risk_tier_tracing_plugin")

    async def after_run_callback(self, *, invocation_context: Any) -> None:
        self._close_invocation(invocation_context.invocation_id, status="SUCCESS", error=None)

    async def on_run_error_callback(self, *, invocation_context: Any, error: Exception) -> None:
        self._close_invocation(invocation_context.invocation_id, status="FAILED", error=error)

    async def on_agent_error_callback(self, *, agent: Any, callback_context: Any, error: Exception) -> None:
        # Notification-only per ADK's contract — never suppress the error,
        # never return a value. Narrower than the run-level sweep: this
        # closes just the one agent that actually failed, so the failure
        # is attributed to it specifically rather than to a generic
        # end-of-run abandonment sweep.
        from app.observability.agent_logging import pop_active_agent_trace

        invocation_id = getattr(callback_context, "invocation_id", None)
        agent_name = getattr(agent, "name", None) or getattr(callback_context, "agent_name", None)
        if not invocation_id or not agent_name:
            return None

        try:
            agent_trace = pop_active_agent_trace(invocation_id, agent_name)
            if agent_trace is not None:
                tracer.finish_agent_trace(agent_trace, status="FAILED", error=error)
        except Exception:
            logger.exception(
                "tracing: on_agent_error_callback cleanup failed for %s/%s", invocation_id, agent_name
            )
        return None

    def _close_invocation(self, invocation_id: str, status: str, error: Exception | None) -> None:
        from app.observability.agent_logging import discard_active_agent_traces_for_invocation

        run = tracer.get_active_run(invocation_id)
        if run is None:
            # Nothing was ever traced for this invocation (e.g. tracing
            # disabled, or the turn never reached any agent callback) —
            # nothing to close.
            return

        try:
            closed_ids = tracer.abandon_open_agent_traces(
                run, reason="invocation ended without this agent's after_agent_callback firing"
            )
            if closed_ids:
                logger.info(
                    "tracing: abandoned %d leaked open agent trace(s) for invocation %s: %s",
                    len(closed_ids), invocation_id, closed_ids,
                )
        except Exception:
            logger.exception("tracing: failed to abandon open agent traces for %s", invocation_id)

        try:
            discard_active_agent_traces_for_invocation(invocation_id)
        except Exception:
            logger.exception("tracing: failed to purge active-agent-trace bookkeeping for %s", invocation_id)

        try:
            tracer.finish_run(run, status=status, error=error, close=True)
        except Exception:
            logger.exception("tracing: failed to finish run %s", invocation_id)
