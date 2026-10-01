import { useEffect, useState } from "react";
import { resolveReleaseId } from "./currentRelease";
import { onRunLifecycle } from "./runStatusBus";

/**
 * True once a release ID exists for this session — either a prior run's
 * (recovered via resolveReleaseId, which checks localStorage then falls
 * back to the backend's "latest completed release" endpoint) or a run that
 * finishes while this hook is mounted. Panels that depend on a completed
 * pipeline (Test Selection, Exclusion Sign-off, Audit Log) should stay
 * gated behind this until it flips true.
 */
export function useHasReleaseId(): boolean {
  const [hasReleaseId, setHasReleaseId] = useState(false);

  useEffect(() => {
    let cancelled = false;
    resolveReleaseId().then((releaseId) => {
      if (!cancelled && releaseId) setHasReleaseId(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(
    () =>
      onRunLifecycle(({ phase }) => {
        if (phase === "finished") setHasReleaseId(true);
      }),
    []
  );

  return hasReleaseId;
}
