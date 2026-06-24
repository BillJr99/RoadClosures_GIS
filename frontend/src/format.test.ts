import { describe, expect, it } from "vitest";
import { formatCoords } from "./format";

describe("formatCoords", () => {
  it("formats incident coordinates to six decimals", () => {
    expect(formatCoords(40.1234567, -75.7654321)).toBe("40.123457, -75.765432");
  });
});

