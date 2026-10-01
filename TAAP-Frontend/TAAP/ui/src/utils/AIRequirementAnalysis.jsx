import { useEffect, useId, useState } from "react";
import { ChevronRight, Cog } from "lucide-react";
import { analysisCacheKey, analysisErrorMessage, analyzeRequirement } from "./requirementAnalysisService.js";

// In-memory only. A changed description, criteria, or model gets a new entry.
const completedAnalyses = new Map();

function StoryAnalysis({ story, initialOpen, onAction }) {
  const [open, setOpen] = useState(initialOpen);
  const [analysis, setAnalysis] = useState(() => completedAnalyses.get(analysisCacheKey(story)) ?? null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [attempt, setAttempt] = useState(0);
  const panelId = useId();
  const cacheKey = analysisCacheKey(story);

  useEffect(() => {
    if (!open || analysis) return;
    const controller = new AbortController();
    setLoading(true);
    setError("");
    // Allow StrictMode's setup/cleanup probe to finish before sending a paid request.
    const timer = setTimeout(() => {
      analyzeRequirement(story, { signal: controller.signal })
        .then(result => {
          if (controller.signal.aborted) return;
          completedAnalyses.set(cacheKey, result);
          if (completedAnalyses.size > 50) completedAnalyses.delete(completedAnalyses.keys().next().value);
          setAnalysis(result);
        })
        .catch(reason => { if (!controller.signal.aborted) setError(analysisErrorMessage(reason)); })
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [open, cacheKey, attempt, analysis]);

  return <>
    <section className="requirements-screen__story-analysis">
      <button type="button" className="requirements-screen__accordion-toggle" aria-expanded={open} aria-controls={panelId} onClick={() => setOpen(value => !value)}>
        <ChevronRight size={15} className={open ? "is-open" : ""} aria-hidden="true" />
        <span><strong>{story.key || story.id}</strong><span>{story.summary || story.title}</span></span>
        {analysis && <b title="AI assessment of requirement quality">{analysis.analysis_score}%</b>}
      </button>
      {open && <div id={panelId} className="requirements-screen__story-analysis-body">
        {loading && <p role="status">Analyzing this story…</p>}
        {error && <div role="alert" className="requirements-screen__analysis-error"><p>{error}</p><button type="button" onClick={() => setAttempt(value => value + 1)}>Retry analysis</button></div>}
        {analysis && <>
          <p className="requirements-screen__analysis-note">AI quality assessment · review suggested gaps</p>
          <h3>REQUIREMENT SUMMARY</h3>
          <p className="requirements-screen__summary-box">{analysis.requirement_summary}</p>
          <h3>FINDINGS</h3>
          {!analysis.findings.length && <p>No significant issues identified.</p>}
          {analysis.findings.map((finding, index) => <div className="requirements-screen__finding" key={`${finding.type}-${index}`}>
            <b>{finding.type === "MISSING_EDGE_CASE" ? "EDGE CASE" : finding.type.replaceAll("_", " ")}</b><span>{finding.message}</span>
          </div>)}
        </>}
        {/* <button className="requirements-screen__analysis-button" type="button" onClick={() => onAction(story, "impact")}>Impact Analysis</button> */}
        <div className="requirements-screen__analysis-actions">
          <button className="impact-analysis-button" type="button" onClick={() => onAction(story, "impact")}>Impact Analysis</button>
          <button className="risk-analysis-button" type="button" onClick={() => onAction(story, "risk")}>Risk Analysis</button>
        </div>
      </div>}
    </section>
  </>;
}

export default function AIRequirementAnalysis({ selectedRequirement, onAction, onCreateTestCases, testCaseSelectionCount = 0 }) {
  const isEpic = selectedRequirement?.type?.toLowerCase() === "epic";
  const stories = !selectedRequirement ? [] : isEpic ? selectedRequirement.children ?? [] : [selectedRequirement];
  return <aside className="requirements-screen__analysis" aria-label="AI Requirement Analysis">
    <div className="requirements-screen__analysis-title"><Cog size={16} /><strong>AI Requirement Analysis</strong></div>
    <p className="requirements-screen__analysis-note">{stories.length ? "Open a story to analyze its description and acceptance criteria." : "Select a story to analyze."}</p>
    <div className="requirements-screen__analysis-stories">
      {stories.map(story => <StoryAnalysis key={analysisCacheKey(story)} story={story} initialOpen={!isEpic} onAction={onAction} />)}
    </div>
    {(stories.length > 0 || testCaseSelectionCount > 0) && <div className="test-case-creation">
      <button className="test-case-button" type="button" onClick={onCreateTestCases} disabled={!onCreateTestCases || !testCaseSelectionCount}>Test Case Creation{testCaseSelectionCount > 1 ? ` (${testCaseSelectionCount} selected)` : ""}</button>
    </div>}
  </aside>;
}
