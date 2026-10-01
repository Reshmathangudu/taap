import { useEffect, useReducer } from "react";
import { startRun, onAgentStatus, onRunLifecycle, type AgentStatus } from "./runStatusBus";

/**
 * Drives the Risk Tier pipeline directly from a Job Review submission —
 * no chat/LLM routing involved. It calls startRun(releaseId), which opens
 * the AG-UI/SSE stream against the backend's deterministic
 * RiskTierPipelineAgent (see runStatusBus.ts), and turns the resulting
 * agent_status / run_lifecycle events into local view state.
 *
 * Events are ignored once they no longer belong to the run this hook
 * started (a stale releaseId), so a previous run's trailing events can
 * never bleed into a newer one.
 */

export interface AgentCardState {
  agent: string;
  agentName?: string;
  status: AgentStatus;
  text: string;
  startedAt: string;
  updatedAt: string;
}

export type RunPhase = "idle" | "running" | "completed" | "failed";

export interface RiskTierRunState {
  phase: RunPhase;
  releaseId: string | null;
  agents: Record<string, AgentCardState>;
  agentOrder: string[];
  error: string | null;
}

const initialState: RiskTierRunState = {
  phase: "idle",
  releaseId: null,
  agents: {},
  agentOrder: [],
  error: null,
};

type Action =
  | { type: "START"; releaseId: string }
  | { type: "AGENT_STATUS"; releaseId: string; agent: string; agentName?: string; status: AgentStatus; text: string }
  | { type: "FINISHED"; releaseId: string }
  | { type: "FAILED"; releaseId: string; error: string };

function timeNow(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function reducer(state: RiskTierRunState, action: Action): RiskTierRunState {
  switch (action.type) {
    case "START":
      return { phase: "running", releaseId: action.releaseId, agents: {}, agentOrder: [], error: null };

    case "AGENT_STATUS": {
      if (state.phase !== "running" || action.releaseId !== state.releaseId) return state;
      const isNew = !(action.agent in state.agents);
      const previous = state.agents[action.agent];
      const now = timeNow();
      return {
        ...state,
        agents: {
          ...state.agents,
          [action.agent]: {
            agent: action.agent,
            agentName: action.agentName ?? previous?.agentName,
            status: action.status,
            text: action.text,
            startedAt: previous?.startedAt ?? now,
            updatedAt: now,
          },
        },
        agentOrder: isNew ? [...state.agentOrder, action.agent] : state.agentOrder,
      };
    }

    case "FINISHED":
      if (state.phase !== "running" || action.releaseId !== state.releaseId) return state;
      return { ...state, phase: "completed" };

    case "FAILED":
      if (state.phase !== "running" || action.releaseId !== state.releaseId) return state;
      return { ...state, phase: "failed", error: action.error };

    default:
      return state;
  }
}

export function useRiskTierRun() {
  const [state, dispatch] = useReducer(reducer, initialState);

  useEffect(
    () =>
      onAgentStatus((detail) => {
        dispatch({
          type: "AGENT_STATUS",
          releaseId: detail.releaseId,
          agent: detail.agent,
          agentName: detail.agentName,
          status: detail.status,
          text: detail.text,
        });
      }),
    []
  );

  useEffect(
    () =>
      onRunLifecycle((detail) => {
        if (detail.phase === "finished") dispatch({ type: "FINISHED", releaseId: detail.releaseId });
        else if (detail.phase === "failed")
          dispatch({ type: "FAILED", releaseId: detail.releaseId, error: detail.error ?? "Unknown error" });
      }),
    []
  );

  function run(releaseId: string): void {
    if (state.phase === "running") return;
    dispatch({ type: "START", releaseId });
    startRun(releaseId);
  }

  return { state, run };
}
