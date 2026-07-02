import { describe, expect, it } from "vitest";
import { planStatusMessages } from "./planStatus";
import type { PlanResponse } from "./types";

function plan(overrides: Partial<PlanResponse>): PlanResponse {
  return {
    cut_value: 1.0,
    selected_hydrant: { type: "Feature", geometry: { type: "Point", coordinates: [-75.4, 40.2] }, properties: {} },
    hose_route: { type: "Feature", geometry: { type: "LineString", coordinates: [] }, properties: {} },
    closures: { type: "FeatureCollection", features: [] },
    overlays: { type: "FeatureCollection", features: [] },
    ranked_closures: [{ rank: 1 }, { rank: 2 }],
    hydrant_candidates: [],
    ...overrides,
  } as PlanResponse;
}

describe("planStatusMessages", () => {
  it("reports a clean plan with no warnings", () => {
    const { status, warnings } = planStatusMessages(plan({ warnings: [] }));
    expect(warnings).toEqual([]);
    expect(status).toBe("Plan ready: 2 closure recommendation(s).");
  });

  it("treats a missing warnings field as no warnings", () => {
    const { status, warnings } = planStatusMessages(plan({}));
    expect(warnings).toEqual([]);
    expect(status).toContain("Plan ready:");
  });

  it("surfaces hose-envelope warnings in the status", () => {
    const warning =
      "No hydrant is reachable within the 300 ft hose envelope. Showing the 1 nearest road-reachable hydrant(s) instead.";
    const { status, warnings } = planStatusMessages(plan({ warnings: [warning] }));
    expect(warnings).toEqual([warning]);
    expect(status).toContain("Plan ready with warnings");
    expect(status).toContain(warning);
    expect(status).not.toContain("Planner failed");
  });
});
