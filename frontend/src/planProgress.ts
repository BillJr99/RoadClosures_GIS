// --- Plan progress helpers -------------------------------------------------
// The planner runs server-side as one request, so the frontend cannot observe
// its real internal steps without streaming. Instead we show honest, useful
// feedback: a REAL elapsed timer, a REAL data-driven ETA (the previous plan's
// measured duration, smoothed), and a stage label that mirrors the planner's
// actual pipeline order. Pure functions live here (no React / localStorage) so
// they can be unit-tested; the timer/storage glue lives in PlanProgress.tsx.

// Ordered to match the backend pipeline (see app/services/planner.py logs):
// graph load -> hydrant filter -> closure min-cut -> warning signs -> assemble.
export const PLAN_STAGES = [
  "Loading street network…",
  "Locating reachable hydrants…",
  "Computing road closures…",
  "Placing warning signs…",
  "Finalizing recommendations…",
];

// Fallback ETA used only until a real plan duration has been measured once.
export const DEFAULT_ETA_MS = 20000;

// Which pipeline stage we most likely occupy, from elapsed time vs. the ETA.
// Without a measured ETA yet, fall back to the default so the label still moves.
export function planStageIndex(elapsedMs: number, etaMs: number | null): number {
  const basis = etaMs && etaMs > 0 ? etaMs : DEFAULT_ETA_MS;
  const fraction = elapsedMs / basis;
  return Math.max(0, Math.min(PLAN_STAGES.length - 1, Math.floor(fraction * PLAN_STAGES.length)));
}

// Determinate progress in [0, 0.98] once an ETA is known (kept under 100% while
// still running so the bar never sits full before the result arrives), or null
// to signal an indeterminate bar on the very first plan.
export function planProgressFraction(elapsedMs: number, etaMs: number | null): number | null {
  if (!etaMs || etaMs <= 0) return null;
  return Math.min(0.98, Math.max(0, elapsedMs / etaMs));
}

// Compact duration: "4.2s" / "37s" under a minute, "1:05" beyond.
export function formatDuration(ms: number): string {
  const s = Math.max(0, ms) / 1000;
  if (s < 60) return `${s < 10 ? s.toFixed(1) : Math.round(s)}s`;
  const m = Math.floor(s / 60);
  const rem = Math.round(s % 60);
  return `${m}:${String(rem).padStart(2, "0")}`;
}

// Blend a freshly measured duration into the stored ETA so one slow/fast run
// (e.g. a cold graph fetch) does not dominate the estimate.
export function nextEta(previousMs: number | null, measuredMs: number): number | null {
  if (!(measuredMs > 0)) return previousMs;
  if (!previousMs || previousMs <= 0) return Math.round(measuredMs);
  return Math.round(previousMs * 0.5 + measuredMs * 0.5);
}

const ETA_KEY = "planEtaMs";

// Ignore implausibly small stored ETAs (e.g. from a cached ~15 ms plan): a tiny
// ETA would drive the bar straight to full on the next real, slow plan.
export const MIN_MEANINGFUL_ETA_MS = 500;

export function readStoredEta(): number | null {
  try {
    const raw = window.localStorage.getItem(ETA_KEY);
    const n = raw ? Number(raw) : NaN;
    return Number.isFinite(n) && n >= MIN_MEANINGFUL_ETA_MS ? n : null;
  } catch {
    return null;
  }
}

export function recordPlanDuration(measuredMs: number): void {
  // Ignore sub-threshold plans: they return near-instantly (warm graph / trivial
  // area) and would only drag the estimate below what readStoredEta will accept.
  if (!(measuredMs >= MIN_MEANINGFUL_ETA_MS)) return;
  try {
    const next = nextEta(readStoredEta(), measuredMs);
    if (next) window.localStorage.setItem(ETA_KEY, String(next));
  } catch {
    /* localStorage unavailable — progress still works, just without a saved ETA */
  }
}
