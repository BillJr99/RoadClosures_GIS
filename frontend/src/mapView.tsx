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
            pointToLayer={(_, latlng) => L.circleMarker(latlng, { radius: 7, color: "#7c3aed", fillColor: "#a855f7", fillOpacity: 0.9, weight: 2 })}
            onEachFeature={(feature, layer) => layer.bindTooltip(`Advisory sign ${String(feature.properties?.mutcd_sign_code ?? "")}: ${featureTooltip(feature, "sign")}`)}
          />
        )}
        {displayDevices && (
          <GeoJSON
            key={`devices-${planVersion}-${displayDevices.features.length}`}
            data={displayDevices}
            pointToLayer={(feature, latlng) =>
              feature.properties?.kind === "barricade"
                ? L.circleMarker(latlng, { radius: 7, color: "#9d174d", fillColor: "#db2777", fillOpacity: 0.95, weight: 2 })
                : L.circleMarker(latlng, { radius: 4, color: "#c2410c", fillColor: "#f97316", fillOpacity: 0.9, weight: 1 })
            }
            onEachFeature={(feature, layer) =>
              layer.bindTooltip(`${String(feature.properties?.device_type ?? "device")}: ${featureTooltip(feature, "device")}`)
            }
          />
        )}
        {incident && (
          <Pane name="incident-pane" style={{ zIndex: 750 }}>
            <CircleMarker
              center={[incident.lat, incident.lon]}
              radius={8}
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
