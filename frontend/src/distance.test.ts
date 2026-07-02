import { describe, expect, it } from "vitest";
import { formatFeet, incidentDistanceText, metersBetween } from "./distance";

describe("metersBetween", () => {
  it("returns 0 for identical points", () => {
    expect(metersBetween(-75.34, 40.22, -75.34, 40.22)).toBe(0);
  });

  it("matches a known short distance (~111 m per 0.001° latitude)", () => {
    const m = metersBetween(-75.34, 40.22, -75.34, 40.221);
    expect(m).toBeGreaterThan(108);
    expect(m).toBeLessThan(114);
  });
});

describe("formatFeet", () => {
  it("shows plain feet under 1000", () => {
    expect(formatFeet(593)).toBe("593 ft");
  });

  it("adds a thousands separator and a miles hint at/above 1000 ft", () => {
    expect(formatFeet(1500)).toBe("1,500 ft (0.28 mi)");
    expect(formatFeet(39164)).toBe("39,164 ft (7.42 mi)");
  });
});

describe("incidentDistanceText", () => {
  const at = { lon: -75.34, lat: 40.22 };

  it("returns empty string when there is no incident", () => {
    expect(incidentDistanceText(at.lon, at.lat, [])).toBe("");
  });

  it("phrases a single incident as '… from incident'", () => {
    const text = incidentDistanceText(at.lon, at.lat, [{ lat: 40.221, lon: -75.34 }]);
    expect(text).toMatch(/^\d+ ft from incident$/);
  });

  it("numbers each incident when there are several", () => {
    const text = incidentDistanceText(at.lon, at.lat, [
      { lat: 40.221, lon: -75.34 },
      { lat: 40.225, lon: -75.34 },
    ]);
    expect(text).toMatch(/^to incidents — #1: .*, #2: .*/);
    expect(text).toContain("#1:");
    expect(text).toContain("#2:");
  });
});
