import { useState } from "react";
import { ArrowLeft, ListChecks, ShieldCheck, ScrollText } from "lucide-react";
import { useRiskTierRun } from "./risk-tier/lib/useRiskTierRun.ts";
import { agentLabel } from "./risk-tier/components/RunConsole/agentLabel.ts";
import TestSelectionReport from "./risk-tier/components/TestSelectionReport/TestSelectionReport.tsx";
import ExclusionSignoffQueue from "./risk-tier/components/ExclusionSignoffQueue/ExclusionSignoffQueue.tsx";
import ExecutionAuditLog from "./risk-tier/components/ExecutionAuditLog/ExecutionAuditLog.tsx";
// Performance Metrics panel is temporarily disabled for testing — its API isn't ready yet.
// import PerformanceMetrics from "./risk-tier/components/PerformanceMetrics/PerformanceMetrics.tsx";
import "./AgentReviewsHome.css";

const initialFormData = {
  releaseId: "",
  dropdownOne: "option-2",
  checkbox1: true,
  checkbox2: true,
  checkbox3: true,
  checkbox4: true,
  notes: "",
  fileName: ""
};

const resultPanels = [
  {
    id: "test-selection",
    label: "Test Selection & Report",
    description: "Regression risk scoring and rationale for every test case in the release.",
    icon: ListChecks
  },
  {
    id: "exclusion-signoff",
    label: "Exclusion Sign Off",
    description: "Human sign-off queue for excluded or optional tests carrying residual risk.",
    icon: ShieldCheck
  },
  {
    id: "audit-log",
    label: "Execution Audit Log",
    description: "Immutable, per-agent decision ledger and the post-release feedback loop.",
    icon: ScrollText
  }
  // Performance Metrics panel is temporarily disabled for testing — its API isn't ready yet.
  // {
  //   id: "performance-metrics",
  //   label: "Performance Metrics",
  //   description: "Evaluation metrics for the Risk Tier pipeline's own accuracy and latency.",
  //   icon: Gauge
  // }
];

function ResultPanelCard({ panel, enabled, onOpen }) {
  const Icon = panel.icon;

  return (
    <button
      className="agent-review-card"
      type="button"
      disabled={!enabled}
      title={enabled ? undefined : "Run Job Review to generate this data first"}
      onClick={() => onOpen(panel.id)}
    >
      <Icon className="agent-review-card__icon" size={22} strokeWidth={1.65} />
      <span className="agent-review-card__title">{panel.label}</span>
      <span className="agent-review-card__description">{panel.description}</span>
    </button>
  );
}

const PANEL_COMPONENTS = {
  "test-selection": TestSelectionReport,
  "exclusion-signoff": ExclusionSignoffQueue,
  "audit-log": ExecutionAuditLog
  // "performance-metrics": PerformanceMetrics
};

export function AgentReviewsHome() {
  const [openPanelId, setOpenPanelId] = useState(null);
  const [formData, setFormData] = useState(initialFormData);
  const [errors, setErrors] = useState({});
  const { state: run, run: runPipeline } = useRiskTierRun();

  const isRunning = run.phase === "running";
  const isCompleted = run.phase === "completed";

  const validateForm = () => {
    const nextErrors = {};

    if (!formData.releaseId.trim()) {
      nextErrors.releaseId = "Please enter a release ID.";
    }

    if (formData.dropdownOne === "option-1") {
      nextErrors.dropdownOne = "Please select a test suite.";
    }

    const anyBusinessRuleSelected = [
      formData.checkbox1,
      formData.checkbox2,
      formData.checkbox3,
      formData.checkbox4
    ].some(Boolean);

    if (!anyBusinessRuleSelected) {
      nextErrors.businessRules = "Please select at least one business rule.";
    }

    return nextErrors;
  };

  const handleChange = (event) => {
    const { name, value, type, checked } = event.target;

    setFormData((previous) => ({
      ...previous,
      [name]: type === "checkbox" ? checked : value
    }));

    setErrors((previous) => {
      if (!previous[name]) {
        return previous;
      }

      const updatedErrors = { ...previous };
      delete updatedErrors[name];
      delete updatedErrors.businessRules;
      delete updatedErrors.dropdownOne;
      delete updatedErrors.releaseId;
      return updatedErrors;
    });
  };

  const handleFileChange = (event) => {
    const file = event.target.files?.[0];
    setFormData((previous) => ({
      ...previous,
      fileName: file ? file.name : ""
    }));
  };

  const handleSubmit = (event) => {
    event.preventDefault();

    if (isRunning) return;

    const nextErrors = validateForm();

    if (Object.keys(nextErrors).length > 0) {
      setErrors(nextErrors);
      return;
    }

    setErrors({});
    runPipeline(formData.releaseId.trim());
  };

  if (openPanelId) {
    const PanelComponent = PANEL_COMPONENTS[openPanelId];
    return (
      <section className="agent-review-tool" aria-label="Risk Tier Result">
        <div className="agent-review-tool__bar">
          <button
            className="agent-review-tool__back"
            type="button"
            onClick={() => setOpenPanelId(null)}
          >
            <ArrowLeft size={16} strokeWidth={1.8} />
            Back to Agent Reviews
          </button>
        </div>
        <div className="agent-review-tool__content">
          <PanelComponent />
        </div>
      </section>
    );
  }

  const agentCards = run.agentOrder.map((key) => run.agents[key]);

  return (
    <section className="agent-review-home" aria-label="Agent Reviews">
      <div className="agent-review-layout">
        <div className="agent-review-main">
          <h1>Risk Tier Agent</h1>
          <p>Submit a Job Review to run the Risk Tier pipeline for a release, then open a result panel below.</p>
        </div>
      </div>
      <div className="agent-review-form-container">
          <form className="agent-review-form" onSubmit={handleSubmit}>
            <div className="agent-review-form__row">
              <label className="agent-review-field"> Release ID
                <input
                  type="text"
                  name="releaseId"
                  value={formData.releaseId}
                  onChange={handleChange}
                  placeholder="e.g. R25.4"
                  disabled={isRunning}
                />
                {errors.releaseId && <span className="agent-review-error">{errors.releaseId}</span>}
              </label>

              <label className="agent-review-field"> Test Suites
                <select name="dropdownOne" value={formData.dropdownOne} onChange={handleChange} disabled={isRunning}>
                  <option value="option-1">---Select---</option>
                  <option value="option-2">Regression</option>
                  <option value="option-3">Functional</option>
                  <option value="option-4">Sanity</option>
                  <option value="option-5">Security</option>
                </select>
                {errors.dropdownOne && <span className="agent-review-error">{errors.dropdownOne}</span>}
              </label>
            </div>

            <div className="agent-review-checkbox-group">
              <span className="agent-review-checkbox-label">Business Rules: </span>

              <label className="agent-review-checkbox">
                <input
                  type="checkbox"
                  name="checkbox1"
                  checked={formData.checkbox1}
                  onChange={handleChange}
                  disabled={isRunning}
                />
                <span>Tier 1</span>
              </label>

              <label className="agent-review-checkbox">
                <input
                  type="checkbox"
                  name="checkbox2"
                  checked={formData.checkbox2}
                  onChange={handleChange}
                  disabled={isRunning}
                />
                <span>Tier 2</span>
              </label>

              <label className="agent-review-checkbox">
                <input
                  type="checkbox"
                  name="checkbox3"
                  checked={formData.checkbox3}
                  onChange={handleChange}
                  disabled={isRunning}
                />
                <span>Tier 3</span>
              </label>

              <label className="agent-review-checkbox">
                <input
                  type="checkbox"
                  name="checkbox4"
                  checked={formData.checkbox4}
                  onChange={handleChange}
                  disabled={isRunning}
                />
                <span>Tier 4</span>
              </label>
            </div>

            {errors.businessRules && <p className="agent-review-error">{errors.businessRules}</p>}

            <label className="agent-review-field">
              <span>Comments</span>
              <textarea
                name="notes"
                value={formData.notes}
                onChange={handleChange}
                rows={5}
                placeholder="Enter your comments here..."
                disabled={isRunning}
              />
            </label>

            <div className="agent-review-upload">
              <input
                id="agent-review-file"
                type="file"
                hidden
                onChange={handleFileChange}
                disabled={isRunning}
              />
              <label htmlFor="agent-review-file" className="agent-review-upload__button">
                Upload File
              </label>
              {formData.fileName ? <span>{formData.fileName}</span> : <span>No file selected</span>}
            </div>

            <div className="review-button">
              <button className="agent-review-submit" type="submit" disabled={isRunning}>
                {isRunning ? "Running…" : "Job Review"}
              </button>
            </div>
          </form>

          <aside className="agent-pipeline-panel" aria-label="Agent Pipeline">
            <h3>Agent Pipeline</h3>

            {run.phase === "idle" && (
              <p className="agent-pipeline-empty">
                No run started yet — fill in the form and click Job Review to start the Risk Tier pipeline.
              </p>
            )}

            {run.phase === "failed" && (
              <p className="agent-pipeline-failure">Run failed — {run.error}</p>
            )}

            {run.phase !== "idle" && (
              <>
                <div className="agent-pipeline-summary">
                  {run.phase === "running" && agentCards.length === 0 && "Waiting for the first agent to start…"}
                  {run.phase === "running" && agentCards.length > 0 && `Analyzing release ${run.releaseId}…`}
                  {run.phase === "completed" && `Completed — ${run.releaseId}`}
                  {run.phase === "failed" && `Stopped — ${run.releaseId}`}
                </div>

                <div className="agent-pipeline-rows">
                  {agentCards.map((agent, index) => (
                    <div key={agent.agent} className="agent-pipeline-row">
                      <div className="agent-pipeline-rail">
                        {index < agentCards.length - 1 && (
                          <span className={`agent-pipeline-line agent-pipeline-line--${agent.status}`} />
                        )}
                        <span className={`agent-pipeline-dot agent-pipeline-dot--${agent.status}`}>
                          {agent.status === "finished" && <span className="agent-pipeline-check">✓</span>}
                          {agent.status === "running" && <span className="agent-pipeline-spinner" />}
                          {agent.status === "failed" && <span className="agent-pipeline-cross">✕</span>}
                        </span>
                      </div>

                      <div className="agent-pipeline-content">
                        <div className="agent-pipeline-namerow">
                          <span className="agent-pipeline-name">{agent.agentName || agentLabel(agent.agent)}</span>
                          <span className="agent-pipeline-time">{agent.updatedAt}</span>
                        </div>
                        <div className={`agent-pipeline-state agent-pipeline-state--${agent.status}`}>
                          {agent.status === "finished" && "Completed"}
                          {agent.status === "running" && "Running"}
                          {agent.status === "pending" && "Pending"}
                          {agent.status === "failed" && "Failed"}
                        </div>
                        {agent.text && <div className="agent-pipeline-detail">{agent.text}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </aside>
      </div>

      <div className="agent-review-grid" aria-label="Risk Tier result panels">
        {resultPanels.map((panel) => (
          <ResultPanelCard key={panel.id} panel={panel} enabled={isCompleted} onOpen={setOpenPanelId} />
        ))}
      </div>
    </section>
  );
}
