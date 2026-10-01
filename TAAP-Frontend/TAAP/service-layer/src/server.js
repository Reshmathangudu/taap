import { createServer } from "node:http";
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { generateTestCasesFromRequirements, AgentRequestError } from "./agents/test-case-generation.js";
import { fetchJiraImpactAnalysis } from "./jira/impact-analysis.js";
import { fetchJiraRiskSection } from "./jira/risk-section.js";
import { fetchJiraTestCases } from "./jira/test-cases.js";
import { fetchJiraImpactSection } from "./jira/impact-section.js";
import { ScriptGenerationAgentError, generateFeatureScriptsWithOpenAI } from "./sdet/scriptGenerationAgentService.js";
import {
  JiraConfigError,
  JiraRequestError,
  fetchJiraIssueGroups,
  testJiraConnection
} from "./jira/rest-client.js";

const DEFAULT_PORT = 8787;
const ALLOWED_ORIGINS = new Set(["http://127.0.0.1:5173", "http://localhost:5173"]);

export function createServiceLayerServer() {
  return createServer(async (request, response) => {
    const requestUrl = new URL(request.url ?? "/", "http://127.0.0.1");

    if (request.method === "OPTIONS") {
      writeJson(request, response, 204, {});
      return;
    }

    try {
      if (request.method === "GET" && requestUrl.pathname === "/health") {
        writeJson(request, response, 200, { ok: true, service: "taap-service-layer" });
        return;
      }

      if (request.method === "GET" && requestUrl.pathname === "/api/jira/test-connection") {
        writeJson(request, response, 200, await testJiraConnection());
        return;
      }

      if (request.method === "GET" && requestUrl.pathname === "/api/jira/test-cases") {
        writeJson(request, response, 200, await fetchJiraTestCases({ keys: requestUrl.searchParams.getAll("key") }));
        return;
      }

      if (request.method === "POST" && requestUrl.pathname === "/api/agents/test-cases/generate") {
        const body = await readJsonBody(request);
        writeJson(request, response, 200, await generateTestCasesFromRequirements({ requirements: body.requirements }));
        return;
      }

      if (request.method === "POST" && requestUrl.pathname === "/api/sdet/script-generation/feature") {
        const body = await readJsonBody(request);
        writeJson(
          request,
          response,
          200,
          await generateFeatureScriptsWithOpenAI({
            testCases: body.testCases,
            issueGroups: body.issueGroups
          })
        );
        return;
      }

      if (request.method === "GET" && requestUrl.pathname === "/api/jira/risk-section") {
        writeJson(request, response, 200, await fetchJiraRiskSection({ key: requestUrl.searchParams.get("key") }));
        return;
      }

      if (request.method === "GET" && requestUrl.pathname === "/api/jira/impact-section") {
        writeJson(request, response, 200, await fetchJiraImpactSection({ key: requestUrl.searchParams.get("key") }));
        return;
      }

      if (request.method === "GET" && requestUrl.pathname === "/api/jira/impact-analysis") {
        writeJson(request, response, 200, await fetchJiraImpactAnalysis({ keys: requestUrl.searchParams.getAll("key") }));
        return;
      }

      if (request.method === "GET" && requestUrl.pathname === "/api/jira/issue-groups") {
        const projectKey = requestUrl.searchParams.get("projectKey") ?? undefined;
        const limit = requestUrl.searchParams.get("limit") ?? undefined;

        writeJson(
          request,
          response,
          200,
          await fetchJiraIssueGroups({ projectKey, limit, requirementsOnly: requestUrl.searchParams.get("requirementsOnly") === "true", writeSnapshot: false })
        );
        return;
      }

      writeJson(request, response, 404, { error: "Not found." });
    } catch (error) {
      writeJson(request, response, statusForError(error), {
        error: publicErrorMessage(error),
        details: error instanceof JiraRequestError ? error.details : undefined
      });
    }
  });
}

export function startServiceLayerServer(options = {}) {
  loadLocalEnv();

  const port = options.port ?? process.env.TAAP_SERVICE_PORT ?? DEFAULT_PORT;
  const numericPort = Number.parseInt(String(port), 10) || DEFAULT_PORT;
  const server = createServiceLayerServer();

  server.on("error", (error) => {
    if (error?.code === "EADDRINUSE") {
      console.log(`TAAP service layer is already running on http://127.0.0.1:${numericPort}`);
      return;
    }

    throw error;
  });

  server.listen(numericPort, "127.0.0.1", () => {
    console.log(`TAAP service layer listening on http://127.0.0.1:${numericPort}`);
  });

  return server;
}

export function loadLocalEnv() {
  const candidates = [
    path.resolve(process.cwd(), ".env"),
    path.resolve(process.cwd(), "..", ".env")
  ];

  for (const candidate of candidates) {
    if (!existsSync(candidate)) {
      continue;
    }

    const contents = readFileSync(candidate, "utf8");

    for (const line of contents.split(/\r?\n/)) {
      const trimmed = line.trim();

      if (!trimmed || trimmed.startsWith("#")) {
        continue;
      }

      const separatorIndex = trimmed.indexOf("=");

      if (separatorIndex < 1) {
        continue;
      }

      const key = trimmed.slice(0, separatorIndex).trim();
      const value = unquoteEnvValue(trimmed.slice(separatorIndex + 1).trim());

      if (!(key in process.env)) {
        process.env[key] = value;
      }
    }

    return candidate;
  }

  return "";
}

function writeJson(request, response, statusCode, payload) {
  response.writeHead(statusCode, {
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
    "Access-Control-Allow-Origin": corsOriginFor(request),
    "Content-Type": "application/json"
  });

  if (statusCode === 204) {
    response.end();
    return;
  }

  response.end(JSON.stringify(payload));
}

async function readJsonBody(request) {
  const chunks = [];

  for await (const chunk of request) {
    chunks.push(chunk);
  }

  const text = Buffer.concat(chunks).toString("utf8").trim();
  if (!text) return {};

  try {
    return JSON.parse(text);
  } catch {
    throw new Error("Request body must be valid JSON.");
  }
}

function corsOriginFor(request) {
  const origin = request.headers.origin;

  return ALLOWED_ORIGINS.has(origin) ? origin : "http://127.0.0.1:5173";
}

function statusForError(error) {
  if (error instanceof JiraConfigError) {
    return 500;
  }

  if (error instanceof JiraRequestError) {
    return error.status && error.status >= 400 ? error.status : 502;
  }

  if (error instanceof AgentRequestError) {
    return error.status && error.status >= 400 ? error.status : 502;
  }

  if (error instanceof ScriptGenerationAgentError) {
    return 502;
  }

  return 500;
}

function publicErrorMessage(error) {
  if (error instanceof Error) {
    return error.message;
  }

  return "Unexpected service-layer error.";
}

function unquoteEnvValue(value) {
  if (
    (value.startsWith('"') && value.endsWith('"')) ||
    (value.startsWith("'") && value.endsWith("'"))
  ) {
    return value.slice(1, -1);
  }

  return value;
}

const currentFile = fileURLToPath(import.meta.url);
const invokedFile = process.argv[1] ? path.resolve(process.argv[1]) : "";

if (currentFile === invokedFile) {
  startServiceLayerServer();
}
