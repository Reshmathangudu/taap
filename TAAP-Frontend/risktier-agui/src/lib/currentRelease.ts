// Tracks which release ID the three result panels (TestSelectionReport,
// ExclusionSignoffQueue, ExecutionAuditLog) should query.
//
// Each panel is independently mountable and doesn't share React state with
// RunConsole. The single source of truth for "which release just ran" is
// runStatusBus.ts's startRun() — it persists here the moment a run finishes,
// regardless of which of the three panels (if any) happen to be mounted at
// that moment. That matters: if only the Run Console tab is open when a run
// completes, none of the three panels are mounted to catch the finish event
// themselves, so they must not depend on that to learn the release id.
//
// fetchLatestReleaseId() is a second-line fallback for a panel that mounts
// with nothing in localStorage yet (private browsing, cleared storage, a
// fresh browser) — it asks the backend what it last completed, so the
// panel can still show the latest real run's data instead of a dead end.

const STORAGE_KEY = "rta:last-release-id";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? "http://127.0.0.1:4000";

export function getStoredReleaseId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setStoredReleaseId(releaseId: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, releaseId);
  } catch {
    // Private browsing / blocked storage — the panel just won't remember
    // across reloads; live onAgentFinished updates still work this session.
  }
}

/** Ask the backend which release it last completed a full run for. */
export async function fetchLatestReleaseId(): Promise<string | null> {
  try {
    const res = await fetch(`${API_BASE_URL}/api/v1/releases/latest`);
    if (!res.ok) return null;
    const data = (await res.json()) as { release_id?: string | null };
    return data.release_id ?? null;
  } catch {
    return null;
  }
}

/**
 * Resolve the release a panel should load on mount: localStorage first
 * (fast, no network), falling back to asking the backend. When the backend
 * fallback finds one, it's persisted locally too so the next mount is fast.
 */
export async function resolveReleaseId(): Promise<string | null> {
  const stored = getStoredReleaseId();
  if (stored) return stored;

  const latest = await fetchLatestReleaseId();
  if (latest) setStoredReleaseId(latest);
  return latest;
}
