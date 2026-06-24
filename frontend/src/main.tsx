import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  GeoJSON,
  MapContainer,
  Marker,
  TileLayer,
  Tooltip,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import {
  Check,
  Droplets,
  FileCheck2,
  Flag,
  MapPin,
  Pencil,
  Play,
  Plus,
  Route,
  Search,
  ShieldAlert,
  Trash2,
  X,
} from "lucide-react";
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

type Scenario = {
  scenario_id: string;
  name: string;
  lat: number;
  lon: number;
  incident_radius_ft: number;
  study_radius_ft: number;
  hose_max_ft: number;
  reviewer_notes: string;
  expected_hydrant_hint: string;
  expected_closure_hint: string;
  status: string;
  updated_at: string;
};

type PlanResponse = {
  cut_value: number;
  selected_hydrant: GeoJSON.Feature;
  hose_route: GeoJSON.Feature;
  closures: FeatureCollection;
  overlays: FeatureCollection;
  warning_signs?: FeatureCollection;
  graph_source?: Record<string, unknown>;
  ranked_closures: Array<Record<string, unknown>>;
  hydrant_candidates: Array<Record<string, unknown>>;
};

type ScenarioRunResult = {
  run_id?: string;
  run_dir: string;
  report_path: string;
  results: Array<{
    scenario_id: string;
    name: string;
    status: string;
    golden_status: string;
    differences: string[];
    error?: string;
  }>;
};

type ScenarioRunListItem = {
  run_id: string;
  report_path: string;
  result_count: number;
  failed_count: number;
  changed_count: number;
  missing_count: number;
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

function IncidentFocus({ incident }: { incident: Incident | null }) {
  const map = useMap();
  useEffect(() => {
    if (incident) {
      map.flyTo([incident.lat, incident.lon], Math.max(map.getZoom(), 15), { duration: 0.7 });
    }
  }, [incident, map]);
  return null;
}

function App() {
  const [roads, setRoads] = useState<FeatureCollection | null>(null);
  const [hydrants, setHydrants] = useState<FeatureCollection | null>(null);
  const [manualHydrants, setManualHydrants] = useState<ManualHydrant[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [editingScenarioId, setEditingScenarioId] = useState<string | null>(null);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [address, setAddress] = useState("");
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [planVersion, setPlanVersion] = useState(0);
  const [isPlanning, setIsPlanning] = useState(false);
  const [scenarioRun, setScenarioRun] = useState<ScenarioRunResult | null>(null);
  const [scenarioRuns, setScenarioRuns] = useState<ScenarioRunListItem[]>([]);
  const [pendingPromoteRunId, setPendingPromoteRunId] = useState<string | null>(null);
  const [pendingRemoveScenarioId, setPendingRemoveScenarioId] = useState<string | null>(null);
  const [runningScenarioId, setRunningScenarioId] = useState<string | null>(null);
  const [message, setMessage] = useState("Load generated layers, then pick an incident.");
  const [manualDraft, setManualDraft] = useState({
    name: "",
    lat: "",
    lon: "",
    flow_class: "unknown",
    source_note: "",
    status: "active",
  });
  const [scenarioDraft, setScenarioDraft] = useState({
    name: "",
    incident_radius_ft: "300",
    study_radius_ft: "2500",
    hose_max_ft: "500",
    reviewer_notes: "",
    expected_hydrant_hint: "",
    expected_closure_hint: "",
    status: "active",
  });

  async function loadLayers() {
    const [roadLayer, hydrantLayer, manual, scenarioRecords, runRecords] = await Promise.all([
      jsonFetch<FeatureCollection>(`${API}/layers/roads`),
      jsonFetch<FeatureCollection>(`${API}/layers/hydrants`),
      jsonFetch<ManualHydrant[]>(`${API}/manual-hydrants`),
      jsonFetch<Scenario[]>(`${API}/scenarios`),
      jsonFetch<ScenarioRunListItem[]>(`${API}/scenario-runs`).catch(() => []),
    ]);
    setRoads(roadLayer);
    setHydrants(hydrantLayer);
    setManualHydrants(manual);
    setScenarios(scenarioRecords);
    setScenarioRuns(runRecords);
    setMessage(
      `${roadLayer.features.length} roads, ${hydrantLayer.features.length} hydrants, ${manual.length} manual hydrants, ${scenarioRecords.length} scenarios loaded.`,
    );
  }

  async function loadScenarios() {
    const scenarioRecords = await jsonFetch<Scenario[]>(`${API}/scenarios`);
    setScenarios(scenarioRecords);
  }

  async function loadScenarioRuns() {
    const runRecords = await jsonFetch<ScenarioRunListItem[]>(`${API}/scenario-runs`);
    setScenarioRuns(runRecords);
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
    setIsPlanning(true);
    setMessage("Calculating closure recommendations. This can take 10-30 seconds.");
    try {
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
      setPlanVersion((version) => version + 1);
      setMessage(`Plan ready: ${result.ranked_closures.length} closure recommendations.`);
    } catch (error) {
      setMessage(`Planner failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setIsPlanning(false);
    }
  }

  function scenarioPayload() {
    const incidentRadius = Number(scenarioDraft.incident_radius_ft);
    const studyRadius = Number(scenarioDraft.study_radius_ft);
    const hoseMax = Number(scenarioDraft.hose_max_ft);
    if (!incident) {
      setMessage("Pick an incident location before saving a scenario.");
      return null;
    }
    if (![incidentRadius, studyRadius, hoseMax].every(Number.isFinite)) {
      setMessage("Scenario distances must be valid numbers.");
      return null;
    }
    return {
      ...scenarioDraft,
      name: scenarioDraft.name.trim() || "Untitled scenario",
      lat: incident.lat,
      lon: incident.lon,
      incident_radius_ft: incidentRadius,
      study_radius_ft: studyRadius,
      hose_max_ft: hoseMax,
    };
  }

  function resetScenarioDraft() {
    setEditingScenarioId(null);
    setScenarioDraft({
      name: "",
      incident_radius_ft: "300",
      study_radius_ft: "2500",
      hose_max_ft: "500",
      reviewer_notes: "",
      expected_hydrant_hint: "",
      expected_closure_hint: "",
      status: "active",
    });
  }

  async function saveScenario() {
    const payload = scenarioPayload();
    if (!payload) return;
    if (editingScenarioId) {
      await jsonFetch<Scenario>(`${API}/scenarios/${editingScenarioId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setMessage(`Scenario updated: ${payload.name}`);
    } else {
      await jsonFetch<Scenario>(`${API}/scenarios`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setMessage(`Scenario saved: ${payload.name}`);
    }
    resetScenarioDraft();
    await loadScenarios();
  }

  function editScenario(scenario: Scenario) {
    setEditingScenarioId(scenario.scenario_id);
    setIncident({ lat: scenario.lat, lon: scenario.lon });
    setScenarioDraft({
      name: scenario.name,
      incident_radius_ft: String(scenario.incident_radius_ft),
      study_radius_ft: String(scenario.study_radius_ft),
      hose_max_ft: String(scenario.hose_max_ft),
      reviewer_notes: scenario.reviewer_notes,
      expected_hydrant_hint: scenario.expected_hydrant_hint,
      expected_closure_hint: scenario.expected_closure_hint,
      status: scenario.status,
    });
    setMessage(`Editing scenario: ${scenario.name}`);
  }

  function loadScenario(scenario: Scenario) {
    setIncident({ lat: scenario.lat, lon: scenario.lon });
    setScenarioDraft({
      name: scenario.name,
      incident_radius_ft: String(scenario.incident_radius_ft),
      study_radius_ft: String(scenario.study_radius_ft),
      hose_max_ft: String(scenario.hose_max_ft),
      reviewer_notes: scenario.reviewer_notes,
      expected_hydrant_hint: scenario.expected_hydrant_hint,
      expected_closure_hint: scenario.expected_closure_hint,
      status: scenario.status,
    });
    setMessage(`Loaded scenario and centered map: ${scenario.name}`);
  }

  async function removeScenario(id: string) {
    if (pendingRemoveScenarioId !== id) {
      setPendingRemoveScenarioId(id);
      setMessage("Click delete again to confirm scenario removal.");
      return;
    }
    try {
      await jsonFetch(`${API}/scenarios/${id}`, { method: "DELETE" });
      if (editingScenarioId === id) resetScenarioDraft();
      await loadScenarios();
      setMessage("Scenario removed.");
    } catch (error) {
      setMessage(`Scenario removal failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setPendingRemoveScenarioId(null);
    }
  }

  async function runScenario(id: string) {
    setRunningScenarioId(id);
    setMessage("Running scenario validation. This can take a while.");
    try {
      const result = await jsonFetch<ScenarioRunResult>(`${API}/scenarios/${id}/run`, { method: "POST" });
      setScenarioRun(result);
      await loadScenarioRuns();
      const first = result.results[0];
      const status = first ? `${first.status}, golden ${first.golden_status}` : "no active scenario run";
      setMessage(`Scenario run complete: ${status}.`);
    } catch (error) {
      setMessage(`Scenario run failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRunningScenarioId(null);
    }
  }

  async function viewScenarioRun(runId: string) {
    const result = await jsonFetch<ScenarioRunResult>(`${API}/scenario-runs/${runId}`);
    setScenarioRun(result);
    setPendingPromoteRunId(null);
    setMessage(`Loaded scenario run ${runId}.`);
  }

  async function loadScenarioPlan(runId: string, scenarioId: string) {
    const saved = await jsonFetch<{ plan: PlanResponse; scenario: Scenario }>(
      `${API}/scenario-runs/${runId}/scenarios/${scenarioId}`,
    );
    setPlan(saved.plan);
    setPlanVersion((version) => version + 1);
    setIncident({ lat: saved.scenario.lat, lon: saved.scenario.lon });
    setMessage(`Loaded saved plan for ${saved.scenario.name}.`);
  }

  async function promoteScenarioRun(runId: string) {
    if (pendingPromoteRunId !== runId) {
      setPendingPromoteRunId(runId);
      setMessage(`Review run ${runId}, then confirm promotion.`);
      return;
    }
    const result = await jsonFetch<{ promoted_count: number }>(`${API}/scenario-runs/${runId}/promote`, {
      method: "POST",
    });
    setPendingPromoteRunId(null);
    await loadScenarioRuns();
    setMessage(`Promoted ${result.promoted_count} scenario summaries.`);
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

  const selectedHydrantProps = plan?.selected_hydrant.properties ?? {};
  const hoseProps = plan?.hose_route.properties ?? {};

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
          <button className="primary" onClick={runPlan} disabled={!incident || isPlanning}>
            <ShieldAlert size={18} /> {isPlanning ? "Recommending..." : "Recommend Closures"}
          </button>
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
          <h2><FileCheck2 size={18} /> Scenarios</h2>
          <input
            value={scenarioDraft.name}
            onChange={(e) => setScenarioDraft({ ...scenarioDraft, name: e.target.value })}
            placeholder="Scenario name"
          />
          <div className="inline three">
            <input
              value={scenarioDraft.incident_radius_ft}
              onChange={(e) => setScenarioDraft({ ...scenarioDraft, incident_radius_ft: e.target.value })}
              placeholder="Incident ft"
            />
            <input
              value={scenarioDraft.study_radius_ft}
              onChange={(e) => setScenarioDraft({ ...scenarioDraft, study_radius_ft: e.target.value })}
              placeholder="Study ft"
            />
            <input
              value={scenarioDraft.hose_max_ft}
              onChange={(e) => setScenarioDraft({ ...scenarioDraft, hose_max_ft: e.target.value })}
              placeholder="Hose ft"
            />
          </div>
          <input
            value={scenarioDraft.expected_hydrant_hint}
            onChange={(e) => setScenarioDraft({ ...scenarioDraft, expected_hydrant_hint: e.target.value })}
            placeholder="Expected hydrant hint"
          />
          <input
            value={scenarioDraft.expected_closure_hint}
            onChange={(e) => setScenarioDraft({ ...scenarioDraft, expected_closure_hint: e.target.value })}
            placeholder="Expected closure hint"
          />
          <div className="inline">
            <select
              value={scenarioDraft.status}
              onChange={(e) => setScenarioDraft({ ...scenarioDraft, status: e.target.value })}
            >
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>
            <button onClick={saveScenario} title={editingScenarioId ? "Update scenario" : "Save scenario"}>
              {editingScenarioId ? <Check size={18} /> : <Plus size={18} />}
            </button>
          </div>
          {editingScenarioId && (
            <button onClick={resetScenarioDraft}><X size={18} /> Cancel Edit</button>
          )}
          <div className="list">
            {scenarios.map((scenario) => (
              <div className="scenario-row" key={scenario.scenario_id}>
                <div>
                  <strong>{scenario.name}</strong>
                  <span>{formatCoords(scenario.lat, scenario.lon)} · {scenario.status}</span>
                </div>
                <div className="row-actions">
                  <button onClick={() => loadScenario(scenario)} title="Load scenario"><MapPin size={16} /></button>
                  <button onClick={() => editScenario(scenario)} title="Edit scenario"><Pencil size={16} /></button>
                  <button
                    onClick={() => runScenario(scenario.scenario_id)}
                    title="Run scenario"
                    disabled={Boolean(runningScenarioId)}
                  >
                    {runningScenarioId === scenario.scenario_id ? <Check size={16} /> : <Play size={16} />}
                  </button>
                  <button onClick={() => removeScenario(scenario.scenario_id)} title="Delete scenario">
                    {pendingRemoveScenarioId === scenario.scenario_id ? <Check size={16} /> : <Trash2 size={16} />}
                  </button>
                </div>
              </div>
            ))}
          </div>
          {scenarioRun && (
            <div className="scenario-result">
              <strong>Last scenario run</strong>
              <span>{scenarioRun.results.length} result(s) · {scenarioRun.report_path}</span>
              {scenarioRun.results.map((result) => (
                <span key={result.scenario_id}>
                  {result.name}: {result.status}, golden {result.golden_status}
                </span>
              ))}
            </div>
          )}
        </section>

        <section className="panel">
          <h2><FileCheck2 size={18} /> Scenario Runs</h2>
          <button onClick={loadScenarioRuns}>Reload Runs</button>
          <div className="list">
            {scenarioRuns.map((run) => (
              <div className="scenario-row" key={run.run_id}>
                <div>
                  <strong>{run.run_id}</strong>
                  <span>
                    {run.result_count} result(s) · {run.failed_count} failed · {run.changed_count} changed · {run.missing_count} missing
                  </span>
                </div>
                <div className="row-actions three-actions">
                  <button onClick={() => viewScenarioRun(run.run_id)} title="Review run"><Search size={16} /></button>
                  <button onClick={() => promoteScenarioRun(run.run_id)} title="Promote run">
                    {pendingPromoteRunId === run.run_id ? <Check size={16} /> : <FileCheck2 size={16} />}
                  </button>
                </div>
              </div>
            ))}
          </div>
          {scenarioRun?.run_id && (
            <div className="scenario-result">
              <strong>Review {scenarioRun.run_id}</strong>
              {scenarioRun.results.map((result) => (
                <button
                  key={result.scenario_id}
                  onClick={() => loadScenarioPlan(scenarioRun.run_id!, result.scenario_id)}
                >
                  <MapPin size={16} /> {result.name}: {result.status}, golden {result.golden_status}
                </button>
              ))}
            </div>
          )}
        </section>

        <section className="panel">
          <h2><Route size={18} /> Layers</h2>
          <button onClick={loadLayers}>Reload Layers</button>
          <button onClick={buildLayers}>Build From Sources</button>
        </section>

        {plan && (
          <section className="panel">
            <h2>Plan Review</h2>
            <div className="scenario-result">
              <strong>Selected hydrant</strong>
              <span>{String(selectedHydrantProps.name || selectedHydrantProps.source || "Hydrant")} · {selectedHydrant ? formatCoords(selectedHydrant.lat, selectedHydrant.lon) : ""}</span>
              <span>Hose {String(hoseProps.length_ft ?? "n/a")} ft · curvature {String(hoseProps.curvature ?? "n/a")} · elevation {String(hoseProps.elevation_change_ft ?? "n/a")} ft · max grade {String(hoseProps.max_grade ?? "n/a")}</span>
              {plan.graph_source && <span>Graph: {String(plan.graph_source.source ?? "graph")} · cache {String(plan.graph_source.cache_hit)}</span>}
            </div>
            <h2>Closure Ranking</h2>
            <div className="list">
              {plan.ranked_closures.map((closure, index) => (
                <div className="closure" key={index}>
                  <strong>#{String(closure.rank)} {String(closure.name)}</strong>
                  <span>{String(closure.reason)}</span>
                  <span>Cost {String(closure.capacity)} · {String(closure.sightline)}</span>
                  {Boolean(closure.county_st_name) && <span>County match: {String(closure.county_st_name)} ({String(closure.county_match_confidence)})</span>}
                  {Boolean(closure.abs_grade) && <span>Grade {String(closure.abs_grade)} · elevation change {String(closure.elevation_change_m)} m</span>}
                </div>
              ))}
            </div>
            {plan.warning_signs && (
              <div className="scenario-result">
                <strong><Flag size={16} /> MUTCD advisory signs</strong>
                <span>{plan.warning_signs.features.length} candidate sign location(s)</span>
                {plan.warning_signs.features.slice(0, 6).map((feature, index) => (
                  <span key={index}>
                    {String(feature.properties?.sequence)} · {String(feature.properties?.approach_road)} · {String(feature.properties?.distance_from_closure_ft)} ft · {String(feature.properties?.placement_status)}
                  </span>
                ))}
              </div>
            )}
          </section>
        )}
      </aside>

      <section className="map-panel">
        <MapContainer center={CENTER} zoom={12} className="map">
          <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <IncidentClick onPick={setIncident} />
          <IncidentFocus incident={incident} />
          {roads && <GeoJSON data={roads} style={{ color: "#74808c", weight: 1, opacity: 0.6 }} />}
          {hydrants && <GeoJSON data={hydrants} pointToLayer={(_, latlng) => L.circleMarker(latlng, { radius: 4, color: "#1677a3", fillOpacity: 0.8 })} />}
          {plan && <GeoJSON key={`plan-overlays-${planVersion}`} data={plan.overlays} style={{ color: "#d9480f", weight: 5 }} />}
          {plan?.warning_signs && <GeoJSON key={`warning-signs-${planVersion}`} data={plan.warning_signs} pointToLayer={(_, latlng) => L.circleMarker(latlng, { radius: 6, color: "#7c3aed", fillOpacity: 0.9 })} />}
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
