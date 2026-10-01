import { useEffect, useState } from "react";
import { fetchJiraRiskSection } from "@taap/service-layer";
import { explainRiskAnalysis } from "./riskAnalysisService.js";
import { analysisErrorMessage } from "./requirementAnalysisService.js";
import "./JiraImpactAnalysis.css";

function StoryRiskExplanation({ storyKey }) {
  const [state, setState] = useState({ phase: "jira" });
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    setState({ phase: "jira" });
    // Avoid duplicate requests during React StrictMode's setup/cleanup probe.
    const timer = setTimeout(async () => {
      let story;
      try {
        story = await fetchJiraRiskSection(storyKey, { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (!story.sections.length) { setState({ phase: "empty", story }); return; }
        setState({ phase: "llm", story });
        const analysis = await explainRiskAnalysis(story, { signal: controller.signal });
        if (!controller.signal.aborted) setState({ phase: "complete", story, analysis });
      } catch (error) {
        if (!controller.signal.aborted) setState({ phase: "error", story, error: story ? analysisErrorMessage(error) : error.message });
      }
    }, 0);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [storyKey, attempt]);
  return <article>
    <h3>{state.story ? <a href={state.story.url} target="_blank" rel="noreferrer">{storyKey}</a> : storyKey}{state.story?.summary ? ` · ${state.story.summary}` : ""}</h3>
    {state.phase === "jira" && <p role="status">Fetching the Risk Analysis section from Jira…</p>}
    {state.phase === "llm" && <p role="status">Generating the risk analysis explanation…</p>}
    {state.phase === "empty" && <p>No Risk Analysis section is recorded for this story in Jira.</p>}
    {state.phase === "error" && <div role="alert"><p>{state.error}</p><button type="button" onClick={() => setAttempt(value => value + 1)}>Retry risk analysis</button></div>}
    {state.analysis && <>
      <p>AI explanation based on this story’s recorded Jira Risk Analysis.</p>
      <h4>Risk summary</h4><p className="jira-impact__text">{state.analysis.summary}</p>
      {state.analysis.details.map((detail, index) => <section key={index}>
        <h4>{detail.area}</h4><p className="jira-impact__text">{detail.explanation}</p>
        <blockquote className="jira-impact__text">{detail.evidence}</blockquote>
      </section>)}
      {state.analysis.missing_information.length > 0 && <><h4>Clarifications needed</h4><ul>{state.analysis.missing_information.map((item, index) => <li key={index}>{item}</li>)}</ul></>}
    </>}
    {!!state.story?.sections.length && <details><summary>View original Jira Risk Analysis</summary>
      {state.story.sections.map((section, index) => <section key={index}><h4>{section.source}</h4><p className="jira-impact__text">{section.text}</p></section>)}
    </details>}
  </article>;
}

export default function JiraRiskAnalysis({ issueKeys, onClose }) {
  const keys = [...new Set(issueKeys)];
  return <section className="jira-impact" aria-label="Jira risk analysis">
    <header><h2>Risk Analysis</h2><button className="back-details" type="button" onClick={onClose}>Back to details</button></header>
    {!keys.length && <p>Select a user story to analyze its recorded risk.</p>}
    {keys.map(key => <StoryRiskExplanation key={key} storyKey={key} />)}
  </section>;
}
