import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronLeft, ExternalLink, Search, SlidersHorizontal } from "lucide-react";
import { fetchJiraIssueGroups } from "@taap/service-layer";
import "./SdetDefectsScreen.css";

const FILTERS = ["All", "AI Drafted", "Manual", "Awaiting Retest"];

export function SdetDefectsScreen() {
  const [activeFilter, setActiveFilter] = useState("All");
  const [query, setQuery] = useState("");
  const [defects, setDefects] = useState([]);
  const [fetchedAt, setFetchedAt] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedDefect, setSelectedDefect] = useState(null);
  const [notice, setNotice] = useState("");

  useEffect(() => {
    let isMounted = true;

    async function loadDefects() {
      setIsLoading(true);
      setError("");

      try {
        const issueGroups = await fetchJiraIssueGroups({ limit: 100 });
        const jiraDefects = issueGroups.groups?.bugs?.issues ?? [];

        if (!isMounted) return;

        setDefects(jiraDefects.map(normalizeDefect));
        setFetchedAt(issueGroups.fetchedAt ?? "");
      } catch (loadError) {
        if (!isMounted) return;

        setError(loadError instanceof Error ? loadError.message : "Unable to load Jira defects.");
      } finally {
        if (isMounted) setIsLoading(false);
      }
    }

    loadDefects();

    return () => {
      isMounted = false;
    };
  }, []);

  const visibleDefects = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return defects.filter((defect) => {
      const matchesFilter = activeFilter === "All"
        || (activeFilter === "AI Drafted" && defect.tone === "draft")
        || (activeFilter === "Awaiting Retest" && defect.tone === "retest")
        || (activeFilter === "Manual" && defect.tone === "manual");
      const matchesQuery = !normalizedQuery
        || `${defect.id} ${defect.title} ${defect.source}`.toLowerCase().includes(normalizedQuery);
      return matchesFilter && matchesQuery;
    });
  }, [activeFilter, defects, query]);

  const awaitingSubmissionCount = defects.filter((defect) => defect.tone === "draft").length;
  const updatedLabel = fetchedAt ? `Updated ${formatRelativeTime(fetchedAt)}` : "Updated just now";

  if (selectedDefect) {
    return (
      <DefectReviewForm
        defect={selectedDefect}
        notice={notice}
        onBack={() => setSelectedDefect(null)}
        onSaveDraft={() => setNotice("Draft saved")}
        onSubmit={() => setNotice("Defect pushed to Jira")}
      />
    );
  }

  return (
    <section className="sdet-defects-screen" aria-label="Defects workspace">
      <header className="sdet-defects-header">
        <div>
          <div className="sdet-defects-breadcrumb">Execute <span>/</span> Defects</div>
          <h1>Defects</h1>
          <p>Review, submit, and track defects found during test execution.</p>
        </div>
        <button className="sdet-defects-primary-action" type="button">+ Log Defect</button>
      </header>

      <div className="sdet-defects-toolbar">
        <div className="sdet-defects-tabs" role="tablist" aria-label="Defect filters">
          {FILTERS.map((filter) => (
            <button
              className={activeFilter === filter ? "is-active" : ""}
              key={filter}
              onClick={() => setActiveFilter(filter)}
              role="tab"
              type="button"
              aria-selected={activeFilter === filter}
            >
              {filter}
              {filter === "All" && <span className="sdet-defects-tab-count">{defects.length}</span>}
            </button>
          ))}
        </div>
        <div className="sdet-defects-tools">
          <label className="sdet-defects-search">
            <Search size={15} aria-hidden="true" />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search defects" aria-label="Search defects" />
          </label>
          <button className="sdet-defects-filter-button" type="button"><SlidersHorizontal size={15} /> Filters <ChevronDown size={14} /></button>
        </div>
      </div>

      <div className="sdet-defects-summary">
        <span><strong>{visibleDefects.length}</strong> defects</span>
        <span className="sdet-defects-summary-divider" />
        <span><strong>{awaitingSubmissionCount}</strong> awaiting submission</span>
        <span className="sdet-defects-summary-spacer" />
        <span>{updatedLabel}</span>
      </div>

      <div className="sdet-defects-list">
        {isLoading && <div className="sdet-defects-empty">Loading defects from Jira...</div>}
        {!isLoading && error && (
          <div className="sdet-defects-empty sdet-defects-empty--error" role="alert">
            Unable to load defects from Jira. {error}
          </div>
        )}
        {!isLoading && !error && visibleDefects.map((defect) => (
          <article className="sdet-defect-card" key={defect.id}>
            <div className="sdet-defect-card__main">
              <div className="sdet-defect-card__title-row">
                <span className="sdet-defect-id">{defect.id}</span>
                <h2>{defect.title}</h2>
              </div>
              <p className="sdet-defect-source">From <strong>{defect.source}</strong></p>
              <button className="sdet-defect-action" type="button" onClick={() => setSelectedDefect(defect)}>{defect.action}</button>
            </div>
            <div className="sdet-defect-card__meta">
              <span className={`sdet-defect-status sdet-defect-status--${defect.tone}`}>{defect.status}</span>
              <span className="sdet-defect-detail">{defect.detail}</span>
              {defect.url && (
                <a className="sdet-defect-open" href={defect.url} target="_blank" rel="noreferrer" aria-label={`Open ${defect.id} in Jira`} title={`Open ${defect.id} in Jira`}><ExternalLink size={15} /></a>
              )}
            </div>
          </article>
        ))}
        {!isLoading && !error && visibleDefects.length === 0 && <div className="sdet-defects-empty">No defects match this view.</div>}
      </div>
    </section>
  );
}

function DefectReviewForm({ defect, notice, onBack, onSaveDraft, onSubmit }) {
  const [formData, setFormData] = useState({
    summary: defect.title,
    steps: defect.stepsToReproduce.join("\n"),
    expected: defect.expectedResult,
    actual: defect.actualResult,
    environment: defect.environment
  });

  function updateField(event) {
    setFormData((current) => ({ ...current, [event.target.name]: event.target.value }));
  }

  return (
    <section className="sdet-defect-review" aria-label="Review defect">
      <header className="sdet-defect-review__header">
        <button className="sdet-defect-review__back" type="button" onClick={onBack}><ChevronLeft size={14} /> Back</button>
        <div className="sdet-defect-review__title-row">
          <span className="sdet-defect-id">{defect.id}</span>
          <h1>{formData.summary}</h1>
          <span className="sdet-defect-review__badge">{defect.tone === "draft" ? "AI DRAFTED" : defect.status.toUpperCase()}</span>
        </div>
        <p>From {defect.source} · Severity {defect.severity}</p>
      </header>

      <form className="sdet-defect-review__form" onSubmit={(event) => { event.preventDefault(); onSubmit(); }}>
        <label>SUMMARY<textarea name="summary" value={formData.summary} onChange={updateField} rows="1" /></label>
        <label>STEPS TO REPRODUCE<textarea name="steps" value={formData.steps} onChange={updateField} rows="3" /></label>
        <div className="sdet-defect-review__split-fields">
          <label>EXPECTED RESULT<textarea name="expected" value={formData.expected} onChange={updateField} rows="2" /></label>
          <label>ACTUAL RESULT<textarea name="actual" value={formData.actual} onChange={updateField} rows="2" /></label>
        </div>
        <label>ENVIRONMENT<textarea name="environment" value={formData.environment} onChange={updateField} rows="1" /></label>
        <div className="sdet-defect-review__actions">
          <button type="button" onClick={onSaveDraft}>Save Draft</button>
          <button className="sdet-defect-review__submit" type="submit">Push to Jira</button>
          {notice && <span role="status">{notice}</span>}
        </div>
      </form>
    </section>
  );
}

function normalizeDefect(issue) {
  const status = issue.status || "Unknown";
  const normalizedStatus = status.toLowerCase();
  const isRetest = normalizedStatus.includes("retest") || normalizedStatus.includes("ready for qa");
  const isDraft = normalizedStatus.includes("draft") || normalizedStatus.includes("triage");

  return {
    id: issue.key || issue.id,
    title: issue.summary || "Untitled Jira defect",
    source: issue.labels?.length ? issue.labels.join(" · ") : "Jira",
    status,
    detail: `${status}${issue.priority ? ` · ${issue.priority}` : ""}`,
    action: isDraft ? "Review & Submit" : "View Defect",
    tone: isDraft ? "draft" : isRetest ? "retest" : "manual",
    url: issue.url,
    severity: issue.severity || issue.priority || "Not provided",
    stepsToReproduce: Array.isArray(issue.stepsToReproduce)
      ? issue.stepsToReproduce
      : issue.description ? [issue.description] : [],
    expectedResult: issue.expectedResult || "Not provided by Jira",
    actualResult: issue.actualResult || "Not provided by Jira",
    environment: issue.environment || "Not provided"
  };
}

function formatRelativeTime(value) {
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "just now";

  const minutes = Math.max(0, Math.round((Date.now() - timestamp) / 60000));
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;

  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}