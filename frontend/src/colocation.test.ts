import { describe, expect, it } from "vitest";
import {
  COLOCATION_SPACING_DEG,
  computeColocationOffsets,
  distanceSqToSegment,
  perpendicularUnit,
  pointFeatureKey,
} from "./colocation";

// These helpers were extracted from mapView.tsx specifically so they can be
// unit-tested under jsdom without importing react-leaflet. computeColocationOffsets
// is also re-exported from mapView.tsx for the render code.

function point(props: Record<string, unknown>, lon = -75.3, lat = 40.1): GeoJSON.Feature {
  return { type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties: props };
}

function line(coords: [number, number][]): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: [{ type: "Feature", geometry: { type: "LineString", coordinates: coords }, properties: {} }],
  };
}

describe("perpendicularUnit", () => {
  it("returns a unit vector perpendicular to the segment", () => {
    // East-west segment -> perpendicular is north-south (0, 1).
    const [px, py] = perpendicularUnit([0, 0], [1, 0]);
    expect(px).toBeCloseTo(0);
    expect(py).toBeCloseTo(1);
    expect(Math.hypot(px, py)).toBeCloseTo(1);
  });

  it("is safe for a zero-length segment", () => {
    const [px, py] = perpendicularUnit([0, 0], [0, 0]);
    expect(Number.isFinite(px)).toBe(true);
    expect(Number.isFinite(py)).toBe(true);
  });
});

describe("distanceSqToSegment", () => {
  it("is zero on the segment and positive off it", () => {
    expect(distanceSqToSegment([0.5, 0], [0, 0], [1, 0])).toBeCloseTo(0);
    expect(distanceSqToSegment([0.5, 1], [0, 0], [1, 0])).toBeCloseTo(1);
  });
});

describe("computeColocationOffsets", () => {
  it("fans two co-located points apart with non-zero, opposite offsets", () => {
    const a = point({ deployment_label: "A" });
    const b = point({ deployment_label: "B" });
    // East-west road -> offsets run north-south.
    const offsets = computeColocationOffsets(
      [{ type: "FeatureCollection", features: [a, b] }],
      [line([[-75.31, 40.1], [-75.29, 40.1]])],
    );
    const oa = offsets.get(pointFeatureKey(a))!;
    const ob = offsets.get(pointFeatureKey(b))!;
    expect(oa).toBeDefined();
    expect(ob).toBeDefined();
    // Non-zero magnitude.
    expect(Math.hypot(oa[0], oa[1])).toBeGreaterThan(0);
    expect(Math.hypot(ob[0], ob[1])).toBeGreaterThan(0);
    // Opposite (symmetric about the true point): components sum to ~0.
    expect(oa[0] + ob[0]).toBeCloseTo(0);
    expect(oa[1] + ob[1]).toBeCloseTo(0);
    // Spread equals the configured spacing for two members (-0.5/+0.5).
    expect(Math.abs(oa[1])).toBeCloseTo(COLOCATION_SPACING_DEG / 2);
  });

  it("offsets are perpendicular to the provided line", () => {
    const a = point({ deployment_label: "A" });
    const b = point({ deployment_label: "B" });
    // North-south road -> offsets must run east-west (x only, y ~ 0).
    const offsets = computeColocationOffsets(
      [{ type: "FeatureCollection", features: [a, b] }],
      [line([[-75.3, 40.09], [-75.3, 40.11]])],
    );
    const oa = offsets.get(pointFeatureKey(a))!;
    expect(Math.abs(oa[0])).toBeGreaterThan(0);
    expect(oa[1]).toBeCloseTo(0);
  });

  it("does not offset a single (non-colocated) point", () => {
    const a = point({ deployment_label: "solo" });
    const offsets = computeColocationOffsets(
      [{ type: "FeatureCollection", features: [a] }],
      [line([[-75.31, 40.1], [-75.29, 40.1]])],
    );
    expect(offsets.size).toBe(0);
    expect(offsets.get(pointFeatureKey(a))).toBeUndefined();
  });

  it("is safe for null / empty / undefined inputs", () => {
    expect(computeColocationOffsets([], []).size).toBe(0);
    expect(computeColocationOffsets([null, undefined], [null, undefined]).size).toBe(0);
    // Co-located points still fan out even with no line (east-west fallback).
    const a = point({ deployment_label: "A" });
    const b = point({ deployment_label: "B" });
    const offsets = computeColocationOffsets([{ type: "FeatureCollection", features: [a, b] }], []);
    expect(offsets.size).toBe(2);
  });
});
