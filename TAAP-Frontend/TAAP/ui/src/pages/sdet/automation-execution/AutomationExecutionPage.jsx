import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Mail, Search, TriangleAlert, FileText } from "lucide-react";
import { fetchSdetExecution } from "@taap/service-layer";
import generatedScriptData from "./testExecutionScripts.json";
import {
  JiraStatusLine,
  SdetChips,
  SdetError,
  SdetField,
  SdetFilters,
  SdetInput,
  SdetLoading,
  SdetPage,
  SdetPanel,
  SdetPill,
  SdetSelect,
  SdetStat,
  SdetTextarea,
  SdetToast,
  SdetToggleGroup,
  downloadCsv,
  environmentTone,
  formatClock,
  formatCountdown,
  formatNextRun,
  formatWhen,
  scheduleSummary
} from "../shared/SdetPageParts.jsx";
import "./AutomationExecutionPage.css";

const PAGE_NOTES = [
  "Runs through GitHub Actions workflow",
  "Scripts from GitHub main",
  "Reports published after each run",
  "Email sent to stakeholders with report link"
];

const TABS = [
  { id: "configure", label: "Test Script Setup" },
  { id: "results", label: "Execution results" }
];

const RESULT_FILTERS = [
  { id: "all", label: "All" },
  { id: "failed", label: "Failed" },
  { id: "QA", label: "QA" },
  { id: "UAT", label: "UAT" },
  { id: "Regression", label: "Regression" },
  { id: "Smoke", label: "Smoke" },
  { id: "SIT", label: "SIT" }
];

const WEEKDAY_OPTIONS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const generatedScripts = generatedScriptData.testScripts.map((script) => ({
  id: script.scriptId,
  testCaseId: script.testCaseId,
  scriptName: script.scriptName,
  suite: script.testCaseId,
  name: script.title,
  description: script.description,
  testType: script.testType,
  layers: script.layers,
  testsInScope: script.testsInScope,
  tag: script.tag,
  workflow: script.workflow,
  workflowParams: script.workflowParams,
  environment: script.environment,
  build: script.build,
  machine: script.machine,
  browsers: script.browsers,
  retry: script.retry,
  schedule: script.schedule,
  recipients: script.recipients,
  sendEmail: script.sendEmail,
  estimatedMinutes: script.estimatedMinutes,
  scriptSteps: script.script,
  active: true
}));

function emptyForm() {
  return {
    scriptId: "",
    description: "",
    testType: "",
    layers: [],
    environment: "",
    build: "",
    machine: "",
    browsers: [],
    retry: "Off",
    frequency: "Daily",
    dayOfWeek: "Mon",
    dayOfMonth: 1,
    time: "22:00",
    recipients: [],
    sendEmail: "After every run"
  };
}

function formFromScript(script) {
  if (!script) return emptyForm();
  return {
    scriptId: script.id,
    description: script.description,
    testType: script.testType,
    layers: [...script.layers],
    environment: script.environment,
    build: script.build,
    machine: script.machine,
    browsers: [...script.browsers],
    retry: script.retry,
    frequency: script.schedule.frequency,
    dayOfWeek: script.schedule.dayOfWeek ?? "Mon",
    dayOfMonth: script.schedule.dayOfMonth ?? 1,
    time: script.schedule.time,
    recipients: [...script.recipients],
    sendEmail: script.sendEmail
  };
}

function validateForm(form) {
  const problems = [];
  if (!form.scriptId) problems.push("Select a script.");
  if (form.layers.length === 0) problems.push("Pick at least one test layer.");
  if (form.layers.some((layer) => layer !== "API") && form.browsers.length === 0) problems.push("UI runs need at least one browser.");
  if (!/^\d{2}:\d{2}$/.test(form.time)) problems.push("Time must be HH:MM.");
  if (form.recipients.length === 0) problems.push("Add at least one email recipient.");
  return problems;
}

function nextRunFromForm(form) {
  return {
    frequency: form.frequency,
    dayOfWeek: form.dayOfWeek,
    dayOfMonth: Number(form.dayOfMonth) || 1,
    time: form.time,
    paused: false
  };
}

function computeNextRunClient(schedule) {
  const [hour, minute] = schedule.time.split(":").map((part) => Number.parseInt(part, 10) || 0);
  const now = new Date();
  const next = new Date(now);
  next.setSeconds(0, 0);
  const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

  if (schedule.frequency === "Weekly") {
    next.setHours(hour, minute, 0, 0);
    let diff = (days.indexOf(schedule.dayOfWeek) - next.getDay() + 7) % 7;
    if (diff === 0 && next <= now) diff = 7;
    next.setDate(next.getDate() + diff);
    return next.toISOString();
  }

  if (schedule.frequency === "Monthly") {
    next.setDate(schedule.dayOfMonth);
    next.setHours(hour, minute, 0, 0);
    if (next <= now) next.setMonth(next.getMonth() + 1, schedule.dayOfMonth);
    return next.toISOString();
  }

  next.setHours(hour, minute, 0, 0);
  if (next <= now) next.setDate(next.getDate() + 1);
  return next.toISOString();
}

export function AutomationExecutionPage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [tab, setTab] = useState("configure");
  const [form, setForm] = useState(emptyForm);
  const [validation, setValidation] = useState({ checked: false, problems: [] });
  const [scripts, setScripts] = useState([]);
  const [runs, setRuns] = useState([]);
  const [resultFilter, setResultFilter] = useState("all");
  const [expandedRun, setExpandedRun] = useState(null);
  const [toast, setToast] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const payload = await fetchSdetExecution();
      const selectedScriptId = window.sessionStorage.getItem("sdet:selectedScriptId") ?? "";
      const selectedGeneratedScript = generatedScripts.find((script) => script.id === selectedScriptId);
      setData(payload);
      setScripts(generatedScripts);
      setRuns([]);
      setForm((current) => current.scriptId ? current : formFromScript(selectedGeneratedScript));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load execution data.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const selectedScript = useMemo(() => scripts.find((script) => script.id === form?.scriptId) ?? null, [scripts, form?.scriptId]);
  const selectedMachine = useMemo(() => data?.machines.find((machine) => machine.id === form?.machine) ?? null, [data, form?.machine]);
  const selectedEnvironment = useMemo(() => data?.environments.find((environment) => environment.id === form?.environment) ?? null, [data, form?.environment]);
  const nextRunAt = useMemo(() => (form ? computeNextRunClient(nextRunFromForm(form)) : null), [form]);
  const testTypeOptions = useMemo(() => [...new Set([...(data?.testTypes ?? []), ...scripts.map((script) => script.testType)])].filter(Boolean), [data?.testTypes, scripts]);
  const layerOptions = useMemo(() => [...new Set([...(data?.layers ?? []), ...scripts.flatMap((script) => script.layers)])].filter(Boolean), [data?.layers, scripts]);
  const browserOptions = useMemo(() => [...new Set([...(data?.browsers ?? []), ...scripts.flatMap((script) => script.browsers)])].filter(Boolean), [data?.browsers, scripts]);

  const summary = useMemo(() => {
    const weekAgo = Date.now() - 7 * 86400000;
    const recent = runs.filter((run) => Date.parse(run.executedAt) >= weekAgo);
    const passed = recent.filter((run) => run.result === "Passed").length;
    const failed = recent.filter((run) => run.result === "Failed").length;
    const totals = recent.reduce((acc, run) => ({ total: acc.total + run.total, pass: acc.pass + run.pass }), { total: 0, pass: 0 });
    const awaiting = runs.filter((run) => run.result === "Failed" && run.analysis === "awaiting").length;
    const last = [...runs].sort((first, second) => Date.parse(second.executedAt) - Date.parse(first.executedAt))[0] ?? null;
    return {
      recent: recent.length,
      scheduled: recent.filter((run) => run.type === "Scheduled").length,
      manual: recent.filter((run) => run.type !== "Scheduled").length,
      passed,
      failed,
      passRate: totals.total > 0 ? Math.round((totals.pass / totals.total) * 100) : 0,
      awaiting,
      last
    };
  }, [runs]);

  const sortedRuns = useMemo(() => [...runs].sort((first, second) => Date.parse(second.executedAt) - Date.parse(first.executedAt)), [runs]);

  const filteredRuns = useMemo(() => {
    if (resultFilter === "all") return sortedRuns;
    if (resultFilter === "failed") return sortedRuns.filter((run) => run.result === "Failed");
    if (["QA", "UAT"].includes(resultFilter)) return sortedRuns.filter((run) => run.environment === resultFilter);
    return sortedRuns.filter((run) => run.phase === resultFilter);
  }, [sortedRuns, resultFilter]);

  const filterCounts = useMemo(
    () => ({
      all: sortedRuns.length,
      failed: sortedRuns.filter((run) => run.result === "Failed").length
    }),
    [sortedRuns]
  );

  function updateForm(patch) {
    setForm((current) => ({ ...current, ...patch }));
    setValidation({ checked: false, problems: [] });
  }

  function selectScript(scriptId) {
    if (!scriptId) {
      setForm(emptyForm());
      setValidation({ checked: false, problems: [] });
      return;
    }
    const script = scripts.find((item) => item.id === scriptId);
    if (script) {
      setForm(formFromScript(script));
      setValidation({ checked: false, problems: [] });
    }
  }

  function selectEnvironment(environmentId) {
    const environment = data.environments.find((item) => item.id === environmentId);
    updateForm({ environment: environmentId, build: environment?.latestBuild ?? form.build });
  }

  function handleValidate() {
    const problems = validateForm(form);
    setValidation({ checked: true, problems });
    setToast(problems.length === 0 ? "Configuration valid — ready to schedule or execute." : `${problems.length} issue${problems.length === 1 ? "" : "s"} to fix before running.`);
    return problems.length === 0;
  }

  function handleSaveSchedule() {
    if (!handleValidate()) return;
    setScripts((current) =>
      current.map((script) =>
        script.id === form.scriptId
          ? {
              ...script,
              description: form.description,
              testType: form.testType,
              layers: [...form.layers],
              environment: form.environment,
              build: form.build,
              machine: form.machine,
              browsers: [...form.browsers],
              retry: form.retry,
              schedule: nextRunFromForm(form),
              nextRunAt,
              recipients: [...form.recipients],
              sendEmail: form.sendEmail,
              active: true
            }
          : script
      )
    );
    setToast(`Schedule saved for ${form.scriptId} — next run ${formatNextRun(nextRunAt)}.`);
  }

  function executeScript(script, type = "Manual rerun") {
    const currentMax = runs.length > 0 ? Math.max(...runs.map((run) => Number.parseInt(run.id.replace(/\D/g, ""), 10))) : 1842;
    const nextNumber = currentMax + 1;
    const run = {
      id: `RUN-${nextNumber}`,
      type,
      script: script.id,
      environment: script.environment,
      build: script.build,
      phase: script.testType,
      executedAt: new Date().toISOString(),
      total: script.testsInScope,
      pass: 0,
      fail: 0,
      skip: 0,
      result: "Running",
      analysis: "none",
      failures: [],
      rca: ""
    };
    setRuns((current) => [run, ...current]);
    setTab("results");
    setResultFilter("all");
    setToast(`${run.id} queued on ${script.machine} via ${script.workflow}.`);

    window.setTimeout(() => {
      setRuns((current) =>
        current.map((item) =>
          item.id === run.id
            ? { ...item, pass: script.testsInScope - 1, skip: 1, result: "Passed" }
            : item
        )
      );
    }, 4000);
  }

  function handleCancel() {
    setForm(formFromScript(selectedScript));
    setValidation({ checked: false, problems: [] });
    setToast("Changes discarded.");
  }

  function handleNewSchedule() {
    setForm(emptyForm());
    setValidation({ checked: false, problems: [] });
    setTab("configure");
    setToast("Select a script to configure execution.");
  }

  function markAnalysed(runId) {
    setRuns((current) => current.map((run) => (run.id === runId ? { ...run, analysis: "done" } : run)));
  }

  function handleIdentifyIssues(run) {
    const scriptIssues = run.failures.filter((failure) => failure.category === "Script issue").length;
    const defects = run.failures.filter((failure) => failure.category === "Application defect").length;
    const environment = run.failures.filter((failure) => failure.category === "Environment").length;
    markAnalysed(run.id);
    setToast(`${run.id}: ${scriptIssues} script issue${scriptIssues === 1 ? "" : "s"} → Automation Maintenance, ${defects} defect${defects === 1 ? "" : "s"} → Defects, ${environment} environment failure${environment === 1 ? "" : "s"} eligible for rerun.`);
  }

  function handleEmail(run) {
    const script = scripts.find((item) => item.id === run.script);
    const count = script?.recipients.length ?? 0;
    setToast(`Report link for ${run.id} emailed to ${count} recipient${count === 1 ? "" : "s"}.`);
  }

  function handleExport() {
    downloadCsv(
      "execution-results.csv",
      ["Run", "Type", "Script", "Environment", "Build", "Phase", "Executed", "Total", "Pass", "Fail", "Skip", "Result"],
      filteredRuns.map((run) => [run.id, run.type, run.script, run.environment, run.build, run.phase, run.executedAt, run.total, run.pass, run.fail, run.skip, run.result])
    );
    setToast(`Exported ${filteredRuns.length} runs to CSV.`);
  }

  if (isLoading && !data) {
    return (
      <SdetPage breadcrumbs={["Automation Execution"]} title="Test Script Setup" tabs={TABS} activeTab={tab} notes={PAGE_NOTES}>
        <SdetLoading label="Loading execution data…" />
      </SdetPage>
    );
  }

  if (error && !data) {
    return (
      <SdetPage breadcrumbs={["Automation Execution"]} title="Test Script Setup" tabs={TABS} activeTab={tab} notes={PAGE_NOTES}>
        <SdetError message={error} onRetry={load} />
      </SdetPage>
    );
  }

  const isValid = validation.checked ? validation.problems.length === 0 : validateForm(form).length === 0;
  const activeScripts = scripts.filter((script) => script.active).length;

  if (tab === "results") {
    return (
      <SdetPage
        ariaLabel="Execution Results"
        breadcrumbs={["Automation Execution", "Execution results"]}
        title="Execution Results"
        status={
          summary.awaiting > 0
            ? { tone: "amber", icon: <TriangleAlert size={15} strokeWidth={1.8} />, text: `${summary.awaiting} failed run${summary.awaiting === 1 ? "" : "s"} awaiting analysis` }
            : { tone: "green", icon: <Check size={15} strokeWidth={2} />, text: "All failed runs analysed" }
        }
        tabs={TABS}
        activeTab={tab}
        onTabChange={setTab}
        notes={PAGE_NOTES}
        footer={{
          summary: "Retry is manual by design · failed runs are analysed first, and only scenarios blocked by environment or network issues are rerun",
          actions: (
            <>
              <button type="button" className="sdet-btn" onClick={handleExport}>Export</button>
              <button type="button" className="sdet-btn" onClick={() => summary.last && handleEmail(summary.last)}>Email Latest Report</button>
              <button type="button" className="sdet-btn sdet-btn--primary" onClick={() => setTab("configure")}>Configure New Run</button>
            </>
          )
        }}
      >
        <div className="sdet-stats">
          <SdetStat label="Runs · last 7 days" value={summary.recent} detail={`${summary.scheduled} sched · ${summary.manual} manual`} />
          <SdetStat label="Passed" swatch="green" value={summary.passed} tone="green" />
          <SdetStat label="Failed" swatch="red" value={summary.failed} tone="red" />
          <SdetStat label="Pass rate" value={`${summary.passRate}%`} detail="tests, all runs" />
          <SdetStat label="Awaiting analysis" swatch="amber" value={summary.awaiting} detail="failed runs" tone="amber" />
          <SdetStat label="Last run" value={summary.last ? formatWhen(summary.last.executedAt) : "-"} detail={summary.last ? `${summary.last.script} · ${summary.last.environment}` : ""} tone="medium" />
        </div>

        <SdetFilters
          label="Runs"
          filters={RESULT_FILTERS.map((filter) => ({ ...filter, count: filterCounts[filter.id] }))}
          active={resultFilter}
          onChange={setResultFilter}
          note={
            <>
              <strong>Run type</strong> Scheduled or Manual rerun &nbsp;&nbsp; <strong>Actions</strong> work on the failed runs
            </>
          }
        />

        <div className="sdet-table-wrap">
          <table className="sdet-table sdet-runs-table">
            <thead>
              <tr>
                <th>Run</th><th>Script</th><th>Env</th><th>Build</th><th>Phase</th><th>Last executed</th>
                <th>Total</th><th>Pass</th><th>Fail</th><th>Skip</th><th>Result</th><th>Report</th><th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredRuns.length === 0 ? (
                <tr><td colSpan={13} className="sdet-empty">No runs match this filter.</td></tr>
              ) : null}
              {filteredRuns.map((run) => {
                const failed = run.result === "Failed";
                const running = run.result === "Running";
                const passPercent = run.total > 0 ? Math.round((run.pass / run.total) * 100) : 0;
                const expanded = expandedRun?.id === run.id;
                return (
                  <FragmentRow key={run.id}>
                    <tr>
                      <td>
                        <span className="sdet-mono sdet-run-id">{run.id}</span>
                        <span className="sdet-table__sub">{run.type}</span>
                      </td>
                      <td className="sdet-mono">{run.script}</td>
                      <td><i className={`sdet-dot sdet-dot--${environmentTone(run.environment)}`} /> {run.environment}</td>
                      <td className="sdet-mono">{run.build}</td>
                      <td>{run.phase}</td>
                      <td>{formatWhen(run.executedAt)}</td>
                      <td>{run.total}</td>
                      <td className="sdet-num--pass">{run.pass}</td>
                      <td className={run.fail > 0 ? "sdet-num--fail" : ""}>{run.fail}</td>
                      <td>{run.skip}</td>
                      <td>
                        {running ? <SdetPill tone="blue">● Running</SdetPill> : failed ? <SdetPill tone="red">✕ Failed</SdetPill> : <SdetPill tone="green">✓ Passed</SdetPill>}
                        <span className="sdet-table__sub">{running ? "in progress" : `${passPercent}% pass`}</span>
                      </td>
                      <td>
                        <button type="button" className="sdet-link" onClick={() => setToast(`Opening published report for ${run.id}.`)} disabled={running}>View report</button>
                      </td>
                      <td>
                        {failed ? (
                          <div className="sdet-actions">
                            <button type="button" className={`sdet-btn sdet-btn--sm ${expanded && expandedRun.mode === "analysis" ? "" : "sdet-btn--purple"}`} onClick={() => { setExpandedRun(expanded && expandedRun.mode === "analysis" ? null : { id: run.id, mode: "analysis" }); markAnalysed(run.id); }}>
                              <Search size={13} strokeWidth={2} /> Failure Analysis
                            </button>
                            <button type="button" className="sdet-btn sdet-btn--sm" onClick={() => handleIdentifyIssues(run)}>
                              <TriangleAlert size={13} strokeWidth={2} /> Identify Issues
                            </button>
                            <button type="button" className="sdet-btn sdet-btn--sm" onClick={() => setExpandedRun(expanded && expandedRun.mode === "rca" ? null : { id: run.id, mode: "rca" })}>
                              <FileText size={13} strokeWidth={2} /> RCA
                            </button>
                            <button type="button" className="sdet-btn sdet-btn--sm" onClick={() => handleEmail(run)}>
                              <Mail size={13} strokeWidth={2} /> Email Notification
                            </button>
                          </div>
                        ) : (
                          <div className="sdet-actions--single">
                            <button type="button" className="sdet-btn sdet-btn--sm" onClick={() => handleEmail(run)} disabled={running}>
                              <Mail size={13} strokeWidth={2} /> Email Notification
                            </button>
                            <span className="sdet-actions__note">{running ? "Running…" : "No failures"}</span>
                          </div>
                        )}
                      </td>
                    </tr>
                    {expanded ? (
                      <tr className="sdet-expand">
                        <td colSpan={13}>
                          <div className="sdet-expand__inner">
                            {expandedRun.mode === "analysis" ? (
                              <>
                                <p className="sdet-expand__title">Failure analysis · {run.id} · {run.fail} failed of {run.total}</p>
                                <ul className="sdet-expand__list">
                                  {run.failures.map((failure) => (
                                    <li key={failure.test}>
                                      <span className="sdet-mono">{failure.test}</span>
                                      <span>{failure.error}</span>
                                      <SdetPill tone={failure.category === "Script issue" ? "purple" : failure.category === "Environment" ? "amber" : failure.category === "Flaky" ? "blue" : "red"}>{failure.category}</SdetPill>
                                    </li>
                                  ))}
                                </ul>
                                <div className="sdet-expand__actions">
                                  <button type="button" className="sdet-btn sdet-btn--sm sdet-btn--primary" onClick={() => handleIdentifyIssues(run)}>Route issues</button>
                                  <button type="button" className="sdet-btn sdet-btn--sm" onClick={() => setToast(`${run.failures.filter((f) => f.category === "Environment").length} environment-blocked scenarios queued for rerun.`)}>Rerun environment failures only</button>
                                  <button type="button" className="sdet-btn sdet-btn--sm" onClick={() => setExpandedRun(null)}>Close</button>
                                </div>
                              </>
                            ) : (
                              <>
                                <p className="sdet-expand__title">Root cause · {run.id}</p>
                                <p className="sdet-expand__rca">{run.rca || "Root cause not recorded yet — run Failure Analysis first."}</p>
                                <div className="sdet-expand__actions">
                                  <button type="button" className="sdet-btn sdet-btn--sm" onClick={() => handleEmail(run)}>Share RCA by email</button>
                                  <button type="button" className="sdet-btn sdet-btn--sm" onClick={() => setExpandedRun(null)}>Close</button>
                                </div>
                              </>
                            )}
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </FragmentRow>
                );
              })}
            </tbody>
          </table>
        </div>
        <SdetToast message={toast} onDone={() => setToast("")} />
      </SdetPage>
    );
  }

  return (
    <SdetPage
      ariaLabel="Test Script Setup"
      breadcrumbs={["Automation Execution", "Test Script Setup"]}
      title="Test Script Setup"
      status={
        isValid
          ? { tone: "green", icon: <Check size={15} strokeWidth={2} />, text: "Configuration valid" }
          : { tone: "amber", icon: <TriangleAlert size={15} strokeWidth={1.8} />, text: `${validation.checked ? validation.problems.length : validateForm(form).length} issue${(validation.checked ? validation.problems.length : validateForm(form).length) === 1 ? "" : "s"} to fix` }
      }
      tabs={TABS}
      activeTab={tab}
      onTabChange={setTab}
      notes={PAGE_NOTES}
      footer={{
        summary: form.scriptId ? `${form.scriptId} · ${selectedScript?.testCaseId ?? "-"} · ${form.environment} · build ${form.build} · ${form.frequency.toLowerCase()} at ${form.time} IST · ${form.recipients.length} recipient${form.recipients.length === 1 ? "" : "s"}` : "Select a generated script to load execution details",
        actions: (
          <>
            <button type="button" className="sdet-btn" onClick={handleCancel}>Cancel</button>
            <button type="button" className="sdet-btn" onClick={handleValidate}>Validate</button>
            <button type="button" className="sdet-btn" onClick={handleSaveSchedule}>Save Schedule</button>
          </>
        )
      }}
    >
      <div className="sdet-two-col">
        <div className="sdet-stack">
          {validation.checked && validation.problems.length > 0 ? (
            <SdetError message={validation.problems.join(" ")} />
          ) : null}

          <SdetPanel label="What to run" aside={<JiraStatusLine jira={data.jira} />}>
            <div className="sdet-grid-3">
              <SdetField label="Script ID">
                <SdetSelect
                  value={form.scriptId}
                  ariaLabel="Script ID"
                  options={[{ value: "", label: "Select script" }, ...scripts.map((script) => ({ value: script.id, label: `${script.id}   ${script.testCaseId}` }))]}
                  onChange={selectScript}
                />
              </SdetField>
              <SdetField label="Description" className="sdet-span-2">
                <SdetTextarea rows={2} value={form.description} ariaLabel="Description" onChange={(value) => updateForm({ description: value })} />
              </SdetField>
            </div>
            <div className="sdet-grid-3">
              <SdetField label="Test type" hint={testTypeOptions.join(" · ")}>
                <SdetSelect value={form.testType} ariaLabel="Test type" options={testTypeOptions} onChange={(value) => updateForm({ testType: value })} />
              </SdetField>
              <SdetField label="Test layer">
                <SdetToggleGroup options={layerOptions} selected={form.layers} multi ariaLabel="Test layer" onChange={(layers) => updateForm({ layers })} />
              </SdetField>
              <SdetField label="Tests in scope">
                <SdetInput mono readOnly value={String(selectedScript?.testsInScope ?? 0)} meta={`from ${selectedScript?.tag ?? "-"} tag`} ariaLabel="Tests in scope" />
              </SdetField>
            </div>
          </SdetPanel>

          <SdetPanel label="Where to run">
            <div className="sdet-grid-3">
              <SdetField label="Environment">
                <SdetSelect
                  value={form.environment}
                  dot={environmentTone(form.environment)}
                  ariaLabel="Environment"
                  options={data.environments.map((environment) => ({ value: environment.id, label: environment.label }))}
                  onChange={selectEnvironment}
                />
              </SdetField>
              <SdetField label="Build">
                <SdetInput mono value={form.build} meta={selectedEnvironment?.latestBuild === form.build ? `latest on ${form.environment}` : `latest ${selectedEnvironment?.latestBuild ?? "-"}`} ariaLabel="Build" onChange={(value) => updateForm({ build: value })} />
              </SdetField>
              <SdetField label="GitHub Actions workflow">
                <SdetInput mono readOnly value={selectedScript?.workflow ?? ""} meta={`params: ${selectedScript?.workflowParams ?? ""}`} ariaLabel="GitHub Actions workflow" />
              </SdetField>
            </div>
            <div className="sdet-grid-3">
              <SdetField label="Remote execution machine">
                <SdetSelect
                  value={form.machine}
                  dot={selectedMachine?.ready ? "green" : "amber"}
                  ariaLabel="Remote execution machine"
                  options={data.machines.map((machine) => ({ value: machine.id, label: `${machine.label} · ${machine.summary}` }))}
                  onChange={(value) => updateForm({ machine: value })}
                />
              </SdetField>
              <SdetField label="Browser">
                <SdetToggleGroup options={browserOptions} selected={form.browsers} multi ariaLabel="Browser" onChange={(browsers) => updateForm({ browsers })} />
              </SdetField>
              <SdetField label="Retry on failure" hint="Failures are analysed first; only environment failures are rerun">
                <SdetSelect value={form.retry} ariaLabel="Retry on failure" options={data.retryOptions} onChange={(value) => updateForm({ retry: value })} />
              </SdetField>
            </div>
          </SdetPanel>

          <SdetPanel label="When to run">
            <div className="sdet-grid-3">
              <SdetField label="Frequency">
                <SdetToggleGroup options={data.frequencies} selected={form.frequency} ariaLabel="Frequency" onChange={(frequency) => updateForm({ frequency })} />
              </SdetField>
              <SdetField label={form.frequency === "Weekly" ? "Day & time" : form.frequency === "Monthly" ? "Day of month & time" : "Time"}>
                <div className="sdet-when">
                  {form.frequency === "Weekly" ? (
                    <SdetSelect value={form.dayOfWeek} ariaLabel="Day of week" options={WEEKDAY_OPTIONS} onChange={(value) => updateForm({ dayOfWeek: value })} />
                  ) : null}
                  {form.frequency === "Monthly" ? (
                    <SdetSelect value={String(form.dayOfMonth)} ariaLabel="Day of month" options={Array.from({ length: 28 }, (_, index) => String(index + 1))} onChange={(value) => updateForm({ dayOfMonth: Number(value) })} />
                  ) : null}
                  <SdetInput mono value={form.time} meta={form.frequency === "Daily" ? "IST · weekdays" : "IST"} ariaLabel="Time" onChange={(value) => updateForm({ time: value })} />
                </div>
              </SdetField>
              <SdetField label="Next run">
                <SdetInput readOnly value={formatNextRun(nextRunAt)} meta={formatCountdown(nextRunAt)} ariaLabel="Next run" />
              </SdetField>
            </div>
          </SdetPanel>

          <SdetPanel label="Who to notify">
            <div className="sdet-grid-3">
              <SdetField label="Email recipients" className="sdet-span-2">
                <SdetChips
                  items={form.recipients}
                  onRemove={(email) => updateForm({ recipients: form.recipients.filter((item) => item !== email) })}
                  onAdd={(email) => updateForm({ recipients: form.recipients.includes(email) ? form.recipients : [...form.recipients, email] })}
                  placeholder="Add recipient and press Enter"
                />
              </SdetField>
              <SdetField label="Send email" hint="Email contains the link to the published report">
                <SdetSelect value={form.sendEmail} ariaLabel="Send email" options={data.emailOptions} onChange={(value) => updateForm({ sendEmail: value })} />
              </SdetField>
            </div>
          </SdetPanel>
        </div>

        <div className="sdet-stack">
          <SdetPanel label={`Generated scripts (${scripts.length})`} aside={`${activeScripts} available`}>
            <div className="sdet-list">
              {scripts.map((script) => (
                <div key={script.id} className={`sdet-list__row ${script.id === form.scriptId ? "sdet-list__row--active" : ""}`}>
                  <button type="button" className="sdet-list__button" onClick={() => selectScript(script.id)}>
                    <span className="sdet-list__id">
                      <span className="sdet-mono">{script.id}</span>
                      <i className={`sdet-dot sdet-dot--${environmentTone(script.environment)}`} />
                      <span className="sdet-list__env">{script.environment}</span>
                    </span>
                    <strong className="sdet-list__title">{script.name}</strong>
                    <span className="sdet-list__meta">
                      {scheduleSummary(script.schedule)} · next {script.schedule.paused ? "Paused" : formatNextRun(script.nextRunAt)}
                    </span>
                  </button>
                  <button
                    type="button"
                    className={`sdet-btn sdet-btn--sm ${script.active ? "sdet-btn--primary" : ""}`}
                    disabled={!script.active}
                    title={script.active ? `Execute ${script.id} now` : "Schedule is paused"}
                    onClick={() => executeScript(script)}
                  >
                    Execute
                  </button>
                </div>
              ))}
            </div>
            <button type="button" className="sdet-btn sdet-btn--block sdet-new-schedule" onClick={handleNewSchedule}>+ New schedule</button>
          </SdetPanel>

          <SdetPanel label="Execution machine health">
            <div className="sdet-kv">
              <div>
                <strong>{selectedMachine?.label ?? form.machine}</strong>
                <SdetPill tone={selectedMachine?.ready ? "green" : "amber"}>{selectedMachine?.status ?? "Unknown"}</SdetPill>
              </div>
              <div><span>Dependencies</span><span>{selectedMachine?.dependencies ?? "-"}</span></div>
              <div><span>Last heartbeat</span><span>{selectedMachine ? `${formatClock(selectedMachine.lastHeartbeat)} ${formatWhen(selectedMachine.lastHeartbeat, { withTime: false }).toLowerCase()}` : "-"}</span></div>
            </div>
          </SdetPanel>

          <SdetPanel label="Estimated execution window" className="sdet-hidden-panel">
            <div className="sdet-window">
              <strong>{selectedScript?.estimatedMinutes.min ?? 0}–{selectedScript?.estimatedMinutes.max ?? 0}</strong>
              <span>minutes on {form.machine}</span>
            </div>
            <div className="sdet-bar">
              <span style={{ flex: 58 }} />
              <span style={{ flex: 42 }} />
            </div>
            <div className="sdet-bar-legend">
              {Object.entries(selectedScript?.estimatedMinutes.perBrowser ?? {}).map(([browser, window]) => (
                <span key={browser}>{browser} {window}</span>
              ))}
              {Object.keys(selectedScript?.estimatedMinutes.perBrowser ?? {}).length === 0 ? <span>API only · no browser stage</span> : null}
            </div>
          </SdetPanel>

        </div>
      </div>
      <SdetToast message={toast} onDone={() => setToast("")} />
    </SdetPage>
  );
}

function FragmentRow({ children }) {
  return children;
}
