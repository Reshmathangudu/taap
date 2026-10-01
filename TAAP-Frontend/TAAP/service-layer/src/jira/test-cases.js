import { jiraRequest, JiraRequestError, normalizeJiraIssue, readJiraConfig, searchIssues } from "./rest-client.js";

const keyPattern = /^[A-Z][A-Z0-9_]*-\d+$/;
const isStory = issue => /^(story|user story)$/i.test(issue.fields?.issuetype?.name ?? "");
const fieldName = name => String(name ?? "").toLowerCase().replace(/[\s_-]/g, "");
const fieldText = value => Array.isArray(value) ? value.map(fieldText).filter(Boolean).join(", ")
  : value && typeof value === "object" ? value.value ?? value.name ?? value.key ?? "" : String(value ?? "");

export async function fetchJiraTestCases({ keys, config = readJiraConfig() } = {}) {
  const selectedKeys = [...new Set((keys ?? []).map(key => String(key).trim().toUpperCase()))];
  if (!selectedKeys.length || selectedKeys.some(key => !keyPattern.test(key))) {
    throw new JiraRequestError("Select valid Jira epic or story keys.", { status: 400 });
  }
  if (config.isMock) throw new JiraRequestError("Live Jira test cases are unavailable in mock mode.", { status: 503 });
  const metadata = await jiraRequest(config, "/rest/api/3/field");
  const custom = names => metadata.filter(field => names.includes(fieldName(field.name)));
  const epicFields = custom(["epiclink"]).filter(field => /^customfield_\d+$/.test(field.id));
  const caseIdFields = custom(["testcaseid", "testid", "tcid"]);
  const typeFields = custom(["testtype", "testcasetype"]);
  const automationFields = custom(["automation", "automationstatus"]);
  const reviewFields = custom(["review", "reviewstatus", "approvalstatus"]);
  const fields = [...new Set(["summary", "description", "issuetype", "parent", "issuelinks", "status", "priority", "assignee", "reporter", "labels", "created", "updated",
    ...[...epicFields, ...caseIdFields, ...typeFields, ...automationFields, ...reviewFields].map(field => field.id)])];
  const get = key => jiraRequest(config, `/rest/api/3/issue/${encodeURIComponent(key)}?fields=${fields.join(",")}`);
  const requirements = new Map();
  const storyKeys = new Set();
  for (const key of selectedKeys) {
    const issue = await get(key);
    if (!isStory(issue) && !/^epic$/i.test(issue.fields?.issuetype?.name ?? "")) {
      throw new JiraRequestError(`${key} is not an epic or user story.`, { status: 400 });
    }
    requirements.set(key, issue);
    if (isStory(issue)) storyKeys.add(key);
    else {
      const clauses = [`parent = "${key}"`, ...epicFields.map(field => `cf[${field.id.slice(12)}] = "${key}"`)];
      const children = await searchIssues(config, { jql: `(${clauses.join(" OR ")}) AND issuetype in ("Story", "User Story")`, fields });
      for (const child of children) {
        requirements.set(child.key, child);
        storyKeys.add(child.key);
      }
    }
  }
  const valueFor = (issue, candidates) => candidates.map(field => fieldText(issue.fields?.[field.id])).find(Boolean) ?? "";
  // This application's Jira model stores test cases as Story subtasks as well as Test issues.
  const isTest = issue => /^(test|test[ _-]?case|sub[ _-]?task)$/i.test(issue.fields?.issuetype?.name ?? "") || !!valueFor(issue, caseIdFields);
  const cases = new Map();
  const add = (issue, requirementKey) => {
    if ([issue.fields?.issuetype?.name, valueFor(issue, typeFields)].some(type => /^bug$/i.test(String(type ?? "").trim()))) return;
    if (!isTest(issue)) return;
    if (!cases.has(issue.key)) {
      const details = normalizeJiraIssue(issue, config.baseUrl);
      cases.set(issue.key, { id: issue.key, title: details.summary, description: details.description,
        type: details.type,
        priority: details.priority || "Not provided", automation: valueFor(issue, automationFields) || "Not provided",
        review: valueFor(issue, reviewFields) || details.status || "Not provided",
        owner: details.assignee, updated: details.updated, requirementKeys: [], jiraDetails: details, url: details.url, source: "jira" });
    }
    const row = cases.get(issue.key);
    if (!row.requirementKeys.includes(requirementKey)) row.requirementKeys.push(requirementKey);
  };
  // Jira subtasks are returned through parent queries. Linked tests may live in another project.
  const requirementKeys = [...requirements.keys()];
  for (let offset = 0; offset < requirementKeys.length; offset += 50) {
    const batch = requirementKeys.slice(offset, offset + 50);
    const children = await searchIssues(config, { jql: `parent in (${batch.map(key => `"${key}"`).join(",")})`, fields });
    for (const child of children) if (requirements.has(child.fields?.parent?.key)) add(child, child.fields.parent.key);
  }
  const linked = new Map();
  for (const [key, issue] of requirements) {
    for (const link of issue.fields?.issuelinks ?? []) {
      const target = link.outwardIssue ?? link.inwardIssue;
      if (!keyPattern.test(target?.key ?? "") || requirements.has(target.key)) continue;
      if (!linked.has(target.key)) linked.set(target.key, []);
      linked.get(target.key).push(key);
    }
  }
  for (const [key, sources] of linked) {
    const issue = await get(key);
    sources.forEach(source => add(issue, source));
  }
  return { source: "jira", selectedKeys, storyKeys: [...storyKeys], cases: [...cases.values()].map(row => ({ ...row, requirement: row.requirementKeys.join(", ") })) };
}
