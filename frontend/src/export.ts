import type { Incident, PlanResponse } from "./types";
import { formatCoords } from "./format";

// Field-deployment exports built from the plan the UI already holds — no server
// round-trip and no extra dependencies. CSVs are ordered by deployment_priority
// so the rows match field set-up order.

function csvCell(value: unknown): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function toCsv(headers: string[], rows: unknown[][]): string {
  return [headers, ...rows].map((row) => row.map(csvCell).join(",")).join("\n");
}

function priority(value: unknown): number {
  const n = Number(value);
  return Number.isFinite(n) ? n : Number.POSITIVE_INFINITY;
}

function coords(feature: GeoJSON.Feature): [number, number] | null {
  if (feature.geometry?.type !== "Point") return null;
  return feature.geometry.coordinates as [number, number];
}

export function signAndDeviceCsv(plan: PlanResponse): string {
  const rows: unknown[][] = [];
  const signs = plan.warning_signs?.features ?? [];
  const devices = plan.devices?.features ?? [];
  for (const feature of [...signs, ...devices]) {
    const p = feature.properties ?? {};
    const c = coords(feature);
    rows.push([
      p.deployment_label ?? "",
      p.deployment_priority ?? "",
      p.kind ?? "",
      p.mutcd_sign_code ?? p.device_type ?? "",
      p.sign_label ?? "",
      p.approach_road ?? "",
      p.distance_from_closure_ft ?? "",
      p.placement_status ?? "",
      c ? c[1] : "",
      c ? c[0] : "",
    ]);
  }
  rows.sort((a, b) => priority(a[1]) - priority(b[1]));
  return toCsv(
    ["priority_label", "priority", "kind", "code", "legend", "approach_road", "distance_ft", "placement", "lat", "lon"],
    rows,
  );
}

export function closureCsv(plan: PlanResponse): string {
  const rows = plan.ranked_closures.map((closure) => [
    closure.deployment_label ?? "",
    closure.deployment_priority ?? "",
    closure.rank ?? "",
    closure.name ?? "",
    closure.capacity ?? "",
    closure.sightline ?? "",
    closure.reason ?? "",
  ]);
  rows.sort((a, b) => priority(a[1]) - priority(b[1]));
  return toCsv(["priority_label", "priority", "rank", "road", "cost", "sightline", "reason"], rows);
}

export function downloadCsv(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

function escapeHtml(value: unknown): string {
  return String(value ?? "").replace(/[&<>]/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[ch] as string));
}

// Leaflet served from a CDN so the standalone printable report (opened in a
// blank window via document.write) can render an OSM map without bundling
// anything. Version pinned to match the app's leaflet dependency.
const LEAFLET_CSS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";
const LEAFLET_JS_URL = "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";

// JSON embedded inside an inline <script> must not contain a literal "</script>"
// or a raw "<" that could prematurely close the tag, so escape "<".
function embedJson(value: unknown): string {
  return JSON.stringify(value).replace(/</g, "\\u003c");
}

// Build the "Incident map" section: a ~640x420 Leaflet map using the same OSM
// tiles as the main app, with the incident marker plus the hydrant, hose line,
// closures, and signs drawn as GeoJSON overlays so the print matches the
// on-screen map. Returns "" when there is no incident and no plottable plan
// geometry. A <noscript> static-image fallback covers JS-disabled prints, and
// the inline script falls back to the same static image if Leaflet fails.
function incidentMapSection(plan: PlanResponse, incident: Incident | null): string {
  const hoseFeatures = plan.hose_routes?.features?.length
    ? plan.hose_routes.features
    : plan.hose_route
      ? [plan.hose_route]
      : [];
  const closureFeatures = plan.closures?.features ?? [];
  const hydrantFeatures = plan.selected_hydrants?.features?.length
    ? plan.selected_hydrants.features
    : plan.selected_hydrant
      ? [plan.selected_hydrant]
      : [];
  const signFeatures = plan.warning_signs?.features ?? [];

  let center: [number, number] | null = incident ? [incident.lat, incident.lon] : null;
  if (!center) {
    const geom = hydrantFeatures[0]?.geometry;
    if (geom?.type === "Point") {
      const coords = geom.coordinates as [number, number];
      center = [coords[1], coords[0]];
    }
  }
  if (!center) return "";

  const data = {
    center,
    incident: incident ? [incident.lat, incident.lon] : null,
    hose: { type: "FeatureCollection", features: hoseFeatures },
    closures: { type: "FeatureCollection", features: closureFeatures },
    hydrants: { type: "FeatureCollection", features: hydrantFeatures },
    signs: { type: "FeatureCollection", features: signFeatures },
  };
  const staticImg = `https://staticmap.openstreetmap.de/staticmap.php?center=${center[0]},${center[1]}&zoom=16&size=640x420&markers=${center[0]},${center[1]},red`;

  return `
  <h2>Incident map</h2>
  <div id="report-map" style="width:640px;max-width:100%;height:420px;border:1px solid #cbd2d9;border-radius:6px;overflow:hidden;">
    <noscript><img src="${staticImg}" width="640" height="420" alt="Incident area map" /></noscript>
  </div>
  <div class="report-map-legend" style="display:flex;flex-wrap:wrap;gap:14px;margin:8px 0 4px;font-size:12px;color:#334e68;width:640px;max-width:100%;">
    <span style="display:flex;align-items:center;gap:6px;"><i style="display:inline-block;width:12px;height:12px;border-radius:50%;background:#c83525;"></i>Incident</span>
    <span style="display:flex;align-items:center;gap:6px;"><i style="display:inline-block;width:12px;height:12px;border-radius:50%;border:2px solid #38bdf8;background:rgba(56,189,248,0.2);box-sizing:border-box;"></i>Selected hydrant</span>
    <span style="display:flex;align-items:center;gap:6px;"><i style="display:inline-block;width:18px;height:4px;border-radius:2px;background:#0969da;"></i>Hose path</span>
    <span style="display:flex;align-items:center;gap:6px;"><i style="display:inline-block;width:18px;height:4px;border-radius:2px;background:#dc2626;"></i>Closure</span>
    <span style="display:flex;align-items:center;gap:6px;"><i style="display:inline-block;width:12px;height:12px;border-radius:50%;border:2px solid #7c3aed;background:#a855f7;box-sizing:border-box;"></i>Sign</span>
  </div>
  <script>
  (function () {
    var DATA = ${embedJson(data)};
    function fallback() {
      var el = document.getElementById("report-map");
      if (el) el.innerHTML = '<img src="${staticImg}" width="640" height="420" alt="Incident area map" />';
    }
    try {
      if (!window.L) { fallback(); return; }
      var map = L.map("report-map").setView(DATA.center, 16);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
      }).addTo(map);
      var bounds = L.latLngBounds([]);
      function extend(layer) { try { var b = layer.getBounds(); if (b && b.isValid()) bounds.extend(b); } catch (e) {} }
      if (DATA.closures.features.length) extend(L.geoJSON(DATA.closures, { style: { color: "#dc2626", weight: 5, opacity: 0.95 } }).addTo(map));
      if (DATA.hose.features.length) extend(L.geoJSON(DATA.hose, { style: { color: "#0969da", weight: 5, opacity: 0.95 } }).addTo(map));
      if (DATA.signs.features.length) extend(L.geoJSON(DATA.signs, { pointToLayer: function (f, ll) { return L.circleMarker(ll, { radius: 6, color: "#7c3aed", fillColor: "#a855f7", fillOpacity: 0.9, weight: 2 }); } }).addTo(map));
      if (DATA.hydrants.features.length) extend(L.geoJSON(DATA.hydrants, { pointToLayer: function (f, ll) { return L.circleMarker(ll, { radius: 8, color: "#38bdf8", fillColor: "#38bdf8", fillOpacity: 0.2, weight: 4 }); } }).addTo(map));
      if (DATA.incident) {
        L.circleMarker(DATA.incident, { radius: 8, color: "#b42318", fillColor: "#c83525", fillOpacity: 0.9, weight: 3 }).addTo(map).bindTooltip("Incident");
        bounds.extend(DATA.incident);
      }
      if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24], maxZoom: 17 });
      else map.setView(DATA.center, 16);
      setTimeout(function () { map.invalidateSize(); }, 200);
    } catch (e) { fallback(); }
  })();
  </script>`;
}

export function printableReportHtml(plan: PlanResponse, incident: Incident | null): string {
  const closureRows = plan.ranked_closures
    .map(
      (c) =>
        `<tr><td>${escapeHtml(c.deployment_label)}</td><td>${escapeHtml(c.name)}</td><td>${escapeHtml(
          c.sightline,
        )}</td><td>${escapeHtml(c.reason)}</td></tr>`,
    )
    .join("");
  const signRows = (plan.warning_signs?.features ?? [])
    .map(
      (f) =>
        `<tr><td>${escapeHtml(f.properties?.deployment_label)}</td><td>${escapeHtml(
          f.properties?.mutcd_sign_code,
        )}</td><td>${escapeHtml(f.properties?.approach_road)}</td><td>${escapeHtml(
          f.properties?.distance_from_closure_ft,
        )} ft</td><td>${escapeHtml(f.properties?.placement_status)}</td></tr>`,
    )
    .join("");
  const compliance = plan.compliance
    ? `<p>Approach coverage: ${escapeHtml(plan.compliance.approach_sides_covered)}/${escapeHtml(
        plan.compliance.approach_sides_total,
      )} sides.</p>`
    : "";
  return `<!doctype html><html><head><meta charset="utf-8"><title>Road Closure Plan</title>
<link rel="stylesheet" href="${LEAFLET_CSS_URL}" />
<script src="${LEAFLET_JS_URL}"></script>
<style>
  body { font-family: system-ui, sans-serif; margin: 24px; color: #1f2933; }
  h1 { font-size: 18px; } h2 { font-size: 14px; margin-top: 20px; }
  table { border-collapse: collapse; width: 100%; font-size: 12px; }
  th, td { border: 1px solid #cbd2d9; padding: 4px 6px; text-align: left; }
  #report-map { margin: 8px 0; }
  @media print { button { display: none; } }
</style></head><body>
  <h1>Road Closure Deployment Plan</h1>
  <p>Incident: ${incident ? escapeHtml(formatCoords(incident.lat, incident.lon)) : "n/a"}</p>
  ${plan.feasible === false ? `<p><strong>Warning:</strong> ${escapeHtml(plan.feasibility_note)}</p>` : ""}
  ${incidentMapSection(plan, incident)}
  ${compliance}
  <h2>Closures (by deployment priority)</h2>
  <table><thead><tr><th>Priority</th><th>Road</th><th>Sightline</th><th>Reason</th></tr></thead><tbody>${closureRows}</tbody></table>
  <h2>Advance-warning signs</h2>
  <table><thead><tr><th>Priority</th><th>MUTCD</th><th>Approach</th><th>Distance</th><th>Placement</th></tr></thead><tbody>${signRows}</tbody></table>
  <button onclick="window.print()">Print</button>
</body></html>`;
}

export function openPrintableReport(plan: PlanResponse, incident: Incident | null): void {
  const win = window.open("", "_blank");
  if (!win) return;
  win.document.write(printableReportHtml(plan, incident));
  win.document.close();
}
