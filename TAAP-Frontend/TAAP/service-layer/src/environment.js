const browserEnv = import.meta.env ?? {};
const nodeEnv = typeof process !== "undefined" ? process.env : {};

export const serviceEnvironment = {
  isMock: readBoolean(browserEnv.VITE_TAAP_IS_MOCK ?? nodeEnv.TAAP_IS_MOCK, false),
  serviceBaseUrl: readString(browserEnv.VITE_TAAP_SERVICE_URL ?? nodeEnv.TAAP_SERVICE_URL, "http://127.0.0.1:8787"),
  jiraProjectKey: readString(browserEnv.VITE_TAAP_JIRA_PROJECT_KEY ?? nodeEnv.JIRA_PROJECT_KEY, ""),
  jiraBaseUrl: readString(browserEnv.VITE_TAAP_JIRA_BASE_URL ?? nodeEnv.JIRA_BASE_URL, "https://jira.example.com")
};

export async function fetchServiceEnvironment() {
  return { ...serviceEnvironment };
}

function readBoolean(value, fallback) {
  if (typeof value === "boolean") {
    return value;
  }

  const normalized = String(value ?? "").trim().toLowerCase();

  if (["true", "1", "yes", "y"].includes(normalized)) {
    return true;
  }

  if (["false", "0", "no", "n"].includes(normalized)) {
    return false;
  }

  return fallback;
}

function readString(value, fallback) {
  const normalized = String(value ?? "").trim();

  return normalized || fallback;
}
