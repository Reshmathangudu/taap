import { useEffect, useReducer, useState } from "react";
import { fetchAllTests, submitSignoff } from "../../data/realApi";
import { resolveReleaseId } from "../../lib/currentRelease";
import type { TestCase } from "../../types/testCase";
import { onNavigateToSignoff } from "../../lib/aguiEvents";
import { onAgentFinished } from "../../lib/runStatusBus";
import { initialState, signoffReducer } from "./state";
import SignoffModal from "./SignoffModal";
import "./ExclusionSignoffQueue.css";

interface ExclusionSummary {
  total: number;
  excludedOrOptional: number;
  low: number;
  medium: number;
  high: number;
}

function summarize(tests: TestCase[]): ExclusionSummary {
  const withExclusion = tests.filter((t) => t.exclusion);
  return {
    total: tests.length,
    excludedOrOptional: withExclusion.length,
    low: withExclusion.filter((t) => t.exclusion!.residual === "low").length,
    medium: withExclusion.filter((t) => t.exclusion!.residual === "medium").length,
    high: withExclusion.filter((t) => t.exclusion!.residual === "high").length,
  };
}

/**
 * AGUI Panel — Exclusion Sign-off
 *
 * The Governance Agent needs an interactive, human-in-the-loop surface
 * (BR-GOV-02) — that's the whole reason Level 2/AGUI was picked over
 * headless chat for this agent. This component owns the sign-off queue and
 * the sign-off modal, and never reaches into TestSelectionReport's state.
 *
 * It listens for `agui:navigate-to-signoff` purely as a convenience: if
 * TestSelectionReport happens to be mounted on the same page (which, per
 * the Level 2 design, is expected — Spider's Workbench hosts all three
 * panels together) and someone clicks through from a test's detail view,
 * this queue highlights and scrolls to the matching card. In production,
 * exactly what relays that signal (same-page CustomEvent vs. something
 * Spider's shell provides) is worth confirming with the platform team —
 * see src/lib/aguiEvents.ts.
 */
export default function ExclusionSignoffQueue() {
  const [state, dispatch] = useReducer(signoffReducer, initialState);
  const [flash, setFlash] = useState(false);
  const [releaseId, setReleaseId] = useState<string | null>(null);
  const [summary, setSummary] = useState<ExclusionSummary | null>(null);

  function loadFor(id: string, onDone?: () => void) {
    fetchAllTests(id)
      .then((tests) => {
        dispatch({ type: "LOAD_SUCCESS", queue: tests.filter((t) => t.exclusion?.status === "pending") });
        setSummary(summarize(tests));
        onDone?.();
      })
      .catch((err) => dispatch({ type: "LOAD_ERROR", error: String(err) }));
  }

  useEffect(() => {
    let cancelled = false;
    dispatch({ type: "LOAD_START" });
    resolveReleaseId().then((resolvedReleaseId) => {
      if (cancelled) return;
      if (!resolvedReleaseId) {
        dispatch({ type: "LOAD_ERROR", error: "No release analyzed yet — run one from the Run Console tab." });
        return;
      }
      setReleaseId(resolvedReleaseId);
      loadFor(resolvedReleaseId);
    });
    return () => { cancelled = true; };
    // Deliberately mount-only: a live run updates releaseId via the
    // onAgentFinished subscription below, which re-fetches itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => onNavigateToSignoff(({ testId }) => dispatch({ type: "HIGHLIGHT", testId })), []);

  // Independently subscribes to Agent 6 (Governance) finishing, same
  // pattern as TestSelectionReport's Agent 5 subscription — see runStatusBus.
  useEffect(
    () =>
      onAgentFinished("agent6", (finishedReleaseId) => {
        setReleaseId(finishedReleaseId);
        loadFor(finishedReleaseId, () => {
          setFlash(true);
          window.setTimeout(() => setFlash(false), 1400);
        });
      }),
    []
  );

  function handleConfirm(role: string, note: string) {
    if (!note) { dispatch({ type: "SUBMIT_NOTE_MISSING" }); return; }
    if (!state.modalTest || !releaseId) return;
    dispatch({ type: "SUBMIT_START" });
    submitSignoff(releaseId, state.modalTest.id, role, note)
      .then(() => {
        dispatch({ type: "SUBMIT_SUCCESS", testId: state.modalTest!.id });
      })
      .catch((err) => {
        dispatch({ type: "SUBMIT_ERROR", error: String(err) });
      });
  }

  const pendingCount = state.queue.length;

  return (
    // See TestSelectionReport.tsx for why content lives in an -inner
    // wrapper: .rta-gv establishes the container-query context sized to
    // this panel, and only a descendant of it can respond to that size.
    <div className={"rta-gv" + (flash ? " rta-flash" : "")}>
      <div className="rta-gv-inner">
        <div className="rta-gv-badgehead"><span className="dot" /><span>AGUI Panel · Exclusion Sign-off</span>{flash && <span className="rta-gv-live">Updated from Agent 6</span>}</div>

        <h1>Exclusion risk &amp; governance</h1>
        <p className="rta-gv-subtitle">
          Every excluded or optional test case carries a documented risk statement. Medium and High
          residual risk require human sign-off (BR-GOV-02) before the release suite finalizes.
        </p>

        <div className="panel">
          <h3>Aggregate exclusion summary <span className="muted">(BR-GOV-04)</span></h3>
          {summary ? (
            <>
              <p style={{ fontSize: 13, margin: "0 0 8px" }}>
                {summary.excludedOrOptional} of {summary.total} test cases classified Exclude or Optional
                {summary.total > 0 ? ` (${((summary.excludedOrOptional / summary.total) * 100).toFixed(1)}% of the suite)` : ""}.
              </p>
              <div style={{ display: "flex", gap: 3, height: 8, marginBottom: 6 }}>
                <div style={{ flex: summary.low, background: "var(--success-strong)", borderRadius: 4 }} title="Low residual risk" />
                <div style={{ flex: summary.medium, background: "var(--warn-strong)", borderRadius: 4 }} title="Medium residual risk" />
                <div style={{ flex: summary.high, background: "var(--danger-strong)", borderRadius: 4 }} title="High residual risk" />
              </div>
              <p style={{ fontSize: 11, color: "var(--text-2)", margin: 0 }}>
                {summary.low} Low · {summary.medium} Medium · {summary.high} High — {pendingCount} exclusion{pendingCount === 1 ? "" : "s"} still pending sign-off.
              </p>
            </>
          ) : (
            <p style={{ fontSize: 13, color: "var(--text-2)" }}>No data yet.</p>
          )}
        </div>

        <div className="panel">
          <h3>Sign-off queue</h3>
          {state.loading && <p style={{ fontSize: 13, color: "var(--text-2)" }}>Loading sign-off queue…</p>}
          {state.error && <p style={{ color: "var(--danger)" }}>Failed to load: {state.error}</p>}
          {!state.loading && !state.error && pendingCount === 0 && (
            <p style={{ fontSize: 13, color: "var(--text-2)" }}>No exclusions currently awaiting sign-off.</p>
          )}
          {!state.loading && !state.error && state.queue.map((t) => {
            const exclusion = t.exclusion!;
            const residualLabel = exclusion.residual.charAt(0).toUpperCase() + exclusion.residual.slice(1);
            return (
              <div
                key={t.id}
                className={"exclusion-card" + (t.id === state.highlightId ? " highlight" : "")}
                ref={(el) => { if (el && t.id === state.highlightId) el.scrollIntoView({ behavior: "smooth", block: "center" }); }}
              >
                <div className="exclusion-card-head">
                  <div>
                    <p className="exclusion-name">{t.id} — {t.name}</p>
                    <p className="exclusion-meta">{t.module} · Tier {t.tier}</p>
                  </div>
                  <span className={"badge risk-" + exclusion.residual}>{residualLabel} residual risk</span>
                </div>
                <div className="stat-row">
                  <div><span>Likelihood</span>{exclusion.likelihood}</div>
                  <div><span>Business impact</span>{exclusion.impact}</div>
                  <div><span>Requires</span>{exclusion.signoff}</div>
                </div>
                <div className="signoff-row">
                  <span className="badge pending">Pending sign-off</span>
                  <button className="btn sm primary" onClick={() => dispatch({ type: "OPEN_MODAL", test: t })}>
                    Sign off
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {state.modalTest && (
        <SignoffModal
          test={state.modalTest}
          submitting={state.submitting}
          noteError={state.noteError}
          submitError={state.submitError}
          onCancel={() => dispatch({ type: "CLOSE_MODAL" })}
          onConfirm={handleConfirm}
        />
      )}
    </div>
  );
}
