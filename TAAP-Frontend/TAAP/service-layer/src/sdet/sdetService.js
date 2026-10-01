// Data for the SDET profile's Automation Execution and Automation
// Maintenance pages.
//
// Jira is the source for anything it can provide: user stories and defects
// (as maintenance references and auto-suggested enhancement items),
// assignees, release labels and the connection status shown in each page
// header. Runs, schedules and runner machines have no Jira equivalent and
// come from sdetSampleData.js.
import { serviceEnvironment } from "../environment.js";
import { fetchJiraIssueGroups } from "../jira/serviceClient.js";
import { clone } from "../shared/clone.js";
import {
  computeNextRun,
  sdetEnvironments,
  sdetMachines,
  sdetMaintenanceItems,
  sdetRuns,
  sdetSampleReferences,
  sdetScripts,
  sdetSprint,
  sdetUsers
} from "./sdetSampleData.js";

const JIRA_ISSUE_LIMIT = 50;
const MAX_JIRA_STORY_ITEMS = 4;
const MAX_JIRA_BUG_ITEMS = 3;

const DONE_STATUSES = new Set(["done", "resolved", "closed", "complete", "completed", "cancelled", "canceled"]);
const IN_PROGRESS_STATUSES = new Set(["in progress", "in review", "in development", "ready for qa", "ready for testing", "in qa"]);

function normalize(value) {
  return String(value ?? "").trim().toLowerCase();
}

function isDone(status) {
  return DONE_STATUSES.has(normalize(status));
}

function isInProgress(status) {
  return IN_PROGRESS_STATUSES.has(normalize(status));
}

function mapPriority(priority) {
  const value = normalize(priority);
  if (["highest", "high", "critical", "blocker", "p1", "p2"].includes(value)) return "High";
  if (["low", "lowest", "minor", "trivial", "p4"].includes(value)) return "Low";
  return "Medium";
}

function firstLine(text) {
  return String(text ?? "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .find(Boolean) ?? "";
}

function byUpdatedDesc(first, second) {
  return Date.parse(second.updated || 0) - Date.parse(first.updated || 0);
}

const SCRIPT_KEYWORDS = [
  { script: "SCR-1987", words: ["payment", "refund", "gateway", "otp", "authoris", "authoriz"] },
  { script: "SCR-2103", words: ["order", "fulfil", "shipment", "invoice", "confirmation"] },
  { script: "SCR-1750", words: ["search", "catalog", "catalogue", "filter", "browse"] },
  { script: "SCR-1622", words: ["billing", "statement", "month-end", "tax"] },
  { script: "SCR-2041", words: ["checkout", "cart", "promo", "discount", "coupon", "address"] }
];

function matchScript(issue) {
  const haystack = normalize(`${issue.summary} ${(issue.labels ?? []).join(" ")} ${issue.description ?? ""}`);
  const match = SCRIPT_KEYWORDS.find(({ words }) => words.some((word) => haystack.includes(word)));
  return match?.script ?? "SCR-2041";
}

async function loadJira() {
  if (serviceEnvironment.isMock) {
    return { mode: "mock", connected: false, projectKey: "", fetchedAt: "", error: "", epics: [], stories: [], bugs: [] };
  }

  try {
    const groups = await fetchJiraIssueGroups({
      limit: JIRA_ISSUE_LIMIT,
      projectKey: serviceEnvironment.jiraProjectKey || undefined
    });

    return {
      mode: "jira",
      connected: true,
      projectKey: groups.projectKey ?? "",
      fetchedAt: groups.fetchedAt ?? new Date().toISOString(),
      error: "",
      epics: groups.groups?.epics?.issues ?? [],
      stories: groups.groups?.stories?.issues ?? [],
      bugs: groups.groups?.bugs?.issues ?? []
    };
  } catch (error) {
    return {
      mode: "jira",
      connected: false,
      projectKey: serviceEnvironment.jiraProjectKey,
      fetchedAt: "",
      error: error instanceof Error ? error.message : "Unable to reach Jira.",
      epics: [],
      stories: [],
      bugs: []
    };
  }
}

function releaseLabelFrom(jira) {
  const labels = [...jira.epics, ...jira.stories, ...jira.bugs].flatMap((issue) => issue.labels ?? []);
  const release = labels.find((label) => /^rel(ease)?[-_ ]?\d/i.test(label));
  return release ?? sdetSprint.release;
}

function jiraSummary(jira) {
  return {
    mode: jira.mode,
    connected: jira.connected,
    projectKey: jira.projectKey,
    fetchedAt: jira.fetchedAt,
    error: jira.error,
    counts: { epics: jira.epics.length, stories: jira.stories.length, bugs: jira.bugs.length }
  };
}

function toReference(issue, type) {
  return {
    key: issue.key,
    type,
    title: issue.summary,
    description: issue.description || "",
    status: issue.status || "-",
    priority: issue.priority || "-",
    assignee: issue.assignee || "Unassigned",
    reporter: issue.reporter || "",
    labels: issue.labels ?? [],
    parentKey: issue.parentKey || "",
    updated: issue.updated || "",
    url: issue.url || "",
    acceptedCases: 0,
    origin: "jira"
  };
}

function jiraMaintenanceItems(jira, startNumber) {
  const stories = jira.stories.filter((issue) => !isDone(issue.status)).sort(byUpdatedDesc).slice(0, MAX_JIRA_STORY_ITEMS);
  const bugs = jira.bugs.filter((issue) => !isDone(issue.status)).sort(byUpdatedDesc).slice(0, MAX_JIRA_BUG_ITEMS);
  let number = startNumber + stories.length + bugs.length;

  const build = (issue, reason, sourceType) => {
    number -= 1;
    const detail = firstLine(issue.description);
    return {
      id: `MT-${number + 1}`,
      script: matchScript(issue),
      reason,
      source: { type: sourceType, ref: issue.key, url: issue.url || "" },
      change: detail && detail !== issue.summary ? `${issue.summary} — ${detail}` : issue.summary,
      priority: mapPriority(issue.priority),
      assignee: issue.assignee || "Unassigned",
      status: isInProgress(issue.status) ? "In progress" : "New",
      updatedAt: issue.updated || jira.fetchedAt,
      origin: "jira",
      jiraStatus: issue.status || "",
      url: issue.url || ""
    };
  };

  // Bugs are coverage gaps; stories are app changes. Most recently updated first.
  const items = [
    ...bugs.map((issue) => build(issue, "Enhancement · coverage gap", "Defect")),
    ...stories.map((issue) => build(issue, "Enhancement · app change", "User story"))
  ];

  return items.sort((first, second) => Date.parse(second.updatedAt || 0) - Date.parse(first.updatedAt || 0));
}

function uniqueNames(values) {
  const seen = new Set();
  return values.filter((value) => {
    const name = String(value ?? "").trim();
    if (!name || name === "Unassigned" || seen.has(name)) return false;
    seen.add(name);
    return true;
  });
}

function decorateScript(script) {
  const machine = sdetMachines.find((item) => item.id === script.machine) ?? null;
  return {
    ...script,
    nextRunAt: computeNextRun(script.schedule),
    machineStatus: machine ? { status: machine.status, ready: machine.ready, summary: machine.summary } : null
  };
}

export async function fetchSdetExecution() {
  const jira = await loadJira();
  const scripts = sdetScripts.map(decorateScript);

  return clone({
    source: jira.connected ? "jira+sample" : "sample",
    jira: jiraSummary(jira),
    release: releaseLabelFrom(jira),
    sprint: sdetSprint.name,
    currentUser: sdetUsers.currentUser,
    scripts,
    runs: sdetRuns,
    machines: sdetMachines,
    environments: sdetEnvironments,
    testTypes: ["Regression", "Smoke", "SIT", "System test"],
    layers: ["UI", "API", "End to end"],
    browsers: ["Chrome", "Edge", "Firefox"],
    frequencies: ["Daily", "Weekly", "Monthly", "Run once"],
    retryOptions: ["Off", "Environment failures only", "All failures once"],
    emailOptions: ["After every run", "Only on failure", "Daily digest"],
    // Jira stories and bugs are offered as linked work for a run configuration.
    jiraStories: jira.stories.map((issue) => toReference(issue, "User story")),
    jiraBugs: jira.bugs.map((issue) => toReference(issue, "Defect"))
  });
}

export async function fetchSdetMaintenance() {
  const jira = await loadJira();
  const highestSampleNumber = Math.max(...sdetMaintenanceItems.map((item) => Number.parseInt(item.id.replace(/\D/g, ""), 10)));
  const jiraItems = jiraMaintenanceItems(jira, highestSampleNumber + 1);

  const references = { ...sdetSampleReferences };
  for (const issue of jira.stories) references[issue.key] = toReference(issue, "User story");
  for (const issue of jira.bugs) references[issue.key] = toReference(issue, "Defect");

  const users = uniqueNames([
    sdetUsers.currentUser,
    ...sdetUsers.members,
    ...jira.stories.map((issue) => issue.assignee),
    ...jira.bugs.map((issue) => issue.assignee),
    ...jira.stories.map((issue) => issue.reporter),
    ...jira.bugs.map((issue) => issue.reporter)
  ]);

  return clone({
    source: jira.connected ? "jira+sample" : "sample",
    jira: jiraSummary(jira),
    release: releaseLabelFrom(jira),
    sprint: sdetSprint,
    currentUser: sdetUsers.currentUser,
    users,
    scripts: sdetScripts.map(({ id, name, suite, description, environment }) => ({ id, name, suite, description, environment })),
    items: [...jiraItems, ...sdetMaintenanceItems],
    references,
    referenceOptions: {
      stories: jira.stories.map((issue) => toReference(issue, "User story")),
      bugs: jira.bugs.map((issue) => toReference(issue, "Defect")),
      runs: sdetRuns.filter((run) => run.result === "Failed").map((run) => ({ key: run.id, title: `${run.script} · ${run.environment} · ${run.fail} failed` })),
      sampleStories: Object.values(sdetSampleReferences).filter((reference) => reference.type === "User story"),
      sampleDefects: Object.values(sdetSampleReferences).filter((reference) => reference.type === "Defect")
    },
    reasons: ["Script failure", "Flaky test", "Enhancement · app change", "Enhancement · coverage gap"],
    sourceTypes: ["Failed run", "Allure report", "User story", "Defect"],
    priorities: ["High", "Medium", "Low"]
  });
}
