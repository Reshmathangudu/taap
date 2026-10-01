import type { AgentCardState } from "./state";
import AgentCard from "./AgentCard";

interface AgentPipelineProps {
  /** Already in discovery order — first-seen-first-rendered, nothing else. */
  agents: AgentCardState[];
  running: boolean;
}

/**
 * Renders however many agent cards the backend has reported for the current
 * run, in the order they were first seen. Takes no fixed list, no assumed
 * count, no assumed order — a run involving 2 agents renders 2 cards, a run
 * involving 9 renders 9, and several can legitimately show "Running"
 * simultaneously since each card's status is independent.
 */
export default function AgentPipeline({ agents, running }: AgentPipelineProps) {
  const completedCount = agents.filter((a) => a.status === "finished").length;
  const runningAgents = agents.filter((a) => a.status === "running");
  const failedCount = agents.filter((a) => a.status === "failed").length;

  let summary: string;
  if (agents.length === 0) {
    summary = running ? "Waiting for the first agent to start…" : "Idle";
  } else {
    const parts = [`${completedCount} completed`];
    if (runningAgents.length) parts.push(`${runningAgents.length} running`);
    if (failedCount) parts.push(`${failedCount} failed`);
    summary = `${parts.join(", ")} — ${agents.length} agent${agents.length === 1 ? "" : "s"} involved so far`;
  }

  return (
    <div className="rta-rc-status">
      <h3>Agent Pipeline</h3>
      <div className="rta-rc-status-sub">{summary}</div>
      {agents.length === 0 && !running && (
        <p className="rta-rc-status-empty">No run started yet — enter a release ID and press Run.</p>
      )}
      {agents.map((card, i) => (
        <AgentCard key={card.agent} card={card} showConnector={i < agents.length - 1} />
      ))}
    </div>
  );
}
