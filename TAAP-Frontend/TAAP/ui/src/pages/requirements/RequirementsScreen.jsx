import JiraRiskAnalysis from "../../utils/JiraRiskAnalysis.jsx";
import { useEffect, useMemo, useState } from "react";
import { ChevronRight, FileText, RefreshCw, Search } from "lucide-react";
import JiraImpactAnalysis from "../../utils/JiraImpactAnalysis.jsx";
import AIRequirementAnalysis from "../../utils/AIRequirementAnalysis.jsx";
import { testDesignRequirements } from "../../utils/testDesignSelection.js";
import { fetchJiraIssueGroups } from "@taap/service-layer";
import "./RequirementsScreen.css";

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
    const rawAcceptanceCriteria = Array.isArray(issue.acceptanceCriteria)
      ? issue.acceptanceCriteria
      : Array.isArray(fields.acceptanceCriteria)
        ? fields.acceptanceCriteria
        : typeof issue.acceptanceCriteria === "string"
          ? issue.acceptanceCriteria.split(/\r?\n/)
          : typeof fields.acceptanceCriteria === "string"
            ? fields.acceptanceCriteria.split(/\r?\n/)
            : [];
    const acceptanceCriteria = rawAcceptanceCriteria
      .map((criterion) => normalizeJiraDescription(criterion).trim())
      .filter(Boolean);

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

  const stories = requirements.filter((requirement) =>
    ["story", "user story"].includes(requirement.type.toLowerCase()) && requirement.acceptanceCriteria.length > 0
  );
  const epicKeys = new Set(stories.map((story) => story.parentKey));
  return requirements.filter((requirement) => stories.includes(requirement) ||
    (requirement.type.toLowerCase() === "epic" && epicKeys.has(requirement.key))
  ).map((requirement) => ({
    ...requirement,
    children: stories.filter((candidate) => candidate.parentKey === requirement.key)
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

  const mapped = explicit.map((label) => ({ label, status: "" }));

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

function AcceptanceCriteriaList({ criteria, emptyMessage }) {
  return criteria.length ? (
    criteria.map((criterion, index) => (
      <div className="requirements-screen__criterion" key={`${index}-${criterion}`}>
        <b>{index + 1}</b>
        <span>{criterion}</span>
      </div>
    ))
  ) : (
    <p className="requirements-screen__criteria-empty">{emptyMessage}</p>
  );
}

function StoryRequirementDetails({ story }) {
  return (
    <section className="requirements-screen__story-details">
      <div className="requirements-screen__story-heading">
        <strong>{story.key}</strong>
        <span>{story.status} · {story.priority} priority</span>
        <h2>{story.summary}</h2>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="requirements-screen__jira-description">{story.description || "No description provided in Jira."}</p>
      <div className="requirements-screen__criteria-heading">
        <h3>ACCEPTANCE CRITERIA</h3>
        <span>{story.acceptanceCriteria.length} criteria from Jira</span>
      </div>
      <AcceptanceCriteriaList
        criteria={story.acceptanceCriteria}
        emptyMessage="No acceptance criteria were returned for this story in Jira."
      />
    </section>
  );
}

function EpicRequirementDetails({ epic }) {
  return (
    <div className="requirements-screen__epic-details">
      <div className="requirements-screen__story-heading">
        <strong>{epic.key}</strong>
        <span>{epic.status} · {epic.priority} priority</span>
        <h2>{epic.summary}</h2>
      </div>
      <div className="requirements-screen__criteria-heading">
        <h3>STORIES AND ACCEPTANCE CRITERIA</h3>
        <span>{epic.children.length} stories with acceptance criteria</span>
      </div>
      {epic.children.length ? epic.children.map((story) => (
        <StoryRequirementDetails key={story.key} story={story} />
      )) : (
        <p className="requirements-screen__criteria-empty">No stories linked to this epic were returned by Jira.</p>
      )}
    </div>
  );
}

function RequirementCard({ requirement, selected, isEpic, checked, onToggle, onSelect }) {
  return (
    <div className={`requirements-screen__card-row ${isEpic ? "requirements-screen__card-row--epic" : ""}`}>
      <button
        className={`requirements-screen__card ${selected ? "is-selected" : ""}`}
        type="button"
        onClick={() => onSelect(requirement)}
      >
        <div className="requirements-screen__card-top">
          <strong>{requirement.key}</strong>
          <span className={`requirements-screen__priority requirements-screen__priority--${requirement.priority.toLowerCase()}`}>
            {requirement.priority} risk
          </span>
          <small>{requirement.completeness ?? 65} pts</small>
        </div>
        <b>{requirement.summary}</b>
        <div className="requirements-screen__card-meta">
          <span>AC {requirement.completeness ?? 65}%</span>
          <span>Cov {requirement.coverage ?? "Partial"}</span>
          <span>Auto {requirement.automation ?? "None"}</span>
        </div>
        <i>
          <em style={{ width: `${requirement.completeness ?? 65}%` }} />
        </i>
      </button>
      {onToggle && (
        <label className="requirements-screen__card-checkbox">
          <input
            type="checkbox"
            checked={checked}
            onChange={() => onToggle(requirement.key)}
            aria-label={`Select ${requirement.type} ${requirement.key}`}
          />
        </label>
      )}
    </div>
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
      <div className="requirements-screen__impact-heading">
        <div>
          <h3>TEST CASE CREATION</h3>
          <h2>{testCase.title}</h2>
          <span>{testCase.source}</span>
        </div>
        <button type="button" onClick={onClose}>Back to details</button>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="requirements-screen__jira-description">{testCase.description}</p>
      <h3>PRECONDITIONS</h3>
      <p className="requirements-screen__jira-description">{testCase.preconditions}</p>
      <h3>TEST STEPS</h3>
      <ol className="requirements-screen__test-steps">
        {testCase.steps.map((step) => <li key={step}>{step}</li>)}
      </ol>
      <h3>EXPECTED RESULT</h3>
      <p className="requirements-screen__jira-description">{testCase.expected}</p>
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
      <div className="requirements-screen__impact-heading">
        <div>
          <h3>TEST PLAN</h3>
          <h2>{requirement.summary}</h2>
          <span>{hasJiraDescription ? `Jira · ${requirement.key}` : "Dummy test plan"}</span>
        </div>
        <button type="button" onClick={onClose}>Back to details</button>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="requirements-screen__jira-description">{description}</p>
      <h3>SCOPE</h3>
      <p className="requirements-screen__jira-description">{scope}</p>
      <h3>TEST SCENARIOS</h3>
      <ol className="requirements-screen__test-steps">
        {scenarios.map((scenario) => <li key={scenario}>{scenario}</li>)}
      </ol>
      <h3>EXIT CRITERIA</h3>
      <p className="requirements-screen__jira-description">All planned scenarios pass and no high-severity defects remain open.</p>
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
      <div className="requirements-screen__impact-heading">
        <div>
          <h3>TEST DATA REQUIREMENTS</h3>
          <h2>{requirement.summary}</h2>
          <span>{hasJiraDescription ? `Jira · ${requirement.key}` : "Dummy test data requirements"}</span>
        </div>
        <button type="button" onClick={onClose}>Back to details</button>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="requirements-screen__jira-description">{description}</p>
      <h3>REQUIRED DATA SETS</h3>
      <div className="requirements-screen__data-sets">
        {dataSets.map(([name, details]) => (
          <div className="requirements-screen__data-set" key={name}>
            <strong>{name}</strong>
            <span>{details}</span>
          </div>
        ))}
      </div>
      <h3>DATA CONTROLS</h3>
      <p className="requirements-screen__jira-description">Do not use production personal data. Reset or isolate test data between runs and record the values used for each test execution.</p>
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
      <div className="requirements-screen__impact-heading">
        <div>
          <h3>DEPENDENCY ANALYSIS</h3>
          <h2>{requirement.summary}</h2>
          <span>{hasJiraDescription ? `Jira · ${requirement.key}` : "Dummy dependency analysis"}</span>
        </div>
        <button type="button" onClick={onClose}>Back to details</button>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="requirements-screen__jira-description">{description}</p>
      <h3>DEPENDENCIES</h3>
      <div className="requirements-screen__dependency-list">
        {dependencies.map(([type, detail, status]) => (
          <div className="requirements-screen__dependency-item" key={type}>
            <div>
              <strong>{type}</strong>
              <span>{detail}</span>
            </div>
            <em>{status}</em>
          </div>
        ))}
      </div>
      <h3>VALIDATION</h3>
      <p className="requirements-screen__jira-description">Verify each dependency independently, test unavailable-service behaviour, and confirm that failures are reported without losing user data.</p>
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
      <div className="requirements-screen__impact-heading">
        <div>
          <h3>EFFORT AND RESOURCE ESTIMATES</h3>
          <h2>{requirement.summary}</h2>
          <span>{hasJiraDescription ? `Jira · ${requirement.key}` : "Dummy effort estimate"}</span>
        </div>
        <button type="button" onClick={onClose}>Back to details</button>
      </div>
      <h3>DESCRIPTION</h3>
      <p className="requirements-screen__jira-description">{description}</p>
      <h3>ESTIMATE BREAKDOWN</h3>
      <div className="requirements-screen__effort-list">
        {estimates.map(([work, resource, duration]) => (
          <div className="requirements-screen__effort-item" key={work}>
            <div>
              <strong>{work}</strong>
              <span>{resource}</span>
            </div>
            <em>{duration}</em>
          </div>
        ))}
      </div>
      <h3>ASSUMPTIONS</h3>
      <p className="requirements-screen__jira-description">The required environments and dependent services are available, scope changes are managed separately, and estimates include normal review and retesting effort.</p>
    </div>
  );
}

const INPUT_SCOPE_OPTIONS = [
  { id: "html", label: "HTML", accept: ".html,.htm,text/html" },
  { id: "audio", label: "Audio", accept: "audio/*" },
  { id: "file", label: "File", accept: ".pdf,.doc,.docx,.txt,.csv,.xlsx,.json" }
];

const INPUT_SCOPE_SOURCE_TYPE = { html: "HTML", audio: "AUDIO", file: "FILE" };

async function fileToBase64(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  const chunkSize = 0x8000;
  let binary = "";
  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }
  return window.btoa(binary);
}

const TEST_CASE_CONDITION_OPTIONS = [
  { id: "boundary", label: "Boundary conditions", detail: "Exercise minimum, maximum and edge values." },
  { id: "negative", label: "Negative test cases", detail: "Cover invalid input, rejected actions and failure states." },
  { id: "positive", label: "Positive test cases", detail: "Validate the happy path and expected business outcome." }
];

function InputScopeDialog({
  inputScopes,
  scopeFiles,
  testCaseConditions,
  canSubmit,
  onScopeToggle,
  onScopeFileChange,
  onConditionToggle,
  onCancel,
  onSubmit
}) {
  return (
    <div className="requirements-screen__scope-overlay" role="presentation" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onCancel();
    }}>
      <section className="requirements-screen__scope-dialog" role="dialog" aria-modal="true" aria-labelledby="input-scope-title">
        <div className="requirements-screen__scope-heading">
          <div>
            <h2 id="input-scope-title">Test Case Creation Setup</h2>
            <p>Choose the source material and coverage types for the selected stories.</p>
          </div>
          <button type="button" aria-label="Close input scope" onClick={onCancel}>x</button>
        </div>
        <div className="requirements-screen__scope-body">
          <section className="requirements-screen__scope-section">
            <div className="requirements-screen__scope-section-title">
              <h3>INPUT SCOPE</h3>
              <span>Select one source</span>
            </div>
            <div className="requirements-screen__scope-grid">
              {INPUT_SCOPE_OPTIONS.map((option) => (
                <label className="requirements-screen__choice-card" key={option.id}>
                  <input
                    type="checkbox"
                    checked={inputScopes[option.id]}
                    onChange={() => onScopeToggle(option.id)}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    <small>{option.id === "html" ? "Use page markup or exported HTML." : option.id === "audio" ? "Use walkthrough or discussion audio." : "Use supporting requirement files."}</small>
                  </span>
                  {inputScopes[option.id] && (
                    <span className="requirements-screen__browse-row">
                      <input
                        type="file"
                        accept={option.accept}
                        onChange={(event) => onScopeFileChange(option.id, event.target.files?.[0] ?? null)}
                      />
                      {scopeFiles[option.id]?.name && <em>{scopeFiles[option.id].name}</em>}
                    </span>
                  )}
                </label>
              ))}
            </div>
          </section>

          <section className="requirements-screen__scope-section">
            <div className="requirements-screen__scope-section-title">
              <h3>TEST CASE GENERATION CONDITIONS</h3>
              <span>Coverage to include</span>
            </div>
            <div className="requirements-screen__condition-list">
              {TEST_CASE_CONDITION_OPTIONS.map((option) => (
                <label className="requirements-screen__condition-row" key={option.id}>
                  <input
                    type="checkbox"
                    checked={testCaseConditions[option.id]}
                    onChange={() => onConditionToggle(option.id)}
                  />
                  <span>
                    <strong>{option.label}</strong>
                    <small>{option.detail}</small>
                  </span>
                </label>
              ))}
            </div>
          </section>
        </div>
        <div className="requirements-screen__scope-actions">
          <button type="button" onClick={onCancel}>Cancel</button>
          <button type="button" className="primary" onClick={onSubmit} disabled={!canSubmit}>Submit</button>
        </div>
      </section>
    </div>
  );
}

export function RequirementsScreen({ onCreateTestCases }) {
  const [payload, setPayload] = useState(null);
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedKey, setSelectedKey] = useState("EP-1003");
  const [checkedKeys, setCheckedKeys] = useState([]);
  const [activeTab, setActiveTab] = useState("Details");
  const [detailMode, setDetailMode] = useState("details");
  const [riskKey, setRiskKey] = useState(null);
  const [impactKeys, setImpactKeys] = useState([]);
  const [showInputScope, setShowInputScope] = useState(false);
  const [inputScopes, setInputScopes] = useState({ html: true, audio: false, file: false });
  const [scopeFiles, setScopeFiles] = useState({});
  const [testCaseConditions, setTestCaseConditions] = useState({
    boundary: true,
    negative: true,
    positive: true
  });

  function loadRequirements() {
    setLoading(true);
    setError("");
    fetchJiraIssueGroups({ requirementsOnly: true })
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
  const detailRequirement = selected;
  const allRequirements = useMemo(() => buildRequirements(payload), [payload]);
  const testCaseSelection = testDesignRequirements(allRequirements, checkedKeys, selected);

  function openInputScopeDialog() {
    if (!testCaseSelection.length) return;
    setShowInputScope(true);
  }

  function toggleInputScope(scope) {
    setInputScopes({ html: scope === "html", audio: scope === "audio", file: scope === "file" });
  }

  async function updateScopeFile(scope, file) {
    if (!file) {
      setScopeFiles((current) => ({ ...current, [scope]: null }));
      return;
    }

    try {
      const base64 = await fileToBase64(file);
      setScopeFiles((current) => ({
        ...current,
        [scope]: { name: file.name, mimeType: file.type || "", base64 }
      }));
    } catch {
      setScopeFiles((current) => ({ ...current, [scope]: null }));
    }
  }

  function toggleTestCaseCondition(condition) {
    setTestCaseConditions((current) => ({ ...current, [condition]: !current[condition] }));
  }

  const activeInputScope = Object.keys(inputScopes).find((scope) => inputScopes[scope]);
  const activeScopeFile = activeInputScope ? scopeFiles[activeInputScope] : null;

  function buildSupplementalContext() {
    if (!activeInputScope || !activeScopeFile) {
      return { source_type: "NONE" };
    }

    return {
      source_type: INPUT_SCOPE_SOURCE_TYPE[activeInputScope],
      file_name: activeScopeFile.name,
      mime_type: activeScopeFile.mimeType,
      content_base64: activeScopeFile.base64
    };
  }

  function buildGenerationConditions() {
    return {
      positive_test_cases: testCaseConditions.positive,
      negative_test_cases: testCaseConditions.negative,
      boundary_conditions: testCaseConditions.boundary
    };
  }

  function submitInputScope() {
    if (!onCreateTestCases || !testCaseSelection.length || !Object.values(testCaseConditions).some(Boolean)) return;
    setShowInputScope(false);
    onCreateTestCases(testCaseSelection, payload?.source, buildSupplementalContext(), buildGenerationConditions());
  }

  if (!selected) {
    return (
      <section className="requirements-screen" aria-label="Requirements workspace">
        <div className="requirements-screen__empty-state">
          {/* <FileText size={18} /> */}
          <strong>{
            loading ? 
            <section className="blank-workspace blank-workspace--message" aria-label="QE Engineer Requirements Loading">
              <div className="blank-workspace__message">
                <h1>Loading Requirements from Jira...</h1>
              </div>
            </section> : 
            "No Jira requirements found"}
          </strong>
          {!loading && <span>{error || "No stories with acceptance criteria were found in Jira."}</span>}
          {!loading && <button type="button" onClick={loadRequirements}><RefreshCw size={14} /> Retry Jira</button>}
        </div>
      </section>
    );
  }
  const selectedAcceptance = buildStoryAcceptance(detailRequirement, detailMode);
  const activeAcceptance = {
    summary: detailMode === "details" ? "Requirement acceptance criteria" : detailMode === "impact" ? "Impact analysis acceptance criteria" : detailMode === "test-case" ? "Test case acceptance criteria" : detailMode === "test-plan" ? "Test plan acceptance criteria" : detailMode === "test-data" ? "Test data acceptance criteria" : detailMode === "risk" ? "Risk analysis acceptance criteria" : detailMode === "dependency" ? "Dependency analysis acceptance criteria" : "Effort and resource acceptance criteria",
    items: selectedAcceptance.map((item) => [item.label, item.status])
  };

  return (
    <section className="requirements-screen" aria-label="Requirements workspace">
      <div className="requirements-screen__breadcrumbs">
        <span>Requirements</span>
        <ChevronRight size={13} />
        <span>Sprint 18</span>
        <ChevronRight size={13} />
        <strong>{selected.key}</strong>
      </div>

      <header className="requirements-screen__topbar">
        <div>
          <h1>Requirements Walkthrough</h1>
          <p>
            <span /> Source of record: {isJira ? `Jira - ${payload.projectKey || "project"}` : "Jira / dummy data"} · Updated moments ago · questions and links post back to Jira
          </p>
        </div>
        {/* <div className="requirements-screen__actions">
          <button type="button">Post Questions to Jira</button>
          <button type="button">Mark as Risk</button>
          <button className="primary" type="button">Create Test Plan</button>
        </div> */}
      </header>

      <div className="requirements-screen__workspace">
        <aside className="requirements-screen__list-panel">
          <label className="requirements-screen__search">
            <Search size={15} />
            <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search requirements" aria-label="Search requirements" />
          </label>
          {/* <div className="requirements-screen__filters">
            <span>Sprint 18 ×</span>
            <span>Risk: High ×</span>
            <button type="button">+ Status</button>
            <button type="button">+ Coverage</button>
            <button type="button">+ Owner</button>
          </div> */}
          {/* <button type="button" className="impact-analysis-button" onClick={() => {
            const selectedItems = checkedKeys.length
              ? buildRequirements(payload).filter(item => checkedKeys.includes(item.key)) : [selected];
            setImpactKeys(selectedItems.flatMap(item => item.type.toLowerCase() === "epic" ? item.children.map(story => story.key) : [item.key]));
            setDetailMode("impact");
          }}>Impact Analysis{checkedKeys.length ? ` (${checkedKeys.length} selected)` : ""}</button> */}
          <div className="requirements-screen__cards">
            {requirements.map((item) => (
              <RequirementCard
                key={item.key}
                requirement={item}
                selected={item.key === selected.key}
                isEpic={item.type.toLowerCase() === "epic"}
                checked={checkedKeys.includes(item.key)}
                onToggle={["story", "user story"].includes(item.type.toLowerCase()) ? (key) => {
                  setDetailMode("details");
                  setCheckedKeys((keys) => keys.includes(key) ? [] : [key]);
                } : undefined}
                onSelect={(value) => {
                  setSelectedKey(value.key);
                  setDetailMode("details");
                }}
              />
            ))}
          </div>
        </aside>

        <main className="requirements-screen__detail">
          {/* <div className="requirements-screen__detail-heading">
            <div>
              <div className="requirements-screen__detail-id">
                <strong>{selected.key}</strong>
                <span className="requirements-screen__risk">△ {selected.priority} risk</span>
                <span>{selected.coverage} coverage</span>
                <span>{selected.automation === "None" ? "No automation" : `${selected.automation} automation`}</span>
              </div>
              <h2>{selected.summary}</h2>
              <p>Epic: {selected.epic} · Owner: {selected.owner} · Dev: {selected.developer} · Updated {selected.updated}</p>
            </div>
            <div className="requirements-screen__scores">
              <span>AC COMPLETENESS <b>{selected.completeness}%</b></span>
              <span>TEST COVERAGE <b>{selected.coverage}</b></span>
            </div>
          </div> */}

          <div className="requirements-screen__tabs">
            {/* {["Details", "Traceability", "Linked defects (2)", "Comments (7)", "Change history"].map((tab) => ( */}
            {["Details"].map((tab) => (
              <button className={activeTab === tab ? "is-active" : ""} type="button" key={tab} onClick={() => setActiveTab(tab)}>{tab}</button>
            ))}
          </div>

          <div className="requirements-screen__description">
            {detailMode === "impact" ? (
              <JiraImpactAnalysis issueKeys={impactKeys} onClose={() => setDetailMode("details")} />
            ) : detailMode === "test-case" ? (
              <TestCaseDetails requirement={detailRequirement} isJira={isJira} onClose={() => setDetailMode("details")} />
            ) : detailMode === "test-plan" ? (
              <TestPlanDetails requirement={detailRequirement} isJira={isJira} onClose={() => setDetailMode("details")} />
            ) : detailMode === "test-data" ? (
              <TestDataRequirementsDetails requirement={detailRequirement} isJira={isJira} onClose={() => setDetailMode("details")} />
            ) : detailMode === "risk" ? (
              <JiraRiskAnalysis issueKeys={riskKey ? [riskKey] : []} onClose={() => setDetailMode("details")} />
            ) : detailMode === "dependency" ? (
              <DependencyAnalysisDetails requirement={detailRequirement} isJira={isJira} onClose={() => setDetailMode("details")} />
            ) : detailMode === "effort" ? (
              <EffortResourceDetails requirement={detailRequirement} isJira={isJira} onClose={() => setDetailMode("details")} />
            ) : (
              selected.type.toLowerCase() === "epic"
                ? <EpicRequirementDetails epic={selected} />
                : <StoryRequirementDetails story={selected} />
            )}
            {detailMode !== "impact" && detailMode !== "risk" && detailMode !== "details" && (
              <>
                <div className="requirements-screen__criteria-heading">
                  <h3>{activeAcceptance.summary}</h3>
                  <span>{activeAcceptance.items.length} criteria for this view</span>
                </div>
                {activeAcceptance.items.map(([label, status], index) => (
                  <div className="requirements-screen__criterion" key={label}>
                    <b>{index + 1}</b>
                    <span>{label}</span>
                    <em className={`criteria-${status.toLowerCase().replaceAll(" ", "-")}`}>{status}</em>
                  </div>
                ))}
              </>
            )}
          </div>
        </main>

        <AIRequirementAnalysis selectedRequirement={selected}
          testCaseSelectionCount={testCaseSelection.length}
          onCreateTestCases={onCreateTestCases ? openInputScopeDialog : undefined}
          onAction={(story, mode) => {
          if (mode === "impact") {
            setImpactKeys([story.key]);
          } else if (mode === "risk") {
            setRiskKey(story.key);
          } else {
            setSelectedKey(story.key);
          }
          setDetailMode(mode);
        }} />
      </div>

      {showInputScope && (
        <InputScopeDialog
          inputScopes={inputScopes}
          scopeFiles={scopeFiles}
          testCaseConditions={testCaseConditions}
          canSubmit={Object.values(testCaseConditions).some(Boolean)}
          onScopeToggle={toggleInputScope}
          onScopeFileChange={updateScopeFile}
          onConditionToggle={toggleTestCaseCondition}
          onCancel={() => setShowInputScope(false)}
          onSubmit={submitInputScope}
        />
      )}

      {error && <div className="requirements-screen__fallback"><FileText size={16} /><span>Jira could not be reached.<small>{error}</small></span></div>}
    </section>
  );
}
