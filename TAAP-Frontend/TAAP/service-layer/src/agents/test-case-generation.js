const DEFAULT_AGENT_BASE_URL = "http://127.0.0.1:8001";

export class AgentRequestError extends Error {
  constructor(message, { status, details } = {}) {
    super(message);
    this.name = "AgentRequestError";
    this.status = status;
    this.details = details;
  }
}

export function readTestCaseAgentConfig(env = process.env) {
  return {
    baseUrl: cleanUrl(env.TAAP_TEST_CASE_AGENT_URL || env.VITE_TAAP_TEST_CASE_AGENT_URL || DEFAULT_AGENT_BASE_URL),
    timeoutMs: readPositiveInteger(env.TAAP_TEST_CASE_AGENT_TIMEOUT_MS, 120000)
  };
}

export async function generateTestCasesFromRequirements({ requirements, config = readTestCaseAgentConfig(), now = new Date() } = {}) {
  const stories = flattenRequirementsToStories(requirements);

  if (!stories.length) {
    throw new AgentRequestError("Select at least one Jira story with acceptance criteria.", { status: 400 });
  }

  const agentCard = await fetchAgentCard(config);
  const results = [];

  for (const story of stories) {
    const context = buildAgentContext(story);
    const result = await callA2AAgent(context, { ...config, agentCard });
    results.push(result);
  }

  return {
    source: "a2a",
    agent: {
      name: agentCard.name || "test_case_generation_agent",
      description: agentCard.description || "",
      version: agentCard.version || "",
      cardUrl: `${config.baseUrl}/.well-known/agent-card.json`
    },
    selectedKeys: stories.map((story) => story.key),
    results,
    cases: results.flatMap((result) => normalizeGeneratedCases(result, agentCard, now))
  };
}

export async function generateTestCasesForRequirements(requirements, { signal } = {}) {
  return fetchFromServiceLayer("/api/agents/test-cases/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ requirements }),
    signal
  });
}

function flattenRequirementsToStories(requirements = []) {
  const seen = new Set();
  const stories = [];

  for (const requirement of Array.isArray(requirements) ? requirements : []) {
    const children = Array.isArray(requirement?.children) ? requirement.children : [];
    const candidates = /^epic$/i.test(requirement?.type ?? "") && children.length ? children.map((child) => ({
      ...child,
      epicKey: requirement.key
    })) : [requirement];

    for (const candidate of candidates) {
      const key = String(candidate?.key ?? "").trim();

      if (!key || seen.has(key)) {
        continue;
      }

      seen.add(key);
      stories.push(candidate);
    }
  }

  return stories;
}

function buildAgentContext(story) {
  const acceptanceCriteria = normalizeAcceptanceCriteria(story.acceptanceCriteria);

  return {
    epic_key: stringOrNull(story.epicKey || story.parentKey),
    story_key: String(story.key ?? ""),
    summary: String(story.summary ?? "Untitled Jira story"),
    description: String(story.description || story.summary || ""),
    priority: stringOrNull(story.priority),
    acceptance_criteria: acceptanceCriteria,
    business_rules: normalizeStringList(story.businessRules),
    existing_test_cases: normalizeExistingTestCases(story.existingTestCases),
    linked_defects: normalizeStringList(story.linkedDefects),
    related_issues: normalizeStringList(story.relatedIssues)
  };
}

function normalizeAcceptanceCriteria(criteria) {
  const normalized = normalizeStringList(criteria).map((text, index) => ({
    id: `AC-${index + 1}`,
    text
  }));

  return normalized.length ? normalized : [{ id: "AC-1", text: "Validate the requirement behavior described by the story." }];
}

function normalizeExistingTestCases(cases) {
  return Array.isArray(cases) ? cases.map((testCase) => ({
    test_case_id: String(testCase.test_case_id || testCase.id || ""),
    title: String(testCase.title || ""),
    preconditions: normalizeStringList(testCase.preconditions),
    test_data: testCase.test_data && typeof testCase.test_data === "object" && !Array.isArray(testCase.test_data) ? testCase.test_data : {},
    steps: Array.isArray(testCase.steps) ? testCase.steps.map((step, index) => ({
      step_number: Number(step.step_number || index + 1),
      action: String(step.action || step),
      expected_result: String(step.expected_result || "")
    })) : [],
    expected_result: testCase.expected_result ? String(testCase.expected_result) : null,
    mapped_acceptance_criteria: normalizeStringList(testCase.mapped_acceptance_criteria)
  })).filter((testCase) => testCase.test_case_id || testCase.title) : [];
}

async function fetchAgentCard(config) {
  const response = await fetchWithTimeout(`${config.baseUrl}/.well-known/agent-card.json`, {
    headers: { Accept: "application/json" },
    timeoutMs: Math.min(config.timeoutMs, 10000)
  });
  const payload = await readJsonResponse(response);

  if (!response.ok) {
    throw new AgentRequestError(`Agent card request failed with ${response.status}.`, {
      status: response.status,
      details: payload
    });
  }

  return payload;
}

async function callA2AAgent(jiraContext, config) {
  const endpoint = resolveJsonRpcEndpoint(config.agentCard, config.baseUrl);
  const methods = ["message/send", "tasks/send", "SendMessage"];
  let lastMethodError = null;
  let payload = null;

  for (const methodName of methods) {
    const response = await fetchWithTimeout(endpoint, {
      method: "POST",
      headers: {
        "A2A-Version": "1.0",
        Accept: "application/json",
        "Content-Type": "application/json"
      },
      body: JSON.stringify(buildA2AEnvelope(methodName, jiraContext)),
      timeoutMs: config.timeoutMs
    });
    payload = await readJsonResponse(response);

    if (!response.ok) {
      throw new AgentRequestError(`A2A request failed with ${response.status}.`, {
        status: response.status,
        details: payload
      });
    }

    if (!isMethodNotFound(payload)) {
      break;
    }

    lastMethodError = payload.error;
    payload = null;
  }

  if (!payload) {
    throw new AgentRequestError(`A2A method not found: ${lastMethodError?.message || "No supported JSON-RPC send method was accepted."}`, {
      status: 502,
      details: lastMethodError
    });
  }

  if (payload.error) {
    throw new AgentRequestError(`A2A error ${payload.error.code}: ${payload.error.message}`, {
      status: 502,
      details: payload.error
    });
  }

  const task = payload.result?.task ?? payload.result;
  const state = task?.status?.state ?? "";

  if (/FAILED/i.test(state)) {
    throw new AgentRequestError(`Agent task failed: ${extractText(task.status?.message) || "No failure message returned."}`, {
      status: 502,
      details: task.status
    });
  }

  const resultText = extractText(task?.artifacts?.[0]) || extractText(task?.status?.message) || extractText(task);

  if (!resultText) {
    throw new AgentRequestError("Agent returned no generated test-case artifact.", {
      status: 502,
      details: payload
    });
  }

  try {
    return JSON.parse(resultText);
  } catch (error) {
    throw new AgentRequestError("Agent returned a non-JSON test-case artifact.", {
      status: 502,
      details: error instanceof Error ? error.message : String(error)
    });
  }
}

function buildA2AEnvelope(method, jiraContext) {
  const text = JSON.stringify(jiraContext);
  const messageId = randomId();

  if (method === "SendMessage") {
    return {
      jsonrpc: "2.0",
      id: randomId(),
      method,
      params: {
        message: {
          messageId,
          role: "ROLE_USER",
          parts: [{ text }]
        }
      }
    };
  }

  return {
    jsonrpc: "2.0",
    id: randomId(),
    method,
    params: {
      message: {
        messageId,
        role: "user",
        parts: [{ kind: "text", text }]
      }
    }
  };
}

function isMethodNotFound(payload) {
  return payload?.error?.code === -32601;
}

function normalizeGeneratedCases(result, agentCard, now) {
  return (Array.isArray(result.generated_test_cases) ? result.generated_test_cases : []).map((testCase) => ({
    id: testCase.generated_test_id,
    title: testCase.title,
    description: testCase.objective,
    type: titleCase(testCase.test_type),
    priority: titleCase(testCase.priority),
    automation: "Candidate",
    review: "Pending Review",
    requirement: testCase.story_key || result.story_key,
    updated: now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    owner: agentCard.name || "Test Design Agent",
    source: "a2a",
    generatedDetails: {
      ...testCase,
      requirementSummary: result.requirement_summary,
      coverageAnalysis: result.coverage_analysis ?? [],
      clarificationsRequired: result.clarifications_required ?? [],
      generationSummary: result.generation_summary ?? ""
    }
  }));
}

function resolveJsonRpcEndpoint(agentCard, fallbackBaseUrl) {
  const supported = Array.isArray(agentCard?.supportedInterfaces) ? agentCard.supportedInterfaces : [];
  const jsonRpc = supported.find((item) => /jsonrpc/i.test(item?.protocolBinding ?? ""));
  return cleanUrl(jsonRpc?.url || fallbackBaseUrl);
}

function extractText(container) {
  if (!container) return "";
  if (typeof container === "string") return container;
  if (typeof container.text === "string") return container.text;

  const parts = Array.isArray(container.parts) ? container.parts : [];
  return parts.map((part) => typeof part?.text === "string" ? part.text : "").find(Boolean) || "";
}

async function fetchWithTimeout(url, { timeoutMs, ...options } = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs ?? 120000);

  try {
    return await fetch(url, {
      ...options,
      signal: options.signal ?? controller.signal
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw new AgentRequestError("Test-case agent request timed out.", { status: 504 });
    }

    throw new AgentRequestError("Test-case agent is unavailable.", {
      status: 502,
      details: error instanceof Error ? error.message : String(error)
    });
  } finally {
    clearTimeout(timeout);
  }
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) return {};

  try {
    return JSON.parse(text);
  } catch {
    return { text };
  }
}

async function fetchFromServiceLayer(path, options = {}) {
  if (typeof fetch !== "function") {
    throw new Error("Fetch API is not available in this runtime.");
  }

  const response = await fetch(`${serviceLayerBaseUrl()}${path}`, options);
  const payload = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(payload.error || `Service layer request failed: ${response.status}`);
  }

  return payload;
}

function serviceLayerBaseUrl() {
  if (typeof window !== "undefined") {
    return "";
  }

  return cleanUrl(process.env.TAAP_SERVICE_URL || "http://127.0.0.1:8787");
}

function normalizeStringList(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value.flatMap(normalizeStringList);
  return [String(value).trim()].filter(Boolean);
}

function titleCase(value) {
  return String(value || "Not provided").toLowerCase().replace(/(^|[_\s-])\w/g, (match) => match.toUpperCase()).replaceAll("_", " ");
}

function stringOrNull(value) {
  const normalized = String(value ?? "").trim();
  return normalized || null;
}

function randomId() {
  return globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function cleanUrl(value) {
  return String(value ?? "").trim().replace(/\/+$/, "");
}

function readPositiveInteger(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ""), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}
