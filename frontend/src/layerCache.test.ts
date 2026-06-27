import { describe, expect, it } from "vitest";
import { isFresh, LAYER_CACHE_TTL_MS } from "./layerCache";

const DAY = 24 * 60 * 60 * 1000;

describe("LAYER_CACHE_TTL_MS", () => {
  it("is exactly 7 days", () => {
    expect(LAYER_CACHE_TTL_MS).toBe(7 * 24 * 60 * 60 * 1000);
    expect(LAYER_CACHE_TTL_MS).toBe(7 * DAY);
  });
});

describe("isFresh", () => {
  const now = 1_000_000_000_000;

  it("treats an entry younger than the ttl as fresh", () => {
    expect(isFresh(now - DAY, now, LAYER_CACHE_TTL_MS)).toBe(true);
    expect(isFresh(now - 6 * DAY, now, LAYER_CACHE_TTL_MS)).toBe(true);
    // Just inside the boundary.
    expect(isFresh(now - (7 * DAY - 1), now, LAYER_CACHE_TTL_MS)).toBe(true);
  });

  it("treats an entry at or beyond the ttl as stale", () => {
    // Exactly at the TTL boundary is stale (re-fetched).
    expect(isFresh(now - 7 * DAY, now, LAYER_CACHE_TTL_MS)).toBe(false);
    expect(isFresh(now - 8 * DAY, now, LAYER_CACHE_TTL_MS)).toBe(false);
  });

  it("defaults the ttl to LAYER_CACHE_TTL_MS when omitted", () => {
    expect(isFresh(now - DAY, now)).toBe(true);
    expect(isFresh(now - 8 * DAY, now)).toBe(false);
  });

  it("honors a custom ttl", () => {
    expect(isFresh(now - 2000, now, 5000)).toBe(true);
    expect(isFresh(now - 5000, now, 5000)).toBe(false);
  });
});
