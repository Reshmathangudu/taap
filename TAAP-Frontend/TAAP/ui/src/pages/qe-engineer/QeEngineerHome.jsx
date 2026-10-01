import { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronLeft, ChevronRight, Search } from "lucide-react";
import "./QeEngineerHome.css";

const issuePageSize = 10;

function AppSummaryHeader({ project }) {
  return (
    <div className="mock-app-header">
      {/* <div className="mock-app-icon">{project.id}</div> */}
      <div>
        <h1>{project.name}</h1>
      </div>
    </div>
  );
}

function MetricCard({ metric }) {
  return (
    <article className={`metric-card metric-card--${metric.accent}`}>
      <span className="metric-card__label">
        <i />
        {metric.label}
      </span>
      <strong>{metric.value}</strong>
      <p>{metric.detail}</p>
      <div className="metric-card__progress">
        <span>{metric.progressPercent}%</span>
        <div
          className="progress-track"
          role="progressbar"
          aria-label={`${metric.label} progress`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={metric.progressPercent}
        >
        <span style={{ width: `${metric.progressPercent}%` }} />
        </div>
      </div>
    </article>
  );
}

function StatusPill({ children, tone = "neutral" }) {
  return <span className={`status-pill status-pill--${tone}`}>{children}</span>;
}

function toneFor(value) {
  if (["Critical", "P1", "High", "Open", "Blocked"].includes(value)) {
    return "high";
  }

  if (["Ready for Testing", "Ready for Retest", "Ready for QA", "In QA", "In Progress", "Medium", "P2", "P3"].includes(value)) {
    return "medium";
  }

  if (["Done", "Passed", "Low"].includes(value)) {
    return "low";
  }

  return "neutral";
}

function EpicCard({ epic }) {
  return (
    <article className="epic-card">
      <div className="epic-card__top">
        <span>{epic.key}</span>
        <StatusPill tone={toneFor(epic.status)}>{epic.status}</StatusPill>
      </div>
      <h3>{epic.title}</h3>
      <div className="progress-track" aria-hidden="true">
        <span style={{ width: `${epic.progressPercent}%` }} />
      </div>
      <p>
        {epic.childIssueSummary}
        <span>{epic.targetRelease}</span>
      </p>
    </article>
  );
}

function getInitials(name) {
  return name
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2);
}

function IssueTypeMarker({ type }) {
  return <span className={`issue-type-marker issue-type-marker--${type.toLowerCase()}`} />;
}

function IssueTypeTabs({ activeType, issues, onChange }) {
  const tabs = [
    { id: "all", label: "All", count: issues.length },
    { id: "Epic", label: "Epics", count: issues.filter((issue) => issue.type === "Epic").length },
    { id: "Story", label: "Stories", count: issues.filter((issue) => issue.type === "Story").length },
    { id: "Bug", label: "Bugs", count: issues.filter((issue) => issue.type === "Bug").length }
  ];

  return (
    <div className="issue-tabs" aria-label="Issue type filters">
      {tabs.map((tab) => (
        <button
          className={activeType === tab.id ? "issue-tab issue-tab--active" : "issue-tab"}
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
        >
          {tab.label} <span className={`issue-tab__count issue-tab__count--${tab.id.toLowerCase()}`}>{tab.count}</span>
        </button>
      ))}
    </div>
  );
}

function IssuesTable({ issues }) {
  return (
    <div className="issues-table-wrap">
      <table className="issues-table">
        <thead>
          <tr>
            <th>Type</th>
            <th>Key</th>
            <th>Summary</th>
            <th>Status</th>
            <th>Priority</th>
            <th>Assignee</th>
            <th>Epic</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          {issues.map((issue) => (
            <tr key={`${issue.type}-${issue.key}`}>
              <td>
                <span className="issue-type-cell">
                  <IssueTypeMarker type={issue.type} />
                  {issue.type}
                </span>
              </td>
              <td>{issue.key}</td>
              <td className="issue-summary-cell">{issue.summary}</td>
              <td>
                <StatusPill tone={toneFor(issue.status)}>{issue.status}</StatusPill>
              </td>
              <td>{issue.priority}</td>
              <td>
                <span className="assignee-cell">
                  <span>{getInitials(issue.relatedAssignees?.[0] ?? issue.assignee)}</span>
                  {issue.relatedAssignees?.length > 0 && issue.assignee === "Unassigned"
                    ? `${issue.relatedAssignees.join(", ")}`
                    : issue.assignee}
                </span>
              </td>
              <td>
                {issue.epicUrl ? (
                  <a href={issue.epicUrl} target="_blank" rel="noreferrer">
                    {issue.epic}
                  </a>
                ) : issue.epic}
              </td>
              <td>{issue.updated}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function IssuesSection({ issues, query, onQueryChange }) {
  const [activeType, setActiveType] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [currentPage, setCurrentPage] = useState(1);

  const statusOptions = useMemo(
    () => ["all", ...Array.from(new Set(issues.map((issue) => issue.status)))],
    [issues]
  );

  const filteredIssues = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();

    return issues.filter((issue) => {
      const matchesType = activeType === "all" || issue.type === activeType;
      const matchesStatus = statusFilter === "all" || issue.status === statusFilter;
      const matchesSearch =
        !normalizedQuery ||
        [issue.key, issue.summary, issue.assignee, issue.epic, issue.status, issue.priority]
          .join(" ")
          .toLowerCase()
          .includes(normalizedQuery);

      return matchesType && matchesStatus && matchesSearch;
    });
  }, [activeType, issues, query, statusFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredIssues.length / issuePageSize));
  const currentPageStart = filteredIssues.length === 0 ? 0 : (currentPage - 1) * issuePageSize + 1;
  const currentPageEnd = Math.min(currentPage * issuePageSize, filteredIssues.length);
  const visibleIssues = filteredIssues.slice((currentPage - 1) * issuePageSize, currentPage * issuePageSize);

  useEffect(() => {
    setCurrentPage(1);
  }, [activeType, query, statusFilter]);

  useEffect(() => {
    setCurrentPage((page) => Math.min(page, totalPages));
  }, [totalPages]);

  return (
    <section className="issues-section">
      <h2>Issues</h2>
      <div className="issues-toolbar">
        <IssueTypeTabs activeType={activeType} issues={issues} onChange={setActiveType} />
        <label className="issues-search">
          <Search size={16} strokeWidth={1.6} />
          <input
            aria-label="Search issues"
            placeholder="Search key, summary, assignee..."
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
          />
        </label>
        <label className="status-select">
          <select
            aria-label="Filter by status"
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            {statusOptions.map((status) => (
              <option key={status} value={status}>
                {status === "all" ? "All statuses" : status}
              </option>
            ))}
          </select>
          <ChevronDown size={16} aria-hidden="true" />
        </label>
      </div>
      <IssuesTable issues={visibleIssues} />
      <div className="table-pagination" aria-label="Issues pagination">
        <span>
          {currentPageStart}-{currentPageEnd} of {filteredIssues.length}
        </span>
        <button
          type="button"
          aria-label="Previous issues page"
          disabled={currentPage === 1}
          onClick={() => setCurrentPage((page) => Math.max(1, page - 1))}
        >
          <ChevronLeft size={17} />
        </button>
        <button
          type="button"
          aria-label="Next issues page"
          disabled={currentPage === totalPages}
          onClick={() => setCurrentPage((page) => Math.min(totalPages, page + 1))}
        >
          <ChevronRight size={17} />
        </button>
      </div>
    </section>
  );
}

export function QeEngineerHome({ data, query, onQueryChange }) {
  return (
    <section className="home-dashboard" aria-label="QE Engineer home dashboard">
      <AppSummaryHeader project={data.project} />
      <div className="metric-grid">
        {data.metrics.map((metric) => (
          <MetricCard key={metric.id} metric={metric} />
        ))}
      </div>
      {/* <section className="epics-strip" aria-labelledby="epics-strip-title">
        <h2 id="epics-strip-title">Epics</h2>
        <div className="epic-card-row">
          {data.epicCards.map((epic) => (
            <EpicCard key={epic.id} epic={epic} />
          ))}
        </div>
      </section> */}
      <IssuesSection issues={data.issues} query={query} onQueryChange={onQueryChange} />
    </section>
  );
}
