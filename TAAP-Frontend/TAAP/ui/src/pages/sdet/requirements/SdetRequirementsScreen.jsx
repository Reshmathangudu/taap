import JiraRiskAnalysis from "../../../utils/JiraRiskAnalysis.jsx";
import JiraImpactAnalysis from "../../../utils/JiraImpactAnalysis.jsx";
import { useEffect, useMemo, useState } from "react";
import { Check, ChevronRight, FileText, RefreshCw, Search, Cog } from "lucide-react";
import { fetchJiraIssueGroups } from "@taap/service-layer";
import "./SdetRequirementsScreen.css";

function normalizeJiraDescription(value) {
  if (!value) return "";

  if (typeof value === "string") return value.trim();

  if (typeof value === "object") {
    if (Array.isArray(value.content)) {
      return value.content
        .map((node) => {
          const text = node?.type === "text" ? node.text ?? "" : "";
          const children = Array.isArray(node?.content) ? node.content.flatMap((child) => normalizeJiraDescription(child).split("\n")).filter(Boolean) : [];
          return [text, ...children].filter(Boolean).join("\n");
        })
        .filter(Boolean)
        .join("\n")
        .trim();
    }

    if (Array.isArray(value)) {
      return value.map((item) => normalizeJiraDescription(item)).filter(Boolean).join("\n").trim();
    }
  }

  return "";
}

function normalizeJiraPerson(value, fallback = "Unassigned") {
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (value && typeof value === "object") return value.displayName || value.name || value.accountId || fallback;
  return fallback;
}

function buildRequirements(payload) {
  const issues = Object.values(payload?.groups ?? {}).flatMap((group) => group.issues ?? []);

  const requirements = issues.map((issue, index) => {
    const fields = issue.fields ?? {};
    const key = issue.key || `REQ-${index + 1}`;
    const summary = issue.summary || fields.summary || "Untitled Jira requirement";
    const description = normalizeJiraDescription(issue.description ?? fields.description ?? "");
    const acceptanceCriteria = Array.isArray(issue.acceptanceCriteria)
      ? issue.acceptanceCriteria
      : Array.isArray(fields.acceptanceCriteria)
        ? fields.acceptanceCriteria
        : [];

    return {
      key,
      type: issue.type || fields.issuetype?.name || "",
      summary,
      status: issue.status || fields.status?.name || "Open",
      priority: issue.priority || fields.priority?.name || "Medium",
      owner: normalizeJiraPerson(issue.assignee || fields.assignee),
      parentKey: issue.parentKey || fields.parent?.key || "",
      description,
      acceptanceCriteria,
      updated: issue.updated || fields.updated ? new Date(issue.updated || fields.updated || Date.now()).toLocaleDateString() : "Recently",
      url: issue.url || (issue.key ? `https://jira.example.com/browse/${issue.key}` : "")
    };
  });

  return requirements.map((requirement) => ({
    ...requirement,
    children: requirements.filter((candidate) => candidate.parentKey === requirement.key)
  }));
}

function buildDefaultAcceptance(criteriaSource, requirement) {
  const summary = requirement.summary || "This story";
  const source = criteriaSource && criteriaSource.length ? criteriaSource : [
    `${summary} behaves correctly in the primary user flow.`,
    "Validation and error handling are clear for the affected workflow.",
    "The outcome is reflected consistently in the impacted screens or records.",
    "Regression and edge-case behaviour are validated before sign-off."
  ];

  return source.slice(0, 4).map((label, index) => ({
    label,
    status: index < 2 ? "Covered" : index === 2 ? "Partial" : "Missing"
  }));
}

function buildStoryAcceptance(requirement, mode = "details") {
  const explicit = Array.isArray(requirement.acceptanceCriteria) && requirement.acceptanceCriteria.length
    ? requirement.acceptanceCriteria
    : [];

  const mapped = buildDefaultAcceptance(explicit, requirement);

  const modeSpecific = {
    details: mapped,
    impact: [
      { label: `The affected flow for ${requirement.summary || "this story"} is identified.`, status: "Covered" },
      { label: "Dependencies and downstream impact are documented.", status: "Covered" },
      { label: "Regression and risk areas are assessed for the story.", status: "Partial" },
      { label: "Open questions are captured before release sign-off.", status: "Missing" }
    ],
    "test-case": [
      { label: "The primary scenario is defined for the story.", status: "Covered" },
      { label: "Required preconditions and execution steps are clear.", status: "Covered" },
      { label: "Expected results are explicit and testable.", status: "Partial" },
      { label: "Negative and boundary scenarios are documented.", status: "Missing" }
    ],
    "test-plan": [
      { label: "Scope and user journey are clearly defined.", status: "Covered" },
      { label: "Happy path coverage is planned.", status: "Covered" },
      { label: "Error and boundary coverage is included.", status: "Partial" },
      { label: "Exit criteria are explicit and agreed.", status: "Missing" }
    ],
    "test-data": [
      { label: "Valid input values for the story are identified.", status: "Covered" },
      { label: "Invalid and negative data cases are defined.", status: "Covered" },
      { label: "Boundary conditions are included.", status: "Partial" },
      { label: "Data isolation and cleanup are documented.", status: "Missing" }
    ],
    risk: [
      { label: "The story risk is assessed against the impacted flow.", status: "Covered" },
      { label: "Operational and regression risks are documented.", status: "Covered" },
      { label: "The mitigation path is identified.", status: "Partial" },
      { label: "Residual risk and reviewer sign-off remain open.", status: "Missing" }
    ],
    dependency: [
      { label: "Upstream and downstream dependencies are identified.", status: "Covered" },
      { label: "Required services or data sources are mapped.", status: "Covered" },
      { label: "Failure handling is considered for the story.", status: "Partial" },
      { label: "Dependency validation is not yet fully proven.", status: "Missing" }
    ],
    effort: [
      { label: "Deliverable activities and sequencing are documented.", status: "Covered" },
      { label: "Required roles and ownership are identified.", status: "Covered" },
      { label: "Validation and regression effort are included.", status: "Partial" },
      { label: "Assumptions and risk for resourcing are not fully recorded.", status: "Missing" }
    ]
  };

  return modeSpecific[mode] || mapped;
}

function buildStorySummary(requirement) {
  const title = requirement.summary || "Untitled story";
  const status = requirement.status || "Open";
  const priority = requirement.priority || "Medium";

  return `${title}. Priority is ${priority.toLowerCase()} and current status is ${status.toLowerCase()}. The requirement should be validated across the main user flow, validation outcomes, and regression risk before sign-off.`;
}

function buildStoryFindings(requirement) {
  const summary = requirement.summary || "This story";
  const findings = [
    ["AMBIGUITY", `${summary} should define edge-case behaviour clearly before release.`],
    ["MISSING AC", "A boundary or regression condition should be captured in the acceptance criteria."],
    ["TESTABILITY", "Confirm the required workflow is observable and repeatable in the QA environment."]
  ];

  if ((requirement.status || "").toLowerCase().includes("done")) {
    findings.push(["COVERED", "The story appears implemented and is ready for final validation."]);
  }

  return findings;
}

function RequirementCard({ requirement, selected, onSelect }) {
  return (
    <button
      className={`sdet-requirements-screen__card ${selected ? "is-selected" : ""}`}
      type="button"
      onClick={() => onSelect(requirement)}
    >
      <div className="sdet-requirements-screen__card-top">
        <strong>{requirement.key}</strong>
        <span className={`sdet-requirements-screen__priority sdet-requirements-screen__priority--${requirement.priority.toLowerCase()}`}>
          {requirement.priority} risk
        </span>
        <small>{requirement.completeness ?? 65} pts</small>
      </div>
      <b>{requirement.summary}</b>
      <div className="sdet-requirements-screen__card-meta">
        <span>AC {requirement.completeness ?? 65}%</span>
        <span>Cov {requirement.coverage ?? "Partial"}</span>
        <span>Auto {requirement.automation ?? "None"}</span>
      </div>
      <i>
        <em style={{ width: `${requirement.completeness ?? 65}%` }} />
      </i>
    </button>
  );
}

function buildTestCase(requirement, isJira) {
  const hasJiraDescription = isJira && requirement.description;

  return {
    title: `Verify ${requirement.summary}`,
    source: hasJiraDescription ? `Jira · ${requirement.key}` : "Dummy test case",
    description: hasJiraDescription
      ? requirement.description
      : `Verify that the requirement "${requirement.summary}" works as expected for a shopper.`,
    preconditions: "The application is available and the shopper can reach the relevant workflow.",
    steps: hasJiraDescription
      ? [
          "Open the workflow described by the Jira requirement.",
          "Perform the action described in the Jira description.",
          "Complete the workflow and observe the result."
        ]
      : [
          `Open the workflow for "${requirement.summary}".`,
          "Perform the primary user action.",
          "Submit or complete the workflow."
        ],
    expected: hasJiraDescription
      ? "The observed result matches the Jira requirement description."
      : "The workflow completes successfully and produces the expected requirement outcome."
  };
}

function TestCaseDetails({ requirement, isJira, onClose }) {
  const testCase = buildTestCase(requirement, isJira);

  return (
    <div className="requirements-screen__test-case-details">
      <div className="sdet-requirements-screen__impact-heading">
        <div>
          <h3>TEST CASE CREATION</h3>
          <h2>{testCase.title}</h2>
          <span>{testCase.source}</span>
        </div>
        <button type="button" onClick={onClose}>Back to details</button>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="sdet-requirements-screen__jira-description">{testCase.description}</p>
      <h3>PRECONDITIONS</h3>
      <p className="sdet-requirements-screen__jira-description">{testCase.preconditions}</p>
      <h3>TEST STEPS</h3>
      <ol className="sdet-requirements-screen__test-steps">
        {testCase.steps.map((step) => <li key={step}>{step}</li>)}
      </ol>
      <h3>EXPECTED RESULT</h3>
      <p className="sdet-requirements-screen__jira-description">{testCase.expected}</p>
    </div>
  );
}

function TestPlanDetails({ requirement, isJira, onClose }) {
  const hasJiraDescription = isJira && requirement.description;
  const description = hasJiraDescription
    ? requirement.description
    : `Validate the requirement "${requirement.summary}" across its primary, error and boundary scenarios.`;
  const scope = hasJiraDescription
    ? "Use the Jira description as the source of truth and verify the behaviour it defines."
    : "Dummy scope covering the main user journey, validation errors and boundary conditions.";
  const scenarios = hasJiraDescription
    ? ["Happy path described in Jira", "Invalid or rejected input", "Boundary and error handling"]
    : ["Primary workflow completes successfully", "Invalid input displays a clear error", "Boundary values are handled without data loss"];

  return (
    <div className="requirements-screen__test-case-details">
      <div className="sdet-requirements-screen__impact-heading">
        <div>
          <h3>TEST PLAN</h3>
          <h2>{requirement.summary}</h2>
          <span>{hasJiraDescription ? `Jira · ${requirement.key}` : "Dummy test plan"}</span>
        </div>
        <button type="button" onClick={onClose}>Back to details</button>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="sdet-requirements-screen__jira-description">{description}</p>
      <h3>SCOPE</h3>
      <p className="sdet-requirements-screen__jira-description">{scope}</p>
      <h3>TEST SCENARIOS</h3>
      <ol className="sdet-requirements-screen__test-steps">
        {scenarios.map((scenario) => <li key={scenario}>{scenario}</li>)}
      </ol>
      <h3>EXIT CRITERIA</h3>
      <p className="sdet-requirements-screen__jira-description">All planned scenarios pass and no high-severity defects remain open.</p>
    </div>
  );
}

function TestDataRequirementsDetails({ requirement, isJira, onClose }) {
  const hasJiraDescription = isJira && requirement.description;
  const description = hasJiraDescription
    ? requirement.description
    : `Prepare data to validate the requirement "${requirement.summary}" across successful, invalid and boundary scenarios.`;
  const dataSets = hasJiraDescription
    ? [
        ["Valid data", "Use valid values and the standard user context described by the Jira requirement."],
        ["Invalid data", "Use an invalid value to confirm that validation and error handling work."],
        ["Boundary data", "Use the smallest, largest and empty values relevant to this workflow."]
      ]
    : [
        ["Valid data", "A valid user account and representative input for the primary workflow."],
        ["Invalid data", "Malformed, empty and unsupported input values."],
        ["Boundary data", "Minimum, maximum and just-over-limit values for relevant fields."]
      ];

  return (
    <div className="requirements-screen__test-case-details">
      <div className="sdet-requirements-screen__impact-heading">
        <div>
          <h3>TEST DATA REQUIREMENTS</h3>
          <h2>{requirement.summary}</h2>
          <span>{hasJiraDescription ? `Jira · ${requirement.key}` : "Dummy test data requirements"}</span>
        </div>
        <button type="button" onClick={onClose}>Back to details</button>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="sdet-requirements-screen__jira-description">{description}</p>
      <h3>REQUIRED DATA SETS</h3>
      <div className="sdet-requirements-screen__data-sets">
        {dataSets.map(([name, details]) => (
          <div className="sdet-requirements-screen__data-set" key={name}>
            <strong>{name}</strong>
            <span>{details}</span>
          </div>
        ))}
      </div>
      <h3>DATA CONTROLS</h3>
      <p className="sdet-requirements-screen__jira-description">Do not use production personal data. Reset or isolate test data between runs and record the values used for each test execution.</p>
    </div>
  );
}

function DependencyAnalysisDetails({ requirement, isJira, onClose }) {
  const hasJiraDescription = isJira && requirement.description;
  const description = hasJiraDescription
    ? requirement.description
    : `Identify the systems, services and workflows that the requirement "${requirement.summary}" depends on.`;
  const dependencies = hasJiraDescription
    ? [
        ["Upstream", "Requirement input and user context must be available before this workflow starts.", "Required"],
        ["Service", "Dependent business service must validate and process the request.", "Required"],
        ["Downstream", "The resulting state must be reflected in the next user-facing workflow.", "Required"]
      ]
    : [
        ["Upstream", "Authenticated user, valid request data and prerequisite configuration.", "Required"],
        ["External service", "The supporting service must be available and return a valid response.", "Required"],
        ["Downstream", "The updated result must be saved and visible in the related workflow.", "Required"]
      ];

  return (
    <div className="requirements-screen__test-case-details">
      <div className="sdet-requirements-screen__impact-heading">
        <div>
          <h3>DEPENDENCY ANALYSIS</h3>
          <h2>{requirement.summary}</h2>
          <span>{hasJiraDescription ? `Jira · ${requirement.key}` : "Dummy dependency analysis"}</span>
        </div>
        <button type="button" onClick={onClose}>Back to details</button>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="sdet-requirements-screen__jira-description">{description}</p>
      <h3>DEPENDENCIES</h3>
      <div className="sdet-requirements-screen__dependency-list">
        {dependencies.map(([type, detail, status]) => (
          <div className="sdet-requirements-screen__dependency-item" key={type}>
            <div>
              <strong>{type}</strong>
              <span>{detail}</span>
            </div>
            <em>{status}</em>
          </div>
        ))}
      </div>
      <h3>VALIDATION</h3>
      <p className="sdet-requirements-screen__jira-description">Verify each dependency independently, test unavailable-service behaviour, and confirm that failures are reported without losing user data.</p>
    </div>
  );
}

function EffortResourceDetails({ requirement, isJira, onClose }) {
  const hasJiraDescription = isJira && requirement.description;
  const description = hasJiraDescription
    ? requirement.description
    : `Estimate the effort and people required to deliver and validate the requirement "${requirement.summary}".`;
  const estimates = hasJiraDescription
    ? [
        ["Analysis and design", "QA lead / Product owner", "1-2 days"],
        ["Implementation", "Development team", "3-5 days"],
        ["Testing and regression", "QA engineer", "2-3 days"]
      ]
    : [
        ["Requirement refinement", "Product owner and QA lead", "1 day"],
        ["Development", "1 frontend and 1 backend engineer", "3 days"],
        ["Test execution", "QA engineer", "2 days"]
      ];

  return (
    <div className="requirements-screen__test-case-details">
      <div className="sdet-requirements-screen__impact-heading">
        <div>
          <h3>EFFORT AND RESOURCE ESTIMATES</h3>
          <h2>{requirement.summary}</h2>
          <span>{hasJiraDescription ? `Jira · ${requirement.key}` : "Dummy effort estimate"}</span>
        </div>
        <button type="button" onClick={onClose}>Back to details</button>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="sdet-requirements-screen__jira-description">{description}</p>
      <h3>ESTIMATE BREAKDOWN</h3>
      <div className="sdet-requirements-screen__effort-list">
        {estimates.map(([work, resource, duration]) => (
          <div className="sdet-requirements-screen__effort-item" key={work}>
            <div>
              <strong>{work}</strong>
              <span>{resource}</span>
            </div>
            <em>{duration}</em>
          </div>
        ))}
      </div>
      <h3>ASSUMPTIONS</h3>
      <p className="sdet-requirements-screen__jira-description">The required environments and dependent services are available, scope changes are managed separately, and estimates include normal review and retesting effort.</p>
    </div>
  );
}

export function SdetRequirementsScreen() {
  const [payload, setPayload] = useState(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedKey, setSelectedKey] = useState("EP-1003");
  const [activeTab, setActiveTab] = useState("Details");
  const [detailMode, setDetailMode] = useState("details");

  function loadRequirements() {
    setLoading(true);
    setError("");
    fetchJiraIssueGroups({ limit: 25 })
      .then(setPayload)
      .catch((reason) => {
        setPayload(null);
        setError(reason instanceof Error ? reason.message : "Jira data unavailable");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadRequirements();
  }, []);

  const requirements = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return buildRequirements(payload).filter((requirement) =>
      !normalizedQuery || `${requirement.key} ${requirement.summary} ${requirement.owner}`.toLowerCase().includes(normalizedQuery)
    );
  }, [payload, query]);
  const isJira = payload?.source === "jira";
  const selected = requirements.find((requirement) => requirement.key === selectedKey) || requirements[0];
  const detailRequirement = selected?.children?.length ? selected.children[0] : selected;
  if (!selected) {
    return (
      <section className="sdet-requirements-screen" aria-label="Requirements workspace">
        <div className="sdet-requirements-screen__empty-state">
          <FileText size={18} />
          <strong>{loading ? "Loading requirements from Jira..." : "No Jira requirements found"}</strong>
          {!loading && <span>{error || "The Jira response did not contain any issues."}</span>}
          {!loading && <button type="button" onClick={loadRequirements}><RefreshCw size={14} /> Retry Jira</button>}
        </div>
      </section>
    );
  }
  const selectedAcceptance = buildStoryAcceptance(detailRequirement, detailMode);
  const selectedSummary = buildStorySummary(detailRequirement);
  const selectedFindings = buildStoryFindings(detailRequirement);
  const activeAcceptance = {
    summary: detailMode === "details" ? "Requirement acceptance criteria" : detailMode === "impact" ? "Impact analysis acceptance criteria" : detailMode === "test-case" ? "Test case acceptance criteria" : detailMode === "test-plan" ? "Test plan acceptance criteria" : detailMode === "test-data" ? "Test data acceptance criteria" : detailMode === "risk" ? "Risk analysis acceptance criteria" : detailMode === "dependency" ? "Dependency analysis acceptance criteria" : "Effort and resource acceptance criteria",
    items: selectedAcceptance.map((item) => [item.label, item.status])
  };

  return (
    <section className="sdet-requirements-screen" aria-label="Requirements workspace">
      <div className="sdet-requirements-screen__breadcrumbs">
        <span>Requirements</span>
        <ChevronRight size={13} />
        <span>Sprint 18</span>
        <ChevronRight size={13} />
        <strong>{selected.key}</strong>
      </div>

      <header className="sdet-requirements-screen__topbar">
        <div>
          <h1>Requirements Walkthrough</h1>
          <p>
            <span /> Source of record: {isJira ? `Jira - ${payload.projectKey || "project"}` : "Jira / dummy data"} · Updated moments ago · questions and links post back to Jira
          </p>
        </div>
        {/* <div className="sdet-requirements-screen__actions">
          <button type="button">Post Questions to Jira</button>
          <button type="button">Mark as Risk</button>
          <button className="primary" type="button">Create Test Plan</button>
        </div> */}
      </header>

      <div className="sdet-requirements-screen__workspace">
        <aside className="sdet-requirements-screen__list-panel">
          <label className="sdet-requirements-screen__search">
            <Search size={15} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search requirements" aria-label="Search requirements" />
          </label>
          {/* <div className="sdet-requirements-screen__filters">
            <span>Sprint 18 ×</span>
            <span>Risk: High ×</span>
            <button type="button">+ Status</button>
            <button type="button">+ Coverage</button>
            <button type="button">+ Owner</button>
          </div> */}
          <div className="sdet-requirements-screen__cards">
            {requirements.map((item) => (
              <RequirementCard
                key={item.key}
                requirement={item}
                selected={item.key === selected.key}
                onSelect={(value) => {
                  setSelectedKey(value.key);
                  setDetailMode("details");
                }}
              />
            ))}
          </div>
        </aside>

        <main className="sdet-requirements-screen__detail">
          {/* <div className="sdet-requirements-screen__detail-heading">
            <div>
              <div className="sdet-requirements-screen__detail-id">
                <strong>{selected.key}</strong>
                <span className="sdet-requirements-screen__risk">△ {selected.priority} risk</span>
                <span>{selected.coverage} coverage</span>
                <span>{selected.automation === "None" ? "No automation" : `${selected.automation} automation`}</span>
              </div>
              <h2>{selected.summary}</h2>
              <p>Epic: {selected.epic} · Owner: {selected.owner} · Dev: {selected.developer} · Updated {selected.updated}</p>
            </div>
            <div className="sdet-requirements-screen__scores">
              <span>AC COMPLETENESS <b>{selected.completeness}%</b></span>
              <span>TEST COVERAGE <b>{selected.coverage}</b></span>
            </div>
          </div> */}

          <div className="sdet-requirements-screen__tabs">
            {/* {["Details", "Traceability", "Linked defects (2)", "Comments (7)", "Change history"].map((tab) => ( */}
            {["Details"].map((tab) => (
              <button className={activeTab === tab ? "is-active" : ""} type="button" key={tab} onClick={() => setActiveTab(tab)}>{tab}</button>
            ))}
          </div>

          <div className="sdet-requirements-screen__description">
            {detailMode === "impact" ? (
              <JiraImpactAnalysis issueKeys={[detailRequirement.key]} onClose={() => setDetailMode("details")} />
            ) : detailMode === "test-case" ? (
              <TestCaseDetails requirement={detailRequirement} isJira={isJira} onClose={() => setDetailMode("details")} />
            ) : detailMode === "test-plan" ? (
              <TestPlanDetails requirement={detailRequirement} isJira={isJira} onClose={() => setDetailMode("details")} />
            ) : detailMode === "test-data" ? (
              <TestDataRequirementsDetails requirement={detailRequirement} isJira={isJira} onClose={() => setDetailMode("details")} />
            ) : detailMode === "risk" ? (
              <JiraRiskAnalysis issueKeys={[detailRequirement.key]} onClose={() => setDetailMode("details")} />
            ) : detailMode === "dependency" ? (
              <DependencyAnalysisDetails requirement={detailRequirement} isJira={isJira} onClose={() => setDetailMode("details")} />
            ) : detailMode === "effort" ? (
              <EffortResourceDetails requirement={detailRequirement} isJira={isJira} onClose={() => setDetailMode("details")} />
            ) : (
              <>
                <h3>DESCRIPTION</h3>
                <p>{detailRequirement.description || ""}</p>
              </>
            )}
            {detailMode !== "impact" && detailMode !== "risk" && (
              <>
                <div className="sdet-requirements-screen__criteria-heading">
                  <h3>{activeAcceptance.summary}</h3>
                  <span>{activeAcceptance.items.length} criteria for this view</span>
                </div>
                {activeAcceptance.items.map(([label, status], index) => (
                  <div className="sdet-requirements-screen__criterion" key={label}>
                    <b>{index + 1}</b>
                    <span>{label}</span>
                    <em className={`criteria-${status.toLowerCase().replaceAll(" ", "-")}`}>{status}</em>
                  </div>
                ))}
              </>
            )}
          </div>
        </main>

        <aside className="sdet-requirements-screen__analysis">
          <div className="sdet-requirements-screen__analysis-title"> 
            <Cog size={16} />
            <strong>AI Requirement Analysis</strong>
            <b>87%</b>
          </div>
          <div className="sdet-requirements-screen__accepted"><Check size={14} /> Analysis accepted by Alex Rivera · 08:14</div>
          <h3>REQUIREMENT SUMMARY</h3>
          <p className="sdet-requirements-screen__summary-box">{selectedSummary}</p>
          <h3>FINDINGS</h3>
          {selectedFindings.map(([tag, text]) => (
            <div className="sdet-requirements-screen__finding" key={`${tag}-${text}`}><b>{tag}</b><span>{text}</span></div>
          ))}
          <button className="sdet-requirements-screen__analysis-button" type="button" onClick={() => setDetailMode("impact")}>Impact Analysis</button>
          <div className="sdet-requirements-screen__analysis-actions">
            <button type="button" onClick={() => setDetailMode("test-case")} className="sdet-amber-color" disabled>
              Test Case Creation (call to agent)
            </button>
            {/* <button type="button" onClick={() => setDetailMode("test-plan")}>Test Plan</button>
            <button type="button" onClick={() => setDetailMode("test-data")}>Test Data Requirements</button> */}
            <button type="button" onClick={() => setDetailMode("risk")}>Risk Analysis</button>
            {/* <button type="button" onClick={() => setDetailMode("dependency")}>Dependency Analysis</button> */}
            {/* <button type="button" onClick={() => setDetailMode("effort")}>Effort and Resource Estimates</button> */}
          </div>
        </aside>
      </div>

      {error && <div className="sdet-requirements-screen__fallback"><FileText size={16} /><span>Jira could not be reached.<small>{error}</small></span></div>}
    </section>
  );
}
