import { useCallback, useEffect, useMemo, useState } from "react";
import { ExternalLink, TriangleAlert } from "lucide-react";
import { fetchSdetMaintenance } from "@taap/service-layer";
import {
  JiraStatusLine,
  SdetError,
  SdetField,
  SdetFilters,
  SdetInput,
  SdetLoading,
  SdetPage,
  SdetPanel,
  SdetPill,
  SdetReason,
  SdetSelect,
  SdetStat,
  SdetTextarea,
  SdetToast,
  SdetToggleGroup,
  downloadCsv,
  formatWhen
} from "../shared/SdetPageParts.jsx";
import "./AutomationMaintenancePage.css";

const PAGE_NOTES = [
  "Script failures & flaky tests arrive from Execution results and Allure reports",
  "Enhancements are added by the team from stories and defects",
  "Output: more scenarios covered"
];

const TABS = [
  { id: "queue", label: "Maintenance queue" },
  { id: "new", label: "+ New maintenance item" }
];

const OPEN_STATUSES = new Set(["New", "In progress", "Fixed", "Verified"]);
const RESOLVED_STATUSES = new Set(["Fixed", "Verified", "Closed"]);

function statusTone(status) {
  if (status === "New") return "red";
  if (status === "In progress") return "blue";
  if (status === "Fixed" || status === "Verified") return "green";
  return "gray";
}

function reasonKind(reason) {
  if (reason.startsWith("Script")) return "failure";
  if (reason.startsWith("Flaky")) return "flaky";
  return "enhancement";
}

function sourceTypeFor(reason) {
  if (reason === "Script failure") return "Failed run";
  if (reason === "Flaky test") return "Allure report";
  if (reason === "Enhancement · coverage gap") return "Defect";
  return "User story";
}

function initialForm(data) {
  const preferred = data.referenceOptions.stories[0] ?? data.referenceOptions.sampleStories[0] ?? null;
  return {
    scriptId: data.scripts[0]?.id ?? "",
    reason: "Enhancement · app change",
    sourceType: "User story",
    reference: preferred?.key ?? "",
    priority: preferred ? mapPriority(preferred.priority) : "High",
    change: preferred ? suggestedChange(preferred) : "",
    assignee: data.currentUser,
    sprint: data.sprint.name,
    changeTouched: false
  };
}

function mapPriority(priority) {
  const value = String(priority ?? "").toLowerCase();
  if (["highest", "high", "critical", "blocker"].includes(value)) return "High";
  if (["low", "lowest", "minor", "trivial"].includes(value)) return "Low";
  return "Medium";
}

function suggestedChange(reference) {
  if (!reference) return "";
  const firstLine = String(reference.description ?? "").split(/\r?\n/).map((line) => line.trim()).find(Boolean);
  return firstLine && firstLine !== reference.title ? `${reference.title} — ${firstLine}` : reference.title;
}

export function AutomationMaintenancePage() {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [tab, setTab] = useState("queue");
  const [items, setItems] = useState([]);
  const [filter, setFilter] = useState("open");
  const [form, setForm] = useState(null);
  const [formError, setFormError] = useState("");
  const [toast, setToast] = useState("");

  const load = useCallback(async () => {
    setIsLoading(true);
    setError("");
    try {
      const payload = await fetchSdetMaintenance();
      setData(payload);
      setItems(payload.items);
      setForm((current) => current ?? initialForm(payload));
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "Unable to load maintenance data.");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const stats = useMemo(() => {
    const open = items.filter((item) => OPEN_STATUSES.has(item.status));
    return {
      open: open.length,
      openHigh: open.filter((item) => item.priority === "High").length,
      failures: items.filter((item) => item.reason === "Script failure" && item.status !== "Closed").length,
      flaky: items.filter((item) => item.reason === "Flaky test" && item.status !== "Closed").length,
      enhancements: items.filter((item) => reasonKind(item.reason) === "enhancement" && item.status !== "Closed").length,
      appChange: items.filter((item) => item.reason === "Enhancement · app change" && item.status !== "Closed").length,
      coverageGap: items.filter((item) => item.reason === "Enhancement · coverage gap" && item.status !== "Closed").length,
      fixed: items.filter((item) => RESOLVED_STATUSES.has(item.status)).length,
      mine: items.filter((item) => item.assignee === data?.currentUser && item.status !== "Closed").length
    };
  }, [items, data?.currentUser]);

  const visibleItems = useMemo(() => {
    const sorted = [...items].sort((first, second) => Date.parse(second.updatedAt || 0) - Date.parse(first.updatedAt || 0));
    switch (filter) {
      case "open": return sorted.filter((item) => OPEN_STATUSES.has(item.status));
      case "failure": return sorted.filter((item) => item.reason === "Script failure" && item.status !== "Closed");
      case "flaky": return sorted.filter((item) => item.reason === "Flaky test" && item.status !== "Closed");
      case "enhancement": return sorted.filter((item) => reasonKind(item.reason) === "enhancement" && item.status !== "Closed");
      case "fixed": return sorted.filter((item) => RESOLVED_STATUSES.has(item.status));
      case "mine": return sorted.filter((item) => item.assignee === data?.currentUser && item.status !== "Closed");
      default: return sorted;
    }
  }, [items, filter, data?.currentUser]);

  const referenceChoices = useMemo(() => {
    if (!data || !form) return [];
    const { referenceOptions } = data;
    if (form.sourceType === "Failed run") return referenceOptions.runs.map((run) => ({ value: run.key, label: `${run.key} · ${run.title}` }));
    if (form.sourceType === "Allure report") return [{ value: "Allure · 30 days", label: "Allure · 30 days" }, { value: "Allure · 7 days", label: "Allure · 7 days" }];
    if (form.sourceType === "Defect") {
      const jira = referenceOptions.bugs.map((bug) => ({ value: bug.key, label: `${bug.key} · ${bug.title}` }));
      const sample = referenceOptions.sampleDefects.map((bug) => ({ value: bug.key, label: `${bug.key} · ${bug.title}` }));
      return [...jira, ...sample];
    }
    const jira = referenceOptions.stories.map((story) => ({ value: story.key, label: `${story.key} · ${story.title}` }));
    const sample = referenceOptions.sampleStories.map((story) => ({ value: story.key, label: `${story.key} · ${story.title}` }));
    return [...jira, ...sample];
  }, [data, form]);

  const linkedReference = data && form ? data.references[form.reference] ?? null : null;
  const selectedScript = data && form ? data.scripts.find((script) => script.id === form.scriptId) ?? null : null;

  function updateForm(patch) {
    setForm((current) => ({ ...current, ...patch }));
    setFormError("");
  }

  function chooseReason(reason) {
    const sourceType = sourceTypeFor(reason);
    setForm((current) => {
      const next = { ...current, reason, sourceType, reference: "" };
      return applyDefaultReference(next);
    });
    setFormError("");
  }

  function chooseSourceType(sourceType) {
    setForm((current) => applyDefaultReference({ ...current, sourceType, reference: "" }));
    setFormError("");
  }

  function applyDefaultReference(next) {
    const choices = referenceChoicesFor(next.sourceType);
    const reference = choices[0]?.value ?? "";
    const linked = data.references[reference] ?? null;
    return {
      ...next,
      reference,
      priority: linked ? mapPriority(linked.priority) : next.priority,
      change: next.changeTouched ? next.change : suggestedChange(linked)
    };
  }

  function referenceChoicesFor(sourceType) {
    const { referenceOptions } = data;
    if (sourceType === "Failed run") return referenceOptions.runs.map((run) => ({ value: run.key }));
    if (sourceType === "Allure report") return [{ value: "Allure · 30 days" }];
    if (sourceType === "Defect") return [...referenceOptions.bugs, ...referenceOptions.sampleDefects].map((bug) => ({ value: bug.key }));
    return [...referenceOptions.stories, ...referenceOptions.sampleStories].map((story) => ({ value: story.key }));
  }

  function chooseReference(reference) {
    const linked = data.references[reference] ?? null;
    setForm((current) => ({
      ...current,
      reference,
      priority: linked ? mapPriority(linked.priority) : current.priority,
      change: current.changeTouched ? current.change : suggestedChange(linked),
      assignee: linked && linked.assignee && linked.assignee !== "Unassigned" && data.users.includes(linked.assignee) ? linked.assignee : current.assignee
    }));
    setFormError("");
  }

  function setStatus(itemId, status) {
    setItems((current) => current.map((item) => (item.id === itemId ? { ...item, status, updatedAt: new Date().toISOString() } : item)));
  }

  function actionsFor(item) {
    const kind = reasonKind(item.reason);
    if (item.status === "Closed") return [];
    if (item.status === "Verified") return [{ label: "Close", onClick: () => { setStatus(item.id, "Closed"); setToast(`${item.id} closed.`); } }];
    if (item.status === "Fixed") {
      return [
        { label: "Verify", primary: true, onClick: () => { setStatus(item.id, "Verified"); setToast(`${item.id} verified by rerun of ${item.script}.`); } },
        { label: "Close", onClick: () => { setStatus(item.id, "Closed"); setToast(`${item.id} closed.`); } }
      ];
    }
    const start = kind === "enhancement"
      ? { label: "Add Coverage", primary: true, onClick: () => { setStatus(item.id, "In progress"); setToast(`${item.id}: coverage work started on ${item.script}.`); } }
      : { label: "Fix Script", primary: true, onClick: () => { setStatus(item.id, "In progress"); setToast(`${item.id}: fix started on ${item.script} — robust locators, async/await, no fixed waits.`); } };
    const finish = kind === "flaky"
      ? { label: "Mark Fixed", onClick: () => { setStatus(item.id, "Fixed"); setToast(`${item.id} marked fixed — a rerun verifies it before close.`); } }
      : { label: "Verify", onClick: () => { setStatus(item.id, "Verified"); setToast(`${item.id} verified by rerun of ${item.script}.`); } };
    return [start, finish];
  }

  function handleExport() {
    downloadCsv(
      "maintenance-queue.csv",
      ["Item", "Script", "Reason", "Source type", "Source ref", "What needs to change", "Priority", "Assigned to", "Status", "Updated", "Origin"],
      visibleItems.map((item) => [item.id, item.script, item.reason, item.source.type, item.source.ref, item.change, item.priority, item.assignee, item.status, item.updatedAt, item.origin])
    );
    setToast(`Exported ${visibleItems.length} items to CSV.`);
  }

  function handleAddToQueue() {
    if (!form.scriptId) { setFormError("Choose the script this item belongs to."); return; }
    if (!form.reference.trim()) { setFormError("Give the item a source reference."); return; }
    if (!form.change.trim()) { setFormError("Describe what needs to change."); return; }

    const nextNumber = Math.max(...items.map((item) => Number.parseInt(item.id.replace(/\D/g, ""), 10))) + 1;
    const newItem = {
      id: `MT-${nextNumber}`,
      script: form.scriptId,
      reason: form.reason,
      source: { type: form.sourceType, ref: form.reference, url: linkedReference?.url ?? "" },
      change: form.change.trim(),
      priority: form.priority,
      assignee: form.assignee,
      status: "New",
      updatedAt: new Date().toISOString(),
      origin: linkedReference?.origin === "jira" ? "jira" : "team",
      url: linkedReference?.url ?? "",
      sprint: form.sprint
    };
    setItems((current) => [newItem, ...current]);
    setForm({ ...initialForm(data) });
    setTab("queue");
    setFilter("open");
    setToast(`${newItem.id} added to the queue for ${form.sprint}.`);
  }

  function handleCancelForm() {
    setForm(initialForm(data));
    setFormError("");
    setTab("queue");
  }

  if (isLoading && !data) {
    return (
      <SdetPage breadcrumbs={["Automation Maintenance", "Maintenance queue"]} title="Automation Maintenance" tabs={TABS} activeTab={tab} notes={PAGE_NOTES}>
        <SdetLoading label="Loading maintenance queue…" />
      </SdetPage>
    );
  }

  if (error && !data) {
    return (
      <SdetPage breadcrumbs={["Automation Maintenance", "Maintenance queue"]} title="Automation Maintenance" tabs={TABS} activeTab={tab} notes={PAGE_NOTES}>
        <SdetError message={error} onRetry={load} />
      </SdetPage>
    );
  }

  const status = { tone: "amber", icon: <TriangleAlert size={15} strokeWidth={1.8} />, text: `${stats.open} items open · ${stats.openHigh} high priority` };

  if (tab === "new") {
    return (
      <SdetPage
        ariaLabel="New maintenance item"
        breadcrumbs={["Automation Maintenance", "Maintenance queue"]}
        title="Automation Maintenance"
        status={status}
        tabs={TABS}
        activeTab={tab}
        onTabChange={setTab}
        notes={PAGE_NOTES}
        footer={{
          summary: [form.scriptId, form.reason, form.reference, form.priority, form.assignee, form.sprint].filter(Boolean).join(" · "),
          actions: (
            <>
              <button type="button" className="sdet-btn" onClick={handleCancelForm}>Cancel</button>
              <button type="button" className="sdet-btn sdet-btn--primary" onClick={handleAddToQueue}>Add to Queue</button>
            </>
          )
        }}
      >
        <div className="sdet-two-col">
          <div className="sdet-stack">
            {formError ? <SdetError message={formError} /> : null}

            <SdetPanel label="Which script">
              <div className="sdet-grid-3">
                <SdetField label="Script ID">
                  <SdetSelect value={form.scriptId} ariaLabel="Script ID" options={data.scripts.map((script) => ({ value: script.id, label: `${script.id}   ${script.suite}` }))} onChange={(value) => updateForm({ scriptId: value })} />
                </SdetField>
                <SdetField label="Description · from script" className="sdet-span-2">
                  <SdetTextarea rows={2} readOnly value={selectedScript?.description ?? ""} ariaLabel="Script description" />
                </SdetField>
              </div>
            </SdetPanel>

            <SdetPanel label="Why it needs work">
              <SdetField label="Reason" hint="Script failures and flaky tests usually arrive automatically from Execution results and Allure. Use this form mainly for enhancements.">
                <SdetToggleGroup options={data.reasons} selected={form.reason} ariaLabel="Reason" onChange={chooseReason} />
              </SdetField>
              <div className="sdet-grid-3 sdet-form-gap">
                <SdetField label="Source" hint={data.sourceTypes.join(" · ")}>
                  <SdetSelect value={form.sourceType} ariaLabel="Source" options={data.sourceTypes} onChange={chooseSourceType} />
                </SdetField>
                <SdetField label="Reference ID">
                  {referenceChoices.length > 0 ? (
                    <SdetSelect value={form.reference} ariaLabel="Reference ID" options={referenceChoices} onChange={chooseReference} />
                  ) : (
                    <SdetInput mono value={form.reference} placeholder="e.g. RUN-1842" ariaLabel="Reference ID" onChange={(value) => updateForm({ reference: value })} />
                  )}
                </SdetField>
                <SdetField label="Priority">
                  <SdetToggleGroup options={data.priorities} selected={form.priority} ariaLabel="Priority" onChange={(priority) => updateForm({ priority })} />
                </SdetField>
              </div>
              <SdetField label="What needs to change">
                <SdetTextarea rows={3} value={form.change} ariaLabel="What needs to change" placeholder="Describe the locator, assertion or scenario that must change" onChange={(value) => updateForm({ change: value, changeTouched: true })} />
              </SdetField>
            </SdetPanel>

            <SdetPanel label="Who and when">
              <div className="sdet-grid-3">
                <SdetField label="Assign to">
                  <SdetSelect value={form.assignee} ariaLabel="Assign to" options={["Unassigned", ...data.users]} onChange={(value) => updateForm({ assignee: value })} />
                </SdetField>
                <SdetField label="Target sprint">
                  <SdetSelect value={form.sprint} ariaLabel="Target sprint" options={data.sprint.options} onChange={(value) => updateForm({ sprint: value })} />
                </SdetField>
                <SdetField label="Verify by">
                  <SdetInput readOnly value={`Rerun ${form.scriptId} on ${selectedScript?.environment ?? "QA"}`} meta="after fix" ariaLabel="Verify by" />
                </SdetField>
              </div>
            </SdetPanel>
          </div>

          <div className="sdet-stack">
            <SdetPanel label="How items reach this queue">
              <div className="sdet-legend">
                <div className="sdet-legend__row"><SdetReason reason="Script failure" /><span>Failure Analysis marks a failed test as a script issue → added automatically</span></div>
                <div className="sdet-legend__row"><SdetReason reason="Flaky test" /><span>Allure report shows pass/fail flips, confirmed by log review → added by the team</span></div>
                <div className="sdet-legend__row"><SdetReason reason="Enhancement" /><span>App changed or a defect exposed an untested flow → added by the team</span></div>
              </div>
            </SdetPanel>

            <SdetPanel label={`Linked reference${form.reference ? ` · ${form.reference}` : ""}`} aside={<JiraStatusLine jira={data.jira} />}>
              {linkedReference ? (
                <>
                  <p className="sdet-reference__title">{linkedReference.title}</p>
                  <div className="sdet-reference__meta">
                    <span>{linkedReference.type}</span>
                    <span>Status {linkedReference.status}</span>
                    <span>Priority {linkedReference.priority}</span>
                    <span>{linkedReference.assignee}</span>
                    {linkedReference.origin === "jira" ? <SdetPill tone="blue">Jira</SdetPill> : <SdetPill tone="gray">Sample</SdetPill>}
                  </div>
                  <p className="sdet-reference__body">
                    {linkedReference.description || <em className="sdet-muted">No description on the Jira issue yet.</em>}
                  </p>
                  <div className="sdet-reference__actions">
                    <button type="button" className="sdet-btn" onClick={() => setToast(linkedReference.acceptedCases > 0 ? `${linkedReference.acceptedCases} accepted cases for ${linkedReference.key} opened in Test Design.` : `No accepted cases yet for ${linkedReference.key} — open Test Design to create them.`)}>
                      Open accepted cases
                    </button>
                    {linkedReference.url ? (
                      <a className="sdet-btn" href={linkedReference.url} target="_blank" rel="noreferrer">
                        <ExternalLink size={14} strokeWidth={1.8} /> Open in Jira
                      </a>
                    ) : null}
                  </div>
                </>
              ) : (
                <p className="sdet-hint">{form.sourceType === "Failed run" ? "Failed runs link to the Execution results page; failures are listed there under Failure Analysis." : form.sourceType === "Allure report" ? "Flaky tests are confirmed from the Allure history before they are added here." : "Pick a story or defect to see its details from Jira."}</p>
              )}
            </SdetPanel>
          </div>
        </div>
        <SdetToast message={toast} onDone={() => setToast("")} />
      </SdetPage>
    );
  }

  return (
    <SdetPage
      ariaLabel="Automation Maintenance"
      breadcrumbs={["Automation Maintenance", "Maintenance queue"]}
      title="Automation Maintenance"
      status={status}
      tabs={TABS}
      activeTab={tab}
      onTabChange={setTab}
      notes={PAGE_NOTES}
      footer={{
        summary: "Fix approach: robust locators and Playwright async/await handling · no explicit waits or timeouts unless necessary · a fixed script is verified by a rerun before it is closed",
        actions: (
          <>
            <button type="button" className="sdet-btn" onClick={handleExport}>Export</button>
            <button type="button" className="sdet-btn" onClick={() => setToast("Opening the Allure report for the last 30 days.")}>Open Allure Report</button>
            <button type="button" className="sdet-btn sdet-btn--primary" onClick={() => setTab("new")}>+ New Maintenance Item</button>
          </>
        )
      }}
    >
      <div className="sdet-stats">
        <SdetStat label="Open items" value={stats.open} detail={`${stats.openHigh} high`} />
        <SdetStat label="Script failures" swatch="red" value={stats.failures} detail="from failed runs" tone="red" />
        <SdetStat label="Flaky tests" swatch="amber" value={stats.flaky} detail="from Allure" tone="amber" />
        <SdetStat label="Enhancements" swatch="blue" value={stats.enhancements} detail={`${stats.appChange} app change · ${stats.coverageGap} coverage gap`} tone="blue" />
        <SdetStat label={`Coverage added · ${data.sprint.name}`} swatch="green" value={`+${data.sprint.scenariosAdded}`} detail={`scenarios · ${data.sprint.scriptsFixed} fixed`} tone="green" />
      </div>

      <SdetFilters
        label="Items"
        filters={[
          { id: "open", label: "Open", count: stats.open },
          { id: "failure", label: "Script failure", count: stats.failures },
          { id: "flaky", label: "Flaky", count: stats.flaky },
          { id: "enhancement", label: "Enhancement", count: stats.enhancements },
          { id: "fixed", label: "Fixed", count: stats.fixed },
          { id: "mine", label: "Mine", count: stats.mine }
        ]}
        active={filter}
        onChange={setFilter}
        note={
          <>
            <strong>Source</strong> = the run, Allure report, story or defect &nbsp;&nbsp; <JiraStatusLine jira={data.jira} />
          </>
        }
      />

      <div className="sdet-table-wrap">
        <table className="sdet-table sdet-maintenance-table">
          <thead>
            <tr>
              <th>Item</th><th>Script</th><th>Reason</th><th>Source</th><th>What needs to change</th>
              <th>Priority</th><th>Assigned to</th><th>Status</th><th>Updated</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {visibleItems.length === 0 ? (
              <tr><td colSpan={10} className="sdet-empty">Nothing in this view.</td></tr>
            ) : null}
            {visibleItems.map((item) => {
              const actions = actionsFor(item);
              return (
                <tr key={item.id}>
                  <td className="sdet-mono sdet-item-id">{item.id}</td>
                  <td className="sdet-mono">{item.script}</td>
                  <td><SdetReason reason={item.reason} /></td>
                  <td>
                    {item.source.url ? (
                      <a className="sdet-mono sdet-link" href={item.source.url} target="_blank" rel="noreferrer">{item.source.ref}</a>
                    ) : (
                      <span className="sdet-mono sdet-source-ref">{item.source.ref}</span>
                    )}
                    <span className="sdet-table__sub">
                      {item.source.type}
                      {item.origin === "jira" ? <span className="sdet-source-tag">Jira</span> : null}
                    </span>
                  </td>
                  <td className="sdet-change">{item.change}</td>
                  <td className={`sdet-priority--${item.priority}`}>{item.priority}</td>
                  <td>{item.assignee}</td>
                  <td><SdetPill tone={statusTone(item.status)}>{item.status}</SdetPill></td>
                  <td className="sdet-updated">{formatWhen(item.updatedAt, { withTime: Date.now() - Date.parse(item.updatedAt) < 86400000 })}</td>
                  <td>
                    {actions.length > 0 ? (
                      <div className="sdet-actions--single">
                        {actions.map((action) => (
                          <button key={action.label} type="button" className={`sdet-btn sdet-btn--sm ${action.primary ? "sdet-btn--primary" : ""}`} onClick={action.onClick}>
                            {action.label}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <span className="sdet-actions__note">Closed</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <SdetToast message={toast} onDone={() => setToast("")} />
    </SdetPage>
  );
}
