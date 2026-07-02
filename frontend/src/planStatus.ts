import type { PlanResponse } from "./types";

export function planStatusMessages(plan: PlanResponse): { status: string; warnings: string[] } {
  const warnings = plan.warnings ?? [];
  const count = plan.ranked_closures.length;
  // Keep the status line short: the full warning text is shown in the
  // warning banner, so repeating it here would bloat the header/status.
  const status = warnings.length
    ? `Plan ready with warnings: ${count} closure recommendation(s). See warning below.`
    : `Plan ready: ${count} closure recommendation(s).`;
  return { status, warnings };
}
