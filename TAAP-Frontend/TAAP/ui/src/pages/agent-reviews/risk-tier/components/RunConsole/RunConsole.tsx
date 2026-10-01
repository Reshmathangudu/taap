import { useEffect, useReducer, useRef } from "react";
import { onAgentStatus, onRunLifecycle, sendMasterQuery } from "../../lib/runStatusBus";
import { initialState, runConsoleReducer } from "./state";
import AgentPipeline from "./AgentPipeline";
import { agentLabel } from "./agentLabel";
import "./RunConsole.css";

/**
 * AGUI Panel — Run Console
 *
 * One unified input: the raw text is forwarded to the LLM-driven Master
 * Orchestrator exactly as typed via sendMasterQuery (POST /agui/chat) — this
 * component makes no decision about what it means. The Master itself decides
 * whether it's a release-analysis request (it stages the release context,
 * then transfers to the risk_tier_pipeline sub-agent, which streams live
 * progress through AG-UI exactly like before — see src/lib/runStatusBus.ts)
 * or a drill-down question (answered directly in its own reply text). Since
 * that decision now happens mid-stream inside one call rather than being
 * signaled upfront, this component watches for the first live agent_status
 * event of a given call to detect that a run started, rather than being told
 * so by a prior classify step. This panel is a peer of the other three
 * panels, not their parent: it never calls into TestSelectionReport,
 * ExclusionSignoffQueue, or ExecutionAuditLog directly. All four panels
 * independently subscribe to the same status stream and each reacts only to
 * the one agent it cares about.
 *
 * The agent pipeline below (AgentPipeline/AgentCard) is fully event-driven:
 * it renders whatever agents the backend actually reports for this run, in
 * whatever order and however many there are — nothing here assumes a fixed
 * list, a fixed count, or a fixed sequence, and multiple agents can be
 * "Running" at once. Today's backend happens to always report the same 8
 * agents in the same sequential order (that's a real property of
 * RiskTierMasterOrchestrator, not a frontend assumption) — a future backend
 * reporting a different set, additional agents, or concurrent agents would
 * render correctly here with no code changes.
 *
 * Visual design (dark theme, connected-dot timeline, chat bubbles) follows
 * Main-html/Main.dc.html, a design-tool mockup — see that folder's README.
 */
export default function RunConsole() {
  const [state, dispatch] = useReducer(runConsoleReducer, initialState);
  const transcriptRef = useRef<HTMLDivElement>(null);

  useEffect(
    () =>
      onAgentStatus(({ agent, agentName, status, text }) => {
        dispatch({ type: "AGENT_STATUS", agent, agentName, status, text });
      }),
    []
  );

  useEffect(
    () =>
      onRunLifecycle(({ phase, error }) => {
        if (phase === "finished") dispatch({ type: "RUN_FINISHED" });
        else if (phase === "failed") dispatch({ type: "RUN_FAILED", error: error ?? "Unknown error" });
      }),
    []
  );

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: "smooth" });
  }, [state.messages.length, state.running]);

  function handleSubmit() {
    if (state.running || state.sending) return;
    const trimmed = state.inputText.trim();
    if (!trimmed) return;

    dispatch({ type: "SUBMIT_QUERY", text: trimmed });

    // The Master Orchestrator decides mid-stream whether this needs the full
    // pipeline — there's no upfront classify response telling us that
    // anymore. Watch for this call's first live agent_status event instead:
    // that's the signal a run actually started, so the transcript can switch
    // from "sending" to the live progress view at that point.
    let sawAgentStatus = false;
    const unsubscribe = onAgentStatus((detail) => {
      if (!sawAgentStatus) {
        sawAgentStatus = true;
        dispatch({ type: "PIPELINE_ROUTED", releaseId: detail.releaseId });
      }
    });

    sendMasterQuery(trimmed)
      .then((answer) => {
        if (answer) dispatch({ type: "CHAT_ANSWERED", answer });
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        if (sawAgentStatus) dispatch({ type: "RUN_FAILED", error: message });
        else dispatch({ type: "CHAT_FAILED", error: message });
      })
      .finally(() => unsubscribe());
  }

  // Derived purely from whatever agents have actually been reported this
  // run — agentOrder is discovery order, not a predefined sequence.
  const agentCards = state.agentOrder.map((key) => state.agents[key]);
  const completedCount = agentCards.filter((a) => a.status === "finished").length;
  const runningAgents = agentCards.filter((a) => a.status === "running");
  const totalKnown = agentCards.length;
  const percent = totalKnown === 0 ? 0 : Math.round((completedCount / totalKnown) * 100);

  return (
    // .rta-rc establishes the container-query context sized to this panel;
    // see TestSelectionReport.css for why an -inner wrapper is needed.
    <div className="rta-rc">
      <div className="rta-rc-inner">
        <div className="rta-rc-topbar">
          <div className="rta-rc-brand">
            <span className="rta-rc-brand-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="5" r="2.1"/><circle cx="5" cy="19" r="2.1"/><circle cx="19" cy="19" r="2.1"/><path d="M12 7.1V12M12 12l-5.6 5.1M12 12l5.6 5.1"/></svg>
            </span>
            <div>
              <div className="rta-rc-brand-title">RiskTier Console</div>
              <div className="rta-rc-brand-subtitle">Regression Risk Assistant</div>
            </div>
          </div>
          <div className={"rta-rc-streambadge" + (state.running ? " live" : "")}>
            <span className="mono">AG-UI</span>
            <span className="rta-rc-streamdot" />
            <span>{state.running ? "Streaming" : "Idle"}</span>
          </div>
        </div>

        <p className="rta-rc-subtitle">
          One box for everything: say "analyze release 25.4" (any phrasing works — the Master
          Orchestrator itself decides what you mean) to kick off a live run, streamed here as the
          backend actually reports it, with Test Selection, Exclusion Sign-off, and the Audit Log
          panels refreshing themselves the moment their agent finishes — or just ask a question.
        </p>

        <div className="rta-rc-body">
          <div className="rta-rc-transcript" ref={transcriptRef}>
            {state.messages.map((m) => (
              <div key={m.id} className={"rta-rc-msg " + m.role}>
                {(m.role === "bot" || m.role === "error") && (
                  <span className="rta-rc-msg-avatar" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="5" r="2.1"/><circle cx="5" cy="19" r="2.1"/><circle cx="19" cy="19" r="2.1"/><path d="M12 7.1V12M12 12l-5.6 5.1M12 12l5.6 5.1"/></svg>
                  </span>
                )}
                <div className="rta-rc-msg-bubble">
                  <span className="rta-rc-msg-text">{m.text}</span>
                  {m.time && <span className="rta-rc-msg-time">{m.time}</span>}
                </div>
              </div>
            ))}

            {state.running && (
              <div className="rta-rc-msg bot">
                <span className="rta-rc-msg-avatar" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="5" r="2.1"/><circle cx="5" cy="19" r="2.1"/><circle cx="19" cy="19" r="2.1"/><path d="M12 7.1V12M12 12l-5.6 5.1M12 12l5.6 5.1"/></svg>
                </span>
                <div className="rta-rc-msg-bubble rta-rc-progresscard">
                  <div className="rta-rc-progresshead">
                    <span className="spin" aria-hidden="true">
                      <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M12 3a9 9 0 1 0 9 9"/></svg>
                    </span>
                    <span>
                      Running regression risk analysis<span className="blink">…</span>
                    </span>
                  </div>
                  <div className="rta-rc-progressbar">
                    <div className="rta-rc-progressfill" style={{ width: `${percent}%` }} />
                  </div>
                  <div className="rta-rc-progresscaption">
                    {totalKnown === 0
                      ? "Waiting for the first agent to start…"
                      : `${completedCount} of ${totalKnown} agents complete` +
                        (runningAgents.length ? ` · ${runningAgents.map((a) => a.agentName || agentLabel(a.agent)).join(", ")} running` : "")}
                  </div>
                  <div className="mono rta-rc-log">
                    {agentCards.map((a) => (
                      <div key={a.agent} className={a.status === "running" ? "running" : ""}>
                        &gt; {a.agentName || agentLabel(a.agent)} — {a.status === "finished" ? "STEP_FINISHED" : a.status === "failed" ? "STEP_FAILED" : a.text || "running…"}
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>

          <AgentPipeline agents={agentCards} running={state.running} />
        </div>

        <div className="rta-rc-inputrow">
          <input
            className="rta-rc-input"
            value={state.inputText}
            onChange={(e) => dispatch({ type: "SET_INPUT_TEXT", text: e.target.value })}
            placeholder='Type anything — "analyze release 25.4", or a question about the last analyzed release…'
            disabled={state.running || state.sending}
            onKeyDown={(e) => {
              if (e.key === "Enter") handleSubmit();
            }}
          />
          <button
            className="rta-rc-sendbtn"
            onClick={handleSubmit}
            disabled={state.running || state.sending || !state.inputText.trim()}
            aria-label="Send"
          >
            {state.running || state.sending ? (
              <span className="spin" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"><path d="M12 3a9 9 0 1 0 9 9"/></svg>
              </span>
            ) : (
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
