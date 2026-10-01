import { serviceEnvironment } from "../environment.js";

export async function fetchJiraIssueGroups(options = {}) {
  const params = new URLSearchParams();
  if (options.requirementsOnly) params.set("requirementsOnly", "true");

  if (options.projectKey) {
    params.set("projectKey", options.projectKey);
  }

  if (options.limit) {
    params.set("limit", String(options.limit));
  }

  return fetchFromServiceLayer(`/api/jira/issue-groups${params.size ? `?${params}` : ""}`);
}

export async function generateSdetFeatureScripts(options = {}) {
  return fetchFromServiceLayer("/api/sdet/script-generation/feature", {
    method: "POST",
    body: JSON.stringify({
      testCases: options.testCases ?? [],
      issueGroups: options.issueGroups ?? null
    })
  });
}

export async function testJiraConnection() {
  return fetchFromServiceLayer("/api/jira/test-connection");
}

export async function fetchJiraImpactAnalysis(keys, { signal } = {}) {
  const params = new URLSearchParams();
  keys.forEach(key => params.append("key", key));
  return fetchFromServiceLayer(`/api/jira/impact-analysis?${params}`, { signal });
}

export async function fetchJiraImpactSection(key, { signal } = {}) {
  return fetchFromServiceLayer(`/api/jira/impact-section?${new URLSearchParams({ key })}`, { signal });
}

export async function fetchJiraRiskSection(key, { signal } = {}) {
  return fetchFromServiceLayer(`/api/jira/risk-section?${new URLSearchParams({ key })}`, { signal });
}

export async function fetchJiraTestCases(keys, { signal } = {}) {
  const params = new URLSearchParams();
  keys.forEach(key => params.append("key", key));
  return fetchFromServiceLayer(`/api/jira/test-cases?${params}`, { signal });
}

async function fetchFromServiceLayer(path, options = {}) {
  if (typeof fetch !== "function") {
    throw new Error("Fetch API is not available in this runtime.");
  }

  const response = await fetch(`${serviceLayerBaseUrl()}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {})
    }
  });
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

  return serviceEnvironment.serviceBaseUrl.replace(/\/+$/, "");
}
