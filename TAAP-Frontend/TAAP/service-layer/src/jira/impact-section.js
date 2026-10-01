import { jiraRequest, JiraRequestError, normalizeJiraDescription, readJiraConfig } from "./rest-client.js";

const impactTitle = text => /^(?:\d+[.)]\s*)?impact[\s_-]+analysis\s*:?$/i.test(text.trim());
const cleanTitle = text => text.trim().replace(/^(?:#{1,6}\s*|h[1-6]\.\s*)/, "").replace(/\*\*|__/g, "").replace(/^\*|\*$/g, "").trim();
const nextSection = text => /^(acceptance criteria|description|test plan|test cases|risk analysis|dependencies|notes|definition of done)\s*:?$/i.test(text);

export function extractImpactSection(description) {
  if (description && typeof description === "object" && !Array.isArray(description)) {
    const blocks = description.content ?? [];
    const sections = [];
    let active = false;
    let level = 6;
    for (const block of blocks) {
      const text = normalizeJiraDescription(block);
      if (impactTitle(cleanTitle(text))) {
        active = true;
        level = block.type === "heading" ? block.attrs?.level ?? 6 : 6;
        continue;
      }
      if (active && ((block.type === "heading" && (block.attrs?.level ?? 6) <= level)
        || (block.type !== "heading" && nextSection(cleanTitle(text))))) active = false;
      if (active && text) sections.push(text);
    }
    // Some Jira descriptions use plain paragraphs rather than ADF headings.
    return sections.length ? sections.join("\n\n") : extractImpactSection(normalizeJiraDescription(description));
  }
  const sections = [];
  let active = false;
  let level = 6;
  for (const line of String(description ?? "").split(/\r?\n/)) {
    const heading = line.trim().match(/^(#{1,6})\s+|^h([1-6])\.\s*/);
    const headingLevel = heading ? heading[1]?.length ?? Number(heading[2]) : null;
    const title = cleanTitle(line);
    const inline = title.match(/^(?:\d+[.)]\s*)?impact[\s_-]+analysis\s*:\s*(.*)$/i);
    if (impactTitle(title) || inline) {
      active = true;
      level = headingLevel ?? 6;
      if (inline?.[1]) sections.push(inline[1]);
      continue;
    }
    if (active && ((headingLevel && headingLevel <= level) || (!headingLevel && nextSection(title)))) active = false;
    if (active) sections.push(line);
  }
  return sections.join("\n").trim();
}

export async function fetchJiraImpactSection({ key, config = readJiraConfig() } = {}) {
  key = String(key ?? "").trim().toUpperCase();
  if (!/^[A-Z][A-Z0-9_]*-\d+$/.test(key)) throw new JiraRequestError("Select a valid Jira story.", { status: 400 });
  if (config.isMock) throw new JiraRequestError("Live Jira impact sections are unavailable in mock mode.", { status: 503 });
  const metadata = await jiraRequest(config, "/rest/api/3/field");
  const impactFields = metadata.filter(field => impactTitle(field.name ?? ""));
  const fields = ["summary", "issuetype", "description", "updated", ...impactFields.map(field => field.id)];
  const issue = await jiraRequest(config, `/rest/api/3/issue/${encodeURIComponent(key)}?fields=${fields.join(",")}`);
  if (!/^(story|user story)$/i.test(issue.fields?.issuetype?.name ?? "")) throw new JiraRequestError("Select a user story to explain its Impact Analysis section.", { status: 400 });
  const sections = impactFields.map(field => ({ source: `Jira field: ${field.name}`, text: normalizeJiraDescription(issue.fields[field.id]) })).filter(section => section.text.trim());
  const descriptionSection = extractImpactSection(issue.fields.description);
  if (descriptionSection) sections.push({ source: "Description: Impact Analysis", text: descriptionSection });
  return { key, summary: issue.fields.summary ?? "", updated: issue.fields.updated ?? "", url: `${config.baseUrl.replace(/\/+$/, "")}/browse/${key}`, sections };
}
