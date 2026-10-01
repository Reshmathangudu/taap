import type { AgentStatus } from "../../lib/runStatusBus";

export interface ChatMessage {
  id: string;
  role: "user" | "bot" | "error";
  text: string;
  time: string;
}

/** One dynamically-discovered agent's live card state. Nothing here assumes
 * a fixed identity or position — `agent` is whatever key the backend used. */
export interface AgentCardState {
  agent: string;
  /** Human-readable name from the backend, if it sent one (preferred over any mechanical fallback). */
  agentName?: string;
  status: AgentStatus;
  text: string;
}

export interface RunConsoleState {
  /** The single unified input — a release trigger and a drill-down question
   * both start life here; see runTrigger.ts for how they're told apart. */
  inputText: string;
  /** True while a pipeline run is live-streaming via /agui/run. */
  running: boolean;
  /** True while a drill-down question is awaiting the conversational agent (/agui/chat). */
  sending: boolean;
  messages: ChatMessage[];
  /** Card state per agent, keyed by the backend-provided agent id. */
  agents: Record<string, AgentCardState>;
  /** Insertion order — the order agents were first reported, nothing else. */
  agentOrder: string[];
}

export const initialState: RunConsoleState = {
  inputText: "",
  running: false,
  sending: false,
  messages: [
    {
      id: "welcome",
      role: "bot",
      text: "One box for everything: type \"analyze release R25.4\" to kick off a live Risk Tier Agent pass, or ask a question like \"which tests are flaky?\" — the Master Orchestrator figures out which of the two you mean, and which specialist agent should answer.",
      time: "",
    },
  ],
  agents: {},
  agentOrder: [],
};

let seq = 0;
function nextId(): string {
  seq += 1;
  return "m" + seq;
}

function now(): string {
  return new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export type RunConsoleAction =
  | { type: "SET_INPUT_TEXT"; text: string }
  | { type: "SUBMIT_QUERY"; text: string }
  | { type: "PIPELINE_ROUTED"; releaseId: string }
  | { type: "AGENT_STATUS"; agent: string; agentName?: string; status: AgentStatus; text: string }
  | { type: "RUN_FINISHED" }
  | { type: "RUN_FAILED"; error: string }
  | { type: "CHAT_ANSWERED"; answer: string }
  | { type: "CHAT_FAILED"; error: string };

export function runConsoleReducer(state: RunConsoleState, action: RunConsoleAction): RunConsoleState {
  switch (action.type) {
    case "SET_INPUT_TEXT":
      return { ...state, inputText: action.text };

    case "SUBMIT_QUERY":
      // The raw text is shown exactly as typed and forwarded to the Master
      // Orchestrator unchanged — this component makes no guess about
      // whether it's a run request or a question; that comes back from
      // the server as either PIPELINE_ROUTED or CHAT_ANSWERED/CHAT_FAILED.
      return {
        ...state,
        sending: true,
        inputText: "",
        messages: [...state.messages, { id: nextId(), role: "user", text: action.text, time: now() }],
      };

    case "PIPELINE_ROUTED":
      // The Master decided this query is a full pipeline run for
      // releaseId — clear the previous run's agents entirely, since a new
      // run may involve a different set of agents, not the same ones
      // re-run in place.
      return {
        ...state,
        sending: false,
        running: true,
        agents: {},
        agentOrder: [],
        messages: [
          ...state.messages,
          { id: nextId(), role: "bot", text: `Running the Risk Tier pipeline for ${action.releaseId}…`, time: now() },
        ],
      };

    case "AGENT_STATUS": {
      const isNewAgent = !(action.agent in state.agents);
      // Post a transcript line for every real transition — including
      // repeated "running" updates with new text (e.g. sub-progress within
      // a single long-running agent), so the transcript always reflects
      // exactly what the backend just reported, with no batching.
      return {
        ...state,
        agents: {
          ...state.agents,
          [action.agent]: {
            agent: action.agent,
            agentName: action.agentName ?? state.agents[action.agent]?.agentName,
            status: action.status,
            text: action.text,
          },
        },
        agentOrder: isNewAgent ? [...state.agentOrder, action.agent] : state.agentOrder,
        messages: [...state.messages, { id: nextId(), role: "bot", text: action.text, time: now() }],
      };
    }

    case "RUN_FINISHED":
      return {
        ...state,
        running: false,
        messages: [
          ...state.messages,
          {
            id: nextId(),
            role: "bot",
            text: "Run complete — Test Selection, Exclusion Sign-off, and the Audit Log have all synced.",
            time: now(),
          },
        ],
      };

    case "RUN_FAILED":
      return {
        ...state,
        running: false,
        messages: [
          ...state.messages,
          {
            id: nextId(),
            role: "error",
            text: `Run failed — ${action.error}`,
            time: now(),
          },
        ],
      };

    case "CHAT_ANSWERED":
      return {
        ...state,
        sending: false,
        messages: [...state.messages, { id: nextId(), role: "bot", text: action.answer, time: now() }],
      };

    case "CHAT_FAILED":
      return {
        ...state,
        sending: false,
        messages: [...state.messages, { id: nextId(), role: "error", text: `Question failed — ${action.error}`, time: now() }],
      };

    default:
      return state;
  }
}
