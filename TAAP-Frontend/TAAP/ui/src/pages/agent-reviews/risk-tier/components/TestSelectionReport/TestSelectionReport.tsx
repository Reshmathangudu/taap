import { useEffect, useReducer, useState } from "react";
import { fetchAllTests } from "../../data/realApi";
import { resolveReleaseId } from "../../lib/currentRelease";
import { onAgentFinished } from "../../lib/runStatusBus";
import { initialState, testSelectionReducer, visibleTests } from "./state";
import TestList from "./TestList";
import TestDetail from "./TestDetail";
import "./TestSelectionReport.css";

/**
 * AGUI Panel — Test Selection & Risk Report
 *
 * This is one independent, embeddable component. It owns its own data
 * fetch and its own local state (via useReducer, since it juggles a
 * filter + search + selected-row + list/detail toggle — plain useState
 * would mean five separate calls tracking related state). It never reads
 * from or writes to ExclusionSignoffQueue or ExecutionAuditLog directly;
 * the only thing that crosses the boundary is the
 * `agui:navigate-to-signoff` event dispatched from TestDetail.
 *
 * It also independently subscribes to Agent 5 (Scoring) finishing via
 * runStatusBus — the same signal RunConsole renders as a chat line — and
 * refetches when that happens. This panel never talks to RunConsole
 * directly; both are just peers reacting to the same status stream.
 */
export default function TestSelectionReport() {
  const [state, dispatch] = useReducer(testSelectionReducer, initialState);
  const [flash, setFlash] = useState(false);
  const [releaseId, setReleaseId] = useState<string | null>(null);

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
      fetchAllTests(resolvedReleaseId)
        .then((tests) => { if (!cancelled) dispatch({ type: "LOAD_SUCCESS", tests }); })
        .catch((err) => { if (!cancelled) dispatch({ type: "LOAD_ERROR", error: String(err) }); });
    });
    return () => { cancelled = true; };
    // Deliberately mount-only: a live run updates releaseId via the
    // onAgentFinished subscription below, which re-fetches itself.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(
    () =>
      onAgentFinished("agent5", (finishedReleaseId) => {
        setReleaseId(finishedReleaseId);
        fetchAllTests(finishedReleaseId)
          .then((tests) => {
            dispatch({ type: "LOAD_SUCCESS", tests });
            setFlash(true);
            window.setTimeout(() => setFlash(false), 1400);
          })
          .catch((err) => dispatch({ type: "LOAD_ERROR", error: String(err) }));
      }),
    []
  );

  return (
    // .rta-ts establishes a container-query context sized to wherever
    // Spider actually places this panel; .rta-ts-inner is what responds to
    // that size (a container can't respond to a query on itself, only its
    // descendants — see TestSelectionReport.css).
    <div className={"rta-ts" + (flash ? " rta-flash" : "")}>
      <div className="rta-ts-inner">
        <div className="rta-ts-badgehead"><span className="dot" /><span>AGUI Panel · Test Selection &amp; Risk Report</span>{flash && <span className="rta-ts-live">Updated from Agent 5</span>}</div>

        {state.loading && <p className="rta-ts-subtitle">Loading test selection report…</p>}
        {state.error && <p style={{ color: "var(--danger)" }}>Failed to load: {state.error}</p>}

        {!state.loading && !state.error && state.view === "list" && (
          <TestList
            releaseId={releaseId}
            rows={visibleTests(state)}
            total={state.tests.length}
            filter={state.filter}
            search={state.search}
            onFilterChange={(filter) => dispatch({ type: "SET_FILTER", filter })}
            onSearchChange={(search) => dispatch({ type: "SET_SEARCH", search })}
            onOpen={(test) => dispatch({ type: "OPEN_DETAIL", test })}
          />
        )}

        {!state.loading && !state.error && state.view === "detail" && state.selected && (
          <TestDetail test={state.selected} onBack={() => dispatch({ type: "BACK_TO_LIST" })} />
        )}
      </div>
    </div>
  );
}
