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
  Sparkles,
  UserRound,
  X
} from "lucide-react";
import { fetchJiraIssueGroups, generateTestCasesForRequirements } from "@taap/service-layer";
import "./TestDesign.css";

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
  const issues = Object.values(issueGroups?.groups ?? {}).flatMap((group) => group.issues ?? []);
  if (!issues.length) return dummyCases;

  return issues.filter(issue => !/^bug$/i.test(issue.type?.trim() ?? "")).map((issue, index) => ({
    id: `TC-${1046 + index}`,
    title: issue.summary || "Validate Jira requirement behavior",
    type: issue.type || "Not provided",
    priority: issue.priority || (index % 2 === 0 ? "High" : "Medium"),
    automation: index % 4 === 0 ? "Manual" : "Candidate",
    review: index % 5 === 0 ? "Draft" : "Pending Review",
    requirement: issue.key,
    updated: issue.updated ? new Date(issue.updated).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) : "07:02",
    jiraDetails: issue,
    url: issue.url,
    duplicate: index === 2,
    source: "jira"
  }));
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
    <aside className="test-design__suite-panel" aria-label="Test suites">
      <div className="test-design__panel-label">Test suites</div>
      <div className="suite-tree">
        {suites.map((suite, index) => (
          <button className={`suite-tree__item ${suite.active ? "suite-tree__item--active" : ""}`} key={suite.label} type="button">
            {suite.open ? <ChevronDown size={14} /> : index < 4 ? <ChevronRight size={14} /> : <span className="suite-tree__spacer" />}
            <span className="suite-tree__folder" aria-hidden="true" />
            <span className="suite-tree__name">{suite.label}</span>
            {suite.count !== null && <span className="suite-tree__count">{suite.count}</span>}
          </button>
        ))}
      </div>
      <div className="test-design__tags">
        <div className="test-design__panel-label">Tags</div>
        <div className="tag-list">
          {['@promo', '@checkout', '@smoke', '@negative', '@api'].map((tag) => <span key={tag}>{tag}</span>)}
        </div>
      </div>
      <div className="test-design__saved-filters">
        <div className="test-design__panel-label">Saved filters</div>
        <button type="button">AI drafts awaiting review (8)</button>
        <button type="button">Automation candidates (23)</button>
        <button type="button">Flaky &amp; quarantined (14)</button>
      </div>
    </aside>
  );
}

function StatusPill({ children, className = "" }) {
  return <span className={`status-pill ${className}`}>{children}</span>;
}

function TestCaseRow({ testCase, selected, onToggle, onOpen }) {
  return (
    <tr>
      <td className="test-design__check-cell"><input type="checkbox" checked={selected} onChange={onToggle} aria-label={`Select ${testCase.id}`} /></td>
      <td><a className="test-design__case-id" href="#" onClick={(event) => { event.preventDefault(); onOpen(testCase); }}>{testCase.id}</a></td>
      <td>
        <div className="test-design__title-cell">
          <strong>{testCase.title}</strong>
          {testCase.description && <span className="test-design__description">{testCase.description}</span>}
          {/* <span className="test-design__ai-mark">AI</span> */}
          {/* {testCase.duplicate && <StatusPill className="status-pill--duplicate">POSSIBLE DUPLICATE</StatusPill>} */}
        </div>
      </td>
      <td><a className="test-design__requirement" href="#" onClick={(event) => { event.preventDefault(); onOpen(testCase); }}>{testCase.requirement}</a></td>
      <td><StatusPill className={`status-pill--${testCase.priority.toLowerCase()}`}>{testCase.priority}</StatusPill></td>
      <td><span className="automation-value"><span>{testCase.automation === "Candidate"}</span>{testCase.automation}</span></td>
      <td><StatusPill className={`status-pill--${testCase.review.toLowerCase().replace(" ", "-")}`}>{testCase.review}</StatusPill></td>
      {/* <td className="test-design__muted">- Not run</td> */}
      <td>{testCase.type || "Not provided"}</td>
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
  if (testCase.generatedDetails) {
    const generated = testCase.generatedDetails;
    const fields = [
      ["Requirement", testCase.requirement],
      ["Type", testCase.type],
      ["Basis", generated.test_basis],
      ["Priority", testCase.priority],
      ["Automation", testCase.automation],
      ["Mapped AC", generated.mapped_acceptance_criteria?.join(", ") || "Not provided"],
      ["Coverage gap", generated.coverage_gap],
      ["Duplicate check", generated.duplicate_check_notes]
    ];

    return (
      <div style={{ position: "fixed", inset: 0, zIndex: 20, display: "flex", justifyContent: "flex-end", background: "rgba(25, 35, 48, .28)" }} onMouseDown={(event) => event.target === event.currentTarget && onClose()}>
        <section role="dialog" aria-modal="true" aria-labelledby="test-case-details-title" style={{ width: "min(560px, 100vw)", height: "100%", overflowY: "auto", padding: "22px 24px", boxSizing: "border-box", background: "#fff", boxShadow: "-8px 0 24px rgba(30, 43, 59, .16)" }}>
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16, borderBottom: "1px solid #e1e2e5", paddingBottom: 16 }}>
            <div>
              <div style={{ color: "#718095", fontSize: 11, letterSpacing: ".08em" }}>{testCase.id} · A2A GENERATED TEST CASE</div>
              <h2 id="test-case-details-title" style={{ margin: "8px 0 0", color: "#24364c", fontSize: 20, lineHeight: 1.25 }}>{testCase.title}</h2>
            </div>
            <button type="button" onClick={onClose} aria-label="Close test case details" style={{ minHeight: 30, minWidth: 30, padding: 0, fontSize: 18 }}>×</button>
          </div>
          <p style={{ margin: "18px 0", color: "#5d6878", lineHeight: 1.5 }}>{testCase.description}</p>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", borderTop: "1px solid #e1e2e5" }}>
            {fields.map(([label, value]) => <div key={label} style={{ minWidth: 0, padding: "14px 10px 14px 0", borderBottom: "1px solid #e1e2e5" }}><div style={{ color: "#8b95a5", fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase" }}>{label}</div><div style={{ marginTop: 5, color: "#263243", overflowWrap: "anywhere" }}>{formatDetailValue(value)}</div></div>)}
          </div>
          <div style={{ marginTop: 18 }}>
            <div style={{ color: "#8b95a5", fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase" }}>Preconditions</div>
            <ul style={{ margin: "8px 0 0", paddingLeft: 18, color: "#263243" }}>{(generated.preconditions ?? []).map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          <div style={{ marginTop: 18 }}>
            <div style={{ color: "#8b95a5", fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase" }}>Steps</div>
            <ol style={{ margin: "8px 0 0", paddingLeft: 18, color: "#263243" }}>{(generated.steps ?? []).map((step) => <li key={`${step.step_number}-${step.action}`}><strong>{step.action}</strong><br /><span style={{ color: "#5d6878" }}>{step.expected_result}</span></li>)}</ol>
          </div>
          <div style={{ marginTop: 18 }}>
            <div style={{ color: "#8b95a5", fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase" }}>Final expected result</div>
            <div style={{ marginTop: 8, color: "#263243" }}>{formatDetailValue(generated.final_expected_result)}</div>
          </div>
          {generated.clarificationsRequired?.length > 0 && <div style={{ marginTop: 18 }}>
            <div style={{ color: "#8b95a5", fontSize: 10, letterSpacing: ".08em", textTransform: "uppercase" }}>Clarifications</div>
            <ul style={{ margin: "8px 0 0", paddingLeft: 18, color: "#263243" }}>{generated.clarificationsRequired.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>}
        </section>
      </div>
    );
  }

  const details = testCase.jiraDetails ?? {};
  const fields = [
    ["Requirement", testCase.requirement],
    ["Type", details.type || testCase.type],
    ["Status", details.status || "Pending review"],
    ["Review", testCase.review],
    ["Priority", testCase.priority],
    ["Automation", testCase.automation],
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
    <div className="test-design__modal-backdrop" onMouseDown={(event) => event.target === event.currentTarget && onCancel()}>
      <section className="test-design__submit-modal" role="dialog" aria-modal="true" aria-labelledby="submit-review-title">
        <div className="test-design__modal-header">
          <h2 id="submit-review-title"><span aria-hidden="true">✓</span> Submit {testCases.length} test cases for review</h2>
          <button type="button" onClick={onCancel} aria-label="Close submit for review dialog"><X size={16} /></button>
        </div>
        <div className="test-design__modal-body">
          <p>Reviewers are notified and the cases move to Pending Review. AI-generated cases stay labelled as AI-generated throughout the review trail.</p>
          <dl>
            <div><dt>Reviewer</dt><dd>M. Okafor (QA Manager)</dd></div>
            <div><dt>Cases</dt><dd>{caseSummary}</dd></div>
            <div><dt>Requirement</dt><dd>{requirements.join(", ")}</dd></div>
          </dl>
        </div>
        <div className="test-design__modal-footer">
          <span>Recorded in the traceability trail</span>
          <div><button type="button" onClick={onCancel}>Cancel</button><button className="primary-button" type="button" onClick={onConfirm}>Submit for Review</button></div>
        </div>
      </section>
    </div>
  );
}

export function TestDesign({ selectedRequirements, selectedSource, supplementalContext, generationConditions, onPrepareTestData }) {
  const [issueGroups, setIssueGroups] = useState(null);
  const [scopedCases, setScopedCases] = useState([]);
  const [scopeLoading, setScopeLoading] = useState(Boolean(selectedRequirements));
  const [attempt, setAttempt] = useState(0);
  const [loadError, setLoadError] = useState("");
  const [selectedIds, setSelectedIds] = useState(() => selectedRequirements
    ? new Set()
    : new Set(["TC-1046", "TC-1047", "TC-1049", "TC-1050", "TC-1052"]));
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("All cases");
  const [activeTab, setActiveTab] = useState("Cases");
  const [openCase, setOpenCase] = useState(null);
  const [approvedIds, setApprovedIds] = useState(new Set());
  const [submittedReviewIds, setSubmittedReviewIds] = useState(new Set());
  const [toastMessage, setToastMessage] = useState("");
  const [submitReviewCases, setSubmitReviewCases] = useState(null);
  const [loadingAction, setLoadingAction] = useState("");
  const [activeDataSet, setActiveDataSet] = useState("cases");

  useEffect(() => {
    if (selectedRequirements) {
      const controller = new AbortController();
      setScopedCases([]);
      setScopeLoading(true);
      setLoadError("");
      setSelectedIds(new Set());
      setSubmittedReviewIds(new Set());
      setOpenCase(null);
      setSubmitReviewCases(null);
      setActiveDataSet("cases");
      generateTestCasesForRequirements(selectedRequirements, {
        signal: controller.signal,
        supplementalContext,
        generationConditions
      })
        .then(data => {
          if (!controller.signal.aborted) {
            setScopedCases(data.cases);
            setToastMessage(`${data.cases.length} test ${data.cases.length === 1 ? "case" : "cases"} generated by ${data.agent?.name || "the test-case agent"}`);
          }
        })
        .catch(error => { if (!controller.signal.aborted) setLoadError(error.message || "Test-case agent unavailable"); })
        .finally(() => { if (!controller.signal.aborted) setScopeLoading(false); });
      return () => controller.abort();
    }
    let active = true;
    setSubmittedReviewIds(new Set());
    fetchJiraIssueGroups({ limit: 12 })
      .then((data) => active && setIssueGroups(data))
      .catch((error) => active && setLoadError(error instanceof Error ? error.message : "Jira data unavailable"));
    return () => { active = false; };
  }, [selectedRequirements, attempt, supplementalContext, generationConditions]);

  useEffect(() => {
    if (!toastMessage) return undefined;
    const timeoutId = window.setTimeout(() => setToastMessage(""), 2500);
    return () => window.clearTimeout(timeoutId);
  }, [toastMessage]);

  const cases = useMemo(
    () => selectedRequirements ? scopedCases : buildCases(issueGroups),
    [issueGroups, selectedRequirements, scopedCases]
  );
  const reviewedCases = useMemo(() => cases.map((testCase) => approvedIds.has(testCase.id) ? { ...testCase, review: "Approved" } : testCase), [approvedIds, cases]);
  const testDataCases = useMemo(() => buildTestDataCases(issueGroups), [issueGroups]);
  const tableCases = (!selectedRequirements && activeDataSet === "test-data" ? testDataCases : reviewedCases)
    .map(testCase => approvedIds.has(testCase.id) ? { ...testCase, review: "Approved" } : testCase)
    .filter(testCase => !submittedReviewIds.has(testCase.id));
  const visibleTableCases = useMemo(() => tableCases.filter((testCase) => {
    if ([testCase.type, testCase.jiraDetails?.type].some(type => /^bug$/i.test(String(type ?? "").trim()))) return false;
    const matchesQuery = `${testCase.id} ${testCase.title} ${testCase.description || ""} ${testCase.requirement}`.toLowerCase().includes(query.toLowerCase());
    const matchesFilter = filter === "All cases" || (filter === "Pending review" ? testCase.review === "Pending Review" : filter === "Approved" ? testCase.review === "Approved" : testCase.automation === filter);
    return matchesQuery && matchesFilter;
  }), [filter, query, tableCases]);
  const selectedCount = visibleTableCases.filter((testCase) => selectedIds.has(testCase.id)).length;
  const casesToApprove = visibleTableCases.filter(testCase => selectedIds.has(testCase.id) && testCase.review !== "Approved");
  const sourceIsJira = selectedRequirements ? !scopeLoading && !loadError : issueGroups?.source === "jira";
  const scopeLabel = selectedRequirements?.map(item => item.key).join(", ");
  const scopedSourceLabel = selectedSource === "jira" ? "Jira requirements" : "selected requirements";

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
    if (!casesToApprove.length) return;
    const ids = new Set(casesToApprove.map(testCase => testCase.id));
    setApprovedIds(current => new Set([...current, ...ids]));
    setSelectedIds(current => new Set([...current].filter(id => !ids.has(id))));
    setOpenCase(current => current && ids.has(current.id) ? { ...current, review: "Approved" } : current);
    setToastMessage(`${ids.size} test ${ids.size === 1 ? "case" : "cases"} approved`);
  }

  function openSubmitReview() {
    const selectedCases = visibleTableCases.filter((testCase) => selectedIds.has(testCase.id));
    if (selectedCases.length > 0) setSubmitReviewCases(selectedCases);
  }

  function confirmSubmitReview() {
    if (!submitReviewCases?.length) return;
    const submittedIds = new Set(submitReviewCases.map((testCase) => testCase.id));
    setSubmittedReviewIds(current => new Set([...current, ...submittedIds]));
    setSelectedIds(current => new Set([...current].filter(id => !submittedIds.has(id))));
    setOpenCase(current => current && submittedIds.has(current.id) ? null : current);
    setSubmitReviewCases(null);
    setToastMessage(`${submitReviewCases.length} cases submitted to M. Okafor for review`);
  }

  async function loadJiraData(actionName) {
    if (selectedRequirements) { setAttempt(value => value + 1); return; }
    setLoadingAction(actionName);
    setActiveDataSet(actionName === "Test data preparation" ? "test-data" : "cases");
    setLoadError("");
    setSubmittedReviewIds(new Set());
    try {
      const data = await fetchJiraIssueGroups({ limit: 12 });
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

  return (
    <section className="test-design" aria-label="Test Design workspace">
      <div className="test-design__breadcrumbs"><span>Test Design</span><ChevronRight size={13} />{selectedRequirements ? <strong>{scopeLabel}</strong> : <><span>Checkout</span><ChevronRight size={13} /><span>Promotions</span><ChevronRight size={13} /><strong>US-458</strong></>}</div>
      <header className="test-design__header">
        <div>
          <h1>Test-Case Design Workspace</h1>
          <p>{selectedRequirements ? `A2A generated test cases for ${scopeLabel} from ${scopedSourceLabel}` : <><span className="source-dot" /> Source of record: {sourceIsJira ? "Jira" : "TestRail / dummy data"} · Checkout / Promotions · {sourceIsJira ? `${issueGroups?.projectKey || "Selected requirements"} data fetched from Jira` : loadError ? "Jira unavailable, showing dummy cases" : "Loading Jira cases"}</>}</p>
        </div>
        <div className="test-design__header-actions">
          <span>{tableCases.length} cases · {tableCases.filter((item) => item.review === "Pending Review").length} Pending Review</span>
          {/* <button type="button"><Link2 size={15} />Push to TestRail</button> */}
          <button type="button" onClick={openSubmitReview} disabled={selectedCount === 0}>Submit for Review</button>
          {/* <button className="primary-button" type="button" onClick={approveSelected} disabled={casesToApprove.length === 0 || scopeLoading || !!loadingAction}>Approve Cases</button> */}
        </div>
      </header>
      <div className="test-design__workspace">
        {/* <SuiteTree /> */}
        <main className="test-design__content">
          <div className="test-design__toolbar">
            {/* <button className="generate-button" type="button" onClick={() => loadJiraData("Traceability mapping")} disabled={loadingAction === "Traceability mapping"} aria-busy={loadingAction === "Traceability mapping"}>
              <Plus size={16} />{loadingAction === "Traceability mapping" ? "Loading traceability..." : "Traceability and Requirement Mapping"}
            </button> */}
            <button className="generate-button" type="button" onClick={() => loadJiraData("Refresh Testcases")} disabled={scopeLoading || !!loadingAction} aria-busy={scopeLoading || !!loadingAction}>
              <RefreshCw size={16} />{selectedRequirements ? "Regenerate Testcases" : "Refresh Testcases"}
            </button>
            <button className="generate-button" type="button" onClick={onPrepareTestData} disabled={!onPrepareTestData}>
              <Plus size={16} />Test Data Preparation
            </button>
            {activeDataSet === "test-data" && (
              <span className="test-design__data-source-message">
                {sourceIsJira ? "Source of record: Dummy / SCRUM data fetched from Dummy" : "Source of record: Jira / SCRUM data fetched from Jira"}
              </span>
            )}
            {/* <button type="button">Add Test Case</button><button type="button"><Sparkles size={15} />Generate Negative Tests</button><button type="button">Generate Boundary Tests</button><button type="button">Identify Duplicates</button><button type="button">Convert to Gherkin</button> */}
          </div>
          {/* <div className="test-design__subtoolbar">
            <span>{selectedCount} selected</span><button className="accept-button" type="button">Accept Selected</button><button type="button">Reject</button><button type="button"><RefreshCw size={14} />Regenerate</button><button type="button"><UserRound size={14} />Assign Reviewer</button>
          </div> */}
          <div className="test-design__tabs">
            {/* {['Cases', 'Traceability', 'Review history'].map((tab) => <button className={activeTab === tab ? "is-active" : ""} key={tab} onClick={() => setActiveTab(tab)} type="button">{tab}{tab === 'Cases' && <span>{cases.length}</span>}</button>)} */}
            <div className="test-design__table-tools">
                <div className="test-design__table-search">
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
                <option>Approved</option>
                <option>Candidate</option>
                <option>Manual</option>
                </select>
                {/* <button type="button" className="icon-button" title="Filter cases"><Filter size={16} /></button>
                <button type="button" className="icon-button" title="More options"><MoreHorizontal size={17} /></button> */}
            </div>
          </div>
          {activeTab === "Cases" ? <div className="test-design__table-wrap">
            <table>
              <thead>
                <tr>
                  <th>
                    <input type="checkbox" checked={visibleTableCases.length > 0 && selectedCount === visibleTableCases.length} onChange={toggleVisible} aria-label="Select visible cases" />
                  </th>
                  <th>Test Case ID</th>
                  <th>Test Case Title</th>
                  <th>Story</th>
                  <th>PRIORITY</th>
                  <th>AUTOMATION</th>
                  <th>REVIEW</th>
                  <th>CATEGORY</th>
                </tr>
              </thead>
              <tbody>
                {visibleTableCases.map((testCase) => <TestCaseRow key={testCase.id} testCase={testCase} selected={selectedIds.has(testCase.id)} onToggle={() => toggleCase(testCase.id)} onOpen={setOpenCase} />)}
              </tbody>
            </table>{visibleTableCases.length === 0 && <div className="test-design__empty"><FileText size={22} /><strong>{scopeLoading ? "Generating test cases…" : loadError && selectedRequirements ? "Could not generate test cases" : selectedRequirements && !cases.length ? "No new test cases generated for the selected epics or stories" : "No cases match this view"}</strong><span role={loadError ? "alert" : "status"}>{selectedRequirements && loadError ? loadError : scopeLoading ? "Calling the A2A test-case agent for your Requirements selection." : cases.length ? "Try a different search or filter." : ""}</span>{selectedRequirements && loadError && <button type="button" onClick={() => setAttempt(value => value + 1)}>Retry</button>}</div>}</div> : <div className="test-design__empty test-design__empty--tab"><CircleHelp size={22} /><strong>{activeTab} is ready for review</strong><span>Traceability and history will appear as cases move through review.</span></div>}
          <footer className="test-design__footer"><span><span className={`connection-indicator ${sourceIsJira ? "connection-indicator--live" : ""}`} />{selectedRequirements ? scopeLoading ? "A2A agent running" : loadError ? "A2A agent unavailable" : "A2A agent connected" : sourceIsJira ? "Jira connected" : "Using dummy data"}</span><span>{selectedRequirements ? scopeLabel : sourceIsJira ? `Project ${issueGroups?.projectKey || "selected requirements"}` : "Jira data will replace this sample set when available"}</span></footer>
        </main>
      </div>
      {openCase && <TestCaseDetails testCase={openCase} onClose={() => setOpenCase(null)} />}
      {submitReviewCases && <SubmitReviewModal testCases={submitReviewCases} onCancel={() => setSubmitReviewCases(null)} onConfirm={confirmSubmitReview} />}
      {toastMessage && <div className="test-design__toast" role="status" aria-live="polite">{toastMessage}</div>}
    </section>
  );
}
