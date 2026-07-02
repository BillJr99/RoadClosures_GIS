import type { PlanResponse } from "./types";

export function planStatusMessages(plan: PlanResponse): { status: string; warnings: string[] } {
  const warnings = plan.warnings ?? [];
  const count = plan.ranked_closures.length;
  const status = warnings.length
    ? `Plan ready with warnings: ${count} closure recommendation(s). ${warnings[0]}`
    : `Plan ready: ${count} closure recommendation(s).`;
  return { status, warnings };
}
