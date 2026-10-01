import { useCallback, useEffect, useState } from "react";
import {
  fetchEvaluationMetrics,
  type EvaluationMetrics,
} from "../../data/evaluationApi";
import { onAgentFinished } from "../../lib/runStatusBus";
import "./PerformanceMetrics.css";

function percent(value: number | null | undefined): string {
  return value == null ? "—" : `${(value * 100).toFixed(1)}%`;
}

function duration(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value >= 1000) return `${(value / 1000).toFixed(2)} s`;
  return `${Math.round(value)} ms`;
}

function numberValue(value: number | null | undefined): string {
  return value == null ? "—" : value.toFixed(2);
}

function MetricCard({
  title,
  value,
}: {
  title: string;
  value: string;
}) {
  return (
    <div className="rta-pm-card">
      <div className="rta-pm-card-label">{title}</div>
      <div className="rta-pm-card-value">{value}</div>
    </div>
  );
}

function MetricLine({
  label,
  value,
}: {
  label: string;
  value: string;
}) {
  return (
    <div className="rta-pm-line">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

export default function PerformanceMetrics() {
  const [metrics, setMetrics] = useState<EvaluationMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await fetchEvaluationMetrics();

      setMetrics(data);
      setError(null);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : String(err),
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();

    // Refresh when the audit ledger agent completes.
    const unsubscribe = onAgentFinished(
      "ledger",
      () => {
        void load();
      },
    );

    // Keep the page current while it is open.
    const timer = window.setInterval(() => {
      void load();
    }, 5000);

    return () => {
      unsubscribe();
      window.clearInterval(timer);
    };
  }, [load]);

  return (
    <div className="rta-pm">
      <div className="rta-pm-inner">

        {/* =====================================================
            HEADER
        ====================================================== */}

        <div className="rta-pm-badgehead">
          <span className="dot" />
          <span>
            AGUI Panel · Performance Metrics
          </span>
        </div>

        <h1>
          Multi-agent performance metrics
        </h1>

        <p className="rta-pm-subtitle">
          Runtime performance for the Master
          Orchestrator and every specialist
          agent, including latency, failures,
          tool usage, cache usage, dependency
          correctness, and concurrency.
        </p>

        {/* =====================================================
            LOADING
        ====================================================== */}

        {loading && !metrics && (
          <div className="rta-pm-panel">
            Loading performance metrics…
          </div>
        )}

        {/* =====================================================
            ERROR
        ====================================================== */}

        {error && (
          <div className="rta-pm-panel rta-pm-error">
            <strong>
              Performance metrics unavailable
            </strong>

            <div
              className="rta-pm-muted"
              style={{
                marginTop: 6,
              }}
            >
              {error}
            </div>
          </div>
        )}

        {metrics && (
          <>

            {/* =================================================
                OVERALL PIPELINE
            ================================================== */}

            <section className="rta-pm-section">
              <h2>
                Overall pipeline
              </h2>

              <div className="rta-pm-grid">

                <MetricCard
                  title="Runs"
                  value={String(metrics.runs)}
                />

                <MetricCard
                  title="Success rate"
                  value={percent(
                    metrics.success_rate,
                  )}
                />

                <MetricCard
                  title="Failure rate"
                  value={percent(
                    metrics.failure_rate,
                  )}
                />

                <MetricCard
                  title="P50 latency"
                  value={duration(
                    metrics.p50_latency_ms,
                  )}
                />

                <MetricCard
                  title="P95 latency"
                  value={duration(
                    metrics.p95_latency_ms,
                  )}
                />

                <MetricCard
                  title="P99 latency"
                  value={duration(
                    metrics.p99_latency_ms,
                  )}
                />

                <MetricCard
                  title="Cache hit rate"
                  value={percent(
                    metrics.cache_hit_rate,
                  )}
                />

                <MetricCard
                  title="Tool calls / run"
                  value={numberValue(
                    metrics.tool_calls_per_run,
                  )}
                />

                <MetricCard
                  title="LLM calls / run"
                  value={numberValue(
                    metrics.llm_calls_per_run,
                  )}
                />

                <MetricCard
                  title="Peak concurrency"
                  value={numberValue(
                    metrics.peak_concurrency,
                  )}
                />

              </div>
            </section>

            {/* =================================================
                AGENT PERFORMANCE
            ================================================== */}

            <section className="rta-pm-panel rta-pm-section">

              <h2>
                Agent performance
              </h2>

              <div className="rta-pm-table-wrap">

                <table className="rta-pm-table">

                  <colgroup>
                    <col className="rta-pm-col-agent" />
                    <col className="rta-pm-col-runs" />
                    <col className="rta-pm-col-average" />
                    <col className="rta-pm-col-p50" />
                    <col className="rta-pm-col-p95" />
                    <col className="rta-pm-col-p99" />
                    <col className="rta-pm-col-failure" />
                    <col className="rta-pm-col-output" />
                  </colgroup>

                  <thead>
                    <tr>
                      <th>
                        Agent
                      </th>

                      <th>
                        Runs
                      </th>

                      <th>
                        Average
                      </th>

                      <th>
                        P50
                      </th>

                      <th>
                        P95
                      </th>

                      <th>
                        P99
                      </th>

                      <th>
                        Failure
                      </th>

                      <th>
                        Output records
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {Object.entries(
                      metrics.agents ?? {},
                    ).map(
                      (
                        [
                          name,
                          agent,
                        ],
                      ) => (
                        <tr key={name}>

                          <td className="rta-pm-agent-cell">
                            {name}
                          </td>

                          <td className="rta-pm-number-cell">
                            {agent.runs}
                          </td>

                          <td className="rta-pm-number-cell">
                            {duration(
                              agent.average_latency_ms,
                            )}
                          </td>

                          <td className="rta-pm-number-cell">
                            {duration(
                              agent.p50_latency_ms,
                            )}
                          </td>

                          <td className="rta-pm-number-cell">
                            {duration(
                              agent.p95_latency_ms,
                            )}
                          </td>

                          <td className="rta-pm-number-cell">
                            {duration(
                              agent.p99_latency_ms,
                            )}
                          </td>

                          <td className="rta-pm-number-cell">
                            {percent(
                              agent.failure_rate,
                            )}
                          </td>

                          <td className="rta-pm-number-cell">
                            {agent.average_output_records != null
                              ? agent.average_output_records.toFixed(
                                  1,
                                )
                              : "—"}
                          </td>

                        </tr>
                      ),
                    )}
                  </tbody>

                </table>

              </div>

            </section>

            {/* =================================================
                ORCHESTRATION / CONCURRENCY / TOOL EFFICIENCY
            ================================================== */}

            <section className="rta-pm-section rta-pm-three">

              <div className="rta-pm-panel">

                <h3>
                  Orchestration correctness
                </h3>

                <MetricLine
                  label="Routing correctness"
                  value={percent(
                    metrics.routing_correct_rate,
                  )}
                />

                <MetricLine
                  label="Dependency order"
                  value={percent(
                    metrics.dependency_order_correct_rate,
                  )}
                />

                <MetricLine
                  label="Required output completeness"
                  value={percent(
                    metrics.required_fields_complete_rate,
                  )}
                />

              </div>

              <div className="rta-pm-panel">

                <h3>
                  Concurrency
                </h3>

                <MetricLine
                  label="Peak concurrent agents"
                  value={numberValue(
                    metrics.peak_concurrency,
                  )}
                />

                <MetricLine
                  label="Parallel duration ratio"
                  value={percent(
                    metrics.parallel_duration_ratio,
                  )}
                />

                <MetricLine
                  label="Cache lookups"
                  value={String(
                    metrics.cache_lookups,
                  )}
                />

              </div>

              <div className="rta-pm-panel">

                <h3>
                  Tool efficiency
                </h3>

                <MetricLine
                  label="Tool calls / run"
                  value={numberValue(
                    metrics.tool_calls_per_run,
                  )}
                />

                <MetricLine
                  label="Tool failure rate"
                  value={percent(
                    metrics.tool_failure_rate,
                  )}
                />

                <MetricLine
                  label="LLM calls / run"
                  value={numberValue(
                    metrics.llm_calls_per_run,
                  )}
                />

              </div>

            </section>

            {/* =================================================
                BUSINESS CORRECTNESS
            ================================================== */}

            <section className="rta-pm-panel rta-pm-section">

              <h2>
                Business correctness evaluation
              </h2>

              <p
                className="rta-pm-subtitle"
                style={{
                  marginBottom: 12,
                }}
              >
                These metrics compare actual
                outputs against verified golden
                test cases. They should not be
                inferred from runtime timing.
              </p>

              {!metrics.golden.available ? (
                <div className="rta-pm-note">

                  <strong>
                    Golden dataset not configured
                  </strong>

                  <div
                    style={{
                      marginTop: 6,
                    }}
                  >
                    Add a verified dataset under
                    app/evaluation/datasets/
                    before calculating
                    business-correctness metrics.
                  </div>

                </div>
              ) : (
                <div className="rta-pm-grid">

                  <MetricCard
                    title="Accuracy"
                    value={percent(
                      metrics.golden.accuracy,
                    )}
                  />

                  <MetricCard
                    title="Precision"
                    value={percent(
                      metrics.golden.precision,
                    )}
                  />

                  <MetricCard
                    title="Recall"
                    value={percent(
                      metrics.golden.recall,
                    )}
                  />

                  <MetricCard
                    title="F1"
                    value={percent(
                      metrics.golden.f1,
                    )}
                  />

                  <MetricCard
                    title="Scoring accuracy"
                    value={percent(
                      metrics.golden.scoring_accuracy,
                    )}
                  />

                  <MetricCard
                    title="Governance rule accuracy"
                    value={percent(
                      metrics.golden.governance_rule_accuracy,
                    )}
                  />

                  <MetricCard
                    title="Golden cases"
                    value={String(
                      metrics.golden.total_cases,
                    )}
                  />

                  <MetricCard
                    title="Passed cases"
                    value={String(
                      metrics.golden.passed_cases,
                    )}
                  />

                </div>
              )}

            </section>

            {/* =================================================
                REFRESH
            ================================================== */}

            <button
              className="rta-pm-button"
              onClick={() => void load()}
            >
              Refresh metrics
            </button>

          </>
        )}

      </div>
    </div>
  );
}