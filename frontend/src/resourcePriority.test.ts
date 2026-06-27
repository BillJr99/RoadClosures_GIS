import { describe, expect, it } from "vitest";
import { filterPlanResources, orderByPriority, resourceTotals } from "./resourcePriority";
import type { PlanResponse } from "./types";

function point(props: Record<string, unknown>, lon = -75.3, lat = 40.1): GeoJSON.Feature {
  return { type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: props };
}

const plan = {
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
});

describe("resourceTotals", () => {
  it("counts each resource type", () => {
    expect(resourceTotals(plan)).toEqual({ barricades: 2, channelizing: 2, signs: 3 });
  });

  it("returns zeros for a null plan", () => {
    expect(resourceTotals(null)).toEqual({ barricades: 0, channelizing: 0, signs: 0 });
  });
});

describe("filterPlanResources", () => {
  it("keeps the top-N highest-priority features of each type", () => {
    const { warning_signs, devices } = filterPlanResources(plan, { barricades: 1, channelizing: 1, signs: 2 });
    expect(warning_signs!.features.map((f) => f.properties?.deployment_label)).toEqual(["P1B", "P1A"]);
    // Original order is preserved; only the kept set differs.
    expect(devices!.features.map((f) => f.properties?.deployment_label)).toEqual(["B1", "C-1"]);
  });

  it("keeps everything when counts are at or above the totals", () => {
    const { warning_signs, devices } = filterPlanResources(plan, { barricades: 5, channelizing: 5, signs: 5 });
    expect(warning_signs!.features).toHaveLength(3);
    expect(devices!.features).toHaveLength(4);
  });

  it("hides everything of a type when its count is zero", () => {
    const { devices } = filterPlanResources(plan, { barricades: 0, channelizing: 0, signs: 0 });
    expect(devices!.features).toHaveLength(0);
  });
});
