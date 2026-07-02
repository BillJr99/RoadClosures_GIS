import React, { useEffect, useRef, useState } from "react";
import {
  PLAN_STAGES,
  formatDuration,
  planProgressFraction,
  planStageIndex,
  readStoredEta,
} from "./planProgress";

// Live progress shown while a plan request is in flight. Displays the current
// pipeline step, a real elapsed timer, a learned ETA, and a progress bar
// (determinate once an ETA exists, indeterminate on the first-ever plan).
export function PlanProgress({ active }: { active: boolean }) {
  const [elapsedMs, setElapsedMs] = useState(0);
  const etaRef = useRef<number | null>(null);

  useEffect(() => {
    if (!active) return;
    etaRef.current = readStoredEta();
    const start = Date.now();
    setElapsedMs(0);
    const id = window.setInterval(() => setElapsedMs(Date.now() - start), 200);
    return () => window.clearInterval(id);
  }, [active]);

  if (!active) return null;

  const eta = etaRef.current;
  const fraction = planProgressFraction(elapsedMs, eta);
  const stageIndex = planStageIndex(elapsedMs, eta);
  const indeterminate = fraction === null;

  return (
    <div className="plan-progress" role="status" aria-live="polite">
      <div className="plan-progress-head">
        <span className="plan-progress-step">
          Step {stageIndex + 1} of {PLAN_STAGES.length}: {PLAN_STAGES[stageIndex]}
        </span>
        <span className="plan-progress-time">
          {formatDuration(elapsedMs)}
          {eta ? ` · ~${formatDuration(eta)} est.` : " · estimating…"}
        </span>
      </div>
      <div className={`plan-progress-bar${indeterminate ? " indeterminate" : ""}`}>
        <div
          className="plan-progress-fill"
          style={indeterminate ? undefined : { width: `${Math.round((fraction ?? 0) * 100)}%` }}
        />
      </div>
    </div>
  );
}
