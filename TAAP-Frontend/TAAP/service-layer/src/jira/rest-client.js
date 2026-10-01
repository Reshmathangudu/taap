import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DEFAULT_FIELDS = [
  "summary",
  "description",
  "status",
  "issuetype",
  "priority",
  "assignee",
  "reporter",
  "created",
  "updated",
  "labels",
  "parent",
  "customfield_10008",
  "customfield_10014",
  "customfield_10016"
];

const JIRA_FIELD_ALIASES = {
  requirementId: ["Requirement ID", "Requirement_ID", "requirement_id", "Requirement"],
  testCaseId: ["Test Case ID", "TestCase ID", "Test_Case_ID", "TestCase_ID", "Test ID", "TC_ID"],
  testName: ["Test Name", "Test_Name", "test_name"],
  testType: ["Test Type", "Test_Type", "test_type"],
  testStatus: ["Test Status", "Test_Status", "TestStatus", "test_status"],
  automationStatus: ["Automation Status", "Automation_Status", "automation_status"],
  businessPriority: ["Business Priority", "Business_Priority", "business_priority"],
  executionMinutes: ["Execution Minutes", "Execution_Minutes", "Duration Minutes", "Duration"],
  environment: ["Environment"],
  testPhase: ["Test Phase", "TestPhase", "Test_Phase"]
};

const ISSUE_GROUPS = [
  { id: "epics", label: "Epics", issueTypes: ["Epic"] },
  { id: "stories", label: "User Stories", issueTypes: ["Story", "User Story"] },
  { id: "bugs", label: "Bugs", issueTypes: ["Bug"] },
  { id: "testCases", label: "Test Cases", issueTypes: ["Testcase", "Test Case", "Test"], optional: true }
];

const JIRA_ISSUE_SNAPSHOT_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
  "data",
  "jira-issue-groups.json"
);

export class JiraConfigError extends Error {
  constructor(message) {
    super(message);
    this.name = "JiraConfigError";
  }
}

export class JiraRequestError extends Error {
  constructor(message, { status, details } = {}) {
    super(message);
    this.name = "JiraRequestError";
    this.status = status;
    this.details = details;
  }
}

export function readJiraConfig(env = process.env) {
  const config = {
    baseUrl: cleanUrlEnv(env.JIRA_BASE_URL),
    email: cleanEnv(env.JIRA_EMAIL),
    apiToken: cleanEnv(env.JIRA_API_TOKEN),
    projectKey: cleanEnv(env.JIRA_PROJECT_KEY || "SCRUM"),
    pageSize: readPositiveInteger(env.JIRA_MCP_PAGE_SIZE, 100),
    maxPages: readPositiveInteger(env.JIRA_MCP_MAX_PAGES, 1000),
    acceptanceCriteriaFieldIds: cleanEnv(env.JIRA_ACCEPTANCE_CRITERIA_FIELDS || env.JIRA_ACCEPTANCE_CRITERIA_FIELD)
      .split(",").map((id) => id.trim()).filter(Boolean),
    isMock: shouldUseMockJira(env)
  };

  const missing = Object.entries({
    JIRA_BASE_URL: config.baseUrl,
    JIRA_EMAIL: config.email,
    JIRA_API_TOKEN: config.apiToken,
    JIRA_PROJECT_KEY: config.projectKey
  })
    .filter(([, value]) => !value)
    .map(([key]) => key);

  if (missing.length > 0 && !config.isMock) {
    throw new JiraConfigError(`Missing Jira configuration: ${missing.join(", ")}`);
  }

  return config;
}

export async function testJiraConnection(options = {}) {
  const config = options.config ?? readJiraConfig(options.env);

  if (config.isMock) {
    return {
      ok: true,
      accountId: "demo-user",
      displayName: "Demo Jira user",
      emailAddress: "demo@example.com",
      mode: "mock"
    };
  }

  const user = await jiraRequest(config, "/rest/api/3/myself");

  return {
    ok: true,
    accountId: user.accountId ?? "",
    displayName: user.displayName ?? "",
    emailAddress: user.emailAddress ?? ""
  };
}

export async function fetchJiraIssueGroups(options = {}) {
  const config = options.config ?? readJiraConfig(options.env);
  const limit = options.limit == null || String(options.limit).trim() === ""
    ? Number.POSITIVE_INFINITY
    : readPositiveInteger(options.limit, Number.POSITIVE_INFINITY);
  const projectKey = cleanEnv(options.projectKey) || config.projectKey;

  if (config.isMock) {
    const payload = buildMockIssueGroups({ projectKey, limit });
    return options.requirementsOnly ? filterRequirements(payload) : payload;
  }

  const jiraFields = await jiraRequest(config, "/rest/api/3/field");
  const acceptanceCriteriaFieldIds = [...new Set([
    ...(config.acceptanceCriteriaFieldIds ?? []),
    ...jiraFields
      .filter((field) => /\bacceptance[\s_-]*(?:criteria|criterion)\b|^ac$/i.test((field.name ?? "").trim()))
      .map((field) => field.id)
  ])];
  const epicLinkFieldIds = jiraFields
    .filter((field) => /epic\s*link/i.test(field.name ?? ""))
    .map((field) => field.id);
  const fieldIds = resolveJiraFieldIds(jiraFields);
  const requestedFields = [...new Set([
    ...DEFAULT_FIELDS,
    ...acceptanceCriteriaFieldIds,
    ...epicLinkFieldIds,
    ...Object.values(fieldIds).filter(Boolean)
  ])];
  const groups = {};

  for (const group of ISSUE_GROUPS) {
    if (options.requirementsOnly && (group.id === "bugs" || group.id === "testCases")) continue;
    let issues = [];

    try {
      issues = await searchIssues(config, {
        jql: buildIssueTypeJql(projectKey, group.issueTypes),
        fields: options.requirementsOnly && group.id === "epics"
          ? requestedFields.filter((field) => field !== "description" && !acceptanceCriteriaFieldIds.includes(field))
          : requestedFields,
        maxResults: limit
      });
    } catch (error) {
      if (!group.optional) {
        throw error;
      }
    }

    groups[group.id] = {
      id: group.id,
      label: group.label,
      issues: issues.map((issue) => normalizeJiraIssue(issue, config.baseUrl, {
        acceptanceCriteriaFieldIds,
        epicLinkFieldIds,
        fieldIds
      }))
    };
  }

  const issueGroups = {
    source: "jira",
    projectKey,
    fetchedAt: new Date().toISOString(),
    groups
  };

  if (options.writeSnapshot !== false) {
    await writeJiraIssueSnapshot(issueGroups, options.snapshotPath);
  }

  return options.requirementsOnly ? filterRequirements(issueGroups) : issueGroups;
}

export function filterRequirements(payload) {
  const stories = (payload.groups.stories?.issues ?? []).filter((story) => story.acceptanceCriteria?.length > 0);
  const parentKeys = new Set(stories.map((story) => story.parentKey));
  const epics = (payload.groups.epics?.issues ?? [])
    .filter((epic) => parentKeys.has(epic.key))
    .map((epic) => ({ ...epic, description: "" }));
  return { ...payload, groups: {
    epics: { id: "epics", label: "Epics", issues: epics },
    stories: { id: "stories", label: "User Stories", issues: stories }
  } };
}

export async function writeJiraIssueSnapshot(issueGroups, snapshotPath = JIRA_ISSUE_SNAPSHOT_PATH) {
  await mkdir(path.dirname(snapshotPath), { recursive: true });
  await writeFile(snapshotPath, `${JSON.stringify(issueGroups, null, 2)}\n`, "utf8");

  return snapshotPath;
}

export async function searchIssues(config, { jql, fields = DEFAULT_FIELDS, maxResults = Number.POSITIVE_INFINITY }) {
  const issues = [];
  const limit = Number.isFinite(Number(maxResults)) && Number(maxResults) > 0
    ? Number(maxResults)
    : Number.POSITIVE_INFINITY;
  let nextPageToken = "";
  const seenTokens = new Set();

  for (let page = 1; page <= config.maxPages; page += 1) {
    const body = {
      jql,
      fields,
      maxResults: Math.min(Number.isFinite(limit) ? limit - issues.length : config.pageSize, config.pageSize, 100)
    };

    if (nextPageToken) {
      body.nextPageToken = nextPageToken;
    }

    const data = await jiraRequest(config, "/rest/api/3/search/jql", {
      method: "POST",
      body
    });

    issues.push(...(Array.isArray(data.issues) ? data.issues : []));

    if (issues.length >= limit || data.isLast === true || (data.isLast !== false && !data.nextPageToken)) {
      return deduplicateIssues(issues).slice(0, limit);
    }
    if (!data.nextPageToken || seenTokens.has(data.nextPageToken)) {
      throw new JiraRequestError("Jira returned incomplete or repeated pagination. Refresh to retry.");
    }
    seenTokens.add(data.nextPageToken);
    nextPageToken = data.nextPageToken;
  }
  throw new JiraRequestError("Jira results exceed JIRA_MCP_MAX_PAGES; increase the limit to fetch all requirements.");
}

export async function jiraRequest(config, resourcePath, { method = "GET", body } = {}) {
  const url = `${config.baseUrl.replace(/\/+$/, "")}${resourcePath}`;
  const headers = {
    Accept: "application/json",
    "Content-Type": "application/json",
    Authorization: `Basic ${Buffer.from(`${config.email}:${config.apiToken}`).toString("base64")}`
  };
  const retryableStatuses = new Set([429, 500, 502, 503, 504]);
  const maxAttempts = 5;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
    let response;

    try {
      response = await fetch(url, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined
      });
    } catch (error) {
      if (attempt === maxAttempts) {
        throw new JiraRequestError("Jira request failed after retries.", {
          details: error instanceof Error ? error.message : String(error)
        });
      }

      await wait(retryDelay(attempt));
      continue;
    }

    if (retryableStatuses.has(response.status) && attempt < maxAttempts) {
      await wait(readRetryAfter(response) ?? retryDelay(attempt));
      continue;
    }

    const text = await response.text();
    const payload = text ? parseJson(text) : {};

    if (!response.ok) {
      throw new JiraRequestError(`Jira ${method} ${resourcePath} failed with ${response.status}.`, {
        status: response.status,
        details: summarizeError(payload, text)
      });
    }

    return payload;
  }

  throw new JiraRequestError(`Jira ${method} ${resourcePath} failed after retries.`);
}

function buildMockIssueGroups({ projectKey = "SCRUM", limit = Number.POSITIVE_INFINITY } = {}) {
  const allIssues = [
    {
      id: "1",
      key: "EP-1003",
      type: "Epic",
      summary: "OTP Retry Enhancement",
      description: "As a banking user, I want the system to allow a defined number of OTP retry attempts so that I can complete authentication if I enter an incorrect OTP by mistake.\n\nThe system should track OTP retry attempts for a transaction. If the user enters an incorrect OTP, the remaining attempts should reduce. When all attempts are used, the transaction should be blocked and the user should be asked to restart the verification process.",
      status: "To Do",
      priority: "Medium",
      assignee: { displayName: "Unassigned" },
      reporter: { displayName: "Product Ops" },
      labels: ["demo", "otp"],
      updated: new Date().toISOString(),
      url: "https://jira.example.com/browse/EP-1003"
    },
    {
      id: "2",
      key: "US-301",
      type: "Story",
      summary: "Create scheduled transfer",
      description: "As a banking user, I want to schedule a fund transfer for a future date so that I can plan payments in advance. The system should allow the user to select a beneficiary, enter an amount, choose a future date, and confirm the scheduled transfer. After successful creation, the scheduled transfer should be visible to the user with the correct date, amount, and beneficiary details.",
      status: "To Do",
      priority: "Medium",
      assignee: { displayName: "Ayesha Khan" },
      reporter: { displayName: "Product Ops" },
      labels: ["demo", "payments"],
      parentKey: "EP-1003",
      updated: new Date().toISOString(),
      url: "https://jira.example.com/browse/US-301"
    },
    {
      id: "3",
      key: "US-302",
      type: "Story",
      summary: "Lock transaction after the final failed OTP",
      description: "After the final invalid OTP entry, the system should block the transaction, prevent further retries, and instruct the user to restart verification from the beginning.",
      status: "In Progress",
      priority: "High",
      assignee: { displayName: "Rohan Mehta" },
      reporter: { displayName: "Product Ops" },
      labels: ["demo", "otp"],
      parentKey: "EP-1003",
      updated: new Date().toISOString(),
      url: "https://jira.example.com/browse/US-302"
    },
    {
      id: "1a",
      key: `${projectKey}-101`,
      type: "Epic",
      summary: "Checkout reliability modernization",
      description: "Improve checkout stability across cart, payment, tax, discount, and order confirmation flows.",
      status: "In Progress",
      priority: "High",
      assignee: { displayName: "Priya Nair" },
      reporter: { displayName: "Product Ops" },
      labels: ["demo", "checkout"],
      updated: new Date().toISOString(),
      url: `https://jira.example.com/browse/${projectKey}-101`
    },
    {
      id: "2",
      key: `${projectKey}-102`,
      type: "Story",
      summary: "Handle payment retries without duplicating orders",
      description: "When a payment request times out, the user must see a retry flow and the system must not create duplicate orders.",
      status: "In Progress",
      priority: "High",
      assignee: { displayName: "Ananya Sharma" },
      reporter: { displayName: "Product Ops" },
      labels: ["demo", "payments"],
      updated: new Date().toISOString(),
      url: `https://jira.example.com/browse/${projectKey}-102`
    },
    {
      id: "3",
      key: `${projectKey}-103`,
      type: "Story",
      summary: "Surface order status changes in the customer portal",
      description: "Customers should be able to see order status updates and delivery exceptions without contacting support.",
      status: "Ready for QA",
      priority: "Medium",
      assignee: { displayName: "Rahul Menon" },
      reporter: { displayName: "Product Ops" },
      labels: ["demo", "orders"],
      updated: new Date().toISOString(),
      url: `https://jira.example.com/browse/${projectKey}-103`
    },
    {
      id: "4",
      key: `${projectKey}-104`,
      type: "Bug",
      summary: "Promo code validation fails on stacked discounts",
      description: "Users applying multiple campaign discounts receive a validation error even when the combination is allowed.",
      status: "Needs Triage",
      priority: "High",
      assignee: { displayName: "Meera Iyer" },
      reporter: { displayName: "Support" },
      labels: ["demo", "bug"],
      updated: new Date().toISOString(),
      url: `https://jira.example.com/browse/${projectKey}-104`
    },
    {
      id: "5",
      key: `${projectKey}-105`,
      type: "Bug",
      summary: "Search results show stale inventory counts",
      description: "Search results intermittently show previous inventory values after stock updates are processed.",
      status: "In Review",
      priority: "Medium",
      assignee: { displayName: "Vikram Rao" },
      reporter: { displayName: "QA" },
      labels: ["demo", "search"],
      updated: new Date().toISOString(),
      url: `https://jira.example.com/browse/${projectKey}-105`
    },
    {
      id: "6",
      key: `${projectKey}-201`,
      type: "Test Case",
      summary: "Verify payment retry does not duplicate the order",
      description: "Validate that timeout retry creates a single order and presents the retry state to the customer.",
      status: "Ready for Review",
      priority: "High",
      assignee: { displayName: "SDET Agent" },
      reporter: { displayName: "QA" },
      labels: ["demo", "payments", "automation-candidate"],
      parentKey: `${projectKey}-102`,
      parentTitle: "Handle payment retries without duplicating orders",
      requirementId: `${projectKey}-102`,
      testCaseId: "TC-PAY-001",
      testName: "Payment retry without duplicate order",
      testType: "Functional",
      testStatus: "Ready for Review",
      automationStatus: "Candidate",
      businessPriority: "High",
      updated: new Date().toISOString(),
      url: `https://jira.example.com/browse/${projectKey}-201`
    },
    {
      id: "7",
      key: `${projectKey}-202`,
      type: "Test Case",
      summary: "Validate promo code rejection for stacked discount conflict",
      description: "Verify that campaign discount combinations are accepted or rejected according to the configured business rule.",
      status: "Pending Review",
      priority: "High",
      assignee: { displayName: "SDET Agent" },
      reporter: { displayName: "QA" },
      labels: ["demo", "checkout", "promo"],
      parentKey: `${projectKey}-104`,
      parentTitle: "Promo code validation fails on stacked discounts",
      requirementId: `${projectKey}-104`,
      testCaseId: "TC-CHK-014",
      testName: "Promo conflict validation",
      testType: "Negative",
      testStatus: "Pending Review",
      automationStatus: "Candidate",
      businessPriority: "High",
      updated: new Date().toISOString(),
      url: `https://jira.example.com/browse/${projectKey}-202`
    }
  ];

  const groups = {
    epics: { id: "epics", label: "Epics", issues: allIssues.filter((issue) => issue.type === "Epic").slice(0, limit) },
    stories: { id: "stories", label: "User Stories", issues: allIssues.filter((issue) => issue.type === "Story").slice(0, limit) },
    bugs: { id: "bugs", label: "Bugs", issues: allIssues.filter((issue) => issue.type === "Bug").slice(0, limit) },
    testCases: { id: "testCases", label: "Test Cases", issues: allIssues.filter((issue) => issue.type === "Testcase" || issue.type === "Test Case" || issue.type === "Test").slice(0, limit) }
  };

  return {
    source: "jira",
    projectKey,
    fetchedAt: new Date().toISOString(),
    groups
  };
}

function shouldUseMockJira(env = process.env) {
  const value = String(env?.TAAP_IS_MOCK ?? env?.VITE_TAAP_IS_MOCK ?? "").trim().toLowerCase();
  return ["true", "1", "yes", "y"].includes(value);
}

function resolveJiraFieldIds(fields) {
  if (!Array.isArray(fields)) {
    return {};
  }

  const byName = new Map(
    fields
      .filter((field) => field?.id && field?.name)
      .map((field) => [String(field.name).trim().toLowerCase(), field.id])
  );

  return Object.fromEntries(
    Object.entries(JIRA_FIELD_ALIASES).map(([key, aliases]) => [
      key,
      aliases.map((alias) => byName.get(alias.toLowerCase())).find(Boolean) ?? ""
    ])
  );
}

export function normalizeJiraIssue(issue, baseUrl, { acceptanceCriteriaFieldIds = [], epicLinkFieldIds = [], fieldIds = {} } = {}) {
  const fields = issue.fields ?? {};
  const key = issue.key ?? "";
  const acceptanceCriteriaValues = [fields.acceptanceCriteria, ...acceptanceCriteriaFieldIds.map((fieldId) => fields[fieldId])]
    .filter((value) => value != null && value !== "");
  const epicLink = epicLinkFieldIds.map((fieldId) => fields[fieldId]).find((value) => value != null && value !== "");
  const description = normalizeJiraDescription(fields.description ?? issue.description ?? "");
  const customCriteria = normalizeAcceptanceCriteria(acceptanceCriteriaValues);
  const requirementId = fieldText(fields, fieldIds.requirementId) || issue.requirementId || fields.parent?.key || normalizeJiraIssueKey(epicLink) || normalizeJiraIssueKey(fields.customfield_10014) || normalizeJiraIssueKey(fields.customfield_10008) || issue.parentKey || "";
  const testCaseId = fieldText(fields, fieldIds.testCaseId) || issue.testCaseId || key;
  const testName = fieldText(fields, fieldIds.testName) || issue.testName || fields.summary || issue.summary || "";

  return {
    id: issue.id ?? key,
    key,
    type: fields.issuetype?.name ?? issue.type ?? "",
    summary: fields.summary ?? issue.summary ?? "",
    description,
    status: fields.status?.name ?? issue.status ?? "",
    priority: fields.priority?.name ?? issue.priority ?? "",
    assignee: fields.assignee?.displayName ?? issue.assignee?.displayName ?? "Unassigned",
    reporter: fields.reporter?.displayName ?? issue.reporter?.displayName ?? "",
    labels: Array.isArray(fields.labels) ? fields.labels : Array.isArray(issue.labels) ? issue.labels : [],
    parentKey: fields.parent?.key || normalizeJiraIssueKey(epicLink) || normalizeJiraIssueKey(fields.customfield_10014) || normalizeJiraIssueKey(fields.customfield_10008) || issue.parentKey || "",
    parentTitle: fields.parent?.fields?.summary ?? fields.parent?.summary ?? issue.parentTitle ?? "",
    requirementId,
    testCaseId,
    testName,
    testType: fieldText(fields, fieldIds.testType) || issue.testType || "",
    testStatus: fieldText(fields, fieldIds.testStatus) || issue.testStatus || "",
    automationStatus: fieldText(fields, fieldIds.automationStatus) || issue.automationStatus || "",
    businessPriority: fieldText(fields, fieldIds.businessPriority) || issue.businessPriority || "",
    executionMinutes: fieldText(fields, fieldIds.executionMinutes) || issue.executionMinutes || "",
    environment: fieldText(fields, fieldIds.environment) || issue.environment || "",
    testPhase: fieldText(fields, fieldIds.testPhase) || issue.testPhase || "",
    acceptanceCriteria: customCriteria.length ? customCriteria : criteriaFromDescription(description),
    storyPoints: fields.customfield_10016 ?? issue.storyPoints ?? "",
    created: fields.created ?? issue.created ?? "",
    updated: fields.updated ?? issue.updated ?? "",
    url: key ? `${baseUrl.replace(/\/+$/, "")}/browse/${key}` : issue.self ?? issue.url ?? ""
  };
}

function fieldText(fields, fieldId) {
  if (!fieldId) return "";
  return valueText(fields[fieldId]);
}

function valueText(value) {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") return String(value);
  if (Array.isArray(value)) return value.map(valueText).filter(Boolean).join(", ");
  if (typeof value === "object") {
    if (value.displayName) return String(value.displayName);
    if (value.name) return String(value.name);
    if (value.value) return String(value.value);
    if (value.key) return String(value.key);
    if (value.content) return normalizeJiraDescription(value);
  }

  return "";
}

function normalizeAcceptanceCriteria(values) {
  return [...new Set(values.flat(Infinity).flatMap((value) => {
    const text = normalizeJiraDescription(value);
    return text.split(/\r?\n/)
      .map((criterion) => criterion.replace(/^\s*(?:#{1,6}\s+|[-*•]\s*|\d+[.)]\s*)/, "").trim())
      .filter((criterion) => criterion && !/^(?:acceptance[\s_-]*(?:criteria|criterion)|AC\s*\d*)\s*:?[\s]*$/i.test(criterion));
  }))];
}

function criteriaFromDescription(description) {
  const lines = description.split(/\r?\n/);
  const criteria = [];
  let inCriteria = false;
  for (const line of lines) {
    // Only explicitly labelled sections count. Ordinary story prose is not criteria.
    const heading = line.trim().replace(/^(?:#{1,6}\s*|h[1-6]\.\s*)/, "").replace(/\*\*|__/g, "").replace(/^\*|\*$/g, "");
    const start = heading.match(/^(?:acceptance[\s_-]*(?:criteria|criterion)(?:\s*\([^)]*\))?|AC)\s*(?::\s*(.*))?$/i);
    if (start) {
      inCriteria = true;
      if (start[1]) criteria.push(start[1]);
      continue;
    }
    if (inCriteria && (/^(?:#{1,6}\s|h[1-6]\.\s)/.test(line.trim()) || /^(?:description|notes|dependencies|business impact|technical notes|out of scope|test data|definition of done)\s*:?$/i.test(heading))) break;
    if (inCriteria && line.trim()) criteria.push(line);
  }
  return normalizeAcceptanceCriteria(criteria);
}

function normalizeJiraIssueKey(value) {
  if (typeof value === "string") return value;
  return value && typeof value === "object" ? value.key ?? "" : "";
}

export function normalizeJiraDescription(description) {
  if (typeof description === "string") return description;
  if (Array.isArray(description)) return description.map(normalizeJiraDescription).join("\n").trim();
  return collectDescriptionText(description).trim();
}

function collectDescriptionText(node) {
  if (!node || typeof node !== "object") return "";
  if (node.type === "text") return node.text ?? "";
  if (node.type === "hardBreak") return "\n";
  const value = (node.content ?? []).map(collectDescriptionText).join("");
  if (node.type === "heading") return `## ${value}\n`;
  return ["paragraph", "listItem", "tableRow", "blockquote"].includes(node.type) ? `${value}\n` : value;
}

function buildIssueTypeJql(projectKey, issueTypes) {
  const quotedTypes = issueTypes.map((issueType) => quoteJqlValue(issueType)).join(", ");

  return `project = ${quoteJqlValue(projectKey)} AND issuetype in (${quotedTypes}) ORDER BY updated DESC`;
}

function quoteJqlValue(value) {
  return `"${String(value).replaceAll("\\", "\\\\").replaceAll("\"", "\\\"")}"`;
}

function cleanUrlEnv(value) {
  const text = cleanEnv(value);
  const markdownUrl = text.match(/^\[(https?:\/\/[^\]]+)\]\(/);

  return markdownUrl?.[1] ?? text;
}

function cleanEnv(value) {
  return String(value ?? "").trim();
}

function readPositiveInteger(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);

  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function parseJson(text) {
  try {
    return JSON.parse(text);
  } catch {
    return {};
  }
}

function summarizeError(payload, text) {
  if (payload && typeof payload === "object") {
    if (Array.isArray(payload.errorMessages) && payload.errorMessages.length > 0) {
      return payload.errorMessages.join(" ");
    }

    if (payload.errors && typeof payload.errors === "object") {
      return Object.values(payload.errors).join(" ");
    }
  }

  return text.slice(0, 500);
}

function readRetryAfter(response) {
  const retryAfter = Number.parseFloat(response.headers.get("retry-after") ?? "");

  return Number.isFinite(retryAfter) ? retryAfter * 1000 : null;
}

function retryDelay(attempt) {
  return Math.min(30000, 2 ** attempt * 1000) + Math.floor(Math.random() * 500);
}

function wait(milliseconds) {
  return new Promise((resolve) => {
    setTimeout(resolve, milliseconds);
  });
}

function deduplicateIssues(issues) {
  const seen = new Set();

  return issues.filter((issue) => {
    const key = String(issue.key ?? issue.id ?? "").trim();

    if (!key) {
      return true;
    }

    if (seen.has(key)) {
      return false;
    }

    seen.add(key);
    return true;
  });
}
