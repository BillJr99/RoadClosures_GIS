import React, { useEffect, useState } from "react";
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Pane,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import { CENTER } from "./api";
import type { Incident, PlanLayers, PlanResponse } from "./types";

// --- Co-located point de-overlap helpers -----------------------------------
// When two plan point markers (warning signs / devices) snap to the same
// location they draw on top of each other and only one is visible. To keep
// every marker readable we fan co-located markers out symmetrically along the
// axis PERPENDICULAR to the nearest road. This is a purely visual nudge: the
// underlying feature data, tooltips, exports, and priority filtering are never
// touched — only the drawn position changes.

// Spacing between adjacent fanned-out members, in degrees (~4-5 m at this
// latitude). Small and fixed so markers sit adjacent but clearly separate.
const COLOCATION_SPACING_DEG = 0.00004;

// Decimal places used to bucket coincident points (~1 m at 5 places). Points
// that round to the same key are treated as co-located.
const COLOCATION_KEY_PRECISION = 5;

type LonLat = [number, number];

// Perpendicular unit vector of a road segment, mirroring the vector math in
// main.tsx's `offsetLineFeature` (perp of (dx,dy) is (-dy,dx), normalized).
// Implemented locally on purpose — we do not import from main.tsx.
function perpendicularUnit(from: LonLat, to: LonLat): LonLat {
  const dx = to[0] - from[0];
  const dy = to[1] - from[1];
  const length = Math.hypot(dx, dy) || 1;
  return [-dy / length, dx / length];
}

// Squared distance from point p to segment [a, b] in lon/lat space. Degrees
// are fine here because we only ever compare nearby candidate segments to pick
// the closest one (no need for true geodesic distance).
function distanceSqToSegment(p: LonLat, a: LonLat, b: LonLat): number {
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
function perpendicularAtPoint(
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
function pointFeatureKey(feature: GeoJSON.Feature): string {
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

// Look up the offset for a feature and apply it to a Leaflet latlng. Leaflet
// latlng is (lat, lng) while our offsets are (lon, lat) deltas.
function applyOffset(
  feature: GeoJSON.Feature,
  latlng: L.LatLng,
  offsets: Map<string, LonLat>,
): L.LatLng {
  const offset = offsets.get(pointFeatureKey(feature));
  if (!offset) return latlng;
  return L.latLng(latlng.lat + offset[1], latlng.lng + offset[0]);
}

export function featureTooltip(feature: GeoJSON.Feature, fallback: string): string {
  const props = feature.properties ?? {};
  const label = String(
    props.name ||
      props.county_st_name ||
      props.source ||
      props.kind ||
      props.approach_road ||
      fallback,
  );
  return props.deployment_label ? `${String(props.deployment_label)} · ${label}` : label;
}

function IncidentClick({
  incident,
  secondaryIncidentMode,
  manualHydrantPickMode,
  onPick,
  onPickSecondary,
  onPickManualHydrant,
  onExistingIncident,
}: {
  incident: Incident | null;
  secondaryIncidentMode: boolean;
  manualHydrantPickMode: boolean;
  onPick: (incident: Incident) => void;
  onPickSecondary: (incident: Incident) => void;
  onPickManualHydrant: (incident: Incident) => void;
  onExistingIncident: () => void;
}) {
  useMapEvents({
    click(event) {
      const target = event.originalEvent.target;
      if (target instanceof Element && target.closest(".leaflet-marker-icon")) {
        return;
      }
      if (manualHydrantPickMode) {
        onPickManualHydrant({ lat: event.latlng.lat, lon: event.latlng.lng });
        return;
      }
      if (incident && event.latlng.distanceTo(L.latLng(incident.lat, incident.lon)) <= 50) {
        onExistingIncident();
        return;
      }
      if (secondaryIncidentMode) {
        onPickSecondary({ lat: event.latlng.lat, lon: event.latlng.lng });
        return;
      }
      onPick({ lat: event.latlng.lat, lon: event.latlng.lng });
    },
  });
  return null;
}

function PlanFocus({ plan, version }: { plan: PlanResponse | null; version: number }) {
  const map = useMap();
  useEffect(() => {
    if (!plan?.overlays.features.length) return;
    const layer = L.geoJSON(plan.overlays);
    const bounds = layer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds, { padding: [36, 36], maxZoom: 17 });
    }
  }, [map, plan, version]);
  return null;
}

function IncidentFocus({ incident }: { incident: Incident | null }) {
  const map = useMap();
  useEffect(() => {
    if (incident) {
      map.flyTo([incident.lat, incident.lon], Math.max(map.getZoom(), 15), { duration: 0.7 });
    }
  }, [incident, map]);
  return null;
}

// Renders children only at or above `minZoom`. Used to skip drawing the large
// county-wide road layer when zoomed far out, where it is expensive and not
// useful.
function ZoomGate({ minZoom, children }: { minZoom: number; children: React.ReactNode }) {
  const map = useMap();
  const [zoom, setZoom] = useState(() => map.getZoom());
  useMapEvents({ zoomend: () => setZoom(map.getZoom()) });
  return zoom >= minZoom ? <>{children}</> : null;
}

export type MapViewProps = {
  roads: GeoJSON.FeatureCollection | null;
  hydrants: GeoJSON.FeatureCollection | null;
  incident: Incident | null;
  secondaryIncidents: Incident[];
  secondaryIncidentMode: boolean;
  manualHydrantPickMode: boolean;
  plan: PlanResponse | null;
  planVersion: number;
  displayPlanLayers: PlanLayers | null;
  displaySigns: GeoJSON.FeatureCollection | null;
  displayDevices: GeoJSON.FeatureCollection | null;
  selectedHydrantFeatures: GeoJSON.Feature[];
  loadToast: string | null;
  onPick: (incident: Incident) => void;
  onPickSecondary: (incident: Incident) => void;
  onPickManualHydrant: (incident: Incident) => void;
  onExistingIncident: () => void;
};

export function MapView({
  roads,
  hydrants,
  incident,
  secondaryIncidents,
  secondaryIncidentMode,
  manualHydrantPickMode,
  plan,
  planVersion,
  displayPlanLayers,
  displaySigns,
  displayDevices,
  selectedHydrantFeatures,
  loadToast,
  onPick,
  onPickSecondary,
  onPickManualHydrant,
  onExistingIncident,
}: MapViewProps) {
  // Per-feature visual offsets that fan co-located sign/device markers out
  // perpendicular to the nearest road so overlapping markers stay readable.
  // Recomputed only when the drawn point/line layers change.
  const colocationOffsets = React.useMemo(
    () =>
      computeColocationOffsets(
        [displaySigns, displayDevices],
        [displayPlanLayers?.closures, displayPlanLayers?.hose],
      ),
    [displaySigns, displayDevices, displayPlanLayers],
  );
  return (
    <section className="map-panel">
      {loadToast && <div className="toast">{loadToast}</div>}
      <MapContainer center={CENTER} zoom={12} className="map" preferCanvas>
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        <IncidentClick
          incident={incident}
          secondaryIncidentMode={secondaryIncidentMode}
          manualHydrantPickMode={manualHydrantPickMode}
          onPick={onPick}
          onPickSecondary={onPickSecondary}
          onPickManualHydrant={onPickManualHydrant}
          onExistingIncident={onExistingIncident}
        />
        <IncidentFocus incident={incident} />
        <PlanFocus plan={plan} version={planVersion} />
        {roads && (
          <ZoomGate minZoom={11}>
            <GeoJSON
              data={roads}
              style={{ color: "#74808c", weight: 1, opacity: 0.6 }}
              onEachFeature={(feature, layer) => layer.bindTooltip(`Road: ${featureTooltip(feature, "road")}`)}
            />
          </ZoomGate>
        )}
        {hydrants && (
          <GeoJSON
            data={hydrants}
            pointToLayer={(_, latlng) => L.circleMarker(latlng, { radius: 4, color: "#1677a3", fillOpacity: 0.8 })}
            onEachFeature={(feature, layer) => layer.bindTooltip(`Hydrant: ${featureTooltip(feature, "hydrant")}`)}
          />
        )}
        {displayPlanLayers?.other.features.length ? (
          <GeoJSON
            key={`plan-other-${planVersion}`}
            data={displayPlanLayers.other}
            style={{ color: "#d9480f", weight: 4 }}
            onEachFeature={(feature, layer) => layer.bindTooltip(featureTooltip(feature, "plan feature"))}
          />
        ) : null}
        {displayPlanLayers?.hose.features.length ? (
          <GeoJSON
            key={`plan-hose-${planVersion}`}
            data={displayPlanLayers.hose}
            style={{ color: "#0969da", weight: 5, opacity: 0.95 }}
            onEachFeature={(feature, layer) => layer.bindTooltip(`Hose path: ${featureTooltip(feature, "hydrant to incident")}`)}
          />
        ) : null}
        {displayPlanLayers?.closures.features.length ? (
          <GeoJSON
            key={`plan-closures-${planVersion}`}
            data={displayPlanLayers.closures}
            style={{ color: "#dc2626", weight: 5, opacity: 0.95 }}
            onEachFeature={(feature, layer) => layer.bindTooltip(`Closure: ${featureTooltip(feature, "road segment")}`)}
          />
        ) : null}
        {displaySigns && (
          <GeoJSON
            key={`warning-signs-${planVersion}-${displaySigns.features.length}`}
            data={displaySigns}
            pointToLayer={(feature, latlng) =>
              L.circleMarker(applyOffset(feature, latlng, colocationOffsets), { radius: 7, color: "#7c3aed", fillColor: "#a855f7", fillOpacity: 0.9, weight: 2 })
            }
            onEachFeature={(feature, layer) => layer.bindTooltip(`Advisory sign ${String(feature.properties?.mutcd_sign_code ?? "")}: ${featureTooltip(feature, "sign")}`)}
          />
        )}
        {displayDevices && (
          <GeoJSON
            key={`devices-${planVersion}-${displayDevices.features.length}`}
            data={displayDevices}
            pointToLayer={(feature, latlng) => {
              const position = applyOffset(feature, latlng, colocationOffsets);
              return feature.properties?.kind === "barricade"
                ? L.circleMarker(position, { radius: 7, color: "#0f172a", fillColor: "#1f2937", fillOpacity: 0.95, weight: 2 })
                : L.circleMarker(position, { radius: 4, color: "#c2410c", fillColor: "#f97316", fillOpacity: 0.9, weight: 1 });
            }}
            onEachFeature={(feature, layer) =>
              layer.bindTooltip(`${String(feature.properties?.device_type ?? "device")}: ${featureTooltip(feature, "device")}`)
            }
          />
        )}
        {incident && (
          <Pane name="incident-pane" style={{ zIndex: 750 }}>
            <CircleMarker
              center={[incident.lat, incident.lon]}
              radius={11}
              pathOptions={{ bubblingMouseEvents: true, className: "incident-marker", color: "#b42318", fillColor: "#c83525", fillOpacity: 0.9, weight: 3 }}
              eventHandlers={{
                click() {
                  onExistingIncident();
                },
              }}
            >
              <Tooltip>Incident: click again to remove</Tooltip>
            </CircleMarker>
          </Pane>
        )}
        {secondaryIncidents.map((item, index) => (
          <CircleMarker
            key={`${item.lat}-${item.lon}-${index}`}
            center={[item.lat, item.lon]}
            radius={7}
            pathOptions={{ color: "#9a3412", fillColor: "#fb923c", fillOpacity: 0.9, weight: 2 }}
          >
            <Tooltip>Secondary incident {index + 1}</Tooltip>
          </CircleMarker>
        ))}
        {selectedHydrantFeatures.length > 0 && (
          // Highlight the chosen hydrant with a light-blue ring drawn in a
          // high-z-index pane (above the regular hydrant dots and plan layers).
          // Using a CircleMarker ring instead of a default Leaflet <Marker>
          // avoids the default PNG marker icon, which Vite does not bundle and
          // which therefore rendered as a broken image. The low fill opacity
          // keeps the underlying hydrant location visible (emphasized, not
          // hidden). Color matches `.legend-swatch.selected-hydrant` (#38bdf8).
          <Pane name="selected-hydrant-pane" style={{ zIndex: 760 }}>
            {selectedHydrantFeatures.map((feature, index) => {
              if (feature.geometry.type !== "Point") return null;
              const coords = feature.geometry.coordinates as [number, number];
              const props = feature.properties ?? {};
              return (
                <CircleMarker
                  key={`selected-hydrant-${index}-${planVersion}`}
                  center={[coords[1], coords[0]]}
                  radius={10}
                  pathOptions={{ color: "#38bdf8", weight: 4, fillColor: "#38bdf8", fillOpacity: 0.1 }}
                >
                  <Tooltip>
                    Selected hydrant {index + 1}: {String(props.name || props.source || "hydrant")}
                  </Tooltip>
                </CircleMarker>
              );
            })}
          </Pane>
        )}
      </MapContainer>
      {plan && (
        <div className="map-legend">
          <span><i className="legend-swatch incident" /> Incident</span>
          <span><i className="legend-swatch hydrant" /> Hydrant</span>
          <span><i className="legend-swatch selected-hydrant" /> Selected hydrant</span>
          <span><i className="legend-line hose" /> Hose path</span>
          <span><i className="legend-line closure-line" /> Closure</span>
          <span><i className="legend-swatch sign" /> Sign</span>
          <span><i className="legend-swatch barricade" /> Barricade</span>
          <span><i className="legend-swatch device" /> Channelizing device</span>
        </div>
      )}
    </section>
  );
}
