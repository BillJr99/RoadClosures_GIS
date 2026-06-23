import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  GeoJSON,
  MapContainer,
  Marker,
  TileLayer,
  Tooltip,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import { Droplets, MapPin, Plus, Route, Search, ShieldAlert, Trash2 } from "lucide-react";
import "leaflet/dist/leaflet.css";
import "./styles.css";
import { formatCoords } from "./format";

const API = import.meta.env.VITE_API_BASE ?? "http://localhost:8001/api";
const CENTER: [number, number] = [40.195, -75.425];

type FeatureCollection = GeoJSON.FeatureCollection;

type ManualHydrant = {
  manual_id: string;
  name: string;
  lat: number;
  lon: number;
  flow_class: string;
  source_note: string;
  status: string;
  updated_at: string;
};

type Incident = { lat: number; lon: number };

type PlanResponse = {
  cut_value: number;
  selected_hydrant: GeoJSON.Feature;
  hose_route: GeoJSON.Feature;
  closures: FeatureCollection;
  overlays: FeatureCollection;
  ranked_closures: Array<Record<string, unknown>>;
  hydrant_candidates: Array<Record<string, unknown>>;
};

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || response.statusText);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

function IncidentClick({ onPick }: { onPick: (incident: Incident) => void }) {
  useMapEvents({
    click(event) {
      onPick({ lat: event.latlng.lat, lon: event.latlng.lng });
    },
  });
  return null;
}

function App() {
  const [roads, setRoads] = useState<FeatureCollection | null>(null);
  const [hydrants, setHydrants] = useState<FeatureCollection | null>(null);
  const [manualHydrants, setManualHydrants] = useState<ManualHydrant[]>([]);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [address, setAddress] = useState("");
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [message, setMessage] = useState("Load generated layers, then pick an incident.");
  const [manualDraft, setManualDraft] = useState({
    name: "",
    lat: "",
    lon: "",
    flow_class: "unknown",
    source_note: "",
    status: "active",
  });

  async function loadLayers() {
    const [roadLayer, hydrantLayer, manual] = await Promise.all([
      jsonFetch<FeatureCollection>(`${API}/layers/roads`),
      jsonFetch<FeatureCollection>(`${API}/layers/hydrants`),
      jsonFetch<ManualHydrant[]>(`${API}/manual-hydrants`),
    ]);
    setRoads(roadLayer);
    setHydrants(hydrantLayer);
    setManualHydrants(manual);
    setMessage(
      `${roadLayer.features.length} roads, ${hydrantLayer.features.length} hydrants, ${manual.length} manual hydrants loaded.`,
    );
  }

  async function buildLayers() {
    setMessage("Building GIS layers. This can take a while for full Montgomery County.");
    await jsonFetch(`${API}/layers/build?include_graph=true`, { method: "POST" });
    await loadLayers();
  }

  async function geocodeAddress() {
    if (!address.trim()) return;
    const results = await jsonFetch<Array<{ label: string; lat: number; lon: number }>>(
      `${API}/geocode?q=${encodeURIComponent(address)}`,
    );
    if (results.length === 0) {
      setMessage("No geocode result found.");
      return;
    }
    setIncident({ lat: results[0].lat, lon: results[0].lon });
    setMessage(results[0].label);
  }

  async function runPlan() {
    if (!incident) {
      setMessage("Pick an incident location first.");
      return;
    }
    const result = await jsonFetch<PlanResponse>(`${API}/plan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat: incident.lat,
        lon: incident.lon,
        incident_radius_ft: 300,
        study_radius_ft: 2500,
        hose_max_ft: 500,
      }),
    });
    setPlan(result);
    setMessage(`Plan ready: ${result.ranked_closures.length} closure recommendations.`);
  }

  async function addManualHydrant() {
    const lat = Number(manualDraft.lat);
    const lon = Number(manualDraft.lon);
    if (!Number.isFinite(lat) || !Number.isFinite(lon)) {
      setMessage("Manual hydrant needs valid latitude and longitude.");
      return;
    }
    await jsonFetch<ManualHydrant>(`${API}/manual-hydrants`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...manualDraft, lat, lon }),
    });
    setManualDraft({ name: "", lat: "", lon: "", flow_class: "unknown", source_note: "", status: "active" });
    await loadLayers();
  }

  async function removeManualHydrant(id: string) {
    await jsonFetch(`${API}/manual-hydrants/${id}`, { method: "DELETE" });
    await loadLayers();
  }

  useEffect(() => {
    loadLayers().catch((error) => setMessage(`Layer load failed: ${error.message}`));
  }, []);

  const selectedHydrant = useMemo(() => {
    const geom = plan?.selected_hydrant.geometry;
    if (!geom || geom.type !== "Point") return null;
    const coords = geom.coordinates as [number, number];
    return { lat: coords[1], lon: coords[0] };
  }, [plan]);

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <header>
          <h1>Fire Police GIS</h1>
          <p>{message}</p>
        </header>

        <section className="panel">
          <h2><MapPin size={18} /> Incident</h2>
          <div className="inline">
            <input value={address} onChange={(e) => setAddress(e.target.value)} placeholder="Address or place" />
            <button onClick={geocodeAddress} title="Search address"><Search size={18} /></button>
          </div>
          <div className="coords">
            {incident ? formatCoords(incident.lat, incident.lon) : "Click the map to set incident"}
          </div>
          <button className="primary" onClick={runPlan}><ShieldAlert size={18} /> Recommend Closures</button>
        </section>

        <section className="panel">
          <h2><Droplets size={18} /> Manual Hydrants</h2>
          <input value={manualDraft.name} onChange={(e) => setManualDraft({ ...manualDraft, name: e.target.value })} placeholder="Name" />
          <div className="inline">
            <input value={manualDraft.lat} onChange={(e) => setManualDraft({ ...manualDraft, lat: e.target.value })} placeholder="Lat" />
            <input value={manualDraft.lon} onChange={(e) => setManualDraft({ ...manualDraft, lon: e.target.value })} placeholder="Lon" />
          </div>
          <div className="inline">
            <select value={manualDraft.flow_class} onChange={(e) => setManualDraft({ ...manualDraft, flow_class: e.target.value })}>
              <option value="unknown">Unknown</option>
              <option value="red">Red</option>
              <option value="orange">Orange</option>
              <option value="green">Green</option>
              <option value="blue">Blue</option>
            </select>
            <button onClick={addManualHydrant} title="Add manual hydrant"><Plus size={18} /></button>
          </div>
          <div className="list">
            {manualHydrants.map((hydrant) => (
              <div className="list-row" key={hydrant.manual_id}>
                <span>{hydrant.name || hydrant.manual_id}</span>
                <button onClick={() => removeManualHydrant(hydrant.manual_id)} title="Remove"><Trash2 size={16} /></button>
              </div>
            ))}
          </div>
        </section>

        <section className="panel">
          <h2><Route size={18} /> Layers</h2>
          <button onClick={loadLayers}>Reload Layers</button>
          <button onClick={buildLayers}>Build From Sources</button>
        </section>

        {plan && (
          <section className="panel">
            <h2>Closure Ranking</h2>
            <div className="list">
              {plan.ranked_closures.map((closure, index) => (
                <div className="closure" key={index}>
                  <strong>#{String(closure.rank)} {String(closure.name)}</strong>
                  <span>{String(closure.reason)}</span>
                  <span>Cost {String(closure.capacity)} · {String(closure.sightline)}</span>
                </div>
              ))}
            </div>
          </section>
        )}
      </aside>

      <section className="map-panel">
        <MapContainer center={CENTER} zoom={12} className="map">
          <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <IncidentClick onPick={setIncident} />
          {roads && <GeoJSON data={roads} style={{ color: "#74808c", weight: 1, opacity: 0.6 }} />}
          {hydrants && <GeoJSON data={hydrants} pointToLayer={(_, latlng) => L.circleMarker(latlng, { radius: 4, color: "#1677a3", fillOpacity: 0.8 })} />}
          {plan && <GeoJSON data={plan.overlays} style={{ color: "#d9480f", weight: 5 }} />}
          {incident && <Marker position={[incident.lat, incident.lon]}><Tooltip>Incident</Tooltip></Marker>}
          {selectedHydrant && <Marker position={[selectedHydrant.lat, selectedHydrant.lon]}><Tooltip>Selected hydrant</Tooltip></Marker>}
        </MapContainer>
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
