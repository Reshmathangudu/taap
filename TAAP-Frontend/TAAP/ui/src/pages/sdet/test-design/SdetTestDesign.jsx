import { useEffect, useMemo, useState } from "react";
import {
  ChevronDown,
  ChevronRight,
  CircleHelp,
  FileText,
  //Filter,
  Link2,
  //MoreHorizontal,
  Plus,
  RefreshCw,
  Search,
  UserRound,
  X
} from "lucide-react";
import { fetchJiraIssueGroups } from "@taap/service-layer";
import { generateScriptDraftsFromTestCases, saveGeneratedScriptDrafts } from "../script-generation/scriptGenerationAgent.js";
import "./SdetTestDesign.css";

const TEST_DESIGN_JIRA_LIMIT = 500;

const dummyCases = [
  { id: "TC-1046", title: "Apply a valid promotional code at checkout", type: "Functional", priority: "Critical", automation: "Candidate", review: "Pending Review", requirement: "US-458", updated: "06:58", source: "dummy" },
  { id: "TC-1047", title: "Reject an invalid promotional code with inline error", type: "Negative", priority: "High", automation: "Candidate", review: "Pending Review", requirement: "US-458", updated: "06:58", source: "dummy" },
  { id: "TC-1049", title: "Reject an expired promotional code", type: "Negative", priority: "High", automation: "Candidate", review: "Pending Review", requirement: "US-458", updated: "06:58", duplicate: true, source: "dummy" },
  { id: "TC-1050", title: "Cap the discount at the configured maximum", type: "Boundary", priority: "High", automation: "Candidate", review: "Pending Review", requirement: "US-458", updated: "06:59", source: "dummy" },
  { id: "TC-1051", title: "Second promotional code replaces the first", type: "Negative", priority: "Medium", automation: "Candidate", review: "Pending Review", requirement: "US-458", updated: "06:59", duplicate: true, source: "dummy" },
  { id: "TC-1052", title: "Guest checkout applies the promotional code", type: "Functional", priority: "High", automation: "Candidate", review: "Pending Review", requirement: "US-458", updated: "06:59", source: "dummy" },
  { id: "TC-1053", title: "Discount rounds correctly after currency conversion", type: "Functional", priority: "Medium", automation: "Manual", review: "Draft", requirement: "US-458", updated: "07:01", source: "dummy" }
];

const dummyTestDataCases = [
  {
    id: "TD-0001",
    title: "Test data preparation",
    description: "creating, maintaining, and validating test data, while upstream/downstream application teams, integration teams, and test-data-management/support teams assist when external or shared data dependencies exist.",
    type: "Functional",
    priority: "High",
    automation: "Manual",
    review: "Draft",
    requirement: "US-458",
    updated: "07:02",
    source: "dummy"
  }
];

const suites = [
  { label: "Checkout", count: 64, open: true },
  { label: "Promotions", count: 18, open: true, active: true },
  { label: "Payments", count: 41 },
  { label: "Orders", count: 37 },
  { label: "Regression Suite", count: 412 },
  { label: "Smoke Suite", count: 48 },
  { label: "API Contract", count: 96 },
  { label: "Requirements view", count: null }
];

function buildCases(issueGroups) {
  const issues = issueGroups?.groups?.testCases?.issues ?? [];
  if (!issues.length) return dummyCases;
  const storiesByKey = new Map((issueGroups?.groups?.stories?.issues ?? []).map((story) => [story.key, story]));

  return issues.map((issue, index) => ({
    storyKey: issue.parentKey || "",
    storySummary: issue.parentTitle || storiesByKey.get(issue.parentKey)?.summary || storiesByKey.get(issue.requirementId)?.summary || "",
    id: issue.testCaseId || issue.key || `JIRA-TC-${index + 1}`,
    jiraKey: issue.key || "",
    title: issue.testName || issue.summary || "Untitled Jira test case",
    description: issue.description || "",
    type: issue.testType || issue.type || "Test Case",
    priority: issue.businessPriority || issue.priority || (index % 2 === 0 ? "High" : "Medium"),
    automation: normalizeAutomationStatus(issue.automationStatus),
    review: normalizeReviewStatus(issue.testStatus || issue.status),
    requirement: issue.requirementId || issue.parentKey || "Not linked",
    updated: issue.updated ? new Date(issue.updated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "07:02",
    jiraDetails: issue,
    url: issue.url,
    source: "jira"
  }));
}

function normalizeAutomationStatus(value) {
  const status = String(value || "").trim();
  if (!status) return "Candidate";
  if (/manual/i.test(status)) return "Manual";
  if (/candidate|autom/i.test(status)) return "Candidate";
  return status;
}

function normalizeReviewStatus(value) {
  const status = String(value || "").trim();
  if (!status) return "Draft";
  if (/approved|ready for execution|accepted/i.test(status)) return "Approved";
  if (/review|qa|ready/i.test(status)) return "Pending Review";
  if (/draft|todo|to do|open/i.test(status)) return "Draft";
  return status;
}

function statusClassName(value) {
  return String(value || "draft").toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function buildTestDataCases(issueGroups) {
  const issues = Object.values(issueGroups?.groups ?? {}).flatMap((group) => group.issues ?? []);
  if (!issues.length) return dummyTestDataCases;

  return issues.map((issue, index) => ({
    id: `TD-${String(index + 1).padStart(4, "0")}`,
    title: issue.summary || "Test data preparation",
    description: issue.description || "Prepare valid, invalid and boundary data required to validate this Jira requirement.",
    type: "Functional",
    priority: issue.priority || "Medium",
    automation: "Manual",
    review: "Draft",
    requirement: issue.key || `REQ-${index + 1}`,
    updated: issue.updated ? new Date(issue.updated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "07:02",
    jiraDetails: issue,
    url: issue.url,
    source: "jira"
  }));
}

function SuiteTree() {
  return (
    <aside className="sdet-test-design__suite-panel" aria-label="Test suites">
      <div className="sdet-test-design__panel-label">Test suites</div>
      <div className="sdet-suite-tree">
        {suites.map((suite, index) => (
          <button className={`sdet-suite-tree__item ${suite.active ? "sdet-suite-tree__item--active" : ""}`} key={suite.label} type="button">
            {suite.open ? <ChevronDown size={14} /> : index < 4 ? <ChevronRight size={14} /> : <span className="sdet-suite-tree__spacer" />}
            <span className="sdet-suite-tree__folder" aria-hidden="true" />
            <span className="sdet-suite-tree__name">{suite.label}</span>
            {suite.count !== null && <span className="sdet-suite-tree__count">{suite.count}</span>}
          </button>
        ))}
      </div>
      <div className="sdet-test-design__tags">
        <div className="sdet-test-design__panel-label">Tags</div>
        <div className="sdet-tag-list">
          {['@promo', '@checkout', '@smoke', '@negative', '@api'].map((tag) => <span key={tag}>{tag}</span>)}
        </div>
      </div>
      <div className="sdet-test-design__saved-filters">
        <div className="sdet-test-design__panel-label">Saved filters</div>
        <button type="button">AI drafts awaiting review (8)</button>
        <button type="button">Automation candidates (23)</button>
        <button type="button">Flaky &amp; quarantined (14)</button>
      </div>
    </aside>
  );
}

function StatusPill({ children, className = "" }) {
  return <span className={`sdet-status-pill ${className}`}>{children}</span>;
}

function TestCaseRow({ testCase, selected, onToggle, onOpen }) {
  return (
    <tr>
      <td className="test-design__check-cell"><input type="checkbox" checked={selected} onChange={onToggle} aria-label={`Select ${testCase.id}`} /></td>
      <td>
        <a className="sdet-test-design__case-id" href="#" onClick={(event) => { event.preventDefault(); onOpen(testCase); }}>{testCase.id}</a>
        {testCase.jiraKey && testCase.jiraKey !== testCase.id ? <span className="sdet-test-design__jira-key">{testCase.jiraKey}</span> : null}
      </td>
      <td><a className="sdet-test-design__requirement" href="#" onClick={(event) => { event.preventDefault(); onOpen(testCase); }}>{testCase.requirement}</a></td>
      <td>
        <span className="sdet-test-design__story-summary">{testCase.storySummary || "Not linked"}</span>
        {testCase.storyKey ? <span className="sdet-test-design__jira-key">{testCase.storyKey}</span> : null}
      </td>
      <td>{testCase.type}</td>
      <td><StatusPill className={`sdet-status-pill--${statusClassName(testCase.priority)}`}>{testCase.priority}</StatusPill></td>
      <td><span className="sdet-automation-value"><span>{testCase.automation === "Candidate"}</span>{testCase.automation}</span></td>
      <td><StatusPill className={`sdet-status-pill--${statusClassName(testCase.review)}`}>{testCase.review}</StatusPill></td>
      {/* <td className="sdet-test-design__muted">- Not run</td> */}
      <td><span className="sdet-test-design__owner"><UserRound size={14} />Test Design<br />Agent</span></td>
      <td className="sdet-test-design__muted">{testCase.updated}</td>
    </tr>
  );
}

function formatDetailValue(value, fallback = "Not provided") {
  if (value === null || value === undefined || value === "") return fallback;
  if (Array.isArray(value)) return value.map((item) => formatDetailValue(item, "")).filter(Boolean).join(", ") || fallback;
  if (typeof value === "object") return value.displayName || value.name || value.accountId || value.key || fallback;
  return String(value);
}

function TestCaseDetails({ testCase, onClose }) {
  const details = testCase.jiraDetails ?? {};
  const fields = [
    ["Jira issue", testCase.jiraKey || details.key || "Not provided"],
    ["Test Case ID", details.testCaseId || testCase.id],
    ["Requirement", testCase.requirement],
    ["Story Summary", testCase.storySummary || "Not linked"],
    ["Story Key", testCase.storyKey || details.parentKey || "Not provided"],
    ["Type", details.testType || details.type || testCase.type],
    ["Jira Status", details.status || "Pending review"],
    ["Test Status", details.testStatus || testCase.review],
    ["Automation Status", details.automationStatus || testCase.automation],
    ["Priority", testCase.priority],
    ["Assignee", details.assignee || "Unassigned"],
    ["Reporter", details.reporter || "Not provided"],
    ["Parent", details.parentKey || "None"],
    ["Story points", details.storyPoints || "Not provided"],
    ["Created", details.created ? new Date(details.created).toLocaleString() : "Not provided"],
    ["Updated", details.updated ? new Date(details.updated).toLocaleString() : testCase.updated]
  ];

  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 20, display: "flex", justifyContent: "flex-end", background: "rgba(25, 35, 48, .28)" }} onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
      <section role="dialog" aria-modal="true" aria-labelledby="test-case-details-title" style={{ width: "min(520px, 100vw)", height: "100%", overflowY: "auto", padding: "22px 24px", boxSizing: "border-box", background: "#fff", boxShadow: "-8px 0 24px rgba(30, 43, 59, .16)" }}>
        <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, borderBottom: "1px solid #e1e2e5", paddingBottom: 16 }}>
          <div>
            <div style={{ color: "#718095", fontSize: 11, letterSpacing: ".08em" }}>{testCase.id} · JIRA REQUIREMENT</div>
            <h2 id="test-case-details-title" style={{ margin: "8px 0 0", color: "#24364c", fontSize: 20, lineHeight: 1.25 }}>{testCase.title}</h2>
          </div>
          <button type="button" onClick={onClose} aria-label="Close test case details" style={{ minHeight: 30, minWidth: 30, padding: 0, fontSize: 18 }}>×</button>
        </div>
        <p style={{ margin: "18px 0", color: "#5d6878", lineHeight: 1.5 }}>Details from Jira for requirement <strong>{testCase.requirement}</strong>.</p>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", borderTop: "1px solid #e1e2e5" }}>
          {fields.map(([label, value]) => <div key={label} style={{ minWidth: 0, padding: "14px 10px 14px 0", borderBottom: "1px solid #e1e2e5" }}><div style={{ color: "#8b95a5", fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase" }}>{label}</div><div style={{ marginTop: 5, color: "#263243", overflowWrap: "anywhere" }}>{formatDetailValue(value)}</div></div>)}
        </div>
        <div style={{ marginTop: 18 }}>
          <div style={{ color: "#8b95a5", fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase" }}>Labels</div>
          <div style={{ marginTop: 8, color: "#263243" }}>{formatDetailValue(details.labels, "No labels")}</div>
        </div>
      </section>
    </div>
  );
}

function SubmitReviewModal({ testCases, onCancel, onConfirm }) {
  const caseIds = testCases.map((testCase) => testCase.id);
  const requirements = [...new Set(testCases.map((testCase) => testCase.requirement))];
  const caseSummary = caseIds.length > 1 ? `${caseIds[0]} ... ${caseIds[caseIds.length - 1]} (${caseIds.length})` : caseIds[0];

  return (
    <div className="sdet-test-design__modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <section className="sdet-test-design__submit-modal" role="dialog" aria-modal="true" aria-labelledby="submit-review-title">
        <div className="sdet-test-design__modal-header">
          <h2 id="submit-review-title"><span aria-hidden="true">✓</span> Submit {testCases.length} test cases for review</h2>
          <button type="button" onClick={onCancel} aria-label="Close submit for review dialog"><X size={16} /></button>
        </div>
        <div className="sdet-test-design__modal-body">
          <p>Reviewers are notified and the cases move to Pending Review. AI-generated cases stay labelled as AI-generated throughout the review trail.</p>
          <dl>
            <div><dt>Reviewer</dt><dd>M. Okafor (QA Manager)</dd></div>
            <div><dt>Cases</dt><dd>{caseSummary}</dd></div>
            <div><dt>Requirement</dt><dd>{requirements.join(", ")}</dd></div>
          </dl>
        </div>
        <div className="sdet-test-design__modal-footer">
          <span>Recorded in the traceability trail</span>
          <div><button type="button" onClick={onCancel}>Cancel</button><button className="sdet-primary-button" type="button" onClick={onConfirm}>Submit for Review</button></div>
        </div>
      </section>
    </div>
  );
}

export function SdetTestDesign({ onSectionOpen }) {
  const [issueGroups, setIssueGroups] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All cases");
  const [activeTab, setActiveTab] = useState("Cases");
  const [openCase, setOpenCase] = useState(null);
  const [approvedIds, setApprovedIds] = useState(new Set());
  const [toastMessage, setToastMessage] = useState("");
  const [submitReviewCases, setSubmitReviewCases] = useState(null);
  const [loadingAction, setLoadingAction] = useState("");
  const [activeDataSet, setActiveDataSet] = useState("cases");

  useEffect(() => {
    let active = true;
    fetchJiraIssueGroups({ limit: TEST_DESIGN_JIRA_LIMIT })
      .then((data) => active && setIssueGroups(data))
      .catch((error) => active && setLoadError(error instanceof Error ? error.message : "Jira data unavailable"));
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!toastMessage) return undefined;
    const timeoutId = window.setTimeout(() => setToastMessage(""), 2500);
    return () => window.clearTimeout(timeoutId);
  }, [toastMessage]);

  const cases = useMemo(() => buildCases(issueGroups), [issueGroups]);
  const reviewedCases = useMemo(() => cases.map((testCase) => approvedIds.has(testCase.id) ? { ...testCase, review: "Approved" } : testCase), [approvedIds, cases]);
  const testDataCases = useMemo(() => buildTestDataCases(issueGroups), [issueGroups]);
  const tableCases = activeDataSet === "test-data" ? testDataCases : reviewedCases;
  const visibleTableCases = useMemo(() => tableCases.filter((testCase) => {
    const matchesQuery = `${testCase.id} ${testCase.jiraKey || ""} ${testCase.title} ${testCase.description || ""} ${testCase.requirement} ${testCase.storyKey || ""} ${testCase.storySummary || ""}`.toLowerCase().includes(query.toLowerCase());
    const matchesFilter = filter === "All cases" || (filter === "Pending review" ? testCase.review === "Pending Review" : testCase.automation === filter);
    return matchesQuery && matchesFilter;
  }), [filter, query, tableCases]);
  const selectedCount = visibleTableCases.filter((testCase) => selectedIds.has(testCase.id)).length;
  const sourceIsJira = issueGroups?.source === "jira";
  const jiraTestCaseCount = issueGroups?.groups?.testCases?.issues?.length ?? 0;
  const usingJiraTestCases = sourceIsJira && jiraTestCaseCount > 0;

  function toggleCase(id) {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  function toggleVisible() {
    setSelectedIds((current) => {
      const next = new Set(current);
      const shouldSelect = selectedCount !== visibleTableCases.length;
      visibleTableCases.forEach((testCase) => shouldSelect ? next.add(testCase.id) : next.delete(testCase.id));
      return next;
    });
  }

  function approveSelected() {
    if (selectedIds.size === 0) return;
    setApprovedIds((current) => new Set([...current, ...selectedIds]));
    setToastMessage(`${selectedIds.size} test cases accepted and published to Checkout Regression`);
  }

  function openSubmitReview() {
    const selectedCases = reviewedCases.filter((testCase) => selectedIds.has(testCase.id));
    if (selectedCases.length > 0) setSubmitReviewCases(selectedCases);
  }

  function confirmSubmitReview() {
    if (!submitReviewCases?.length) return;
    setSubmitReviewCases(null);
    setToastMessage(`${submitReviewCases.length} cases submitted to M. Okafor for review`);
  }

  async function loadJiraData(actionName) {
    setLoadingAction(actionName);
    setActiveDataSet(actionName === "Test data preparation" ? "test-data" : "cases");
    setLoadError("");
    try {
      const data = await fetchJiraIssueGroups({ limit: TEST_DESIGN_JIRA_LIMIT });
      setIssueGroups(data);
      setToastMessage(data?.source === "jira" ? `${actionName} loaded Jira data` : `${actionName}: Jira data unavailable, showing dummy cases`);
    } catch (error) {
      setIssueGroups(null);
      setLoadError(error instanceof Error ? error.message : "Jira data unavailable");
      setToastMessage(`${actionName}: Jira data unavailable, showing dummy cases`);
    } finally {
      setLoadingAction("");
    }
  }

  async function openScriptGeneration() {
    const selectedCases = reviewedCases.filter((testCase) => selectedIds.has(testCase.id));
    if (selectedCases.length === 0) {
      setToastMessage("Select at least one test case to generate scripts.");
      return;
    }

    setLoadingAction("Generate Test Scripts");
    setLoadError("");

    try {
      const drafts = await generateScriptDraftsFromTestCases({ testCases: selectedCases, issueGroups });
      saveGeneratedScriptDrafts(drafts);
      setToastMessage(`${drafts.length} script draft${drafts.length === 1 ? "" : "s"} generated by SDET Script Generation Agent.`);
      onSectionOpen?.("script-generation");
    } catch (error) {
      setToastMessage(error instanceof Error ? error.message : "Unable to generate script drafts.");
    } finally {
      setLoadingAction("");
    }
  }

  return (
    <section className="sdet-test-design" aria-label="Test Design workspace">
      <div className="sdet-test-design__breadcrumbs"><span>Test Design</span><ChevronRight size={13} /><span>Checkout</span><ChevronRight size={13} /><span>Promotions</span><ChevronRight size={13} /><strong>US-458</strong></div>
      <header className="sdet-test-design__header">
        <div>
          <h1>Test-Case Design Workspace</h1>
          <p><span className="sdet-source-dot" /> Source of record: {usingJiraTestCases ? "Jira Test Cases" : "Dummy test cases"} · {sourceIsJira ? `${issueGroups.projectKey} data fetched from Jira` : loadError ? "Jira unavailable, showing dummy cases" : "Loading Jira cases"}{sourceIsJira ? ` · ${jiraTestCaseCount} Jira test cases` : ""}</p>
        </div>
        <div className="sdet-test-design__header-actions"><span>{reviewedCases.length} cases · {reviewedCases.filter((item) => item.review === "Pending Review").length} pending review</span><button type="button"><Link2 size={15} />Push to TestRail</button><button type="button" onClick={openSubmitReview} disabled={selectedIds.size === 0}>Submit for Review</button><button className="sdet-primary-button" type="button" onClick={approveSelected} disabled={selectedIds.size === 0}>Approve Cases</button></div>
      </header>
      <div className="sdet-test-design__workspace">
        {/* <SuiteTree /> */}
        <main className="sdet-test-design__content">
          <div className="sdet-test-design__toolbar">
            <button className="sdet-generate-button" type="button" onClick={openScriptGeneration} disabled={loadingAction === "Generate Test Scripts"} aria-busy={loadingAction === "Generate Test Scripts"}>
              {loadingAction === "Generate Test Scripts" ? <RefreshCw size={16} className="sdet-test-design__spin" /> : <Plus size={16} />}
              {loadingAction === "Generate Test Scripts" ? "Generating scripts..." : "Generate Test Scripts"}
            </button>
            <button className="sdet-generate-button" type="button" onClick={() => loadJiraData("Test Data Preparation")} disabled={loadingAction === "Test Data Preparation"} aria-busy={loadingAction === "Test Data Preparation"}>
              <Plus size={16} />{loadingAction === "Test Data Preparation" ? "Loading test data..." : "Test Data Preparation"}
            </button>
            {activeDataSet === "test-data" && (
              <span className="sdet-test-design__data-source-message">
                {sourceIsJira ? "Source of record: Dummy / SCRUM data fetched from Dummy" : "Source of record: Jira / SCRUM data fetched from Jira"}
              </span>
            )}
            {/* <button type="button">Add Test Case</button><button type="button"><Sparkles size={15} />Generate Negative Tests</button><button type="button">Generate Boundary Tests</button><button type="button">Identify Duplicates</button><button type="button">Convert to Gherkin</button> */}
          </div>
          {/* <div className="sdet-test-design__subtoolbar">
            <span>{selectedCount} selected</span><button className="sdet-accept-button" type="button">Accept Selected</button><button type="button">Reject</button><button type="button"><RefreshCw size={14} />Regenerate</button><button type="button"><UserRound size={14} />Assign Reviewer</button>
          </div> */}
          <div className="sdet-test-design__tabs">
            {/* {['Cases', 'Traceability', 'Review history'].map((tab) => <button className={activeTab === tab ? "is-active" : ""} key={tab} onClick={() => setActiveTab(tab)} type="button">{tab}{tab === 'Cases' && <span>{cases.length}</span>}</button>)} */}
            <div className="sdet-test-design__table-tools">
                <div className="sdet-test-design__table-search">
                    <Search size={14} />
                        <input value={query} 
                        onChange={(event) => setQuery(event.target.value)} 
                        placeholder="Search cases" 
                        aria-label="Search test cases" />
                        {query && <button type="button" 
                        onClick={() => setQuery("")} 
                        aria-label="Clear search"><X size={13} />
                        </button>}
                </div>
                <select value={filter} 
                onChange={(event) => setFilter(event.target.value)} 
                aria-label="Filter cases">
                <option>All cases</option>
                <option>Pending review</option>
                <option>Candidate</option>
                <option>Manual</option>
                </select>
                {/* <button type="button" className="icon-button" title="Filter cases"><Filter size={16} /></button>
                <button type="button" className="icon-button" title="More options"><MoreHorizontal size={17} /></button> */}
            </div>
          </div>
          {activeTab === "Cases" ? <div className="sdet-test-design__table-wrap">
            <table>
              <thead>
                <tr>
                  <th>
                    <input type="checkbox" checked={visibleTableCases.length > 0 && selectedCount === visibleTableCases.length} onChange={toggleVisible} aria-label="Select visible cases" />
                  </th>
                  <th>ID</th>
                  <th>REQ</th>
                  <th>STORY SUMMARY</th>
                  <th>TYPE</th>
                  <th>PRIORITY</th>
                  <th>AUTOMATION</th>
                  <th>REVIEW</th>
                  <th>OWNER</th>
                  <th>UPDATED</th>
                </tr>
              </thead>
              <tbody>
                {visibleTableCases.map((testCase) => <TestCaseRow key={testCase.id} testCase={testCase} selected={selectedIds.has(testCase.id)} onToggle={() => toggleCase(testCase.id)} onOpen={setOpenCase} />)}
              </tbody>
            </table>{visibleTableCases.length === 0 && <div className="sdet-test-design__empty"><FileText size={22} /><strong>No cases match this view</strong><span>Try a different search or filter.</span></div>}</div> : <div className="sdet-test-design__empty sdet-test-design__empty--tab"><CircleHelp size={22} /><strong>{activeTab} is ready for review</strong><span>Traceability and history will appear as cases move through review.</span></div>}
          <footer className="sdet-test-design__footer"><span><span className={`sdet-connection-indicator ${usingJiraTestCases ? "sdet-connection-indicator--live" : ""}`} />{usingJiraTestCases ? "Jira test cases loaded" : sourceIsJira ? "Jira connected, no test cases returned" : "Using dummy data"}</span><span>{sourceIsJira ? `Project ${issueGroups.projectKey}` : "Jira data will replace this sample set when available"}</span></footer>
        </main>
      </div>
      {openCase && <TestCaseDetails testCase={openCase} onClose={() => setOpenCase(null)} />}
      {submitReviewCases && <SubmitReviewModal testCases={submitReviewCases} onCancel={() => setSubmitReviewCases(null)} onConfirm={confirmSubmitReview} />}
      {toastMessage && <div className="sdet-test-design__toast" role="status" aria-live="polite">{toastMessage}</div>}
    </section>
  );
}
