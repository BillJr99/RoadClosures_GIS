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
<style>
  body { font-family: system-ui, sans-serif; margin: 24px; color: #1f2933; }
  h1 { font-size: 18px; } h2 { font-size: 14px; margin-top: 20px; }
  table { border-collapse: collapse; width: 100%; font-size: 12px; }
  th, td { border: 1px solid #cbd2d9; padding: 4px 6px; text-align: left; }
  @media print { button { display: none; } }
</style></head><body>
  <h1>Road Closure Deployment Plan</h1>
  <p>Incident: ${incident ? escapeHtml(formatCoords(incident.lat, incident.lon)) : "n/a"}</p>
  ${plan.feasible === false ? `<p><strong>Warning:</strong> ${escapeHtml(plan.feasibility_note)}</p>` : ""}
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
