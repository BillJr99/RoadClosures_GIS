import { describe, expect, it } from "vitest";
import { closureCsv, printableReportHtml, signAndDeviceCsv } from "./export";
import type { PlanResponse } from "./types";

function point(props: Record<string, unknown>, lon = -75.3, lat = 40.1): GeoJSON.Feature {
  return { type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: props };
}

const plan = {
  feasible: true,
  ranked_closures: [
    { rank: 1, deployment_priority: 2, deployment_label: "P2", name: "Second St", capacity: 5, sightline: "good", reason: "cut" },
    { rank: 2, deployment_priority: 1, deployment_label: "P1", name: "Main, St", capacity: 9, sightline: "caution", reason: "cut" },
  ],
  warning_signs: {
    type: "FeatureCollection",
    features: [
      point({ kind: "warning_sign", deployment_priority: 2, deployment_label: "P2A", mutcd_sign_code: "W20-3", sign_label: "ROAD CLOSED AHEAD", approach_road: "Second St", distance_from_closure_ft: 100, placement_status: "placed" }),
      point({ kind: "warning_sign", deployment_priority: 1, deployment_label: "P1A", mutcd_sign_code: "W20-3", sign_label: "ROAD CLOSED AHEAD", approach_road: "Main St", distance_from_closure_ft: 100, placement_status: "placed" }),
    ],
  },
  devices: {
    type: "FeatureCollection",
    features: [point({ kind: "barricade", deployment_priority: 1, device_type: "Type III barricade", mutcd_sign_code: "R11-2", approach_road: "Main St" })],
  },
  compliance: { approach_sides_covered: 3, approach_sides_total: 4 },
} as unknown as PlanResponse;

describe("signAndDeviceCsv", () => {
  it("orders rows by deployment priority and includes signs and devices", () => {
    const lines = signAndDeviceCsv(plan).split("\n");
    expect(lines[0]).toContain("priority_label");
    // Three data rows: two signs + one barricade.
    expect(lines).toHaveLength(4);
    // Priority 1 rows come before priority 2.
    expect(lines[1]).toContain("P1A");
    expect(lines[3]).toContain("P2A");
    // Lat/lon are emitted.
    expect(lines[1]).toContain("40.1");
  });
});

describe("closureCsv", () => {
  it("orders by priority and quotes cells containing commas", () => {
    const lines = closureCsv(plan).split("\n");
    expect(lines[0]).toContain("road");
    expect(lines[1]).toContain("P1");
    // "Main, St" must be quoted because it contains a comma.
    expect(lines[1]).toContain('"Main, St"');
  });
});

describe("printableReportHtml", () => {
  it("renders incident coords and escapes html", () => {
    const html = printableReportHtml(plan, { lat: 40.1, lon: -75.3 });
    expect(html).toContain("Road Closure Deployment Plan");
    expect(html).toContain("40.100000, -75.300000");
    expect(html).toContain("Second St");
  });

  it("embeds an OSM incident map (Leaflet + tiles) when an incident is given", () => {
    const html = printableReportHtml(plan, { lat: 40.1, lon: -75.3 });
    expect(html).toContain("leaflet@1.9.4");
    expect(html).toContain('id="report-map"');
    expect(html).toContain("tile.openstreetmap.org");
    // Static-image fallback for JS-disabled prints.
    expect(html).toContain("staticmap.openstreetmap.de");
  });

  it("omits the map when there is no incident and no plottable geometry", () => {
    expect(printableReportHtml(plan, null)).not.toContain('id="report-map"');
  });

  it("shows a warning when the plan is infeasible", () => {
    const infeasible = { ...plan, feasible: false, feasibility_note: "no cut" } as PlanResponse;
    expect(printableReportHtml(infeasible, null)).toContain("no cut");
  });
});
