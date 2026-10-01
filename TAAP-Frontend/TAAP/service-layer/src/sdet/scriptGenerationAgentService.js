const OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses";
const DEFAULT_MODEL = "gpt-5";

function normalize(value) {
  return String(value ?? "").trim();
}

function toCamelCase(value, fallback) {
  const words = normalize(value).replace(/[^a-zA-Z0-9]+/g, " ").trim().split(/\s+/).filter(Boolean);
  if (!words.length) return fallback;
  return words.map((word, index) => {
    const lower = word.toLowerCase();
    return index === 0 ? lower : `${lower.charAt(0).toUpperCase()}${lower.slice(1)}`;
  }).join("");
}

function escapeRegExp(value) {
  return String(value).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function flattenIssues(issueGroups) {
  return Object.values(issueGroups?.groups ?? {}).flatMap((group) => group.issues ?? []);
}

function findJiraIssue(testCase, issueGroups) {
  if (testCase?.jiraDetails) return testCase.jiraDetails;
  const issues = flattenIssues(issueGroups);
  return issues.find((issue) => issue.key === testCase?.jiraKey || issue.key === testCase?.requirement || issue.testCaseId === testCase?.id || issue.key === testCase?.id) ?? null;
}

function compactIssue(issue) {
  if (!issue) return null;
  return {
    key: issue.key || "",
    type: issue.type || "",
    summary: issue.summary || "",
    description: issue.description || "",
    status: issue.status || "",
    priority: issue.priority || "",
    labels: issue.labels || [],
    parentKey: issue.parentKey || "",
    parentTitle: issue.parentTitle || "",
    requirementId: issue.requirementId || "",
    testCaseId: issue.testCaseId || "",
    testName: issue.testName || "",
    testType: issue.testType || "",
    testStatus: issue.testStatus || "",
    automationStatus: issue.automationStatus || "",
    businessPriority: issue.businessPriority || "",
    executionMinutes: issue.executionMinutes || "",
    environment: issue.environment || "",
    testPhase: issue.testPhase || "",
    url: issue.url || ""
  };
}

function buildAgentInput(testCases, issueGroups) {
  return testCases.map((testCase) => {
    const jiraIssue = findJiraIssue(testCase, issueGroups);
    return {
      selectedTestCase: {
        id: testCase.id || "",
        title: testCase.title || "",
        description: testCase.description || "",
        type: testCase.type || "",
        priority: testCase.priority || "",
        automation: testCase.automation || "",
        review: testCase.review || "",
        requirement: testCase.requirement || "",
        storyKey: testCase.storyKey || "",
        storySummary: testCase.storySummary || "",
        jiraKey: testCase.jiraKey || ""
      },
      jiraIssue: compactIssue(jiraIssue)
    };
  });
}

function buildPrompt(agentInput) {
  return [
    {
      role: "system",
      content: [
        {
          type: "input_text",
          text: [
            "You are an SDET BDD feature generation agent.",
            "Generate one high-quality Gherkin feature script for each selected Jira test case.",
            "Use only the information present in the provided test case and Jira issue. Do not invent URLs, locators, application screens, credentials, extra scenarios, or business rules.",
            "If the Jira test case has steps, preserve the same flow but rewrite it into clean Given/When/Then wording.",
            "If test data is present, use Scenario Outline with an Examples table. Use only the provided test data values.",
            "If preconditions are present, place them in Background.",
            "If expected results are present, place them as Then/And assertions.",
            "Keep wording simple and business-readable.",
            "Return strict JSON only."
          ].join(" ")
        }
      ]
    },
    {
      role: "user",
      content: [
        {
          type: "input_text",
          text: JSON.stringify({
            outputContract: {
              drafts: [
                {
                  testCaseId: "string",
                  jiraKey: "string",
                  requirementKey: "string",
                  story: "string",
                  title: "string",
                  fileName: "string.feature",
                  featureScript: "complete Gherkin feature file text",
                  notes: "short note about the Jira sections used",
                  missing: ["important missing Jira information only"]
                }
              ]
            },
            testCases: agentInput
          }, null, 2)
        }
      ]
    }
  ];
}

function parseJsonOutput(text) {
  const trimmed = normalize(text);
  if (!trimmed) throw new Error("OpenAI returned an empty response.");

  try {
    return JSON.parse(trimmed);
  } catch {
    const match = trimmed.match(/\{[\s\S]*\}/);
    if (!match) throw new Error("OpenAI response did not contain JSON.");
    return JSON.parse(match[0]);
  }
}

function outputTextFromResponse(payload) {
  if (typeof payload?.output_text === "string") return payload.output_text;
  const chunks = [];
  for (const item of payload?.output ?? []) {
    for (const content of item.content ?? []) {
      if (typeof content.text === "string") chunks.push(content.text);
    }
  }
  return chunks.join("\n");
}

function normalizeDraft(draft, fallbackInput) {
  const selected = fallbackInput.selectedTestCase;
  const jira = fallbackInput.jiraIssue ?? {};
  const title = normalize(draft.title) || selected.title || jira.testName || jira.summary || "Generated feature";
  const testCaseId = normalize(draft.testCaseId) || selected.id || jira.testCaseId || jira.key || "";
  const jiraKey = normalize(draft.jiraKey) || selected.jiraKey || jira.key || "";
  const requirementKey = normalize(draft.requirementKey) || selected.requirement || jira.requirementId || "";
  const featureScript = normalizeFeatureScript(normalize(draft.featureScript), {
    testCaseId,
    jiraKey,
    requirementKey,
    testType: selected.type || jira.testType || "",
    automationStatus: selected.automation || jira.automationStatus || ""
  });

  if (!featureScript) {
    throw new Error(`OpenAI did not return a feature script for ${testCaseId || jiraKey || title}.`);
  }

  return {
    testCaseId,
    jiraKey,
    requirementKey,
    story: normalize(draft.story) || selected.storySummary || jira.parentTitle || jira.parentKey || "",
    title,
    fileName: normalize(draft.fileName) || `${title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "generated-feature"}.feature`,
    featureScript,
    notes: normalize(draft.notes),
    missing: Array.isArray(draft.missing) ? draft.missing.map(normalize).filter(Boolean) : []
  };
}

function tagValue(value) {
  const tag = normalize(value).replace(/[^a-zA-Z0-9]+/g, "");
  return tag ? `@${tag}` : "";
}

function normalizeFeatureScript(script, context) {
  if (!script) return "";
  const lines = script.split(/\r?\n/);
  const headerIndex = lines.findIndex((line) => /^\s*\|.*\|\s*$/.test(line));
  let normalized = script;

  if (headerIndex >= 0) {
    const headers = lines[headerIndex]
      .split("|")
      .slice(1, -1)
      .map((header) => header.trim());

    for (const header of headers) {
      const clean = toCamelCase(header, header);
      if (!header || clean === header) continue;
      normalized = normalized.replaceAll(`<${header}>`, `<${clean}>`);
      const headerPattern = new RegExp(`(\\|\\s*)${escapeRegExp(header)}(\\s*(?=\\|))`, "g");
      normalized = normalized.replace(headerPattern, `$1${clean}$2`);
    }
  }

  if (!normalized.trimStart().startsWith("@")) {
    const tags = [
      tagValue(context.testCaseId),
      tagValue(context.requirementKey),
      tagValue(context.jiraKey),
      tagValue(context.testType),
      tagValue(context.automationStatus)
    ].filter(Boolean).join(" ");
    if (tags) normalized = `${tags}\n${normalized}`;
  }

  return normalized;
}

export class ScriptGenerationAgentError extends Error {
  constructor(message, details = undefined) {
    super(message);
    this.name = "ScriptGenerationAgentError";
    this.details = details;
  }
}

export async function generateFeatureScriptsWithOpenAI({ testCases = [], issueGroups = null } = {}) {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new ScriptGenerationAgentError("OPENAI_API_KEY is not configured.");
  }

  const cases = Array.isArray(testCases) ? testCases.filter(Boolean) : [];
  if (!cases.length) {
    return { source: "openai", model: process.env.OPENAI_MODEL || DEFAULT_MODEL, drafts: [] };
  }

  const model = process.env.OPENAI_MODEL || DEFAULT_MODEL;
  const agentInput = buildAgentInput(cases, issueGroups);
  const response = await fetch(OPENAI_RESPONSES_URL, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model,
      input: buildPrompt(agentInput),
      text: {
        format: {
          type: "json_object"
        }
      }
    })
  });

  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new ScriptGenerationAgentError(payload.error?.message || `OpenAI request failed with ${response.status}.`, payload.error);
  }

  const parsed = parseJsonOutput(outputTextFromResponse(payload));
  const rawDrafts = Array.isArray(parsed?.drafts) ? parsed.drafts : [];

  return {
    source: "openai",
    model,
    generatedAt: new Date().toISOString(),
    drafts: rawDrafts.map((draft, index) => normalizeDraft(draft, agentInput[index] ?? agentInput[0]))
  };
}
