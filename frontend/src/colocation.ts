// --- Co-located point de-overlap helpers -----------------------------------
// When two plan point markers (warning signs / devices) snap to the same
// location they draw on top of each other and only one is visible. To keep
// every marker readable we fan co-located markers out symmetrically along the
// axis PERPENDICULAR to the nearest road. This is a purely visual nudge: the
// underlying feature data, tooltips, exports, and priority filtering are never
// touched — only the drawn position changes.
//
// These helpers are pure (no Leaflet / react-leaflet imports) so they can be
// unit-tested under jsdom without rendering a map. mapView.tsx imports them and
// adds the Leaflet-specific glue (applyOffset).

// Spacing between adjacent fanned-out members, in degrees (~4-5 m at this
// latitude). Small and fixed so markers sit adjacent but clearly separate.
export const COLOCATION_SPACING_DEG = 0.00004;

// Decimal places used to bucket coincident points (~1 m at 5 places). Points
// that round to the same key are treated as co-located.
export const COLOCATION_KEY_PRECISION = 5;

export type LonLat = [number, number];

// Perpendicular unit vector of a road segment, mirroring the vector math in
// main.tsx's `offsetLineFeature` (perp of (dx,dy) is (-dy,dx), normalized).
// Implemented locally on purpose — we do not import from main.tsx.
export function perpendicularUnit(from: LonLat, to: LonLat): LonLat {
  const dx = to[0] - from[0];
  const dy = to[1] - from[1];
  const length = Math.hypot(dx, dy) || 1;
  return [-dy / length, dx / length];
}

// Squared distance from point p to segment [a, b] in lon/lat space. Degrees
// are fine here because we only ever compare nearby candidate segments to pick
// the closest one (no need for true geodesic distance).
export function distanceSqToSegment(p: LonLat, a: LonLat, b: LonLat): number {
  const abx = b[0] - a[0];
  const aby = b[1] - a[1];
  const apx = p[0] - a[0];
  const apy = p[1] - a[1];
  const abLenSq = abx * abx + aby * aby;
  const t = abLenSq === 0 ? 0 : Math.max(0, Math.min(1, (apx * abx + apy * aby) / abLenSq));
  const cx = a[0] + t * abx;
  const cy = a[1] + t * aby;
  const ddx = p[0] - cx;
  const ddy = p[1] - cy;
  return ddx * ddx + ddy * ddy;
}

// Walk every LineString segment of the provided line layers and return the
// perpendicular unit vector of the segment closest to `point`. Falls back to
// east-west ([1, 0]) when no usable line is available.
export function perpendicularAtPoint(
  point: LonLat,
  lineLayers: Array<GeoJSON.FeatureCollection | null | undefined>,
): LonLat {
  let bestDist = Infinity;
  let bestPerp: LonLat | null = null;
  for (const collection of lineLayers) {
    if (!collection?.features) continue;
    for (const feature of collection.features) {
      const geom = feature?.geometry;
      if (!geom || geom.type !== "LineString") continue;
      const coords = geom.coordinates as LonLat[];
      for (let i = 0; i + 1 < coords.length; i += 1) {
        const a = coords[i];
        const b = coords[i + 1];
        if (!a || !b) continue;
        const dist = distanceSqToSegment(point, a, b);
        if (dist < bestDist) {
          bestDist = dist;
          bestPerp = perpendicularUnit(a, b);
        }
      }
    }
  }
  // Fallback: nudge east-west when there is no line to align against.
  return bestPerp ?? [1, 0];
}

// A stable identity for a point feature so we can look its offset up again in
// `pointToLayer` (which only receives the feature, not an index). Built from
// the rounded geometry plus a few discriminating properties; good enough to
// distinguish co-located-but-distinct features in practice.
export function pointFeatureKey(feature: GeoJSON.Feature): string {
  const coords =
    feature.geometry?.type === "Point" ? (feature.geometry.coordinates as LonLat) : [0, 0];
  const props = feature.properties ?? {};
  const tag = String(
    props.kind ??
      props.device_type ??
      props.mutcd_sign_code ??
      props.sequence ??
      props.deployment_label ??
      "",
  );
  return `${coords[0]},${coords[1]}|${tag}`;
}

// Compute a per-feature lon/lat offset (in degrees) that fans co-located
// markers out perpendicular to the nearest road. Returns a map keyed by
// `pointFeatureKey`. Resilient to null/empty inputs.
export function computeColocationOffsets(
  pointLayers: Array<GeoJSON.FeatureCollection | null | undefined>,
  lineLayers: Array<GeoJSON.FeatureCollection | null | undefined>,
): Map<string, LonLat> {
  const offsets = new Map<string, LonLat>();
  // Bucket every drawn point feature by its rounded location.
  const groups = new Map<string, GeoJSON.Feature[]>();
  for (const collection of pointLayers) {
    if (!collection?.features) continue;
    for (const feature of collection.features) {
      if (feature?.geometry?.type !== "Point") continue;
      const coords = feature.geometry.coordinates as LonLat;
      const groupKey = `${coords[0].toFixed(COLOCATION_KEY_PRECISION)},${coords[1].toFixed(
        COLOCATION_KEY_PRECISION,
      )}`;
      const bucket = groups.get(groupKey);
      if (bucket) bucket.push(feature);
      else groups.set(groupKey, [feature]);
    }
  }

  for (const members of groups.values()) {
    if (members.length < 2) continue; // nothing to de-overlap
    const coords = (members[0].geometry as GeoJSON.Point).coordinates as LonLat;
    const [px, py] = perpendicularAtPoint(coords, lineLayers);
    // Center the spread on the true point: e.g. for 2 members use offsets
    // (-0.5, +0.5); for 3 use (-1, 0, +1); etc.
    const mid = (members.length - 1) / 2;
    members.forEach((feature, index) => {
      const factor = (index - mid) * COLOCATION_SPACING_DEG;
      offsets.set(pointFeatureKey(feature), [px * factor, py * factor]);
    });
  }
  return offsets;
}
