import { describe, expect, it } from "vitest";
import { filterPlanResources, orderByPriority, resourceTotals } from "./resourcePriority";
import type { PlanResponse } from "./types";

function point(props: Record<string, unknown>, lon = -75.3, lat = 40.1): GeoJSON.Feature {
  return { type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: props };
}

const plan = {
  closures: {
    type: "FeatureCollection",
    features: [
      point({ kind: "closure", rank: 2, deployment_priority: 2, deployment_label: "P2" }),
      point({ kind: "closure", rank: 1, deployment_priority: 1, deployment_label: "P1" }),
    ],
  },
  warning_signs: {
    type: "FeatureCollection",
    features: [
      point({ kind: "warning_sign", deployment_priority: 2, sequence: "A", closure_rank: 1, deployment_label: "P2A" }),
      point({ kind: "warning_sign", deployment_priority: 1, sequence: "B", closure_rank: 1, deployment_label: "P1B" }),
      point({ kind: "warning_sign", deployment_priority: 1, sequence: "A", closure_rank: 1, deployment_label: "P1A" }),
    ],
  },
  devices: {
    type: "FeatureCollection",
    features: [
      point({ kind: "barricade", deployment_priority: 2, closure_rank: 2, deployment_label: "B2" }),
      point({ kind: "barricade", deployment_priority: 1, closure_rank: 1, deployment_label: "B1" }),
      point({ kind: "channelizing_device", deployment_priority: 1, closure_rank: 1, device_index: 2, deployment_label: "C-2" }),
      point({ kind: "channelizing_device", deployment_priority: 1, closure_rank: 1, device_index: 1, deployment_label: "C-1" }),
    ],
  },
} as unknown as PlanResponse;

const ALL = { closures: 9, barricades: 9, channelizing: 9, signs: 9 };

describe("orderByPriority", () => {
  it("orders signs by priority, then sequence A<B, then closure_rank", () => {
    const labels = orderByPriority(plan.warning_signs!.features, "signs").map((f) => f.properties?.deployment_label);
    expect(labels).toEqual(["P1A", "P1B", "P2A"]);
  });

  it("orders channelizing devices by device_index within the same priority", () => {
    const channelizing = plan.devices!.features.filter((f) => f.properties?.kind === "channelizing_device");
    const labels = orderByPriority(channelizing, "channelizing").map((f) => f.properties?.deployment_label);
    expect(labels).toEqual(["C-1", "C-2"]);
  });

  it("orders closures by deployment priority", () => {
    const labels = orderByPriority(plan.closures!.features, "closures").map((f) => f.properties?.deployment_label);
    expect(labels).toEqual(["P1", "P2"]);
  });
});

describe("resourceTotals", () => {
  it("counts each resource type, including closures", () => {
    expect(resourceTotals(plan)).toEqual({ closures: 2, barricades: 2, channelizing: 2, signs: 3 });
  });

  it("returns zeros for a null plan", () => {
    expect(resourceTotals(null)).toEqual({ closures: 0, barricades: 0, channelizing: 0, signs: 0 });
  });
});

describe("filterPlanResources per-type caps", () => {
  it("keeps the top-N highest-priority features of each type", () => {
    const { warning_signs, devices } = filterPlanResources(plan, { ...ALL, barricades: 1, channelizing: 1, signs: 2 });
    expect(warning_signs!.features.map((f) => f.properties?.deployment_label)).toEqual(["P1B", "P1A"]);
    // Original order is preserved; only the kept set differs.
    expect(devices!.features.map((f) => f.properties?.deployment_label)).toEqual(["B1", "C-1"]);
  });

  it("keeps everything when counts are at or above the totals", () => {
    const { closures, warning_signs, devices } = filterPlanResources(plan, ALL);
    expect(closures!.features).toHaveLength(2);
    expect(warning_signs!.features).toHaveLength(3);
    expect(devices!.features).toHaveLength(4);
  });

  it("hides everything of a type when its count is zero", () => {
    const { devices } = filterPlanResources(plan, { ...ALL, barricades: 0, channelizing: 0, signs: 0 });
    expect(devices!.features).toHaveLength(0);
  });
});

describe("filterPlanResources closure cap cascade", () => {
  it("capping closures hides the lowest-priority closure and the resources tied to it", () => {
    const { closures, warning_signs, devices } = filterPlanResources(plan, { ...ALL, closures: 1 });
    // Only the highest-priority closure (rank 1 / P1) remains.
    expect(closures!.features.map((f) => f.properties?.deployment_label)).toEqual(["P1"]);
    // B2 is tied to the removed closure (closure_rank 2) and is dropped.
    expect(devices!.features.map((f) => f.properties?.deployment_label)).toEqual(["B1", "C-2", "C-1"]);
    // All signs are tied to the surviving closure (closure_rank 1), so all remain.
    expect(warning_signs!.features).toHaveLength(3);
  });

  it("restores a closure and its resources when the cap is raised again", () => {
    const { closures, devices } = filterPlanResources(plan, { ...ALL, closures: 2 });
    expect(closures!.features).toHaveLength(2);
    expect(devices!.features.map((f) => f.properties?.deployment_label)).toEqual(["B2", "B1", "C-2", "C-1"]);
  });

  it("applies per-type caps to what survives the cascade", () => {
    const { warning_signs, devices } = filterPlanResources(plan, { closures: 1, barricades: 9, channelizing: 1, signs: 1 });
    // Cascade drops B2; channelizing capped to its top-1 (C-1 by device_index).
    expect(devices!.features.map((f) => f.properties?.deployment_label)).toEqual(["B1", "C-1"]);
    // Signs capped to top-1 by priority.
    expect(warning_signs!.features.map((f) => f.properties?.deployment_label)).toEqual(["P1A"]);
  });

  it("dropping all closures frees every tied resource", () => {
    const { closures, warning_signs, devices } = filterPlanResources(plan, { ...ALL, closures: 0 });
    expect(closures!.features).toHaveLength(0);
    expect(warning_signs!.features).toHaveLength(0);
    expect(devices!.features).toHaveLength(0);
  });
});
