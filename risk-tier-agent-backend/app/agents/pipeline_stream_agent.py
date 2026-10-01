from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncGenerator

from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.events.event_actions import EventActions

from app.config import get_settings
from app.observability.agent_logging import log_after_agent_callback, log_before_agent_callback
from app.orchestrator.master_orchestrator import RiskTierMasterOrchestrator
from app.persistence.errors import ReleaseDataUnavailableError

logger = logging.getLogger(__name__)


class RiskTierPipelineAgent(BaseAgent):
    """Drives the deterministic Risk Tier pipeline and streams per-stage progress.

    Makes no LLM call itself. It runs
    ``RiskTierMasterOrchestrator.execute()`` directly (in a background thread,
    since that call is synchronous) and turns its ``on_stage`` progress
    callback into ADK ``Event``s carrying ``state_delta``, which ``ag-ui-adk``
    forwards to the browser as AG-UI STATE_DELTA events in real time. The
    scoring/tiering/exclusion business logic itself lives entirely in the six
    agents' own ``tools.py`` modules and is unchanged by this class.
    """

    async def _run_async_impl(
        self,
        ctx: InvocationContext,
    ) -> AsyncGenerator[Event, None]:
        release_id = str(ctx.session.state.get("release_id") or "").strip().upper()
        jira_link = ctx.session.state.get("jira_link") or None

        if not release_id:
            yield Event(
                author=self.name,
                actions=EventActions(
                    state_delta={
                        "run_lifecycle": {
                            "phase": "failed",
                            "release_id": "",
                            "error": "release_id is required",
                        }
                    }
                ),
            )
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[
            tuple[str, str, str, str | None, dict[str, Any] | None] | None
        ] = asyncio.Queue()

        # Captured here, synchronously, before crossing into the
        # run_in_executor background thread below — contextvars (and thus
        # anything derived from them) don't survive that boundary, but a
        # plain argument does. Threaded into execute() purely so its own
        # tracer.start_run() can record which ADK turn triggered this
        # pipeline run; see app/orchestrator/master_orchestrator.py.
        trace_parent_run_id = ctx.invocation_id

        def on_stage(
            stage_key: str,
            status: str,
            text: str,
            agent_name: str | None,
            envelope: dict[str, Any] | None = None,
        ) -> None:
            loop.call_soon_threadsafe(queue.put_nowait, (stage_key, status, text, agent_name, envelope))

        def run_pipeline() -> Exception | None:
            try:
                orchestrator = RiskTierMasterOrchestrator.from_settings(
                    get_settings(),
                    jira_link=jira_link,
                )
                print('Execute_function started..........................')
                orchestrator.execute(
                    release_id,
                    on_stage=on_stage,
                    trace_parent_run_id=trace_parent_run_id,
                )
                print('Execute_function completed..........................')
                return None
            except ReleaseDataUnavailableError as exc:
                # Not a failure — the release simply has no cached data yet.
                # Logged at info, not exception, so it doesn't read as a bug.
                logger.info("Risk Tier pipeline run for %s: %s", release_id, exc)
                return exc
            except Exception as exc:
                logger.exception("Risk Tier pipeline run failed for %s", release_id)
                return exc
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        future = loop.run_in_executor(None, run_pipeline)

        while True:
            item = await queue.get()
            if item is None:
                break
            stage_key, status, text, agent_name, envelope = item
            agent_status: dict[str, Any] = {
                "agent": stage_key,
                "agent_name": agent_name,
                "status": status,
                "release_id": release_id,
                "text": text,
            }
            if envelope:
                # Additive only — run_id/trace_id/event_type are new keys,
                # the 5 above are unchanged, so any existing frontend
                # consumer that only reads those keeps working untouched.
                agent_status["run_id"] = envelope.get("run_id")
                agent_status["trace_id"] = envelope.get("trace_id")
                agent_status["event_type"] = envelope.get("event_type")
            yield Event(
                author=self.name,
                actions=EventActions(state_delta={"agent_status": agent_status}),
            )

        error = await future

        if isinstance(error, ReleaseDataUnavailableError):
            phase = "not_found"
        elif error is not None:
            phase = "failed"
        else:
            phase = "finished"

        lifecycle: dict[str, object] = {
            "phase": phase,
            "release_id": release_id,
        }
        if error is not None:
            lifecycle["error"] = str(error)

        yield Event(
            author=self.name,
            actions=EventActions(state_delta={"run_lifecycle": lifecycle}),
        )


risk_tier_pipeline_agent = RiskTierPipelineAgent(
    name="risk_tier_pipeline",
    description=(
        "Executes the complete deterministic Risk Tier pipeline (all six "
        "specialist agents) for one release and streams live per-agent "
        "progress. Transfer here only after stage_pipeline_run has staged "
        "the release id (and Jira link, if any) for this session — this "
        "agent reads them from session state, not from the transfer call."
    ),
    before_agent_callback=log_before_agent_callback,
    after_agent_callback=log_after_agent_callback,
)
