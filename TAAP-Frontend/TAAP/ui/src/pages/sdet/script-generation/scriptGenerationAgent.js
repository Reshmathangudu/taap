import { fetchJiraIssueGroups, generateSdetFeatureScripts } from "@taap/service-layer";

export const GENERATED_SCRIPT_STORAGE_KEY = "sdet:generatedScriptDrafts";
const DEFAULT_AGENT_PROMPT = [
  "Analyze each selected Jira test case independently.",
  "Use the test case summary, description, linked requirement, story summary, labels, type, priority, status, and any available custom fields.",
  "Extract structured sections from the Jira description when present: Objective, Preconditions, Test Data, Steps, and Expected Result.",
  "Generate an informative script draft for the scenario described by the test case without assuming a specific domain.",
  "Do not invent concrete data values when Jira does not provide them; mark those values as required review gaps.",
  "Keep the output traceable to the Jira test case and linked requirement/story."
].join(" ");

const DESCRIPTION_LABELS = [
  "Test Case ID",
  "Title",
  "Linked User Story",
  "Linked Requirement",
  "Objective",
  "Preconditions",
  "Precondition",
  "Test Data",
  "Steps",
  "Test Steps",
  "Expected Result",
  "Expected Results",
  "Acceptance Criteria",
  "User Type",
  "Current Daily Limit",
  "New Daily Limit",
  "Minimum Allowed Limit",
  "Maximum Allowed Limit",
  "Currency"
];

function flattenIssues(issueGroups) {
  return Object.values(issueGroups?.groups ?? {}).flatMap((group) => group.issues ?? []);
}

function normalize(value) {
  return String(value ?? "").trim();
}

function slugify(value) {
  return normalize(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 70) || "generated-script";
}

function firstSentence(value) {
  const text = normalize(value).replace(/\s+/g, " ");
  if (!text) return "";
  const match = text.match(/^(.+?[.!?])\s/);
  return match?.[1] ?? text;
}

function unique(items) {
  return [...new Set(items.map((item) => normalize(item)).filter(Boolean))];
}

function stripListPrefix(value) {
  return normalize(value).replace(/^[-*•]\s*/, "").replace(/^\d+[.)]\s*/, "").trim();
}

function prepareDescriptionText(description) {
  return DESCRIPTION_LABELS.reduce((text, label) => {
    const pattern = new RegExp(`\\s*(${label})\\s*:`, "gi");
    return text.replace(pattern, "\n$1:");
  }, String(description ?? "")).trim();
}

function splitCompactSentences(value) {
  return normalize(value)
    .replace(/([a-z0-9])\.([A-Z])/g, "$1.\n$2")
    .split(/\r?\n/)
    .map((item) => stripListPrefix(item).replace(/\.$/, "").trim())
    .filter(Boolean);
}

function sectionKey(line) {
  const key = normalize(line).replace(/:$/, "").toLowerCase();
  if (/^(test case id)$/.test(key)) return "testCaseId";
  if (/^(title)$/.test(key)) return "title";
  if (/^(linked user story|user story)$/.test(key)) return "linkedUserStory";
  if (/^(linked requirement|requirement)$/.test(key)) return "linkedRequirement";
  if (/^(objective|purpose)$/.test(key)) return "objective";
  if (/^(preconditions?|setup)$/.test(key)) return "preconditions";
  if (/^(test data|data|input data|inputs?)$/.test(key)) return "testData";
  if (/^(steps?|test steps?|actions?)$/.test(key)) return "steps";
  if (/^(expected results?|expected behaviour|expected behavior|assertions?)$/.test(key)) return "expected";
  if (/^(acceptance criteria|ac)$/.test(key)) return "acceptanceCriteria";
  return "";
}

function parseDescriptionSections(description) {
  const sections = {
    testCaseId: [],
    title: [],
    linkedUserStory: [],
    linkedRequirement: [],
    objective: [],
    preconditions: [],
    testData: [],
    steps: [],
    expected: [],
    acceptanceCriteria: [],
    notes: []
  };
  let current = "notes";

  function addToCurrent(value) {
    const items = ["preconditions", "steps", "expected", "acceptanceCriteria"].includes(current)
      ? splitCompactSentences(value)
      : [stripListPrefix(value)].filter(Boolean);
    sections[current].push(...items);
  }

  for (const rawLine of prepareDescriptionText(description).split(/\r?\n/)) {
    const line = normalize(rawLine);
    if (!line) continue;

    const heading = sectionKey(line);
    if (heading) {
      current = heading;
      continue;
    }

    const inlineHeading = line.match(/^([A-Za-z ]{2,40})\s*:\s*(.+)$/);
    const inlineKey = inlineHeading ? sectionKey(inlineHeading[1]) : "";
    if (inlineKey) {
      current = inlineKey;
      addToCurrent(inlineHeading[2]);
      continue;
    }

    addToCurrent(line);
  }

  return sections;
}

function splitNameValue(value, fallbackName) {
  const text = stripListPrefix(value);
  const match = text.match(/^([^:=\-]+)\s*[:=\-]\s*(.+)$/);
  if (!match) return { name: fallbackName, value: text, description: text };
  return {
    name: slugify(match[1]).replaceAll("-", "_") || fallbackName,
    value: match[2].trim(),
    description: `${match[1].trim()}: ${match[2].trim()}`
  };
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

function findJiraIssue(testCase, issueGroups) {
  if (testCase.jiraDetails) return testCase.jiraDetails;
  const issues = flattenIssues(issueGroups);
  return issues.find((issue) => issue.key === testCase.jiraKey || issue.key === testCase.requirement || issue.key === testCase.id) ?? null;
}

function inferLayer(testCase, jiraIssue) {
  const haystack = `${testCase.title} ${testCase.type} ${jiraIssue?.summary ?? ""} ${jiraIssue?.description ?? ""}`.toLowerCase();
  if (haystack.includes("api") || haystack.includes("endpoint") || haystack.includes("payload")) return "API";
  if (haystack.includes("integration") || haystack.includes("order to cash")) return "End to end";
  return "UI";
}

function inferSuite(testCase, jiraIssue) {
  const labels = Array.isArray(jiraIssue?.labels) ? jiraIssue.labels : [];
  const haystack = `${testCase.title} ${testCase.storySummary ?? ""} ${jiraIssue?.summary ?? ""} ${labels.join(" ")}`.toLowerCase();
  if (labels.length) return `${labels[0]} Suite`;
  if (haystack.includes("api")) return "API Suite";
  if (haystack.includes("regression")) return "Regression Suite";
  if (haystack.includes("smoke")) return "Smoke Suite";
  return "Regression Suite";
}

function inferTags(testCase, jiraIssue) {
  const labels = Array.isArray(jiraIssue?.labels) ? jiraIssue.labels : [];
  const words = `${testCase.title} ${testCase.storySummary ?? ""} ${jiraIssue?.summary ?? ""}`.toLowerCase();
  const tags = new Set(labels.map((label) => String(label).toLowerCase()));

  words.split(/[^a-z0-9]+/).filter((word) => word.length >= 4 && word.length <= 18).slice(0, 4).forEach((word) => tags.add(word));
  if (testCase.type) tags.add(String(testCase.type).toLowerCase().replace(/\s+/g, "-"));

  return [...tags].filter(Boolean).slice(0, 6);
}

function inferPreconditions(testCase, jiraIssue, parsed) {
  const fromDescription = parsed.preconditions.length ? parsed.preconditions : [];
  return unique([
    ...fromDescription,
    "Target environment is available",
    testCase.requirement && testCase.requirement !== "Not linked" ? `Linked requirement ${testCase.requirement} is available` : "Linked requirement is available",
    testCase.storySummary ? `User story context is ${testCase.storySummary}` : ""
  ]);
}

function inferTestDataRequirements(testCase, jiraIssue, parsed) {
  if (parsed.testData.length > 0) {
    return parsed.testData.map((item, index) => {
      const parsedItem = splitNameValue(item, `data_${index + 1}`);
      return {
        name: parsedItem.name,
        description: parsedItem.description,
        value: parsedItem.value,
        required: true,
        available: true
      };
    });
  }

  return [{
    name: "scenarioData",
    description: "Input data needed to validate the Jira test case; add values in Jira description under Test Data.",
    value: "",
    required: true,
    available: false
  }];
}

function featureTestData(parsed) {
  return parsed.testData.map((item, index) => {
    const parts = splitNameValue(item, `data_${index + 1}`);
    const rawName = parts.description.includes(":") ? parts.description.split(":")[0] : parts.name;
    return {
      name: toCamelCase(rawName, `data${index + 1}`),
      label: rawName.trim(),
      value: parts.value
    };
  }).filter((item) => item.value);
}

function tagValue(value) {
  const tag = normalize(value).replace(/[^a-zA-Z0-9]+/g, "");
  return tag ? `@${tag}` : "";
}

function replaceFeatureData(value, data) {
  return data.reduce((text, item) => {
    if (!item.value) return text;
    return text.replace(new RegExp(escapeRegExp(item.value), "g"), `<${item.name}>`);
  }, normalize(value));
}

function lowerFirst(value) {
  const text = normalize(value);
  return text ? `${text.charAt(0).toLowerCase()}${text.slice(1)}` : "";
}

function asUserStep(value, data) {
  const text = replaceFeatureData(value, data).replace(/\.$/, "");
  const replacements = [
    [/^Navigate to\s+/i, "the user navigates to "],
    [/^View\s+/i, "the user views "],
    [/^Enter\s+/i, "the user enters "],
    [/^Submit\s+/i, "the user submits "],
    [/^Verify\s+/i, "the user verifies "],
    [/^Click\s+/i, "the user clicks "],
    [/^Select\s+/i, "the user selects "],
    [/^Update\s+/i, "the user updates "]
  ];

  const matched = replacements.find(([pattern]) => pattern.test(text));
  if (matched) return text.replace(matched[0], matched[1]);
  return lowerFirst(text);
}

function asExpectedStep(value, data) {
  const text = lowerFirst(replaceFeatureData(value, data).replace(/\.$/, ""));
  if (/^(user|system|current|daily|updated|new)\b/.test(text)) return `the ${text}`;
  if (/^success\b/.test(text)) return `a ${text}`;
  return text;
}

function tableRow(values, widths) {
  return `      | ${values.map((value, index) => String(value).padEnd(widths[index], " ")).join(" | ")} |`;
}

function examplesTable(data) {
  if (!data.length) return "";
  const headers = data.map((item) => item.name);
  const values = data.map((item) => item.value);
  const widths = headers.map((header, index) => Math.max(header.length, values[index].length));
  return [
    "",
    "    Examples:",
    tableRow(headers, widths),
    tableRow(values, widths)
  ].join("\n");
}

function buildFeatureScript({ testCase, jiraIssue, parsed }) {
  const data = featureTestData(parsed);
  const testCaseId = parsed.testCaseId[0] || testCase.id || jiraIssue?.testCaseId || jiraIssue?.key || "";
  const requirement = parsed.linkedRequirement[0] || testCase.requirement || jiraIssue?.requirementId || "";
  const story = parsed.linkedUserStory[0] || jiraIssue?.parentTitle || testCase.storySummary || "";
  const jiraKey = jiraIssue?.key || testCase.jiraKey || "";
  const title = parsed.title[0] || testCase.title || jiraIssue?.summary || "Generated feature";
  const tags = unique([
    tagValue(testCaseId),
    tagValue(requirement),
    tagValue(jiraKey),
    tagValue(testCase.type || jiraIssue?.testType),
    tagValue(testCase.automation || jiraIssue?.automationStatus)
  ]).join(" ");
  const lines = [];

  if (tags) lines.push(tags);
  lines.push(`Feature: ${title}`, "");

  if (jiraKey || testCaseId) lines.push(`  # Source: Jira test case ${[jiraKey, testCaseId].filter(Boolean).join(" / ")}`);
  if (requirement) lines.push(`  # Requirement: ${requirement}`);
  if (story) lines.push(`  # Story: ${story}`);
  if (jiraKey || testCaseId || requirement || story) lines.push("");

  if (parsed.preconditions.length) {
    lines.push("  Background:");
    parsed.preconditions.forEach((item, index) => {
      const keyword = index === 0 ? "Given" : "And";
      lines.push(`    ${keyword} ${asExpectedStep(item, data)}`);
    });
    lines.push("");
  }

  const scenarioKeyword = data.length ? "Scenario Outline" : "Scenario";
  lines.push(`  ${scenarioKeyword}: ${title}`);

  if (parsed.steps.length) {
    parsed.steps.forEach((item, index) => {
      const keyword = index === 0 ? "When" : "And";
      lines.push(`    ${keyword} ${asUserStep(item, data)}`);
    });
  }

  if (parsed.expected.length) {
    parsed.expected.forEach((item, index) => {
      const keyword = index === 0 ? "Then" : "And";
      lines.push(`    ${keyword} ${asExpectedStep(item, data)}`);
    });
  }

  const feature = `${lines.join("\n")}${examplesTable(data)}`;
  return {
    fileName: `${slugify(title)}.feature`,
    language: "Gherkin",
    framework: "BDD",
    content: feature,
    data,
    sectionsUsed: {
      preconditions: parsed.preconditions.length,
      testData: parsed.testData.length,
      steps: parsed.steps.length,
      expectedResults: parsed.expected.length
    }
  };
}

function getExpectedText(parsed) {
  return unique([...parsed.expected, ...parsed.acceptanceCriteria]).join(" ");
}

function cleanTargetPhrase(step) {
  const text = stripListPrefix(step)
    .replace(/\b(user|tester|qa|system)\b\s*/gi, "")
    .replace(/\b(should|shall|must|can)\b\s*/gi, "")
    .replace(/^(open|navigate to|go to|access|launch|login|log in|sign in|enter|fill|provide|input|select|choose|configure|set|update|change|modify|click|tap|submit|save|apply|continue|verify|validate|check|ensure|confirm|assert)\b\s*/i, "")
    .replace(/^(the|a|an)\s+/i, "")
    .trim();

  return text || "";
}

function inferStepType(step, index, total) {
  const lower = stripListPrefix(step).toLowerCase();
  if (/\b(api|endpoint|request|response|payload|status code)\b/.test(lower)) return "api";
  if (/\b(login|log in|sign in|authenticate)\b/.test(lower)) return "auth";
  if (/\b(open|navigate|go to|access|launch)\b/.test(lower)) return "navigate";
  if (/\b(enter|fill|provide|input|select|choose)\b/.test(lower)) return "data-entry";
  if (/\b(configure|set|update|change|modify)\b/.test(lower)) return "configure";
  if (/\b(click|tap|submit|save|apply|continue|confirm)\b/.test(lower)) return "submit";
  if (/\b(verify|validate|check|ensure|assert)\b/.test(lower)) return "validate";
  if (index === 0) return "prepare";
  if (index === total - 1) return "validate";
  return "execute";
}

function buildGeneratedInstruction({ type, step, title }) {
  const target = cleanTargetPhrase(step);
  const scenario = title || "the selected test case";

  switch (type) {
    case "api":
      return {
        action: "Send service request",
        instruction: `Prepare and send the required request for ${scenario}.`,
        expectedResult: "Service response is successful and matches the expected business rule."
      };
    case "auth":
      return {
        action: "Authenticate test user",
        instruction: "Sign in with an authorised user that can perform this scenario.",
        expectedResult: "User session is active and the required application area is accessible."
      };
    case "navigate":
      return {
        action: "Open scenario context",
        instruction: `Navigate to the application area needed for ${scenario}.`,
        expectedResult: "Required page, module, or service context is available."
      };
    case "data-entry":
      return {
        action: "Populate required input",
        instruction: `Enter or select the required value${target ? ` for ${target}` : ""} using the test data.`,
        expectedResult: "Input is accepted without validation errors."
      };
    case "configure":
      return {
        action: "Configure business value",
        instruction: `Set ${target || "the required value"} according to the test data and requirement.`,
        expectedResult: "Configured value is retained for validation."
      };
    case "submit":
      return {
        action: "Submit the change",
        instruction: `Trigger the control that applies or saves ${target || "the scenario changes"}.`,
        expectedResult: "System processes the action successfully."
      };
    case "validate":
      return {
        action: "Validate expected outcome",
        instruction: `Verify ${target || "the final business outcome"} against the expected result.`,
        expectedResult: "Actual result matches the expected behaviour."
      };
    case "prepare":
      return {
        action: "Prepare scenario",
        instruction: `Set up the user, environment, and data needed for ${scenario}.`,
        expectedResult: "Scenario is ready for execution."
      };
    default:
      return {
        action: "Execute scenario action",
        instruction: `Perform the next business action required for ${scenario}.`,
        expectedResult: "Action completes and the scenario can continue."
      };
  }
}

function buildSteps(testCase, jiraIssue, parsed) {
  const title = testCase.title ?? "Validate selected test case";
  const expected = getExpectedText(parsed);

  if (parsed.steps.length > 0) {
    return parsed.steps.map((step, index) => {
      const type = inferStepType(step, index, parsed.steps.length);
      const generated = buildGeneratedInstruction({ type, step, title });
      return {
        stepNo: index + 1,
        type,
        action: generated.action,
        instruction: generated.instruction,
        input: parsed.testData[index] ?? "",
        expectedResult: expected || generated.expectedResult,
        source: "jira-description",
        sourceStep: stripListPrefix(step)
      };
    });
  }

  return [
    {
      stepNo: 1,
      type: "prepare",
      action: "Prepare scenario",
      instruction: `Set up the user, environment, and data needed for ${title}.`,
      input: jiraIssue?.key ?? testCase.requirement ?? "",
      expectedResult: "Required preconditions and data are available.",
      source: "agent-inference"
    },
    {
      stepNo: 2,
      type: "execute",
      action: "Execute test scenario",
      instruction: `Perform the business behaviour described by ${testCase.id}.`,
      input: firstSentence(jiraIssue?.description) || title,
      expectedResult: expected || "Application behaviour follows the linked requirement or story acceptance criteria.",
      source: jiraIssue?.description ? "jira-description" : "test-case-title"
    },
    {
      stepNo: 3,
      type: "validate",
      action: "Capture validation evidence",
      instruction: "Record the actual result, execution evidence, and defect reference if validation fails.",
      input: "",
      expectedResult: "Execution result is ready for review.",
      source: "agent-inference"
    }
  ];
}

function buildReadiness(testCase, jiraIssue, testDataRequirements, parsed) {
  const missing = [];
  if (!jiraIssue) missing.push("Jira issue details were not found for this requirement");
  if (!normalize(jiraIssue?.description)) missing.push("Jira description or acceptance details are missing");
  if (testDataRequirements.some((item) => item.required && !item.available)) missing.push("Concrete test data values are not available");
  if (!parsed.steps.length) missing.push("Structured test steps were not found in Jira description");
  if (!parsed.expected.length && !parsed.acceptanceCriteria.length) missing.push("Expected result or acceptance criteria were not found in Jira description");
  if (testCase.review !== "Approved") missing.push("Test case is not approved yet");

  return {
    status: missing.length ? "Needs Review" : "Ready for Review",
    canBeExecuted: false,
    missing,
    checks: {
      hasTestCase: true,
      hasJiraContext: Boolean(jiraIssue),
      hasSteps: true,
      hasTestDataRequirements: testDataRequirements.length > 0,
      hasExecutionAdapter: false
    }
  };
}

function buildDraft(testCase, jiraIssue, metadata) {
  const parsed = parseDescriptionSections(jiraIssue?.description ?? testCase.description ?? "");
  const layer = inferLayer(testCase, jiraIssue);
  const suite = inferSuite(testCase, jiraIssue);
  const tags = inferTags(testCase, jiraIssue);
  const testDataRequirements = inferTestDataRequirements(testCase, jiraIssue, parsed);
  const steps = buildSteps(testCase, jiraIssue, parsed);
  const preconditions = inferPreconditions(testCase, jiraIssue, parsed);
  const scriptId = `SCR-${String(testCase.id ?? "").replace(/\D/g, "") || Date.now()}`;
  const title = parsed.title[0] || testCase.title || jiraIssue?.summary || "Generated script draft";
  const featureScript = buildFeatureScript({ testCase: { ...testCase, title }, jiraIssue, parsed });
  const objectiveSource = parsed.objective.join(" ") || firstSentence(jiraIssue?.description) || title;
  const objective = `Validate that ${objectiveSource.charAt(0).toLowerCase()}${objectiveSource.slice(1)}`;
  const expectedOutcome = getExpectedText(parsed) || "The actual result satisfies the linked Jira test case and requirement.";

  return {
    scriptId,
    scriptName: featureScript.fileName,
    title,
    status: "Draft",
    source: {
      testCaseId: testCase.id,
      testCaseTitle: testCase.title,
      jiraKey: testCase.jiraKey || jiraIssue?.key || "",
      requirementKey: testCase.requirement || jiraIssue?.requirementId || jiraIssue?.parentKey || "",
      jiraSummary: jiraIssue?.summary || "",
      generatedFrom: "Test Design"
    },
    classification: {
      testType: testCase.type || jiraIssue?.type || "Functional",
      priority: testCase.priority || jiraIssue?.priority || "Medium",
      automationLayer: layer,
      suite,
      tags,
      automationCandidate: testCase.automation === "Candidate",
      automationStatus: jiraIssue?.automationStatus || testCase.automation || "",
      reviewStatus: testCase.review || "Draft"
    },
    jiraContext: {
      key: jiraIssue?.key || testCase.jiraKey || "",
      type: jiraIssue?.type || "",
      summary: jiraIssue?.summary || "",
      description: jiraIssue?.description || "",
      status: jiraIssue?.status || "",
      priority: jiraIssue?.priority || "",
      assignee: jiraIssue?.assignee || "",
      reporter: jiraIssue?.reporter || "",
      labels: jiraIssue?.labels || [],
      parentKey: jiraIssue?.parentKey || "",
      parentTitle: jiraIssue?.parentTitle || testCase.storySummary || "",
      requirementId: jiraIssue?.requirementId || testCase.requirement || "",
      updated: jiraIssue?.updated || "",
      url: jiraIssue?.url || testCase.url || ""
    },
    objective,
    agentPrompt: DEFAULT_AGENT_PROMPT,
    extractedSections: parsed,
    featureScript,
    script: {
      format: "Structured test script",
      scenario: title,
      objective,
      preconditions,
      testData: testDataRequirements,
      procedure: steps,
      expectedOutcome
    },
    preconditions,
    testDataRequirements,
    steps,
    executionIntent: {
      environment: "QA",
      build: "",
      runMode: "Automation draft",
      estimatedDurationMinutes: Math.max(3, steps.length * 2),
      adapterRequired: true
    },
    readiness: buildReadiness(testCase, jiraIssue, testDataRequirements, parsed),
    generation: {
      generatedBy: "SDET Script Generation Agent",
      generatedAt: metadata.generatedAt,
      jiraLookup: metadata.jiraLookup,
      confidence: jiraIssue ? 0.74 : 0.48,
      notes: jiraIssue
        ? "Draft enriched with Jira issue context and current Test Design metadata."
        : "Draft generated from Test Design metadata because matching Jira details were not available."
    }
  };
}

function applyLlmFeatureDraft(localDraft, llmDraft, llmResult) {
  if (!llmDraft?.featureScript) return localDraft;

  const featureScript = {
    ...(localDraft.featureScript ?? {}),
    fileName: llmDraft.fileName || localDraft.featureScript?.fileName || localDraft.scriptName,
    language: "Gherkin",
    framework: "BDD",
    content: llmDraft.featureScript,
    source: "openai",
    notes: llmDraft.notes || "",
    missing: Array.isArray(llmDraft.missing) ? llmDraft.missing : [],
    sectionsUsed: localDraft.featureScript?.sectionsUsed ?? {}
  };

  return {
    ...localDraft,
    scriptName: featureScript.fileName,
    title: llmDraft.title || localDraft.title,
    source: {
      ...localDraft.source,
      testCaseId: llmDraft.testCaseId || localDraft.source.testCaseId,
      jiraKey: llmDraft.jiraKey || localDraft.source.jiraKey,
      requirementKey: llmDraft.requirementKey || localDraft.source.requirementKey
    },
    featureScript,
    readiness: {
      ...localDraft.readiness,
      missing: unique([...(localDraft.readiness?.missing ?? []), ...featureScript.missing])
    },
    generation: {
      ...localDraft.generation,
      generatedBy: "SDET LLM Script Generation Agent",
      model: llmResult.model || "",
      source: llmResult.source || "openai",
      generatedAt: llmResult.generatedAt || localDraft.generation.generatedAt,
      notes: featureScript.notes || "BDD feature generated by OpenAI using the selected Jira test case."
    }
  };
}

export async function generateScriptDraftsFromTestCases({ testCases, issueGroups }) {
  const cases = Array.isArray(testCases) ? testCases.filter(Boolean) : [];
  const missingJiraContext = cases.some((testCase) => !findJiraIssue(testCase, issueGroups));
  let enrichedIssueGroups = issueGroups;
  let jiraLookup = issueGroups?.source ? `Used ${issueGroups.source} issue groups already loaded in Test Design` : "No Jira data loaded";

  if (missingJiraContext) {
    try {
      enrichedIssueGroups = await fetchJiraIssueGroups({ limit: 50 });
      jiraLookup = `${enrichedIssueGroups?.source === "jira" ? "Fetched" : "Loaded"} Jira issue groups for enrichment`;
    } catch (error) {
      jiraLookup = error instanceof Error ? `Jira lookup failed: ${error.message}` : "Jira lookup failed";
    }
  }

  const generatedAt = new Date().toISOString();
  const localDrafts = cases.map((testCase) => buildDraft(testCase, findJiraIssue(testCase, enrichedIssueGroups), { generatedAt, jiraLookup }));

  try {
    const llmResult = await generateSdetFeatureScripts({ testCases: cases, issueGroups: enrichedIssueGroups });
    return localDrafts.map((draft, index) => applyLlmFeatureDraft(draft, llmResult.drafts?.[index], llmResult));
  } catch (error) {
    const note = error instanceof Error ? error.message : "LLM script generation unavailable.";
    return localDrafts.map((draft) => ({
      ...draft,
      generation: {
        ...draft.generation,
        notes: `${draft.generation.notes} LLM fallback used: ${note}`
      }
    }));
  }
}

export function saveGeneratedScriptDrafts(drafts) {
  window.sessionStorage.setItem(GENERATED_SCRIPT_STORAGE_KEY, JSON.stringify(drafts ?? []));
}

export function readGeneratedScriptDrafts() {
  try {
    const parsed = JSON.parse(window.sessionStorage.getItem(GENERATED_SCRIPT_STORAGE_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}
