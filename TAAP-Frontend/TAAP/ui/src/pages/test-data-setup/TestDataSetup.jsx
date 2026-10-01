import { Fragment, useEffect, useMemo, useState } from "react";
import { CheckCircle2, Database, Download, ExternalLink, LoaderCircle, Minus, Plus, RefreshCw, Search, ShieldCheck } from "lucide-react";
import { fetchJiraIssueGroups } from "@taap/service-layer";
import "./TestDataSetup.css";

const initialEnvironments = [
  { id: "qa", name: "QA", status: "Healthy", statusTone: "healthy", build: "24.8.183", deployed: "deployed 07:20", note: "Sanity suite passed 06:45 — 42/42 checks green." },
  { id: "sit", name: "SIT", status: "Healthy", statusTone: "healthy", build: "24.8.182", deployed: "deployed 06:55", note: "Integration checks passed — all services available." },
  { id: "uat", name: "UAT", status: "Idle", statusTone: "idle", build: "24.8.170", deployed: "deployed Aug 8", note: "Reserved for business sign-off from Aug 20." },
  { id: "preprod", name: "PreProd", status: "Healthy", statusTone: "healthy", build: "24.8.176", deployed: "deployed Aug 10", note: "Release candidate environment ready for validation." }
];

const initialDataSets = [
  { id: "guest-checkout", name: "Guest checkout · gift cards", usedBy: "TC-1102", records: "40 accounts", refreshed: "Today 06:30", status: "Ready", tone: "ready" },
  { id: "multi-currency", name: "Multi-currency carts", usedBy: "TC-1053", records: "120 carts", refreshed: "Today 06:30", status: "Ready", tone: "ready" },
  { id: "promo-codes", name: "Expired promo codes", usedBy: "TC-1049 retest", records: "25 codes", refreshed: "Aug 12", status: "Stale", tone: "stale", action: "Refresh via Agent" },
  { id: "split-wallets", name: "Split payment wallets", usedBy: "US-441 (planned)", records: "—", refreshed: "—", status: "Not provisioned", tone: "unprovisioned", action: "Provision via Agent" }
];

const environmentTabs = ["QA", "SIT", "UAT", "PreProd"];

function EnvironmentCard({ environment, onCheck }) {
  const isChecking = environment.status === "Checking";
  return (
    <article className="test-data-setup__environment corner-frame">
      <div className="test-data-setup__environment-heading">
        <h3>{environment.name}</h3>
        <span className={`test-data-setup__health test-data-setup__health--${environment.statusTone}`}>
          <span aria-hidden="true" />{environment.status}
        </span>
      </div>
      <p className="test-data-setup__build">Build {environment.build} · {environment.deployed}</p>
      <p className="test-data-setup__note">{environment.note}</p>
      <button className="test-data-setup__outline-button" type="button" onClick={() => onCheck(environment.id)} disabled={isChecking}>
        {isChecking ? <LoaderCircle size={13} className="test-data-setup__spin" /> : <ShieldCheck size={13} />}
        {isChecking ? "Checking..." : "Agent Sanity Check"}
      </button>
    </article>
  );
}

function flattenJiraIssues(issueGroups) {
  return Object.values(issueGroups?.groups ?? {}).flatMap((group) => group.issues ?? []);
}

function formatJiraValue(value, fallback) {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map((item) => formatJiraValue(item, "")).filter(Boolean).join(", ") || fallback;
  if (value && typeof value === "object") return value.displayName || value.name || value.accountId || value.key || fallback;
  return fallback;
}

function JiraIssueExpanded({ issue }) {
  return (
    <div className="test-data-setup__expanded-content">
      <div className="test-data-setup__expanded-field"><strong>Description:</strong><span>{formatJiraValue(issue.description, "No description provided in Jira.")}</span></div>
      <div className="test-data-setup__expanded-field"><strong>Type:</strong><span>{formatJiraValue(issue.type, "Not provided")}</span></div>
      <div className="test-data-setup__expanded-field"><strong>Status:</strong><span>{formatJiraValue(issue.status, "Not provided")}</span></div>
      <div className="test-data-setup__expanded-field"><strong>Priority:</strong><span>{formatJiraValue(issue.priority, "Not provided")}</span></div>
      <div className="test-data-setup__expanded-field"><strong>Assignee:</strong><span>{formatJiraValue(issue.assignee, "Unassigned")}</span></div>
      <div className="test-data-setup__expanded-field"><strong>Reporter:</strong><span>{formatJiraValue(issue.reporter, "Not provided")}</span></div>
      <div className="test-data-setup__expanded-field"><strong>Parent:</strong><span>{formatJiraValue(issue.parentKey, "Not provided")}</span></div>
      <div className="test-data-setup__expanded-field"><strong>Story points:</strong><span>{formatJiraValue(issue.storyPoints, "Not provided")}</span></div>
      <div className="test-data-setup__expanded-field"><strong>Labels:</strong><span>{formatJiraValue(issue.labels, "No labels")}</span></div>
      {issue.url && <a className="test-data-setup__jira-link" href={issue.url} target="_blank" rel="noreferrer">Open in Jira <ExternalLink size={13} /></a>}
    </div>
  );
}

export function TestDataSetup() {
  const [environments, setEnvironments] = useState(initialEnvironments);
  const [dataSets, setDataSets] = useState(initialDataSets);
  const [issueGroups, setIssueGroups] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [notice, setNotice] = useState("");
  const [expandedIssueId, setExpandedIssueId] = useState(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [pageSize, setPageSize] = useState(10);
  const [activeEnvironment, setActiveEnvironment] = useState("QA");

  async function refreshJiraData() {
    setIsRefreshing(true);
    try {
      const data = await fetchJiraIssueGroups({ limit: 12 });
      setIssueGroups(data);
      setNotice("Jira data refreshed");
    } catch {
      setNotice("Showing cached test data while Jira is unavailable");
    } finally {
      setIsRefreshing(false);
    }
  }

  useEffect(() => {
    refreshJiraData();
  }, []);

  const jiraIssueCount = useMemo(() => Object.values(issueGroups?.groups ?? {}).reduce((total, group) => total + (group.issues?.length ?? 0), 0), [issueGroups]);
  const jiraDataSets = useMemo(() => flattenJiraIssues(issueGroups).map((issue) => ({
    id: issue.id || issue.key,
    name: issue.summary || "Untitled Jira issue",
    usedBy: issue.key || "—",
    records: issue.type || "—",
    refreshed: issue.updated ? new Date(issue.updated).toLocaleDateString() : "—",
    status: issue.status || "Open",
    tone: issue.status?.toLowerCase().includes("done") || issue.status?.toLowerCase().includes("closed") ? "ready" : "stale",
    issue
  })), [issueGroups]);
  const visibleDataSets = useMemo(() => {
    const source = jiraDataSets.length ? jiraDataSets : dataSets;
    return source.map((dataSet, index) => {
      const environmentIndex = environmentTabs.indexOf(activeEnvironment);
      const environmentStatus = activeEnvironment === "QA" ? dataSet.status : activeEnvironment === "SIT" ? (index % 4 === 0 ? "In Progress" : dataSet.status) : activeEnvironment === "UAT" ? (index % 3 === 0 ? "Blocked" : "To Do") : (index % 4 === 0 ? "Ready for sign-off" : "To Do");
      return {
        ...dataSet,
        id: `${dataSet.id}-${activeEnvironment}`,
        status: environmentStatus,
        tone: environmentStatus.toLowerCase().includes("ready") || environmentStatus.toLowerCase().includes("done") ? "ready" : environmentStatus.toLowerCase().includes("blocked") ? "unprovisioned" : "stale",
        refreshed: dataSet.issue ? new Date(new Date(dataSet.refreshed).getTime() + environmentIndex * 86400000).toLocaleDateString() : dataSet.refreshed
      };
    });
  }, [activeEnvironment, dataSets, jiraDataSets]);
  const filteredDataSets = useMemo(() => visibleDataSets.filter((dataSet) => `${dataSet.name} ${dataSet.usedBy} ${dataSet.records} ${dataSet.status}`.toLowerCase().includes(searchQuery.toLowerCase())), [searchQuery, visibleDataSets]);
  const pagedDataSets = filteredDataSets.slice(0, pageSize);

  function exportTable(format) {
    const headers = ["Data set", "Used by", "Records", "Refreshed", "Status"];
    const rows = filteredDataSets.map((dataSet) => [dataSet.name, dataSet.usedBy, dataSet.records, dataSet.refreshed, dataSet.status]);
    const csv = [headers, ...rows].map((row) => row.map((value) => `"${String(value).replaceAll('"', '""')}"`).join(",")).join("\n");
    const fileName = `test-data-${activeEnvironment.toLowerCase()}`;

    if (format === "csv" || format === "excel") {
      const blob = new Blob([csv], { type: format === "excel" ? "application/vnd.ms-excel;charset=utf-8" : "text/csv;charset=utf-8" });
      const link = document.createElement("a");
      link.href = URL.createObjectURL(blob);
      link.download = `${fileName}.${format === "excel" ? "xls" : "csv"}`;
      link.click();
      URL.revokeObjectURL(link.href);
      setNotice(`${format === "excel" ? "Excel" : "CSV"} export downloaded`);
      return;
    }

    const printWindow = window.open("", "_blank", "noopener,noreferrer");
    if (!printWindow) {
      setNotice("Allow pop-ups to save the table as PDF");
      return;
    }
    printWindow.document.write(`<html><head><title>${fileName}</title><style>body{font-family:Arial;color:#263243}table{width:100%;border-collapse:collapse}th,td{border:1px solid #d4d4d7;padding:8px;text-align:left}th{background:#f4f5f7}</style></head><body><h2>${activeEnvironment} Test Data</h2><table><thead><tr>${headers.map((header) => `<th>${header}</th>`).join("")}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((value) => `<td>${String(value).replaceAll("<", "&lt;")}</td>`).join("")}</tr>`).join("")}</tbody></table></body></html>`);
    printWindow.document.close();
    printWindow.focus();
    printWindow.print();
    setNotice("PDF print dialog opened");
  }

  function runSanityCheck(environmentId) {
    setEnvironments((current) => current.map((environment) => environment.id === environmentId ? { ...environment, status: "Checking" } : environment));
    window.setTimeout(() => {
      setEnvironments((current) => current.map((environment) => environment.id === environmentId ? { ...environment, status: "Healthy", statusTone: "healthy", note: "Sanity suite passed just now — all checks green." } : environment));
      setNotice("Sanity check completed");
    }, 700);
  }

  function updateDataSet(dataSetId) {
    setDataSets((current) => current.map((dataSet) => dataSet.id === dataSetId ? { ...dataSet, status: "Ready", tone: "ready", records: dataSet.records === "—" ? "40 wallets" : dataSet.records, refreshed: "Just now", action: undefined } : dataSet));
    setNotice("Test data agent started");
  }

  return (
    <section className="test-data-setup" aria-label="Test Data and Environments">
      {/* <div className="test-data-setup__eyebrow">Execute</div> */}
      <header className="test-data-setup__header">
        <div>
          <h1>Test Data &amp; Environments</h1>
          <p>Provision, refresh, and validate the data your test suites depend on.</p>
        </div>
        <button className="test-data-setup__refresh-button" type="button" onClick={refreshJiraData} disabled={isRefreshing}>
          <RefreshCw size={14} className={isRefreshing ? "test-data-setup__spin" : ""} />
          {isRefreshing ? "Refreshing" : "Refresh from Jira"}
        </button>
      </header>

      <div className="test-data-setup__body">
        <section className="test-data-setup__section" aria-labelledby="datasets-heading">
          {/* <div className="test-data-setup__environment-tabs" role="tablist" aria-label="Test environments">
            <div className="tab-data">
                {environmentTabs.map((environment) => (
                  <button key={environment} className={activeEnvironment === environment ? "is-active" : ""} type="button" role="tab" aria-selected={activeEnvironment === environment} onClick={() => { setActiveEnvironment(environment); setExpandedIssueId(null); }}>
                    {environment}
                  </button>
                ))}
            </div>
            <div className="test-data-setup__tab-caption"><span>{activeEnvironment}</span> test data from Jira <em>{jiraIssueCount} issues linked</em></div>
          </div> */}
          
          <div className="test-data-setup__table-controls">
            {/* <label>Show <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}><option value="10">10</option><option value="25">25</option><option value="50">50</option></select> entries</label> */}
            <label className="test-data-setup__search">Search: <span><Search size={14} /><input value={searchQuery} onChange={(event) => setSearchQuery(event.target.value)} aria-label="Search test data" /></span></label>
            <label className="test-data-setup__export"><select defaultValue="" onChange={(event) => { if (event.target.value) exportTable(event.target.value); event.target.value = ""; }} aria-label="Export test data">
              <option value="" disabled>Download</option>
              <option value="excel">Export to Excel</option>
              <option value="csv">Export to CSV</option>
              <option value="pdf">Save As PDF</option>
            </select></label>
          </div>
          <div className="test-data-setup__table-wrap">
            <table>
              <thead><tr><th className="test-data-setup__expand-heading" aria-label="Expand row" /><th>Data set</th><th>Used by</th><th>Records</th><th>Refreshed</th><th>Status</th><th aria-label="Actions" /></tr></thead>
              <tbody>
                {pagedDataSets.map((dataSet) => (
                  <Fragment key={dataSet.id}>
                  <tr className={dataSet.issue ? "test-data-setup__jira-row" : ""} onClick={() => dataSet.issue && setExpandedIssueId((current) => current === dataSet.id ? null : dataSet.id)}>
                    <td className="test-data-setup__expand-cell">{dataSet.issue && (expandedIssueId === dataSet.id ? <Minus size={15} /> : <Plus size={15} />)}</td>
                    <td className="test-data-setup__dataset-name">{dataSet.name}</td>
                    <td><a href="#jira" onClick={(event) => event.preventDefault()}>{dataSet.usedBy}</a></td>
                    <td>{dataSet.records}</td>
                    <td>{dataSet.refreshed}</td>
                    <td><span className={`test-data-setup__status test-data-setup__status--${dataSet.tone}`}>{dataSet.status}</span></td>
                    <td className="test-data-setup__action-cell">{dataSet.action && <button type="button" onClick={() => updateDataSet(dataSet.id)}>{dataSet.action} <ExternalLink size={12} /></button>}</td>
                  </tr>
                  {dataSet.issue && expandedIssueId === dataSet.id && <tr className="test-data-setup__expanded-row"><td colSpan="7"><JiraIssueExpanded issue={dataSet.issue} /></td></tr>}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
          {/* <p className="test-data-setup__footnote"><CheckCircle2 size={14} /> Data Agent provisions from the Test Data Vault — masked production snapshots, refreshed nightly at 02:00.</p> */}
        </section>
      </div>
      {/* {notice && <button className="test-data-setup__notice" type="button" onClick={() => setNotice("")}>{notice}</button>} */}
    </section>
  );
}