// --- Straight-line distance helpers ----------------------------------------
// Distances shown in map tooltips ("… ft from incident"). Kept pure (no Leaflet
// / react-leaflet imports) so they can be unit-tested under jsdom, following the
// same pattern as ./colocation. The haversine below uses the same spherical
// Earth model (R = 6,371,000 m) as Leaflet's CRS.Earth.distance, so tooltip
// distances stay consistent with the map's scale bar.
import type { Incident } from "./types";

const EARTH_RADIUS_M = 6371000;
const METERS_TO_FEET = 3.280839895;

// Great-circle distance in meters between two lon/lat points.
export function metersBetween(aLon: number, aLat: number, bLon: number, bLat: number): number {
  const rad = Math.PI / 180;
  const dLat = (bLat - aLat) * rad;
  const dLon = (bLon - aLon) * rad;
  const lat1 = aLat * rad;
  const lat2 = bLat * rad;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.min(1, Math.sqrt(h)));
}

// Human-readable distance: whole feet with a thousands separator, plus a miles
// hint once the distance is far enough that feet alone are hard to gauge.
export function formatFeet(feet: number): string {
  const ft = `${Math.round(feet).toLocaleString()} ft`;
  return feet >= 1000 ? `${ft} (${(feet / 5280).toFixed(2)} mi)` : ft;
}

// Distance from a point to each incident. With one incident: "120 ft from
// incident". With several: "to incidents — #1: 120 ft, #2: 340 ft". Returns ""
// when there is no incident selected.
export function incidentDistanceText(lon: number, lat: number, incidents: Incident[]): string {
  if (!incidents.length) return "";
  const feet = (inc: Incident) => metersBetween(lon, lat, inc.lon, inc.lat) * METERS_TO_FEET;
  if (incidents.length === 1) return `${formatFeet(feet(incidents[0]))} from incident`;
  return `to incidents — ${incidents.map((inc, i) => `#${i + 1}: ${formatFeet(feet(inc))}`).join(", ")}`;
}
