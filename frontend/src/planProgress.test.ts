import { describe, expect, it } from "vitest";
import {
  DEFAULT_ETA_MS,
  PLAN_STAGES,
  formatDuration,
  nextEta,
  planProgressFraction,
  planStageIndex,
} from "./planProgress";

describe("planStageIndex", () => {
  it("starts at the first stage and ends at the last", () => {
    expect(planStageIndex(0, 20000)).toBe(0);
    expect(planStageIndex(19999, 20000)).toBe(PLAN_STAGES.length - 1);
  });

  it("advances through stages proportionally to elapsed/eta", () => {
    // 5 stages over a 10s ETA => ~2s per stage.
    expect(planStageIndex(2100, 10000)).toBe(1);
    expect(planStageIndex(6100, 10000)).toBe(3);
  });

  it("clamps past the ETA to the final stage instead of overflowing", () => {
    expect(planStageIndex(100000, 10000)).toBe(PLAN_STAGES.length - 1);
  });

  it("falls back to the default ETA when none is known", () => {
    expect(planStageIndex(DEFAULT_ETA_MS / 2, null)).toBe(Math.floor(PLAN_STAGES.length / 2));
  });
});

describe("planProgressFraction", () => {
  it("is null (indeterminate) without an ETA", () => {
    expect(planProgressFraction(5000, null)).toBeNull();
    expect(planProgressFraction(5000, 0)).toBeNull();
  });

  it("tracks elapsed/eta but never reaches 100% while running", () => {
    expect(planProgressFraction(5000, 10000)).toBeCloseTo(0.5, 5);
    expect(planProgressFraction(100000, 10000)).toBe(0.98);
  });
});

describe("formatDuration", () => {
  it("shows tenths under 10 seconds", () => {
    expect(formatDuration(4200)).toBe("4.2s");
  });
  it("shows whole seconds under a minute", () => {
    expect(formatDuration(37000)).toBe("37s");
  });
  it("shows m:ss beyond a minute", () => {
    expect(formatDuration(65000)).toBe("1:05");
  });
});

describe("nextEta", () => {
  it("seeds from the first measurement", () => {
    expect(nextEta(null, 12000)).toBe(12000);
  });
  it("blends new measurements with the previous estimate (50/50)", () => {
    expect(nextEta(10000, 20000)).toBe(15000);
  });
  it("ignores non-positive measurements", () => {
    expect(nextEta(10000, 0)).toBe(10000);
  });
});
