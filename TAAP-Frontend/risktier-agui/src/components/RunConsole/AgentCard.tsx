import type { AgentCardState } from "./state";
import { agentLabel } from "./agentLabel";

const STATUS_CAPTION: Record<AgentCardState["status"], string> = {
  pending: "Pending",
  running: "Running",
  finished: "Completed",
  failed: "Failed",
};

interface AgentCardProps {
  card: AgentCardState;
  /** Whether to draw the connector line to the next card (false for the last one). */
  showConnector: boolean;
}

/**
 * One row in the dynamic agent pipeline timeline. Purely presentational —
 * takes whatever card state it's given and renders it; it has no idea how
 * many agents exist, what order they're in, or what any of them are called.
 */
export default function AgentCard({ card, showConnector }: AgentCardProps) {
  const { status } = card;
  return (
    <div className="rta-rc-timeline-row">
      <div className="rta-rc-timeline-dotcol">
        <span className={"rta-rc-dot dot-" + status}>
          {status === "finished" && (
            <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M4 12.5l4.5 4.5L20 6"/></svg>
          )}
          {status === "running" && (
            <span className="spin" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M12 3a9 9 0 1 0 9 9"/></svg>
            </span>
          )}
          {status === "failed" && (
            <svg viewBox="0 0 24 24" width="11" height="11" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M6 6l12 12M18 6L6 18"/></svg>
          )}
        </span>
        {showConnector && <span className={"rta-rc-connector connector-" + status} />}
      </div>
      <div className="rta-rc-timeline-body">
        <div className="rta-rc-timeline-label">{card.agentName || agentLabel(card.agent)}</div>
        <div className={"rta-rc-timeline-caption caption-" + status}>{STATUS_CAPTION[status]}</div>
        {status === "running" && card.text && <div className="rta-rc-timeline-detail">{card.text}</div>}
      </div>
    </div>
  );
}
