export interface EvaluationAgentMetric {
  runs: number;
  average_latency_ms: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  p99_latency_ms: number | null;
  failure_rate: number;
  average_output_records: number;
}

export interface GoldenEvaluation {
  available: boolean;
  runs_evaluated: number;
  total_cases: number;
  passed_cases: number;
  failed_cases: number;
  accuracy: number | null;
  precision: number | null;
  recall: number | null;
  f1: number | null;
  scoring_accuracy: number | null;
  governance_rule_accuracy: number | null;
}

export interface EvaluationMetrics {
  runs: number;
  success_rate: number;
  failure_rate: number;
  p50_latency_ms: number | null;
  p95_latency_ms: number | null;
  p99_latency_ms: number | null;
  cache_hit_rate: number | null;
  cache_lookups: number;
  tool_calls_per_run: number;
  tool_failure_rate: number | null;
  llm_calls_per_run: number;
  llm_failure_rate: number | null;
  llm_p50_latency_ms: number | null;
  llm_p95_latency_ms: number | null;
  llm_p99_latency_ms: number | null;
  prompt_tokens_per_run: number;
  completion_tokens_per_run: number;
  total_tokens_per_run: number;
  routing_correct_rate: number | null;
  dependency_order_correct_rate: number | null;
  required_fields_complete_rate: number | null;
  peak_concurrency: number | null;
  parallel_duration_ratio: number | null;
  golden: GoldenEvaluation;
  agents: Record<string, EvaluationAgentMetric>;
}

export interface EvaluationRun {
  run_id: string;
  release_id: string;
  query?: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  total_latency_ms: number;
  agents: Record<
    string,
    {
      status: string;
      started_at: string;
      finished_at: string | null;
      latency_ms: number;
      error: string | null;
      output_record_count: number | null;
    }
  >;
}

export interface EvaluationRunsResponse {
  runs: EvaluationRun[];
}

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.trim() ||
  "http://127.0.0.1:4000";

async function getJson<T>(path: string): Promise<T> {
  const url = `${API_BASE_URL}${path}`;

  let response: Response;

  try {
    response = await fetch(url, {
      method: "GET",
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
  } catch {
    throw new Error(
      `Cannot connect to backend at ${API_BASE_URL}. ` +
        `Make sure FastAPI is running on port 4000.`,
    );
  }

  if (!response.ok) {
    const body = await response.text().catch(() => "");
    throw new Error(
      `Request failed (${response.status}): ${path}${body ? ` - ${body}` : ""}`,
    );
  }

  return response.json() as Promise<T>;
}

export function fetchEvaluationMetrics(
  limit = 1000,
): Promise<EvaluationMetrics> {
  return getJson<EvaluationMetrics>(
    `/api/v1/evaluation/metrics?limit=${limit}`,
  );
}

export function fetchEvaluationRuns(
  limit = 100,
): Promise<EvaluationRunsResponse> {
  return getJson<EvaluationRunsResponse>(
    `/api/v1/evaluation/runs?limit=${limit}`,
  );
}
