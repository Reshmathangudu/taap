import { jiraRequest, JiraRequestError, normalizeJiraIssue, readJiraConfig, searchIssues } from "./rest-client.js";

const isStory = issue => /^(story|user story)$/i.test(issue.fields?.issuetype?.name ?? "");
const keyPattern = /^[A-Z][A-Z0-9_]*-\d+$/;

// Labels are read from the selected issue's perspective. Reverse and neutral
// links are not evidence that the other issue is impacted by this issue.
export function impactLinks(issue) {
  return (issue.fields?.issuelinks ?? []).flatMap(link => {
    const target = link.outwardIssue ?? link.inwardIssue;
    const relationship = link.outwardIssue ? link.type?.outward : link.type?.inward;
    if (!target?.key || !/^(impacts|affects|blocks|is required by|is depended on by)$/i.test(relationship?.trim() ?? "")) return [];
    return [{ sourceKey: issue.key, targetKey: target.key, relationship, evidence: "Jira issue link" }];
  });
}

export async function fetchJiraImpactAnalysis({ keys, config = readJiraConfig() } = {}) {
  const selectedKeys = [...new Set((keys ?? []).map(key => String(key).trim().toUpperCase()))];
  if (!selectedKeys.length || selectedKeys.some(key => !keyPattern.test(key))) {
    throw new JiraRequestError("Select valid Jira story or epic keys.", { status: 400 });
  }
  if (config.isMock) return { selectedKeys, stories: [], relationships: [], warnings: ["Jira is in mock mode. Live impact information is unavailable."] };
  const metadata = await jiraRequest(config, "/rest/api/3/field");
  const impactFields = metadata.filter(field => /^(impacted|affected) (stories|issues|work items)$/i.test(field.name?.trim() ?? ""));
  const fields = ["summary", "status", "issuetype", "issuelinks", ...impactFields.map(field => field.id)];
  const cache = new Map();
  const warnings = new Set();
  async function getIssue(key) {
    if (cache.has(key)) return cache.get(key);
    try {
      const issue = await jiraRequest(config, `/rest/api/3/issue/${encodeURIComponent(key)}?fields=${fields.join(",")}`);
      cache.set(key, issue);
      return issue;
    } catch (error) {
      if (![403, 404].includes(error.status)) throw error;
      warnings.add(`${key} could not be read from Jira; results may be incomplete.`);
      cache.set(key, null);
      return null;
    }
  }
  const roots = new Set();
  for (const key of selectedKeys) {
    const issue = await getIssue(key);
    if (!issue) continue;
    if (isStory(issue)) roots.add(key);
    else if (/^epic$/i.test(issue.fields?.issuetype?.name ?? "")) {
      const parentClauses = [`parent = "${key}"`, ...metadata.filter(field => /epic\s*link/i.test(field.name ?? "") && /^customfield_\d+$/.test(field.id))
        .map(field => `cf[${field.id.slice(12)}] = "${key}"`)];
      const children = await searchIssues(config, { jql: `(${parentClauses.join(" OR ")}) AND issuetype in ("Story", "User Story")`, fields });
      for (const child of children) { cache.set(child.key, child); roots.add(child.key); }
    } else warnings.add(`${key} is not a story or epic.`);
  }
  const queue = [...roots];
  const visited = new Set();
  const impacted = new Map();
  const relationships = new Map();
  for (let index = 0; index < queue.length; index += 1) {
    const key = queue[index];
    if (visited.has(key)) continue;
    if (visited.size >= 1000) { warnings.add("Impact traversal reached 1,000 issues; results are incomplete."); break; }
    visited.add(key);
    const issue = await getIssue(key);
    if (!issue) continue;
    const links = impactLinks(issue);
    for (const field of impactFields) {
      const value = issue.fields?.[field.id];
      const values = Array.isArray(value) ? value : value == null ? [] : [value];
      for (const item of values) {
        // Only explicit issue references qualify, never guessed keys in prose.
        const targetKey = typeof item === "string" ? item.trim() : item?.key;
        if (keyPattern.test(targetKey ?? "")) links.push({ sourceKey: key, targetKey, relationship: field.name, evidence: `Jira field: ${field.name}` });
        else warnings.add(`${key}: ${field.name} contains information that is not an issue reference; review this field in Jira.`);
      }
    }
    for (const link of links) {
      relationships.set(`${key}:${link.targetKey}:${link.relationship}`, link);
      if (!visited.has(link.targetKey)) queue.push(link.targetKey);
      const target = await getIssue(link.targetKey);
      if (target && isStory(target) && !roots.has(target.key)) impacted.set(target.key, normalizeJiraIssue(target, config.baseUrl));
    }
  }
  return { selectedKeys: [...roots], stories: [...impacted.values()], relationships: [...relationships.values()], warnings: [...warnings] };
}
