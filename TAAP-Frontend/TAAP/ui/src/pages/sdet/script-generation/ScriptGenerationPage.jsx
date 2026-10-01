import { Bot, CheckCircle2, Code2, Copy, Download, FileJson } from "lucide-react";
import { SdetPage, SdetPanel, SdetPill, SdetToast } from "../shared/SdetPageParts.jsx";
import { readGeneratedScriptDrafts } from "./scriptGenerationAgent.js";
import "./ScriptGenerationPage.css";
import { useMemo, useState } from "react";

function downloadFeature(draft) {
  const content = draft.featureScript?.content || "";
  const blob = new Blob([content], { type: "text/plain;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = draft.featureScript?.fileName || `${draft.scriptId}.feature`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function readinessTone(status) {
  if (status === "Ready for Review") return "green";
  if (status === "Needs Review") return "amber";
  return "gray";
}

function formatGeneratedAt(value) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Not recorded" : date.toLocaleString();
}

function jiraContextRows(draft) {
  return [
    ["Test Case", draft.source.testCaseId],
    ["Jira", draft.source.jiraKey || "Not linked"],
    ["Requirement", draft.source.requirementKey || "Not linked"],
    ["Story", draft.jiraContext.parentTitle || draft.jiraContext.parentKey || "Not linked"]
  ];
}

function informationRows(draft) {
  const sections = draft.featureScript?.sectionsUsed ?? {};
  return [
    ["Script Type", "BDD feature"],
    ["File", draft.featureScript?.fileName || draft.scriptName || "Not generated"],
    ["Agent", draft.generation.generatedBy],
    ["Model", draft.generation.model || "Local fallback"],
    ["Test Type", draft.classification.testType],
    ["Automation", draft.classification.automationStatus || (draft.classification.automationCandidate ? "Candidate" : "Not provided")],
    ["Preconditions", sections.preconditions ?? draft.preconditions.length],
    ["Steps", sections.steps ?? draft.steps.length],
    ["Test Data", sections.testData ?? draft.testDataRequirements.length],
    ["Expected Results", sections.expectedResults ?? 0]
  ];
}

function ScriptDraftList({ drafts, selectedId, onSelect }) {
  return (
    <div className="sdet-script-generation__draft-list" aria-label="Generated script drafts">
      {drafts.map((draft) => (
        <button
          key={draft.scriptId}
          type="button"
          className={`sdet-script-generation__draft-item ${draft.scriptId === selectedId ? "is-active" : ""}`}
          onClick={() => onSelect(draft.scriptId)}
        >
          <span className="sdet-script-generation__draft-id">{draft.scriptId}</span>
          <strong>{draft.title}</strong>
          <span>{draft.source.testCaseId} / {draft.source.jiraKey || "No Jira key"}</span>
          <span>Req: {draft.source.requirementKey || "Not linked"}</span>
          <span className="sdet-script-generation__draft-meta">
            {draft.classification.automationLayer} / {draft.classification.testType}
          </span>
        </button>
      ))}
    </div>
  );
}

function DraftDetail({ draft, onDownload, onCopyFeature }) {
  if (!draft) {
    return (
      <div className="sdet-script-generation__empty">
        <FileJson size={22} />
        <strong>Select a generated script draft</strong>
        <span>The agent output for each selected test case appears here.</span>
      </div>
    );
  }

  const featureContent = draft.featureScript?.content || "";

  return (
    <article className="sdet-script-generation__draft-detail">
      <header className="sdet-script-generation__draft-head">
        <div>
          <span className="sdet-script-generation__eyebrow">BDD feature script</span>
          <h2>{draft.title}</h2>
          <p>Generated from the information present in the selected Jira test case.</p>
        </div>
        <div className="sdet-script-generation__draft-actions">
          <button type="button" className="sdet-btn sdet-btn--sm" onClick={() => onCopyFeature(featureContent, draft.scriptId)} disabled={!featureContent}>
            <Copy size={13} strokeWidth={2} /> Copy Feature
          </button>
          <button type="button" className="sdet-btn sdet-btn--sm sdet-btn--primary" onClick={() => onDownload(draft)} disabled={!featureContent}>
            <Download size={13} strokeWidth={2} /> Download Feature
          </button>
        </div>
      </header>

      <div className="sdet-script-generation__pills">
        <SdetPill tone="blue">{draft.scriptId}</SdetPill>
        <SdetPill tone={readinessTone(draft.readiness.status)}>{draft.readiness.status}</SdetPill>
        <SdetPill tone="purple">Gherkin</SdetPill>
        <SdetPill tone="gray">BDD</SdetPill>
      </div>

      <dl className="sdet-script-generation__summary-grid">
        {informationRows(draft).map(([label, value]) => (
          <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
        ))}
        <div><dt>Generated At</dt><dd>{formatGeneratedAt(draft.generation.generatedAt)}</dd></div>
      </dl>

      <section className="sdet-script-generation__section">
        <h3>Jira information used</h3>
        <div className="sdet-script-generation__context-grid">
          {jiraContextRows(draft).map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="sdet-script-generation__section">
        <h3>Feature script</h3>
        {featureContent ? (
          <pre className="sdet-script-generation__feature-script">{featureContent}</pre>
        ) : (
          <p>Feature script is not available for this draft. Regenerate scripts from Test Design.</p>
        )}
      </section>

      <section className="sdet-script-generation__section">
        <h3>Readiness gaps</h3>
        {draft.readiness.missing.length ? (
          <ul className="sdet-script-generation__list sdet-script-generation__list--gaps">
            {draft.readiness.missing.map((item) => <li key={item}>{item}</li>)}
          </ul>
        ) : (
          <p className="sdet-script-generation__ready"><CheckCircle2 size={15} /> No blocking review gaps found.</p>
        )}
      </section>
    </article>
  );
}

export function ScriptGenerationPage() {
  const [toast, setToast] = useState("");
  const [generatedDrafts, setGeneratedDrafts] = useState(() => readGeneratedScriptDrafts());
  const [selectedDraftId, setSelectedDraftId] = useState(() => readGeneratedScriptDrafts()[0]?.scriptId ?? "");
  const selectedDraft = useMemo(() => generatedDrafts.find((draft) => draft.scriptId === selectedDraftId) ?? generatedDrafts[0] ?? null, [generatedDrafts, selectedDraftId]);
  const hasAgentDrafts = generatedDrafts.length > 0;

  function refreshAgentOutput() {
    const drafts = readGeneratedScriptDrafts();
    setGeneratedDrafts(drafts);
    setSelectedDraftId(drafts[0]?.scriptId ?? "");
    setToast(drafts.length ? `${drafts.length} generated script draft${drafts.length === 1 ? "" : "s"} loaded.` : "No generated script drafts found.");
  }

  async function copyFeature(content, scriptId) {
    try {
      await navigator.clipboard.writeText(content);
      setToast(`${scriptId} feature script copied.`);
    } catch {
      setToast("Clipboard unavailable. Download the feature file instead.");
    }
  }

  return (
    <SdetPage
      ariaLabel="Script Generation"
      breadcrumbs={["Script Generation"]}
      title="Script Generation"
      status={{ tone: hasAgentDrafts ? "green" : "amber", icon: hasAgentDrafts ? <Bot size={15} strokeWidth={2} /> : <Code2 size={15} strokeWidth={2} />, text: hasAgentDrafts ? `${generatedDrafts.length} generated script${generatedDrafts.length === 1 ? "" : "s"}` : "No generated scripts" }}
      notes={hasAgentDrafts ? ["Generated from selected Test Design cases", "Jira context is included where available"] : ["No agent output yet", "Use Generate Test Scripts in Test Design after selecting cases"]}
    >
      {hasAgentDrafts ? (
        <SdetPanel
          label="SDET Script Generation Agent"
          aside={<button type="button" className="sdet-link" onClick={refreshAgentOutput}>Refresh agent output</button>}
        >
          <div className="sdet-script-generation__agent-banner">
            <Bot size={18} />
            <div>
              <strong>Generated from selected test cases</strong>
              <span>Each draft shows a BDD feature script created from the selected Jira test case.</span>
            </div>
          </div>
          <div className="sdet-script-generation__draft-layout">
            <ScriptDraftList drafts={generatedDrafts} selectedId={selectedDraft?.scriptId} onSelect={setSelectedDraftId} />
            <DraftDetail draft={selectedDraft} onDownload={downloadFeature} onCopyFeature={copyFeature} />
          </div>
        </SdetPanel>
      ) : (
        <SdetPanel label="Generated scripts" aside={<button type="button" className="sdet-link" onClick={refreshAgentOutput}>Refresh agent output</button>}>
          <div className="sdet-script-generation__empty sdet-script-generation__empty--inline">
            <FileJson size={22} />
            <strong>No agent-generated scripts yet</strong>
            <span>Select cases in Test Design and click Generate Test Scripts.</span>
          </div>
        </SdetPanel>
      )}
      <SdetToast message={toast} onDone={() => setToast("")} />
    </SdetPage>
  );
}
