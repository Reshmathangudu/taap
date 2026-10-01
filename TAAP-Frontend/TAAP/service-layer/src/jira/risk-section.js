import { jiraRequest, JiraRequestError, readJiraConfig } from "./rest-client.js";

// Keep heading levels and table cell boundaries when converting Jira rich text.
export function normalizeRiskData(value) {
  if (typeof value === "string") return value;
  if (value == null) return "";
  if (Array.isArray(value)) return value.map(normalizeRiskData).join("\n");
  if (typeof value !== "object") return String(value);
  if (value.type === "text") return value.text ?? "";
  if (value.type === "hardBreak") return "\n";
  if (value.type === "mention") return value.attrs?.text ?? value.attrs?.id ?? "";
  if (value.type === "inlineCard") return value.attrs?.url ?? "";
  if (!value.type) return JSON.stringify(value);
  const content = (value.content ?? []).map(normalizeRiskData).join(value.type === "tableRow" ? " | " : "");
  if (value.type === "heading") return `${"#".repeat(value.attrs?.level ?? 2)} ${content}\n`;
  if (["tableCell", "tableHeader"].includes(value.type)) return content.trim();
  return ["paragraph", "heading", "listItem", "tableRow", "blockquote"].includes(value.type) ? `${content}\n` : content;
}

const riskTitle = text => /^(?:\d+[.)]\s*)?risk[\s_-]+analysis\s*:?$/i.test(text.trim());
const cleanTitle = text => text.trim().replace(/^(?:#{1,6}\s*|h[1-6]\.\s*)/, "").replace(/\*\*|__/g, "").replace(/^\*|\*$/g, "").trim();
const nextSection = text => /^(acceptance criteria|description|test plan|test cases|impact analysis|dependencies|notes|definition of done)\s*:?$/i.test(text);

export function extractRiskSection(description) {
  if (description && typeof description === "object" && !Array.isArray(description)) {
    const blocks = description.content ?? [];
    const sections = [];
    let active = false;
    let level = 6;
    for (const block of blocks) {
      const text = normalizeRiskData(block).trim();
      const inline = cleanTitle(text).match(/^(?:\d+[.)]\s*)?risk[\s_-]+analysis\s*:\s*(.*)$/i);
      if (riskTitle(cleanTitle(text)) || inline) {
        active = true;
        level = block.type === "heading" ? block.attrs?.level ?? 6 : 6;
        if (inline?.[1]) sections.push(inline[1]);
        continue;
      }
      if (active && ((block.type === "heading" && (block.attrs?.level ?? 6) <= level)
        || (block.type !== "heading" && nextSection(cleanTitle(text))))) active = false;
      if (active && text) sections.push(text);
    }
    // Some Jira descriptions use plain paragraphs rather than ADF headings.
    return sections.length ? sections.join("\n\n") : extractRiskSection(normalizeRiskData(description));
  }
  const sections = [];
  let active = false;
  let level = 6;
  for (const line of String(description ?? "").split(/\r?\n/)) {
    const heading = line.trim().match(/^(#{1,6})\s+|^h([1-6])\.\s*/);
    const headingLevel = heading ? heading[1]?.length ?? Number(heading[2]) : null;
    const title = cleanTitle(line);
    const inline = title.match(/^(?:\d+[.)]\s*)?risk[\s_-]+analysis\s*:\s*(.*)$/i);
    if (riskTitle(title) || inline) {
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

export async function fetchJiraRiskSection({ key, config = readJiraConfig() } = {}) {
  key = String(key ?? "").trim().toUpperCase();
  if (!/^[A-Z][A-Z0-9_]*-\d+$/.test(key)) throw new JiraRequestError("Select a valid Jira story.", { status: 400 });
  if (config.isMock) throw new JiraRequestError("Live Jira risk sections are unavailable in mock mode.", { status: 503 });
  const metadata = await jiraRequest(config, "/rest/api/3/field");
  const riskFields = metadata.filter(field => riskTitle(field.name ?? ""));
  const fields = ["summary", "issuetype", "description", "updated", ...riskFields.map(field => field.id)];
  const issue = await jiraRequest(config, `/rest/api/3/issue/${encodeURIComponent(key)}?fields=${fields.join(",")}`);
  if (!/^(story|user story)$/i.test(issue.fields?.issuetype?.name ?? "")) throw new JiraRequestError("Select a user story to explain its Risk Analysis section.", { status: 400 });
  const sections = riskFields.map(field => ({ source: `Jira field: ${field.name}`, text: normalizeRiskData(issue.fields[field.id]).trim() })).filter(section => section.text);
  const descriptionSection = extractRiskSection(issue.fields.description);
  if (descriptionSection) sections.push({ source: "Description: Risk Analysis", text: descriptionSection });
  return { key, summary: issue.fields.summary ?? "", updated: issue.fields.updated ?? "", url: `${config.baseUrl.replace(/\/+$/, "")}/browse/${key}`, sections };
}
