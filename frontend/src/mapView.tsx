import React, { useEffect, useState } from "react";
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Pane,
  ScaleControl,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import { CENTER } from "./api";
import type { Incident, PlanLayers, PlanResponse } from "./types";
import { computeColocationOffsets, pointFeatureKey, type LonLat } from "./colocation";
import { incidentDistanceText } from "./distance";

// The co-located point de-overlap math lives in ./colocation (pure, unit-tested
// under jsdom). Re-exported here so existing importers of mapView keep working.
export { computeColocationOffsets } from "./colocation";

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

// Lon/lat of a Point feature (our marker layers are all points), else null.
function featureLonLat(feature: GeoJSON.Feature): [number, number] | null {
  if (feature.geometry?.type !== "Point") return null;
  const coords = feature.geometry.coordinates as number[];
  return [coords[0], coords[1]];
}

// Bind a hover tooltip to a point marker that appends the live straight-line
// distance to the current incident(s). The incident list is read from a ref on
// each hover so distances stay correct without re-mounting the (large) marker
// layers every time the incident moves.
function bindPointTooltip(
  feature: GeoJSON.Feature,
  layer: L.Layer,
  baseHtml: string,
  incidentsRef: React.MutableRefObject<Incident[]>,
): void {
  layer.bindTooltip(baseHtml);
  const lonLat = featureLonLat(feature);
  if (!lonLat) return;
  layer.on("mouseover", () => {
    const distance = incidentDistanceText(lonLat[0], lonLat[1], incidentsRef.current);
    layer.setTooltipContent(
      distance ? `${baseHtml}<br><span class="tooltip-distance">${distance}</span>` : baseHtml,
    );
  });
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
  // Current incident(s) in placement order (primary first). Held in a ref so
  // marker hover tooltips can read the latest positions without re-mounting the
  // large hydrant/sign/device layers whenever the incident moves.
  const incidents = React.useMemo<Incident[]>(
    () => (incident ? [incident, ...secondaryIncidents] : []),
    [incident, secondaryIncidents],
  );
  const incidentsRef = React.useRef<Incident[]>(incidents);
  incidentsRef.current = incidents;
  return (
    <section className="map-panel">
      {loadToast && <div className="toast">{loadToast}</div>}
      <MapContainer center={CENTER} zoom={12} className="map" preferCanvas>
        <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
        {/* Distance reference: an imperial scale bar (feet/miles, matching the
            planner's units) so the map conveys a sense of distance at a glance. */}
        <ScaleControl position="bottomleft" imperial metric={false} />
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
            onEachFeature={(feature, layer) => bindPointTooltip(feature, layer, `Hydrant: ${featureTooltip(feature, "hydrant")}`, incidentsRef)}
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
            key={`plan-closures-${planVersion}-${displayPlanLayers.closures.features.length}`}
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
            onEachFeature={(feature, layer) => bindPointTooltip(feature, layer, `Advisory sign ${String(feature.properties?.mutcd_sign_code ?? "")}: ${featureTooltip(feature, "sign")}`, incidentsRef)}
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
              bindPointTooltip(feature, layer, `${String(feature.properties?.device_type ?? "device")}: ${featureTooltip(feature, "device")}`, incidentsRef)
            }
          />
        )}
        {incident && (
          // All incident dots share the same red styling (primary and
          // secondaries alike) and carry a permanent number label: the primary
          // is "1" and secondaries are numbered 2, 3, … in placement order.
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
              <Tooltip permanent direction="center" className="incident-number">1</Tooltip>
            </CircleMarker>
            {secondaryIncidents.map((item, index) => (
              <CircleMarker
                key={`secondary-${item.lat}-${item.lon}-${index}`}
                center={[item.lat, item.lon]}
                radius={11}
                pathOptions={{ className: "incident-marker", color: "#b42318", fillColor: "#c83525", fillOpacity: 0.9, weight: 3 }}
              >
                <Tooltip permanent direction="center" className="incident-number">{index + 2}</Tooltip>
              </CircleMarker>
            ))}
          </Pane>
        )}
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
              // Amber ring when the hydrant's hose run exceeds the envelope
              // (fallback selection); matches `.legend-swatch.envelope-exceeded`.
              const exceedsEnvelope = Boolean(props.exceeds_envelope);
              const ringColor = exceedsEnvelope ? "#f59e0b" : "#38bdf8";
              return (
                <CircleMarker
                  key={`selected-hydrant-${index}-${planVersion}`}
                  center={[coords[1], coords[0]]}
                  radius={10}
                  pathOptions={{ color: ringColor, weight: 4, fillColor: ringColor, fillOpacity: 0.1 }}
                >
                  <Tooltip>
                    Selected hydrant {index + 1}: {String(props.name || props.source || "hydrant")}
                    {exceedsEnvelope ? ` — exceeds hose envelope by ${props.hose_deficit_ft} ft` : ""}
                    {incidents.length ? (
                      <>
                        <br />
                        <span className="tooltip-distance">{incidentDistanceText(coords[0], coords[1], incidents)}</span>
                      </>
                    ) : null}
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
          <span><i className="legend-swatch envelope-exceeded" /> Hydrant beyond hose envelope</span>
          <span><i className="legend-line hose" /> Hose path</span>
          <span><i className="legend-line closure-line" /> Closure</span>
          <span><i className="legend-swatch sign" /> Sign</span>
          <span><i className="legend-swatch barricade" /> Barricade</span>
          <span><i className="legend-swatch device" /> Channelizing device</span>
          <span className="legend-hint">Scale bar (lower-left) shows distance.</span>
          <span className="legend-hint">Hover a point for its distance to the incident.</span>
        </div>
      )}
    </section>
  );
}
