import { Fragment, useState } from "react";
import { Briefcase, FileText } from "lucide-react";
import workflowData from "./workflowData.json";
import "./WorkflowPage.css";

// Manual QE Workflow — a 10-stage guided flow, laid out per the approved
// design mockups: a numbered stage stepper, a banded stage header with
// prev/next, an agent banner, then one card per task splitting what YOU do
// from what the AGENT did behind the scenes.
//
// Stage content is data-driven from workflowData.json. The supporting data
// panels below each stage's cards render from three primitives (stats /
// table / tree) chosen by a `type` field, so adding a panel is a JSON edit
// rather than a new component.
//
// Each stage also carries a `source` marker surfaced as a small badge —
// without it there is nothing on screen distinguishing a real Jira row from
// a fabricated one, and several stages (Planning, Data & env, Defects) have
// no Jira backing at all today.

const SOURCE_BADGE = {
  jira: { label: "Live Jira", tone: "live" },
  partial: { label: "Partly live", tone: "partial" },
  mock: { label: "Sample data", tone: "mock" },
  empty: { label: "Not wired", tone: "empty" }
};

// Stage sources that survive Jira-only mode. "partial" counts as Jira-backed
// per the brief — those stages do read real Jira, just not for every field.
const JIRA_BACKED = new Set(["jira", "partial"]);

// VITE_TAAP_WORKFLOW_SHOW_ALL (Integration/TAAP/.env)
//   true  -> every stage, Jira and sample data alike
//   false -> only Jira-backed stages; sample-data and not-yet-wired stages
//            are hidden outright rather than shown empty
// Anything other than an explicit "false" leaves the full view on, so a
// missing or malformed value can never silently hide real stages.
const SHOW_ALL =
  String(import.meta.env.VITE_TAAP_WORKFLOW_SHOW_ALL ?? "true").trim().toLowerCase() !==
  "false";

const TASK_STATUS = {
  "agent-handled": { label: "Agent-handled · evidence attached", tone: "done" },
  "awaiting-review": { label: "Awaiting your review", tone: "review" },
  approved: { label: "Approved", tone: "approved" },
  todo: { label: "Not started", tone: "todo" }
};

// Status-ish cell values get a coloured pill. Anything not listed renders as
// plain text, so a new value can never break a table.
const VALUE_TONE = {
  pass: "good", passed: "good", covered: "good", ready: "good", yes: "good",
  available: "good", done: "good", answered: "good", high: "good",
  "on track": "good", approved: "good",
  fail: "bad", failed: "bad", uncovered: "bad", down: "bad", no: "bad",
  critical: "bad", open: "bad", "at risk": "bad", low: "bad",
  blocked: "warn", stale: "warn", busy: "warn", pending: "warn",
  "in progress": "warn", medium: "warn",
  "to do": "neutral", "not started": "neutral", "not required": "neutral"
};

// Identifiers and figures inside the agent's narration are tinted so the
// concrete facts ("BUG-801", "42/42", "24.8.183") stand out from the prose,
// matching the mockups. Purely presentational — driven by shape, so the
// copy in workflowData.json stays plain text with no markup to maintain.
const ENTITY_RE =
  /\b(?:US|TC|BUG|EP|SCRUM|AC|Q)-\d+\b|\b\d+(?:\.\d+)+\b|\b\d+\/\d+\b|\b\d+(?:\.\d+)?%\b|\bbuild \.?\d[\d.]*\b/g;

function highlight(text) {
  const out = [];
  let last = 0;
  for (const match of text.matchAll(ENTITY_RE)) {
    if (match.index > last) out.push(text.slice(last, match.index));
    out.push(
      <span className="wf-ent" key={`${match.index}-${match[0]}`}>
        {match[0]}
      </span>
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out.map((part, i) => <Fragment key={i}>{part}</Fragment>);
}

function toneFor(value) {
  return VALUE_TONE[String(value).trim().toLowerCase()] ?? "neutral";
}

function StatsPanel({ panel }) {
  return (
    <div className="wf-stats">
      {panel.items.map((item) => (
        <div key={item.label} className={`wf-stat wf-stat--${item.tone ?? "plain"}`}>
          <span className="wf-stat__value">{item.value}</span>
          <span className="wf-stat__label">{item.label}</span>
        </div>
      ))}
    </div>
  );
}

function TablePanel({ panel }) {
  return (
    <div className="wf-tablewrap">
      <table className="wf-table">
        <thead>
          <tr>
            {panel.columns.map((col) => (
              <th key={col.key} className={col.align === "right" ? "is-right" : undefined}>
                {col.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {panel.rows.map((row, index) => (
            <tr key={row.key ?? row.id ?? index}>
              {panel.columns.map((col) => {
                const value = row[col.key];
                const className = [
                  col.align === "right" ? "is-right" : "",
                  col.wide ? "is-wide" : ""
                ].filter(Boolean).join(" ");
                return (
                  <td key={col.key} className={className || undefined}>
                    {col.as === "status" ? (
                      <span className={`wf-pill wf-pill--${toneFor(value)}`}>{value}</span>
                    ) : (
                      value
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function TreePanel({ panel }) {
  return (
    <ul className="wf-tree">
      {panel.nodes.map((epic) => (
        <li key={epic.key} className="wf-tree__epic">
          <span className="wf-tree__label">
            {epic.label}
            <span className="wf-tree__key">{epic.key}</span>
          </span>
          <ul>
            {epic.children.map((story) => (
              <li key={story.key} className="wf-tree__story">
                <span className="wf-tree__label">
                  {story.label}
                  <span className="wf-tree__key">{story.key}</span>
                </span>
                {story.cases.length > 0 ? (
                  <span className="wf-tree__cases">
                    {story.cases.map((testCase) => (
                      <span key={testCase} className="wf-chip">{testCase}</span>
                    ))}
                  </span>
                ) : (
                  <span className="wf-pill wf-pill--bad">No test cases</span>
                )}
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

function Panel({ panel }) {
  return (
    <section className="wf-panel">
      <h3 className="wf-panel__title">{panel.title}</h3>
      {panel.type === "stats" && <StatsPanel panel={panel} />}
      {panel.type === "table" && <TablePanel panel={panel} />}
      {panel.type === "tree" && <TreePanel panel={panel} />}
    </section>
  );
}

/**
 * The per-task workspace — where the reviewer actually does the work that
 * the card only summarises: read both sides, open the agent's evidence,
 * leave an audit note, then decide. Reached from any card's "Open
 * workspace" link and shared by every stage, so each task gets the same
 * review surface rather than ten bespoke ones.
 */
function WorkspaceView({ stage, task, evidence, placeholder, decisionNote, onBack }) {
  const status = TASK_STATUS[task.status] ?? TASK_STATUS.todo;

  return (
    <div className="wf-ws">
      <nav className="wf-ws__crumb">
        <button type="button" onClick={onBack}>Manual QE Workflow</button>
        <span aria-hidden="true">›</span>
        <button type="button" onClick={onBack}>{stage.title}</button>
      </nav>

      <header className="wf-ws__head">
        <h1 className="wf-ws__title">{task.title}</h1>
        <span className={`wf-badge wf-badge--${status.tone}`}>{status.label}</span>
      </header>

      <div className="wf-ws__split">
        <section className="wf-ws__pane">
          <span className="wf-lbl">Your part</span>
          <p>{task.you}</p>
        </section>
        <section className="wf-ws__pane wf-ws__pane--agent">
          <span className="wf-lbl">
            <Briefcase size={13} strokeWidth={1.7} />
            Agent — behind the scenes
          </span>
          <p>{highlight(task.agent)}</p>
        </section>
      </div>

      <section className="wf-ws__block">
        <span className="wf-lbl">Attached evidence</span>
        <div className="wf-ws__evidence">
          {evidence.map((item) => (
            <button key={item.id} className="wf-ws__file" type="button">
              <FileText size={15} strokeWidth={1.7} />
              {item.label}
            </button>
          ))}
        </div>
      </section>

      <section className="wf-ws__block">
        <span className="wf-lbl">Review notes</span>
        <textarea className="wf-ws__notes" rows={5} placeholder={placeholder} />
      </section>

      <footer className="wf-ws__decision">
        <p>
          <strong>Your decision</strong> — {decisionNote}
        </p>
        <div className="wf-ws__decisionbtns">
          {task.actions.length > 0 ? (
            task.actions.map((action) => (
              <button
                key={action.id}
                type="button"
                className={`wf-btn wf-btn--${action.variant}`}
              >
                {action.label}
              </button>
            ))
          ) : (
            <span className="wf-ws__noaction">No decision required — evidence attached.</span>
          )}
        </div>
      </footer>
    </div>
  );
}

function TaskCard({ task, onOpen }) {
  const status = TASK_STATUS[task.status] ?? TASK_STATUS.todo;

  return (
    <article className="wf-task">
      <header className="wf-task__head">
        <h3 className="wf-task__title">{task.title}</h3>
        <div className="wf-task__meta">
          <span className={`wf-badge wf-badge--${status.tone}`}>{status.label}</span>
          <button className="wf-task__workspace" type="button" onClick={onOpen}>
            Open workspace <span aria-hidden="true">→</span>
          </button>
        </div>
      </header>

      <div className="wf-task__cols">
        <div className="wf-task__col">
          <span className="wf-task__collabel">You</span>
          <p>{task.you}</p>
          {task.actions.length > 0 && (
            <div className="wf-task__actions">
              {task.actions.map((action) => (
                <button
                  key={action.id}
                  type="button"
                  className={`wf-btn wf-btn--${action.variant}`}
                >
                  {action.label}
                </button>
              ))}
            </div>
          )}
        </div>
        <div className="wf-task__col">
          <span className="wf-task__collabel">Agent — behind the scenes</span>
          <p>{highlight(task.agent)}</p>
        </div>
      </div>
    </article>
  );
}

export function WorkflowPage() {
  const {
    context,
    stages: allStages,
    defaultEvidence,
    reviewNotesPlaceholder,
    decisionNote
  } = workflowData;

  // In Jira-only mode the sample-data stages are dropped from the flow
  // entirely, so the stepper renumbers 1..N over what remains rather than
  // leaving gaps where the hidden stages used to be.
  const stages = SHOW_ALL
    ? allStages
    : allStages.filter((stage) => JIRA_BACKED.has(stage.source));

  const [activeId, setActiveId] = useState(stages[0].id);
  // Which task's workspace is open, if any. Cleared whenever the stage
  // changes so switching stages always lands back on the stage view.
  const [openTaskId, setOpenTaskId] = useState(null);

  const activeIndex = stages.findIndex((stage) => stage.id === activeId);
  const stage = stages[activeIndex];
  const prevStage = stages[activeIndex - 1];
  const nextStage = stages[activeIndex + 1];
  const badge = SOURCE_BADGE[stage.source] ?? SOURCE_BADGE.mock;

  const goToStage = (id) => {
    setActiveId(id);
    setOpenTaskId(null);
  };

  const openTask = stage.tasks.find((task) => task.id === openTaskId) ?? null;

  if (openTask) {
    return (
      <section className="wf" aria-label={`${openTask.title} workspace`}>
        <WorkspaceView
          stage={stage}
          task={openTask}
          evidence={openTask.evidence ?? defaultEvidence}
          placeholder={reviewNotesPlaceholder}
          decisionNote={decisionNote}
          onBack={() => setOpenTaskId(null)}
        />
      </section>
    );
  }

  return (
    <section className="wf" aria-label="Manual QE Workflow">
      <div className="wf-context">
        {[
          ["Project", context.project],
          ["Release", context.release],
          ["Sprint", context.sprint],
          ["Environment", context.environment]
        ].map(([label, value]) => (
          <div key={label} className="wf-context__item">
            <span className="wf-context__label">{label}</span>
            <span className="wf-context__value">{value}</span>
          </div>
        ))}
        <div className="wf-context__spacer" />
        <div className="wf-context__integrations">
          {context.integrations.map((integration) => (
            <span
              key={integration.id}
              className={`wf-int ${integration.connected ? "is-on" : ""}`}
              title={integration.connected ? "Connected" : "Not connected"}
            >
              {integration.label}
            </span>
          ))}
          <span className="wf-context__fetched">fetched {context.fetchedAt}</span>
        </div>
      </div>

      {!SHOW_ALL && (
        <div className="wf-modebar">
          Jira-only view — showing {stages.length} of {allStages.length} stages.
          {" "}
          {allStages.length - stages.length} sample-data stages are hidden. Set{" "}
          <code>VITE_TAAP_WORKFLOW_SHOW_ALL=true</code> to see them.
        </div>
      )}

      <div className="wf-head">
        <p className="wf__crumb">{context.sprint} · {context.project}</p>
        <h1 className="wf__title">Manual QE Workflow</h1>

        <nav className="wf-steps" aria-label="Workflow stages">
          {stages.map((item, position) => {
            const isActive = item.id === activeId;
            const started = item.completed > 0;
            const complete = item.total > 0 && item.completed >= item.total;
            return (
              <button
                key={item.id}
                type="button"
                className={`wf-step${isActive ? " is-active" : ""}`}
                onClick={() => goToStage(item.id)}
              >
                <span className="wf-step__num">{String(position + 1).padStart(2, "0")}</span>
                <span className="wf-step__label">{item.label}</span>
                <span className="wf-step__count">{item.completed}/{item.total}</span>
                <span
                  className={
                    "wf-step__dot" +
                    (complete ? " is-complete" : started ? " is-started" : "")
                  }
                  aria-hidden="true"
                />
              </button>
            );
          })}
        </nav>
      </div>

      <div className="wf-stagebar">
        <div className="wf-stagebar__left">
          <span className="wf-stagebar__counter">
            Stage <strong>{activeIndex + 1}</strong> / {stages.length}
          </span>
          <h2 className="wf-stagebar__name">{stage.title}</h2>
          <span className={`wf-srcbadge wf-srcbadge--${badge.tone}`}>{badge.label}</span>
        </div>
        <div className="wf-stagebar__nav">
          {prevStage && (
            <button
              className="wf-prev"
              type="button"
              onClick={() => goToStage(prevStage.id)}
            >
              <span aria-hidden="true">←</span> Prev stage
            </button>
          )}
          {nextStage && (
            <button
              className="wf-next"
              type="button"
              onClick={() => goToStage(nextStage.id)}
            >
              Next stage <span aria-hidden="true">→</span>
            </button>
          )}
        </div>
      </div>

      <div className="wf-body">
        {stage.source === "empty" ? (
          <div className="wf-empty">{stage.emptyMessage}</div>
        ) : (
          <>
            {stage.agentBanner && (
              <div className="wf-agentbanner">
                <Briefcase size={15} strokeWidth={1.7} />
                <span>{highlight(stage.agentBanner)}</span>
              </div>
            )}

            <div className="wf-tasks">
              {stage.tasks.map((task) => (
                <TaskCard
                  key={task.id}
                  task={task}
                  onOpen={() => setOpenTaskId(task.id)}
                />
              ))}
            </div>

            {stage.panels.length > 0 && (
              <div className="wf-panels">
                {stage.panels.map((panel) => (
                  <Panel key={panel.title} panel={panel} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
