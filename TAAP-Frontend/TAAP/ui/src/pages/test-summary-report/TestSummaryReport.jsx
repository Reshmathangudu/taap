import { useCallback, useEffect, useState } from "react";
import { Check, FileText, Pencil, RefreshCw, Upload } from "lucide-react";
import { fetchJiraIssueGroups } from "@taap/service-layer";
import "./TestSummaryReport.css";

const fallbackTraceabilityRows = [
  { story: "US-458", cases: 12, executed: 10, passed: 8, defects: 2, coverage: 83, tone: "green" },
  { story: "US-441", cases: 10, executed: 4, passed: 4, defects: 0, coverage: 40, tone: "amber" },
  { story: "US-461", cases: 6, executed: 3, passed: 2, defects: 1, coverage: 50, tone: "amber" },
  { story: "US-462", cases: 11, executed: 11, passed: 11, defects: 0, coverage: 100, tone: "green" },
  { story: "US-470", cases: 8, executed: 6, passed: 6, defects: 0, coverage: 75, tone: "green" },
  { story: "US-473", cases: 5, executed: 0, passed: 0, defects: 0, coverage: 0, tone: "red" }
];

function buildTraceabilityRows(issueGroups) {
  const stories = issueGroups.groups?.stories?.issues ?? [];
  const bugs = issueGroups.groups?.bugs?.issues ?? [];

  return stories.map((story) => {
    const linkedBugs = bugs.filter((bug) => bug.parentKey === story.key);
    const cases = Number(story.testCases ?? story.cases ?? 0);
    const executed = Number(story.executed ?? 0);
    const passed = Number(story.passed ?? 0);
    const coverage = cases > 0 ? Math.round((executed / cases) * 100) : 0;

    return {
      story: story.key,
      cases,
      executed,
      passed,
      defects: linkedBugs.length,
      coverage,
      tone: coverage >= 75 ? "green" : coverage > 0 ? "amber" : "red"
    };
  });
}

function CornerFrame({ children, className = "" }) {
  return <div className={`summary-corner-frame ${className}`}>{children}</div>;
}

export function TestSummaryReport() {
  const [issueGroups, setIssueGroups] = useState(null);
  const [syncError, setSyncError] = useState("");
  const [isSyncing, setIsSyncing] = useState(false);

  const syncJira = useCallback(async () => {
    setIsSyncing(true);
    setSyncError("");

    try {
      const data = await fetchJiraIssueGroups({ limit: 100 });
      setIssueGroups(data);
    } catch (error) {
      setSyncError(error instanceof Error ? error.message : "Unable to sync Jira data.");
    } finally {
      setIsSyncing(false);
    }
  }, []);

  useEffect(() => {
    syncJira();
  }, [syncJira]);

  const traceabilityRows = issueGroups ? buildTraceabilityRows(issueGroups) : fallbackTraceabilityRows;
  const syncedFromJira = issueGroups?.source === "jira" && !syncError;
  const storyCount = issueGroups?.groups?.stories?.issues?.length ?? traceabilityRows.length;
  const bugCount = issueGroups?.groups?.bugs?.issues?.length ?? 0;

  return (
    <section className="test-summary-report" aria-label="Test Summary Report">
      <header className="test-summary-report__header">
        <div>
          <p className="test-summary-report__eyebrow">Agents &amp; report</p>
          <h1>Test Summary Report</h1>
        </div>
        <div className="test-summary-report__meta">
          <FileText size={17} strokeWidth={1.7} />
          <span>Release R25.4</span>
          <span className="test-summary-report__meta-divider" />
          <span>{syncedFromJira ? `Jira synced ${new Date(issueGroups.fetchedAt).toLocaleTimeString()}` : "Jira sync pending"}</span>
        </div>
      </header>

      <div className="test-summary-report__body">
        <div className="test-summary-report__overview">
          <CornerFrame className="summary-status-card">
            <div className="summary-card-heading">
              <p>Daily status - today</p>
              <span className="summary-draft-badge">Drafted by Reporting Agent</span>
            </div>
            <ul className="summary-status-list">
              <li>Executed 5 of 8 planned manual runs - 4 passed, 1 failed (TC-1091, accessibility).</li>
              <li>Logged BUG-801 (High) from the failed run; BUG-799 (High) still blocks guest gift-card checkout.</li>
              <li>BUG-783 fix deployed to QA on build 24.8.183 - retest scheduled today.</li>
              <li>Test data and QA environment healthy; Staging degraded but outside today&apos;s scope.</li>
            </ul>
            <div className="summary-card-actions">
              <button type="button" className="summary-button summary-button--secondary"><Pencil size={14} />Edit draft</button>
              <button type="button" className="summary-button summary-button--primary"><Check size={14} />Approve &amp; post to Teams</button>
            </div>
          </CornerFrame>

          <CornerFrame className="summary-week-card">
            <p className="summary-section-label">Weekly test summary - sprint 18</p>
            <dl className="summary-metrics">
              <div><dt>Planned runs executed</dt><dd>38 / 46</dd></div>
              <div><dt>Manual pass rate</dt><dd>93%</dd></div>
              <div><dt>New defects</dt><dd>9 <span>- 3 critical</span></dd></div>
              <div><dt>Retests closed</dt><dd>6</dd></div>
            </dl>
            <div className="summary-card-actions">
              <button type="button" className="summary-button summary-button--secondary"><Pencil size={14} />Draft with Agent</button>
              <button type="button" className="summary-text-button"><Upload size={14} />Export to Confluence</button>
            </div>
          </CornerFrame>
        </div>

        <section className="traceability-section" aria-labelledby="traceability-heading">
          <div className="traceability-heading-row">
            <h2 id="traceability-heading">Traceability matrix - requirement to execution</h2>
            <span>{storyCount} stories / {bugCount} bugs from Jira</span>
          </div>
          <div className="traceability-table-wrap">
            <table className="traceability-table">
              <thead>
                <tr><th>Story</th><th>Cases</th><th>Executed</th><th>Passed</th><th>Open defects</th><th>Coverage</th></tr>
              </thead>
              <tbody>
                {traceabilityRows.map((row) => (
                  <tr key={row.story}>
                    <td className="traceability-story">{row.story}</td>
                    <td>{row.cases}</td>
                    <td>{row.executed}</td>
                    <td>{row.passed}</td>
                    <td>{row.defects}</td>
                    <td>
                      <div className="coverage-cell">
                        <div className="coverage-track"><span className={`coverage-fill coverage-fill--${row.tone}`} style={{ width: `${row.coverage}%` }} /></div>
                        <span className={`coverage-value coverage-value--${row.tone}`}>{row.coverage}%</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <footer className="traceability-footer">
            <span>Auto-updated after every manual and agent run.</span>
            <button type="button" onClick={syncJira} disabled={isSyncing}>
              <RefreshCw size={14} className={isSyncing ? "summary-spin" : ""} />
              {isSyncing ? "Syncing Jira..." : "Sync from Jira"}
            </button>
          </footer>
          {syncError && <p className="traceability-sync-error">{syncError}</p>}
        </section>
      </div>
    </section>
  );
}
