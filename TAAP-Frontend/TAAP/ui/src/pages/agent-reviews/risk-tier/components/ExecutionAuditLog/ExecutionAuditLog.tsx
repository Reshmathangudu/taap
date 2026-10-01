import { useEffect, useState } from "react";
import type { AuditEntry, FeedbackItem } from "../../types/testCase";
import { fetchAuditLog, fetchFeedbackLoop } from "../../data/realApi";
import { resolveReleaseId } from "../../lib/currentRelease";
import { onAgentFinished } from "../../lib/runStatusBus";
import "./ExecutionAuditLog.css";

/**
 * AGUI Panel — Execution Audit Log
 *
 * Read-only: no sign-off action, no drill-down, nothing another panel
 * needs to react to. A plain useState pair is enough here — useReducer
 * earns its keep when there are several related pieces of state changing
 * together (see TestSelectionReport / ExclusionSignoffQueue), not for a
 * component that just renders what it fetched.
 *
 * Subscribes to the "ledger" step finishing, not any single agent — the
 * Immutable Audit Ledger aggregates all 7 agents' decisions (see the
 * Panel-to-Agent Mapping table in the AGUI integration addendum), so this
 * is the one panel that refreshes on the pipeline's last step rather than
 * on Agent 5 or Agent 6 specifically.
 */
export default function ExecutionAuditLog() {
  const [entries, setEntries] = useState<AuditEntry[] | null>(null);
  const [feedback, setFeedback] = useState<FeedbackItem[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState(false);
  const [releaseId, setReleaseId] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    resolveReleaseId().then((resolvedReleaseId) => {
      if (cancelled) return;
      if (!resolvedReleaseId) {
        setError("No release analyzed yet — run one from the Run Console tab.");
        return;
      }
      setReleaseId(resolvedReleaseId);
      Promise.all([fetchAuditLog(resolvedReleaseId), fetchFeedbackLoop(resolvedReleaseId)])
        .then(([e, f]) => {
          if (!cancelled) { setEntries(e); setFeedback(f); setError(null); }
        })
        .catch((err) => { if (!cancelled) setError(String(err)); });
    });
    return () => { cancelled = true; };
    // Deliberately mount-only: a live run updates releaseId via the
    // onAgentFinished subscription below, which re-fetches itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(
    () =>
      onAgentFinished("ledger", (finishedReleaseId) => {
        setReleaseId(finishedReleaseId);
        Promise.all([fetchAuditLog(finishedReleaseId), fetchFeedbackLoop(finishedReleaseId)])
          .then(([e, f]) => {
            setEntries(e);
            setFeedback(f);
            setError(null);
            setFlash(true);
            window.setTimeout(() => setFlash(false), 1400);
          })
          .catch((err) => setError(String(err)));
      }),
    []
  );

  return (
    // See TestSelectionReport.tsx for why content lives in an -inner
    // wrapper: .rta-al establishes the container-query context sized to
    // this panel, and only a descendant of it can respond to that size.
    <div className={"rta-al" + (flash ? " rta-flash" : "")}>
      <div className="rta-al-inner">
        <div className="rta-al-badgehead"><span className="dot" /><span>AGUI Panel · Execution Audit Log</span>{flash && <span className="rta-al-live">Updated from Ledger</span>}</div>

        <h1>Execution audit log &amp; feedback loop</h1>
        <p className="rta-al-subtitle">Every decision is traceable to a specific rule, agent, and data point.</p>

        <div className="panel">
          <h3>Execution audit log{releaseId ? ` — ${releaseId}` : ""}</h3>
          {error && <p style={{ color: "var(--danger)" }}>{error}</p>}
          {!error && entries === null && <p style={{ fontSize: 13, color: "var(--text-2)" }}>Loading audit log…</p>}
          {!error && entries?.length === 0 && <p style={{ fontSize: 13, color: "var(--text-2)" }}>No audit entries yet.</p>}
          {entries?.map((e, i) => (
            <div className="audit-entry" key={i}>
              <span className="audit-time">{e.time}</span>
              <span className="audit-agent">{e.agent}</span>
              <span>{e.message}</span>
            </div>
          ))}
        </div>

        <div className="panel">
          <h3>Post-release feedback loop <span className="muted">(BR-GOV-03)</span></h3>
          {feedback?.map((f, i) => (
            <div className="feedback-item" key={i}>
              <p><strong>{f.title}:</strong> {f.body}</p>
            </div>
          ))}
          <p style={{ fontSize: 11, color: "var(--text-3)", margin: 0 }}>
            This monitoring loop runs automatically for every release and cannot be disabled (GR-GOV-02).
          </p>
        </div>
      </div>
    </div>
  );
}
