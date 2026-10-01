// Real-time run-status stream, backed by the AG-UI Gateway.
//
// startRun() opens an AG-UI run against the backend's deterministic
// RiskTierPipelineAgent (app/agents/pipeline_stream_agent.py, mounted at
// POST /agui/run — see app/api/api.py). That agent makes no LLM call: it
// drives RiskTierMasterOrchestrator.execute() directly and turns its
// per-stage progress into AG-UI STATE_DELTA events carrying `agent_status`
// and `run_lifecycle` keys, which land here via HttpAgent's onStateChanged
// callback.
//
// This module makes NO assumption about which agents exist, how many there
// are, or what order they run in — `agent` is whatever identifier the
// backend sends in a given event, full stop. The backend today happens to
// always emit the same 8 keys in the same sequential order (that's a
// property of RiskTierMasterOrchestrator, unchanged by this file), but
// nothing here hardcodes that: a future backend that renamed a stage, added
// a new one, ran several concurrently, or only invoked a subset for a given
// query would work here with zero changes — every consumer (RunConsole,
// the three result panels) builds its own view purely from the stream of
// AgentStatusDetail/RunLifecycleDetail events, not from a fixed list.

import { HttpAgent } from "@ag-ui/client";
import { setStoredReleaseId } from "./currentRelease";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://127.0.0.1:4000";

export type AgentStatus = "pending" | "running" | "finished" | "failed";

export interface AgentStatusDetail {
  /** Backend-provided identifier for whichever agent this event is about — not a closed set. */
  agent: string;
  /** Human-readable name the backend sent for this agent, if any (e.g. "Feature / Epic Change Impact Agent"). */
  agentName?: string;
  status: AgentStatus;
  releaseId: string;
  text: string;
}

export interface RunLifecycleDetail {
  phase: "started" | "finished" | "failed";
  releaseId: string;
  /** Set only when phase is "failed" — the actual backend error message. */
  error?: string;
}

const AGENT_STATUS_EVENT = "agui:agent-status";
const RUN_LIFECYCLE_EVENT = "agui:run-lifecycle";

function dispatchAgentStatus(detail: AgentStatusDetail) {
  window.dispatchEvent(
    new CustomEvent<AgentStatusDetail>(AGENT_STATUS_EVENT, { detail }),
  );
}

function dispatchRunLifecycle(detail: RunLifecycleDetail) {
  window.dispatchEvent(
    new CustomEvent<RunLifecycleDetail>(RUN_LIFECYCLE_EVENT, { detail }),
  );
}

/** Subscribe to every agent status transition. Returns an unsubscribe function. */
export function onAgentStatus(
  handler: (detail: AgentStatusDetail) => void,
): () => void {
  const listener = (e: Event) =>
    handler((e as CustomEvent<AgentStatusDetail>).detail);
  window.addEventListener(AGENT_STATUS_EVENT, listener);
  return () => window.removeEventListener(AGENT_STATUS_EVENT, listener);
}

/**
 * Convenience used by TestSelectionReport, ExclusionSignoffQueue, and
 * ExecutionAuditLog: fire only when the one specific agent each panel is
 * backed by reaches "finished". Each panel subscribes independently to the
 * single step whose data it owns — none of them reach into RunConsole or
 * into each other, which keeps the "independently mounted panels"
 * principle intact even with this new cross-cutting signal.
 */
export function onAgentFinished(
  agent: string,
  handler: (releaseId: string) => void,
): () => void {
  return onAgentStatus((detail) => {
    if (detail.agent === agent && detail.status === "finished")
      handler(detail.releaseId);
  });
}

export function onRunLifecycle(
  handler: (detail: RunLifecycleDetail) => void,
): () => void {
  const listener = (e: Event) =>
    handler((e as CustomEvent<RunLifecycleDetail>).detail);
  window.addEventListener(RUN_LIFECYCLE_EVENT, listener);
  return () => window.removeEventListener(RUN_LIFECYCLE_EVENT, listener);
}

let runInFlight = false;

interface AgentStatusState {
  agent?: string;
  agent_name?: string;
  status?: string;
  release_id?: string;
  text?: string;
}

interface RunLifecycleState {
  phase?: string;
  release_id?: string;
  error?: string;
}

const isNonEmptyString = (value: string | undefined): value is string =>
  !!value && value.trim().length > 0;

const isAgentStatus = (value: string | undefined): value is AgentStatus =>
  value === "pending" ||
  value === "running" ||
  value === "finished" ||
  value === "failed";

/** Dedupe guards for one createStateChangeHandler instance. Pulled out to a
 * plain object (rather than closure-local variables) so a caller that reuses
 * one long-lived session across turns can hold a single guards object across
 * calls instead of getting a fresh one each time — see the sendMasterQuery
 * note below for why that distinction matters. */
interface StateChangeGuards {
  lastAgentStatusKey: string;
  /** Content key of the last-dispatched lifecycle, not just a "did we ever
   * dispatch" boolean — so a run_lifecycle that hasn't actually changed
   * since the last dispatch (e.g. still reporting the previous run's
   * "finished") is recognized as already-seen and skipped, the same way
   * lastAgentStatusKey already does for agent_status. */
  lastLifecycleKey: string;
}

function createStateChangeGuards(): StateChangeGuards {
  return { lastAgentStatusKey: "", lastLifecycleKey: "" };
}

/**
 * Shared onStateChanged handling for both startRun and sendMasterQuery: turns
 * cumulative agent_status/run_lifecycle session state into the same
 * dispatchAgentStatus/dispatchRunLifecycle calls either caller needs.
 *
 * `guards` dedupes by content, not by "have we ever fired" — so passing the
 * SAME guards object across multiple calls is safe and, for a reused
 * session, required: startRun() opens a brand-new HttpAgent/session per
 * call (nothing carries over, so a fresh createStateChangeGuards() per call
 * is fine either way), but sendMasterQuery reuses one long-lived
 * HttpAgent/session across a whole conversation for LLM memory. Its
 * agent_status/run_lifecycle session state is cumulative across turns, not
 * reset between them — an unrelated follow-up question still carries the
 * previous run's "finished" lifecycle and last agent's "finished" status in
 * state. A fresh, empty guards object on every call would see that
 * unchanged leftover state as new and replay "Running the pipeline...",
 * "Run complete...", etc. on every subsequent turn, real change or not.
 * Content-keyed dedupe against a guards object that persists across calls
 * fixes that while still firing normally for a genuinely new run's
 * genuinely new status/lifecycle values.
 */
function createStateChangeHandler(
  fallbackReleaseId: string,
  guards: StateChangeGuards = createStateChangeGuards(),
) {
  const onStateChanged = ({ state }: { state: unknown }) => {
    const s = state as Record<string, unknown> | undefined;
    const agentStatus = s?.agent_status as AgentStatusState | undefined;
    if (
      agentStatus &&
      isNonEmptyString(agentStatus.agent) &&
      isAgentStatus(agentStatus.status)
    ) {
      // release_id is part of the key, not just agent:status:text — the
      // backend's status text is generic ("Audit ledger updated.", with no
      // release id in it), so a genuinely new run for a *different*
      // release that happens to reach the same agent/status with the same
      // generic text must still produce a different key here, or it would
      // be wrongly suppressed as an already-seen duplicate too.
      const key = `${agentStatus.agent}:${agentStatus.status}:${agentStatus.release_id ?? ""}:${agentStatus.text ?? ""}`;
      if (key !== guards.lastAgentStatusKey) {
        guards.lastAgentStatusKey = key;
        dispatchAgentStatus({
          agent: agentStatus.agent,
          agentName: agentStatus.agent_name,
          status: agentStatus.status,
          releaseId: agentStatus.release_id ?? fallbackReleaseId,
          text: agentStatus.text ?? "",
        });
      }
    }

    const lifecycle = s?.run_lifecycle as RunLifecycleState | undefined;
    if (
      lifecycle &&
      (lifecycle.phase === "finished" || lifecycle.phase === "failed")
    ) {
      const lifecycleKey = `${lifecycle.phase}:${lifecycle.release_id ?? ""}:${lifecycle.error ?? ""}`;
      if (lifecycleKey !== guards.lastLifecycleKey) {
        guards.lastLifecycleKey = lifecycleKey;
        const finishedReleaseId = lifecycle.release_id ?? fallbackReleaseId;
        if (lifecycle.phase === "failed") {
          dispatchRunLifecycle({
            phase: "failed",
            releaseId: finishedReleaseId,
            error: lifecycle.error ?? "Unknown error",
          });
        } else {
          // Single source of truth for "which release just completed" — set
          // here, not in the consuming panels, so it's persisted regardless of
          // which of the three result panels (if any) are mounted at the
          // moment the run finishes. See currentRelease.ts.
          setStoredReleaseId(finishedReleaseId);
          dispatchRunLifecycle({
            phase: "finished",
            releaseId: finishedReleaseId,
          });
        }
      }
    }
  };

  return {
    onStateChanged,
    sawAgentStatus: () => guards.lastAgentStatusKey !== "",
  };
}

/**
 * Opens a real AG-UI run against the backend's deterministic pipeline agent
 * and translates its STATE_DELTA events into the same dispatch calls the
 * scripted mock used to make — see the module comment above.
 *
 * Deliberately does NOT pre-seed any agents as "pending": which agents run,
 * how many, and in what order is entirely up to whatever the backend
 * actually reports for this run. Consumers (RunConsole's reducer) build
 * their own list purely from the AGENT_STATUS events that arrive.
 */
export function startRun(releaseId: string): void {
  if (runInFlight) return;
  runInFlight = true;

  dispatchRunLifecycle({ phase: "started", releaseId });

  // google-adk's Runner.run_async() requires either a new_message or an
  // invocation_id to resume — ag-ui-adk only builds new_message from
  // input.messages, so a run with only `state` and zero messages fails with
  // "Running an agent requires either a new_message or an invocation_id...".
  // RiskTierPipelineAgent never reads this message's content (it only reads
  // ctx.session.state), but ADK's Runner still requires one to be present.
  //
  // release_id must be set as `initialState` here, NOT passed into
  // runAgent()'s parameters below — HttpAgent.runAgent() ignores any `state`
  // field on its parameters object entirely; prepareRunAgentInput() always
  // serializes the agent INSTANCE's own `this.state`, which only `initialState`
  // (or a later addMessage-style state update) can set.
  const agent = new HttpAgent({
    url: `${API_BASE_URL}/agui/run`,
    initialState: { release_id: releaseId },
    initialMessages: [
      {
        id: crypto.randomUUID(),
        role: "user",
        content: `Analyze release ${releaseId}`,
      },
    ],
  });

  const { onStateChanged } = createStateChangeHandler(releaseId);
  let lifecycleFailed = false;

  agent
    .runAgent(undefined, {
      onStateChanged: (args) => {
        onStateChanged(args);
        const lifecycle = (args.state as Record<string, unknown> | undefined)
          ?.run_lifecycle as RunLifecycleState | undefined;
        if (lifecycle?.phase === "failed") lifecycleFailed = true;
      },
    })
    .catch((err: unknown) => {
      console.error("Risk Tier run failed", err);
      if (!lifecycleFailed) {
        lifecycleFailed = true;
        dispatchRunLifecycle({
          phase: "failed",
          releaseId,
          error: err instanceof Error ? err.message : String(err),
        });
      }
    })
    .finally(() => {
      runInFlight = false;
    });
}

let masterChatAgent: HttpAgent | null = null;

// Shared across every sendMasterQuery call, deliberately not recreated per
// call — see createStateChangeHandler's doc comment. This is what stops an
// unrelated follow-up turn from replaying the previous turn's already-seen
// agent_status/run_lifecycle values.
const masterChatGuards: StateChangeGuards = createStateChangeGuards();

function getMasterChatAgent(): HttpAgent {
  if (!masterChatAgent) {
    masterChatAgent = new HttpAgent({
      url: `${API_BASE_URL}/agui/chat`,
      initialMessages: [],
    });
  }
  return masterChatAgent;
}

/**
 * Single entry point for the unified chat input: forwards the user's raw
 * text unchanged to the LLM-driven root_agent (POST /agui/chat). The Master
 * Orchestrator itself decides whether this needs the full pipeline (it
 * stages the release context, then transfers to the risk_tier_pipeline
 * sub-agent — see app/agent.py) or a targeted question — either way, live
 * agent_status/run_lifecycle STATE_DELTA events flow through exactly like
 * startRun()'s, via the same dispatchAgentStatus/dispatchRunLifecycle calls,
 * so the AgentPipeline cards and the three result panels' onAgentFinished
 * listeners keep working unchanged regardless of which path the LLM took.
 *
 * Reuses ONE HttpAgent (module-level, lazily created) across every call —
 * unlike startRun's fresh-per-run agent — so the underlying ADK session
 * persists across turns, giving the LLM real multi-turn memory (e.g.
 * answering "for which release?" as a follow-up).
 *
 * Resolves to the trailing assistant message's text, if the LLM produced
 * one this turn (null for a pure pipeline-transfer turn with no trailing
 * text — the live progress events are the response in that case).
 */
export async function sendMasterQuery(text: string): Promise<string | null> {
  const agent = getMasterChatAgent();
  agent.addMessage({ id: crypto.randomUUID(), role: "user", content: text });

  const { onStateChanged } = createStateChangeHandler("", masterChatGuards);
  const { newMessages } = await agent.runAgent(undefined, { onStateChanged });

  for (let i = newMessages.length - 1; i >= 0; i -= 1) {
    const message = newMessages[i];
    if (
      message.role === "assistant" &&
      typeof message.content === "string" &&
      message.content.trim()
    ) {
      return message.content;
    }
  }
  return null;
}
