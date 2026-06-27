import type { FeatureCollection, PlanResponse } from "./types";

// Per-resource availability filtering. The plan returned by the backend carries
// every advance-warning sign, barricade, and channelizing device it would
// recommend. The UI lets a user say how many of each TYPE are actually
// available; we then keep only the highest-priority N of that type and hide the
// rest. All of this is pure data work (no backend round-trip) so the map can
// update in real time as the counts change.

export type ResourceType = "barricades" | "channelizing" | "signs";

export type ResourceCounts = Record<ResourceType, number>;

const isBarricade = (feature: GeoJSON.Feature) => feature.properties?.kind === "barricade";
const isChannelizing = (feature: GeoJSON.Feature) => feature.properties?.kind === "channelizing_device";

function num(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : Number.POSITIVE_INFINITY;
}

// "A" < "B" < "C"; anything missing/non-letter sorts last so it never jumps
// ahead of an explicitly sequenced sign.
function sequenceRank(value: unknown): number {
  if (typeof value !== "string" || value.length === 0) return Number.POSITIVE_INFINITY;
  return value.trim().toUpperCase().charCodeAt(0);
}

// Comparators per type: deployment_priority ascending (lower = stage first),
// then a stable secondary key so it is deterministic which feature is the
// "extra" that gets hidden as the available count drops.
const COMPARATORS: Record<ResourceType, (a: GeoJSON.Feature, b: GeoJSON.Feature) => number> = {
  signs: (a, b) => {
    const pa = a.properties ?? {};
    const pb = b.properties ?? {};
    return (
      num(pa.deployment_priority) - num(pb.deployment_priority) ||
      sequenceRank(pa.sequence) - sequenceRank(pb.sequence) ||
      num(pa.closure_rank) - num(pb.closure_rank)
    );
  },
  channelizing: (a, b) => {
    const pa = a.properties ?? {};
    const pb = b.properties ?? {};
    return (
      num(pa.deployment_priority) - num(pb.deployment_priority) ||
      num(pa.closure_rank) - num(pb.closure_rank) ||
      num(pa.device_index) - num(pb.device_index)
    );
  },
  barricades: (a, b) => {
    const pa = a.properties ?? {};
    const pb = b.properties ?? {};
    return (
      num(pa.deployment_priority) - num(pb.deployment_priority) ||
      num(pa.closure_rank) - num(pb.closure_rank)
    );
  },
};

// Stable priority ordering: sort by the type comparator, breaking any remaining
// ties by the feature's original index so the result is fully deterministic.
export function orderByPriority(features: GeoJSON.Feature[], type: ResourceType): GeoJSON.Feature[] {
  return features
    .map((feature, index) => ({ feature, index }))
    .sort((a, b) => COMPARATORS[type](a.feature, b.feature) || a.index - b.index)
    .map((entry) => entry.feature);
}

function clamp(n: number, lo: number, hi: number): number {
  return Math.max(lo, Math.min(hi, n));
}

export function resourceTotals(plan: PlanResponse | null): ResourceCounts {
  const devices = plan?.devices?.features ?? [];
  return {
    barricades: devices.filter(isBarricade).length,
    channelizing: devices.filter(isChannelizing).length,
    signs: plan?.warning_signs?.features.length ?? 0,
  };
}

// Build the filtered sign and device FeatureCollections the map should draw,
// keeping only the top-N highest-priority features of each type. Devices that
// are neither barricades nor channelizing devices (should not happen, but be
// safe) are always retained. When a count is >= that type's total, every
// feature is kept and the collection matches the original exactly.
export function filterPlanResources(
  plan: PlanResponse | null,
  counts: ResourceCounts,
): { warning_signs?: FeatureCollection; devices?: FeatureCollection } {
  if (!plan) return {};

  const signsAll = plan.warning_signs?.features ?? [];
  const devicesAll = plan.devices?.features ?? [];
  const barricades = devicesAll.filter(isBarricade);
  const channelizing = devicesAll.filter(isChannelizing);
  const otherDevices = devicesAll.filter((f) => !isBarricade(f) && !isChannelizing(f));

  const keptSigns = orderByPriority(signsAll, "signs").slice(0, clamp(counts.signs, 0, signsAll.length));
  const keptBarricades = orderByPriority(barricades, "barricades").slice(0, clamp(counts.barricades, 0, barricades.length));
  const keptChannelizing = orderByPriority(channelizing, "channelizing").slice(
    0,
    clamp(counts.channelizing, 0, channelizing.length),
  );

  const keptDevices = new Set<GeoJSON.Feature>([...keptBarricades, ...keptChannelizing, ...otherDevices]);

  return {
    warning_signs: plan.warning_signs
      ? { ...plan.warning_signs, features: signsAll.filter((f) => keptSigns.includes(f)) }
      : undefined,
    devices: plan.devices
      ? { ...plan.devices, features: devicesAll.filter((f) => keptDevices.has(f)) }
      : undefined,
  };
}
