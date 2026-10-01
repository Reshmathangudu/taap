import { useState } from "react";
import RunConsole from "./components/RunConsole/RunConsole";
import TestSelectionReport from "./components/TestSelectionReport/TestSelectionReport";
import ExclusionSignoffQueue from "./components/ExclusionSignoffQueue/ExclusionSignoffQueue";
import ExecutionAuditLog from "./components/ExecutionAuditLog/ExecutionAuditLog";
import PerformanceMetrics from "./components/PerformanceMetrics/PerformanceMetrics";
import { useHasReleaseId } from "./lib/useHasReleaseId";
import "./App.css";

// This file is a LOCAL DEV/DEMO SHELL ONLY — it is not part of what ships
// to Spider. In the real Workbench, Spider's own shell decides where and
// how each of the four panels below gets mounted; this app just gives you
// somewhere to see and click through all four during development, tabbed
// so you can confirm each one truly works standalone (switch tabs and each
// panel keeps its own state — nothing here wires them together beyond the
// shared signals each panel already subscribes to on its own: the
// agui:navigate-to-signoff event between TestSelectionReport and
// ExclusionSignoffQueue, and the runStatusBus status stream that
// RunConsole publishes into and the other three panels each independently
// listen to for their own agent finishing).
//
// Run Console sits leftmost, matching the requested tab order — it's the
// entry point of the workflow (trigger a run), so it reads left-to-right
// before the three panels that display what that run produced.
//
// Each panel mounts lazily, the first time its tab is actually clicked —
// not eagerly on page load — so a panel's own data fetch only fires once
// the user asks to see it. After that first visit, it stays mounted for
// the rest of this dev shell's lifetime, and tab-switching only toggles
// which one is visible (via the `hidden` attribute) rather than
// unmounting/remounting on every switch. This matters for this specific
// shell: if a run is started while only the Run Console tab is showing,
// TestSelectionReport/ExclusionSignoffQueue/ExecutionAuditLog still need
// to stay mounted once visited to catch their onAgentFinished signal and
// refetch — and switching back to their tab afterward must show what they
// already loaded instantly, not remount and refetch from scratch. (The
// real Spider host mounts panels according to its own layout, which this
// local shell doesn't need to replicate exactly — it only needs to not
// fetch before the user has asked to see a panel, and not lose state on
// its own tab switches.)

type Tab = "run-console" | "test-selection" | "exclusion-signoff" | "audit-log" | "all-four" | "performance-metrics";

const PANEL_TABS: Exclude<Tab, "all-four" | "performance-metrics">[] = [
  "run-console",
  "test-selection",
  "exclusion-signoff",
  "audit-log",
];

const TABS: { id: Tab; label: string; dependsOnReleaseId?: boolean }[] = [
  { id: "run-console", label: "Run Console" },
  { id: "test-selection", label: "Test Selection & Risk Report", dependsOnReleaseId: true },
  { id: "exclusion-signoff", label: "Exclusion Sign-off", dependsOnReleaseId: true },
  { id: "audit-log", label: "Execution Audit Log", dependsOnReleaseId: true },
  { id: "performance-metrics", label: "Performance Metrics" },
  { id: "all-four", label: "All Four " },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("run-console");
  // Which panels have been visited at least once — only these are mounted.
  // Seeded with the initial tab so the first-rendered panel doesn't need an
  // extra click to appear.
  const [visited, setVisited] = useState<Set<Tab>>(() => new Set(["run-console"]));
  const allFour = tab === "all-four";
  // Session-based gating: these three panels only mean anything once a full
  // pipeline run has produced a release ID (see requirement #7) — before
  // that, their tabs stay disabled rather than switching to a panel that
  // can only show "No release analyzed yet".
  const hasReleaseId = useHasReleaseId();

  const selectTab = (id: Tab) => {
    setTab(id);
    setVisited((prev) => {
      // Selecting "All four" is itself the user's click asking to see every
      // panel, so it marks all of them visited at once.
      const toAdd = id === "all-four" ? PANEL_TABS : [id];
      const next = new Set(prev);
      for (const panelId of toAdd) next.add(panelId);
      return next;
    });
  };

  return (
    <div className="dev-shell">
      <header className="dev-shell-header">
        <div className="dev-shell-title">Risk Tier Agent — AGUI components (local dev shell)</div>
        <nav className="dev-shell-tabs">
          {TABS.map((t) => {
            const disabled = t.dependsOnReleaseId && !hasReleaseId;
            return (
              <button
                key={t.id}
                className={"dev-shell-tab" + (tab === t.id ? " active" : "")}
                onClick={() => selectTab(t.id)}
                disabled={disabled}
                title={disabled ? "Run a release from the Run Console tab first" : undefined}
              >
                {t.label}
              </button>
            );
          })}
        </nav>
      </header>

      <main className="dev-shell-main">
        <div className={"dev-shell-grid" + (allFour ? " multi" : "")}>
          <div hidden={!(allFour || tab === "run-console")}>
            {visited.has("run-console") && <RunConsole />}
          </div>
          <div hidden={!(allFour || tab === "test-selection")}>
            {visited.has("test-selection") && <TestSelectionReport />}
          </div>
          <div hidden={!(allFour || tab === "exclusion-signoff")}>
            {visited.has("exclusion-signoff") && <ExclusionSignoffQueue />}
          </div>
          <div hidden={!(allFour || tab === "audit-log")}>
            {visited.has("audit-log") && <ExecutionAuditLog />}
          </div>
          <div hidden={!(allFour || tab === "performance-metrics")}>
            {visited.has("performance-metrics") && <PerformanceMetrics />}
          </div>
        </div>
      </main>
    </div>
  );
}
