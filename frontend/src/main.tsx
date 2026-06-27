import React, { useEffect, useMemo, useState } from "react";
import ReactDOM from "react-dom/client";
import {
  CircleMarker,
  GeoJSON,
  MapContainer,
  Marker,
  Pane,
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
  History,
  ChevronDown,
  ChevronRight,
  MapPin,
  Pencil,
  Plus,
  Route,
  Search,
  Settings,
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
  selected_hydrants?: FeatureCollection;
  hose_route: GeoJSON.Feature;
  hose_routes?: FeatureCollection;
  closures: FeatureCollection;
  incidents?: FeatureCollection;
  overlays: FeatureCollection;
  warning_signs?: FeatureCollection;
  graph_source?: Record<string, unknown>;
  ranked_closures: Array<Record<string, unknown>>;
  hydrant_candidates: Array<Record<string, unknown>>;
  run_id?: string;
  scenario_id?: string;
  report_path?: string;
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

type ScenarioGolden = {
  scenario_id: string;
  reviewer: string;
  reviewed_at: string;
  expected_hydrant: {
    name: string;
    source: string;
    source_id: string;
    notes: string;
  };
  expected_closures: Array<{ road: string; reason: string; notes: string }>;
  expected_warning_signs: Array<{ road: string; sign_label: string; distance_ft: number | null; notes: string }>;
  notes: string;
  updated_at: string;
};

type GoldenDraft = {
  reviewer: string;
  reviewed_at: string;
  hydrant_name: string;
  hydrant_source: string;
  hydrant_source_id: string;
  hydrant_notes: string;
  closures_text: string;
  warning_signs_text: string;
  notes: string;
};

type PlanMeaning = {
  closureText: string;
  signText: string;
  nextStep: string;
};

type PlanLayers = {
  hose: FeatureCollection;
  closures: FeatureCollection;
  other: FeatureCollection;
};

function emptyGoldenDraft(): GoldenDraft {
  return {
    reviewer: "",
    reviewed_at: "",
    hydrant_name: "",
    hydrant_source: "",
    hydrant_source_id: "",
    hydrant_notes: "",
    closures_text: "",
    warning_signs_text: "",
    notes: "",
  };
}

function goldenToDraft(golden: ScenarioGolden): GoldenDraft {
  return {
    reviewer: golden.reviewer,
    reviewed_at: golden.reviewed_at,
    hydrant_name: golden.expected_hydrant.name,
    hydrant_source: golden.expected_hydrant.source,
    hydrant_source_id: golden.expected_hydrant.source_id,
    hydrant_notes: golden.expected_hydrant.notes,
    closures_text: golden.expected_closures
      .map((closure) => [closure.road, closure.reason, closure.notes].filter(Boolean).join(" | "))
      .join("\n"),
    warning_signs_text: golden.expected_warning_signs
      .map((sign) => [sign.road, sign.sign_label, sign.distance_ft ?? "", sign.notes].filter((part) => part !== "").join(" | "))
      .join("\n"),
    notes: golden.notes,
  };
}

function parseClosures(text: string) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [road = "", reason = "", notes = ""] = line.split("|").map((part) => part.trim());
      return { road, reason, notes };
    });
}

function parseWarningSigns(text: string) {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [road = "", sign_label = "", distance = "", notes = ""] = line.split("|").map((part) => part.trim());
      const parsedDistance = Number(distance);
      const distance_ft = distance && Number.isFinite(parsedDistance) ? parsedDistance : null;
      return { road, sign_label, distance_ft, notes };
    });
}

function offsetLineFeature(feature: GeoJSON.Feature, offset: number): GeoJSON.Feature {
  if (feature.geometry.type !== "LineString") return feature;
  const coordinates = feature.geometry.coordinates as [number, number][];
  if (coordinates.length < 2) return feature;
  const first = coordinates[0];
  const last = coordinates[coordinates.length - 1];
  const dx = last[0] - first[0];
  const dy = last[1] - first[1];
  const length = Math.hypot(dx, dy) || 1;
  const ox = (-dy / length) * offset;
  const oy = (dx / length) * offset;
  return {
    ...feature,
    geometry: {
      ...feature.geometry,
      coordinates: coordinates.map(([lon, lat]) => [lon + ox, lat + oy]),
    },
  };
}

function featureTooltip(feature: GeoJSON.Feature, fallback: string): string {
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

async function jsonFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const text = await response.text();
    let message = text || response.statusText;
    try {
      const parsed = JSON.parse(text);
      message = String(parsed.detail || message);
    } catch {
      // Keep the raw response text when it is not JSON.
    }
    throw new Error(message);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
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

function App() {
  const [roads, setRoads] = useState<FeatureCollection | null>(null);
  const [hydrants, setHydrants] = useState<FeatureCollection | null>(null);
  const [manualHydrants, setManualHydrants] = useState<ManualHydrant[]>([]);
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [editingScenarioId, setEditingScenarioId] = useState<string | null>(null);
  const [selectedScenarioId, setSelectedScenarioId] = useState<string | null>(null);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [secondaryIncidents, setSecondaryIncidents] = useState<Incident[]>([]);
  const [secondaryIncidentMode, setSecondaryIncidentMode] = useState(false);
  const [manualHydrantPickMode, setManualHydrantPickMode] = useState(false);
  const [address, setAddress] = useState("");
  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [planVersion, setPlanVersion] = useState(0);
  const [isPlanning, setIsPlanning] = useState(false);
  const [pendingIncidentRemove, setPendingIncidentRemove] = useState(false);
  const [scenarioRun, setScenarioRun] = useState<ScenarioRunResult | null>(null);
  const [scenarioRuns, setScenarioRuns] = useState<ScenarioRunListItem[]>([]);
  const [expandedRunIds, setExpandedRunIds] = useState<Set<string>>(new Set());
  const [lastRunSource, setLastRunSource] = useState<"incident" | "scenario" | null>(null);
  const [pendingPromoteRunId, setPendingPromoteRunId] = useState<string | null>(null);
  const [pendingRemoveScenarioId, setPendingRemoveScenarioId] = useState<string | null>(null);
  const [runningScenarioId, setRunningScenarioId] = useState<string | null>(null);
  const [plannerStatus, setPlannerStatus] = useState("");
  const [scenarioStatus, setScenarioStatusMessage] = useState("");
  const [goldenStatus, setGoldenStatus] = useState("");
  const [showInactiveScenarios, setShowInactiveScenarios] = useState(false);
  const [showConfiguration, setShowConfiguration] = useState(false);
  const [message, setMessage] = useState("Pick an incident or load a scenario.");
  const [loadToast, setLoadToast] = useState("Loading GIS data in the background...");
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
  const [goldenDraft, setGoldenDraft] = useState<GoldenDraft>(emptyGoldenDraft());
  const [hydrantCount, setHydrantCount] = useState(1);
  const [plannerConfig, setPlannerConfig] = useState({
    hose_max_ft: "500",
    study_radius_ft: "2500",
    sign_max_distance_ft: "1500",
  });
  const [plannerConfigDraft, setPlannerConfigDraft] = useState({
    hose_max_ft: "500",
    study_radius_ft: "2500",
    sign_max_distance_ft: "1500",
  });

  async function loadLayers() {
    setLoadToast("Loading GIS data in the background...");
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
    const loadedMessage = `${roadLayer.features.length} roads, ${hydrantLayer.features.length} hydrants, ${manual.length} manual hydrants, ${scenarioRecords.length} scenarios loaded.`;
    setLoadToast(loadedMessage);
    setMessage(loadedMessage);
    window.setTimeout(() => setLoadToast(""), 4500);
  }

  async function loadScenarios() {
    const scenarioRecords = await jsonFetch<Scenario[]>(`${API}/scenarios`);
    setScenarios(scenarioRecords);
  }

  async function loadScenarioRuns() {
    const runRecords = await jsonFetch<ScenarioRunListItem[]>(`${API}/scenario-runs`);
    setScenarioRuns(runRecords);
  }

  async function loadScenarioGolden(scenarioId: string) {
    try {
      const golden = await jsonFetch<ScenarioGolden>(`${API}/scenarios/${scenarioId}/golden`);
      setGoldenDraft(goldenToDraft(golden));
      setGoldenStatus(golden.updated_at ? `Golden JSON loaded: ${golden.updated_at}` : "No golden JSON saved yet.");
    } catch (error) {
      setGoldenDraft(emptyGoldenDraft());
      setGoldenStatus(`Golden JSON load failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  function goldenPayload() {
    return {
      reviewer: goldenDraft.reviewer.trim(),
      reviewed_at: goldenDraft.reviewed_at.trim(),
      expected_hydrant: {
        name: goldenDraft.hydrant_name.trim(),
        source: goldenDraft.hydrant_source.trim(),
        source_id: goldenDraft.hydrant_source_id.trim(),
        notes: goldenDraft.hydrant_notes.trim(),
      },
      expected_closures: parseClosures(goldenDraft.closures_text),
      expected_warning_signs: parseWarningSigns(goldenDraft.warning_signs_text),
      notes: goldenDraft.notes.trim(),
    };
  }

  async function saveScenarioGolden() {
    if (!selectedScenarioId) {
      setGoldenStatus("Load or edit a scenario before saving golden JSON.");
      return;
    }
    try {
      const saved = await jsonFetch<ScenarioGolden>(`${API}/scenarios/${selectedScenarioId}/golden`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(goldenPayload()),
      });
      setGoldenDraft(goldenToDraft(saved));
      setGoldenStatus(`Golden saved for ${selectedScenarioId}.`);
      setMessage(`Golden JSON saved for ${selectedScenarioId}.`);
    } catch (error) {
      setGoldenStatus(`Golden save failed: ${error instanceof Error ? error.message : String(error)}`);
    }
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
    setIncidentLocation({ lat: results[0].lat, lon: results[0].lon });
    setMessage(results[0].label);
  }

  function setIncidentLocation(nextIncident: Incident) {
    setIncident(nextIncident);
    setSecondaryIncidents([]);
    setSecondaryIncidentMode(false);
    setManualHydrantPickMode(false);
    setHydrantCount(1);
    setPlan(null);
    setPlannerStatus("");
    setPendingIncidentRemove(false);
    setPlanVersion((version) => version + 1);
  }

  function pickManualHydrantLocation(nextLocation: Incident) {
    setManualDraft((draft) => ({
      ...draft,
      lat: nextLocation.lat.toFixed(6),
      lon: nextLocation.lon.toFixed(6),
    }));
    setManualHydrantPickMode(false);
    setLoadToast("Manual hydrant location set. Click Add manual hydrant to save it.");
    setMessage("Manual hydrant location set. Click Add manual hydrant to save it.");
  }

  function savePlannerConfig() {
    const hoseMax = Number(plannerConfigDraft.hose_max_ft);
    const studyRadius = Number(plannerConfigDraft.study_radius_ft);
    const signMax = Number(plannerConfigDraft.sign_max_distance_ft);
    if (
      !Number.isFinite(hoseMax) ||
      hoseMax <= 0 ||
      !Number.isFinite(studyRadius) ||
      studyRadius <= 0 ||
      !Number.isFinite(signMax) ||
      signMax <= 0
    ) {
      setLoadToast("Configuration values must be positive numbers.");
      setMessage("Configuration values must be positive numbers.");
      return;
    }
    setPlannerConfig(plannerConfigDraft);
    setLoadToast("Configuration saved for new recommendation runs.");
    setMessage("Configuration saved for new recommendation runs.");
    window.setTimeout(() => setLoadToast(""), 4500);
  }

  function addSecondaryIncident(nextIncident: Incident) {
    setSecondaryIncidents((items) => [...items, nextIncident]);
    setSecondaryIncidentMode(false);
    setManualHydrantPickMode(false);
    setPlan(null);
    setPlannerStatus("Secondary incident placed. Run recommendations again.");
    setMessage("Secondary incident placed. Run recommendations again.");
  }

  function requestIncidentRemoval() {
    if (!incident) return;
    setPendingIncidentRemove(true);
    setMessage("Confirm incident removal or cancel to keep it.");
  }

  function removeIncident() {
    setIncident(null);
    setSecondaryIncidents([]);
    setSecondaryIncidentMode(false);
    setManualHydrantPickMode(false);
    setHydrantCount(1);
    setPlan(null);
    setPlannerStatus("");
    setPendingIncidentRemove(false);
    setPlanVersion((version) => version + 1);
    setMessage("Incident removed. Click the map to set incident.");
  }

  function cancelIncidentRemoval() {
    setPendingIncidentRemove(false);
    setMessage("Incident kept.");
  }

  async function runPlan(nextHydrantCount = hydrantCount, nextSecondaryIncidents = secondaryIncidents) {
    if (!incident) {
      setMessage("Pick an incident location first.");
      setPlannerStatus("Pick an incident location first.");
      return;
    }
    const hoseMax = Number(plannerConfig.hose_max_ft);
    const studyRadius = Number(plannerConfig.study_radius_ft);
    const signMax = Number(plannerConfig.sign_max_distance_ft);
    if (
      !Number.isFinite(hoseMax) ||
      hoseMax <= 0 ||
      !Number.isFinite(studyRadius) ||
      studyRadius <= 0 ||
      !Number.isFinite(signMax) ||
      signMax <= 0
    ) {
      setMessage("Planner config values must be positive numbers.");
      setPlannerStatus("Planner config values must be positive numbers.");
      return;
    }
    setIsPlanning(true);
    setMessage("Calculating closure recommendations. This can take 10-30 seconds.");
    setPlannerStatus("Calculating closure recommendations...");
    setLoadToast("Running closure recommendations...");
    try {
      const result = await jsonFetch<PlanResponse>(`${API}/plan`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lat: incident.lat,
          lon: incident.lon,
          incident_radius_ft: 300,
          study_radius_ft: studyRadius,
          hose_max_ft: hoseMax,
          hydrant_count: nextHydrantCount,
          secondary_incidents: nextSecondaryIncidents,
          sign_max_distance_ft: signMax,
        }),
      });
      setPlan(result);
      setPlanVersion((version) => version + 1);
      if (result.run_id && result.scenario_id) {
        const runResult = {
          run_id: result.run_id,
          run_dir: "",
          report_path: result.report_path ?? "",
          results: [
            {
              scenario_id: result.scenario_id,
              name: "Ad hoc incident",
              status: "passed",
              golden_status: "not_checked",
              differences: ["Ad hoc incident run"],
            },
          ],
        };
        setScenarioRun(runResult);
        setLastRunSource("incident");
        setExpandedRunIds((ids) => new Set(ids).add(result.run_id!));
        await loadScenarioRuns();
      }
      setMessage(`Plan ready: ${result.ranked_closures.length} closure recommendations.`);
      setPlannerStatus(`Plan ready: ${result.ranked_closures.length} closure recommendation(s).`);
      setLoadToast(`Recommendations ready: ${result.ranked_closures.length} closure recommendation(s).`);
      window.setTimeout(() => setLoadToast(""), 4500);
    } catch (error) {
      setMessage(`Planner failed: ${error instanceof Error ? error.message : String(error)}`);
      setPlannerStatus(`Planner failed: ${error instanceof Error ? error.message : String(error)}`);
      setLoadToast(`Planner failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setIsPlanning(false);
    }
  }

  async function addHydrantAndRerun() {
    const nextCount = Math.min(hydrantCount + 1, 4);
    setHydrantCount(nextCount);
    await runPlan(nextCount, secondaryIncidents);
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
      const saved = await jsonFetch<Scenario>(`${API}/scenarios/${editingScenarioId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSelectedScenarioId(saved.scenario_id);
      await loadScenarioGolden(saved.scenario_id);
      setMessage(`Scenario updated: ${payload.name}`);
    } else {
      const saved = await jsonFetch<Scenario>(`${API}/scenarios`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setSelectedScenarioId(saved.scenario_id);
      await loadScenarioGolden(saved.scenario_id);
      setMessage(`Scenario saved: ${payload.name}`);
    }
    resetScenarioDraft();
    await loadScenarios();
  }

  function editScenario(scenario: Scenario) {
    setEditingScenarioId(scenario.scenario_id);
    setSelectedScenarioId(scenario.scenario_id);
    setIncidentLocation({ lat: scenario.lat, lon: scenario.lon });
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
    void loadScenarioGolden(scenario.scenario_id);
    setMessage(`Editing scenario: ${scenario.name}`);
  }

  function loadScenario(scenario: Scenario) {
    setSelectedScenarioId(scenario.scenario_id);
    setIncidentLocation({ lat: scenario.lat, lon: scenario.lon });
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
    void loadScenarioGolden(scenario.scenario_id);
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
      if (selectedScenarioId === id) {
        setSelectedScenarioId(null);
        setGoldenDraft(emptyGoldenDraft());
        setGoldenStatus("");
      }
      await loadScenarios();
      setMessage("Scenario removed.");
    } catch (error) {
      setMessage(`Scenario removal failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setPendingRemoveScenarioId(null);
    }
  }

  async function runScenario(id: string) {
    const scenario = scenarios.find((item) => item.scenario_id === id);
    if (scenario?.status !== "active") {
      setScenarioStatusMessage(`${scenario?.name ?? "Scenario"} is inactive and cannot start.`);
      setMessage(`${scenario?.name ?? "Scenario"} is inactive and cannot start.`);
      return;
    }
    setRunningScenarioId(id);
    setMessage("Running scenario validation. This can take a while.");
    setScenarioStatusMessage(`Running ${scenario.name}...`);
    setLoadToast(`Running scenario: ${scenario.name}...`);
    try {
      const result = await jsonFetch<ScenarioRunResult>(`${API}/scenarios/${id}/run`, { method: "POST" });
      setScenarioRun(result);
      setLastRunSource("scenario");
      if (result.run_id) {
        setExpandedRunIds((ids) => new Set(ids).add(result.run_id!));
      }
      await loadScenarioRuns();
      const first = result.results[0];
      const status = first ? `${first.status}, golden ${first.golden_status}` : "no active scenario run";
      if (result.run_id && first?.scenario_id && first.status !== "failed") {
        await loadScenarioPlan(result.run_id, first.scenario_id);
      }
      setMessage(`Scenario run complete: ${status}.`);
      setScenarioStatusMessage(`${scenario.name} complete: ${status}.`);
      setLoadToast(`Scenario ready: ${scenario.name} ${status}.`);
      window.setTimeout(() => setLoadToast(""), 4500);
    } catch (error) {
      setMessage(`Scenario run failed: ${error instanceof Error ? error.message : String(error)}`);
      setScenarioStatusMessage(`Scenario run failed: ${error instanceof Error ? error.message : String(error)}`);
      setLoadToast(`Scenario run failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setRunningScenarioId(null);
    }
  }

  async function setScenarioStatus(scenario: Scenario, status: "active" | "inactive") {
    try {
      await jsonFetch<Scenario>(`${API}/scenarios/${scenario.scenario_id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: scenario.name,
          lat: scenario.lat,
          lon: scenario.lon,
          incident_radius_ft: scenario.incident_radius_ft,
          study_radius_ft: scenario.study_radius_ft,
          hose_max_ft: scenario.hose_max_ft,
          reviewer_notes: scenario.reviewer_notes,
          expected_hydrant_hint: scenario.expected_hydrant_hint,
          expected_closure_hint: scenario.expected_closure_hint,
          status,
        }),
      });
      await loadScenarios();
      setMessage(`${scenario.name} moved to ${status} scenarios.`);
      setScenarioStatusMessage(`${scenario.name} is now ${status}.`);
    } catch (error) {
      setMessage(`Scenario update failed: ${error instanceof Error ? error.message : String(error)}`);
      setScenarioStatusMessage(`Scenario update failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }

  async function viewScenarioRun(runId: string) {
    const result = await jsonFetch<ScenarioRunResult>(`${API}/scenario-runs/${runId}`);
    setScenarioRun(result);
    setExpandedRunIds((ids) => {
      const next = new Set(ids);
      if (next.has(runId)) {
        next.delete(runId);
      } else {
        next.add(runId);
      }
      return next;
    });
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
    setSecondaryIncidents([]);
    setSecondaryIncidentMode(false);
    setHydrantCount(1);
    setPendingIncidentRemove(false);
    setPlannerStatus("");
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
    setManualHydrantPickMode(false);
    await loadLayers();
  }

  async function removeManualHydrant(id: string) {
    await jsonFetch(`${API}/manual-hydrants/${id}`, { method: "DELETE" });
    await loadLayers();
  }

  useEffect(() => {
    window.setTimeout(() => {
      loadLayers().catch((error) => {
        setMessage(`Layer load failed: ${error.message}`);
        setLoadToast(`Layer load failed: ${error.message}`);
      });
    }, 0);
  }, []);

  const selectedHydrant = useMemo(() => {
    const geom = plan?.selected_hydrant.geometry;
    if (!geom || geom.type !== "Point") return null;
    const coords = geom.coordinates as [number, number];
    return { lat: coords[1], lon: coords[0] };
  }, [plan]);

  const selectedHydrantProps = plan?.selected_hydrant.properties ?? {};
  const hoseProps = plan?.hose_route.properties ?? {};
  const activeScenarios = scenarios
    .filter((scenario) => scenario.status === "active")
    .sort((left, right) => left.name.localeCompare(right.name));
  const inactiveScenarios = scenarios
    .filter((scenario) => scenario.status !== "active")
    .sort((left, right) => left.name.localeCompare(right.name));
  const displayPlanLayers = useMemo<PlanLayers | null>(() => {
    if (!plan) return null;
    const nonPointFeatures = plan.overlays.features.filter((feature) => feature.geometry.type !== "Point");
    const hoseFeatures = plan.hose_routes?.features.length ? plan.hose_routes.features : plan.hose_route ? [plan.hose_route] : [];
    const closureFeatures = plan.closures.features.length ? plan.closures.features : [];
    const isHose = (feature: GeoJSON.Feature) => feature.properties?.kind === "hose_route";
    const isClosure = (feature: GeoJSON.Feature) => {
      const kind = feature.properties?.kind;
      return kind === "closure" || feature.properties?.rank || feature.properties?.reason;
    };
    const overlayHoseFeatures = nonPointFeatures.filter(isHose);
    const overlayClosureFeatures = nonPointFeatures.filter(isClosure);
    const selectedHoseFeatures = overlayHoseFeatures.length ? overlayHoseFeatures : hoseFeatures;
    const selectedClosureFeatures = closureFeatures.length ? closureFeatures : overlayClosureFeatures;
    return {
      hose: { ...plan.overlays, features: selectedHoseFeatures.map((feature) => offsetLineFeature(feature, 0.000025)) },
      closures: { ...plan.overlays, features: selectedClosureFeatures.map((feature) => offsetLineFeature(feature, -0.000025)) },
      other: { ...plan.overlays, features: nonPointFeatures.filter((feature) => !isHose(feature) && !isClosure(feature)) },
    };
  }, [plan]);
  const selectedHydrantFeatures = plan?.selected_hydrants?.features.length
    ? plan.selected_hydrants.features
    : plan?.selected_hydrant
      ? [plan.selected_hydrant]
      : [];
  const planMeaning = useMemo<PlanMeaning | null>(() => {
    if (!plan) return null;
    const closureCount = plan.ranked_closures.length;
    const signCount = plan.warning_signs?.features.length ?? 0;
    return {
      closureText:
        closureCount > 0
          ? `${closureCount} closure recommendation(s) ranked below and drawn in red on the map.`
          : "No closure road segments were returned for this incident and search radius.",
      signText:
        signCount > 0
          ? `${signCount} advisory sign location(s) returned and drawn in purple on the map.`
          : "No MUTCD advisory sign locations were returned for this plan.",
      nextStep:
        closureCount > 0
          ? "Review the blue hose path from hydrant to incident, the selected hydrant marker, and the red closure segments."
          : "Try moving the incident pin to the roadway centerline or increasing the scenario study radius, then recommend closures again.",
    };
  }, [plan]);
  const renderRunBox = (run: ScenarioRunResult | null, title: string) => {
    if (!run?.run_id) return null;
    const expanded = expandedRunIds.has(run.run_id);
    return (
      <div className="run-box">
        <button
          className="tree-toggle"
          onClick={() =>
            setExpandedRunIds((ids) => {
              const next = new Set(ids);
              if (next.has(run.run_id!)) next.delete(run.run_id!);
              else next.add(run.run_id!);
              return next;
            })
          }
          aria-expanded={expanded}
        >
          {expanded ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
          {title}: {run.results.length} result(s)
        </button>
        {expanded && (
          <div className="scenario-result">
            <strong>{run.run_id}</strong>
            {run.report_path && <span>{run.report_path}</span>}
            {run.results.map((result) => (
              <div className="run-result-row" key={result.scenario_id}>
                <span>
                  {result.name}: {result.status}, golden {result.golden_status}
                </span>
                <button onClick={() => loadScenarioPlan(run.run_id!, result.scenario_id)}>
                  <MapPin size={16} /> Show on map
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  };

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
          {incident && !pendingIncidentRemove && (
            <button onClick={requestIncidentRemoval}><X size={18} /> Clear Incident</button>
          )}
          {pendingIncidentRemove && (
            <div className="confirm-row">
              <span>Remove this incident and clear recommendations?</span>
              <button onClick={removeIncident}><Check size={16} /> Remove</button>
              <button onClick={cancelIncidentRemoval}><X size={16} /> Cancel</button>
            </div>
          )}
          <button className="primary" onClick={() => runPlan()} disabled={!incident || isPlanning}>
            <ShieldAlert size={18} /> {isPlanning ? "Recommending..." : "Recommend Closures"}
          </button>
          {plannerStatus && <div className="inline-status">{plannerStatus}</div>}
          {lastRunSource === "incident" && renderRunBox(scenarioRun, "Recommendation run")}
        </section>

        <section className="panel">
          <button
            className="tree-toggle"
            onClick={() => setShowConfiguration((show) => !show)}
            aria-expanded={showConfiguration}
          >
            {showConfiguration ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
            <Settings size={18} /> Configuration
          </button>
          {showConfiguration && (
            <div className="config-panel">
              <label className="field">
                <span>Hose envelope feet</span>
                <input
                  value={plannerConfigDraft.hose_max_ft}
                  onChange={(e) => setPlannerConfigDraft({ ...plannerConfigDraft, hose_max_ft: e.target.value })}
                  placeholder="500"
                />
              </label>
              <label className="field">
                <span>Study radius feet</span>
                <input
                  value={plannerConfigDraft.study_radius_ft}
                  onChange={(e) => setPlannerConfigDraft({ ...plannerConfigDraft, study_radius_ft: e.target.value })}
                  placeholder="2500"
                />
              </label>
              <label className="field">
                <span>Maximum sign distance feet</span>
                <input
                  value={plannerConfigDraft.sign_max_distance_ft}
                  onChange={(e) => setPlannerConfigDraft({ ...plannerConfigDraft, sign_max_distance_ft: e.target.value })}
                  placeholder="1500"
                />
              </label>
              <button onClick={savePlannerConfig} title="Save configuration">
                <Check size={18} /> Save Configuration
              </button>
            </div>
          )}
        </section>

        <section className="panel">
          <h2><Droplets size={18} /> Manual Hydrants</h2>
          <label className="field">
            <span>Name</span>
            <input value={manualDraft.name} onChange={(e) => setManualDraft({ ...manualDraft, name: e.target.value })} placeholder="Known hydrant" />
          </label>
          <div className="inline">
            <label className="field">
              <span>Latitude</span>
              <input value={manualDraft.lat} onChange={(e) => setManualDraft({ ...manualDraft, lat: e.target.value })} placeholder="Lat" />
            </label>
            <label className="field">
              <span>Longitude</span>
              <input value={manualDraft.lon} onChange={(e) => setManualDraft({ ...manualDraft, lon: e.target.value })} placeholder="Lon" />
            </label>
          </div>
          <div className="inline">
            <button
              onClick={() => {
                setManualHydrantPickMode(true);
                setSecondaryIncidentMode(false);
                setLoadToast("Click the map to fill manual hydrant latitude and longitude.");
                setMessage("Click the map to fill manual hydrant latitude and longitude.");
              }}
              title="Pick manual hydrant location on map"
            >
              <MapPin size={18} /> Pick
            </button>
            <button onClick={addManualHydrant} title="Add manual hydrant"><Plus size={18} /> Add</button>
          </div>
          {manualHydrantPickMode && <div className="inline-status">Click the map to fill the manual hydrant coordinates. It will not be saved until you click Add.</div>}
          <div className="inline">
            <label className="field">
              <span>Flow class</span>
              <select value={manualDraft.flow_class} onChange={(e) => setManualDraft({ ...manualDraft, flow_class: e.target.value })}>
                <option value="unknown">Unknown</option>
                <option value="red">Red</option>
                <option value="orange">Orange</option>
                <option value="green">Green</option>
                <option value="blue">Blue</option>
              </select>
            </label>
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
          <label className="field">
            <span>Scenario name</span>
            <input
              value={scenarioDraft.name}
              onChange={(e) => setScenarioDraft({ ...scenarioDraft, name: e.target.value })}
              placeholder="Scenario name"
            />
          </label>
          <div className="inline three">
            <label className="field">
              <span>Incident radius ft</span>
              <input
                value={scenarioDraft.incident_radius_ft}
                onChange={(e) => setScenarioDraft({ ...scenarioDraft, incident_radius_ft: e.target.value })}
                placeholder="300"
              />
            </label>
            <label className="field">
              <span>Study radius ft</span>
              <input
                value={scenarioDraft.study_radius_ft}
                onChange={(e) => setScenarioDraft({ ...scenarioDraft, study_radius_ft: e.target.value })}
                placeholder="2500"
              />
            </label>
            <label className="field">
              <span>Hose envelope ft</span>
              <input
                value={scenarioDraft.hose_max_ft}
                onChange={(e) => setScenarioDraft({ ...scenarioDraft, hose_max_ft: e.target.value })}
                placeholder="500"
              />
            </label>
          </div>
          <label className="field">
            <span>Reviewer note: expected hydrant</span>
            <input
              value={scenarioDraft.expected_hydrant_hint}
              onChange={(e) => setScenarioDraft({ ...scenarioDraft, expected_hydrant_hint: e.target.value })}
              placeholder="Optional note, not used as golden data"
            />
          </label>
          <label className="field">
            <span>Reviewer note: expected closure</span>
            <input
              value={scenarioDraft.expected_closure_hint}
              onChange={(e) => setScenarioDraft({ ...scenarioDraft, expected_closure_hint: e.target.value })}
              placeholder="Optional note, not used as golden data"
            />
          </label>
          <div className="inline">
            <button onClick={saveScenario} title={editingScenarioId ? "Update scenario" : "Save scenario"}>
              {editingScenarioId ? <Check size={18} /> : <Plus size={18} />}
              {editingScenarioId ? "Update Scenario" : "Save Active Scenario"}
            </button>
          </div>
          {editingScenarioId && (
            <button onClick={resetScenarioDraft}><X size={18} /> Cancel Edit</button>
          )}
          <div className="subsection">
            <h3>Golden Expert Data</h3>
            {selectedScenarioId ? (
              <>
                <div className="coords">Selected scenario: {selectedScenarioId}</div>
                <div className="inline">
                  <input
                    value={goldenDraft.reviewer}
                    onChange={(e) => setGoldenDraft({ ...goldenDraft, reviewer: e.target.value })}
                    placeholder="Reviewer"
                  />
                  <input
                    value={goldenDraft.reviewed_at}
                    onChange={(e) => setGoldenDraft({ ...goldenDraft, reviewed_at: e.target.value })}
                    placeholder="Reviewed at"
                  />
                </div>
                <input
                  value={goldenDraft.hydrant_name}
                  onChange={(e) => setGoldenDraft({ ...goldenDraft, hydrant_name: e.target.value })}
                  placeholder="Expected hydrant name"
                />
                <div className="inline">
                  <input
                    value={goldenDraft.hydrant_source}
                    onChange={(e) => setGoldenDraft({ ...goldenDraft, hydrant_source: e.target.value })}
                    placeholder="Hydrant source"
                  />
                  <input
                    value={goldenDraft.hydrant_source_id}
                    onChange={(e) => setGoldenDraft({ ...goldenDraft, hydrant_source_id: e.target.value })}
                    placeholder="Hydrant source ID"
                  />
                </div>
                <input
                  value={goldenDraft.hydrant_notes}
                  onChange={(e) => setGoldenDraft({ ...goldenDraft, hydrant_notes: e.target.value })}
                  placeholder="Hydrant notes"
                />
                <textarea
                  value={goldenDraft.closures_text}
                  onChange={(e) => setGoldenDraft({ ...goldenDraft, closures_text: e.target.value })}
                  placeholder="Expected closures, one per line: Road | reason | notes"
                />
                <textarea
                  value={goldenDraft.warning_signs_text}
                  onChange={(e) => setGoldenDraft({ ...goldenDraft, warning_signs_text: e.target.value })}
                  placeholder="Expected warning signs, one per line: Road | sign label | distance ft | notes"
                />
                <textarea
                  value={goldenDraft.notes}
                  onChange={(e) => setGoldenDraft({ ...goldenDraft, notes: e.target.value })}
                  placeholder="Golden notes"
                />
                <button onClick={saveScenarioGolden} title="Save Golden JSON">
                  <FileCheck2 size={18} /> Save Golden JSON
                </button>
              </>
            ) : (
              <div className="empty-state">Load or edit a scenario to save golden JSON.</div>
            )}
            {goldenStatus && <div className="inline-status">{goldenStatus}</div>}
          </div>
          <div className="list">
            {activeScenarios.map((scenario) => (
              <div className="scenario-row" key={scenario.scenario_id}>
                <div>
                  <strong>{scenario.name}</strong>
                  <span>{formatCoords(scenario.lat, scenario.lon)} · {scenario.status}</span>
                </div>
                <div className="row-actions">
                  <button onClick={() => loadScenario(scenario)} title="Load scenario"><MapPin size={16} /></button>
                  <button onClick={() => editScenario(scenario)} title="Edit scenario"><Pencil size={16} /></button>
                  <button
                    className={runningScenarioId === scenario.scenario_id ? "run-action running" : ""}
                    onClick={() => runScenario(scenario.scenario_id)}
                    title="Run scenario"
                    disabled={Boolean(runningScenarioId)}
                  >
                    Run
                  </button>
                  <button
                    className="text-action"
                    onClick={() => setScenarioStatus(scenario, "inactive")}
                    title="Make inactive"
                  >
                    Deactivate
                  </button>
                  <button onClick={() => removeScenario(scenario.scenario_id)} title="Delete scenario">
                    {pendingRemoveScenarioId === scenario.scenario_id ? <Check size={16} /> : <Trash2 size={16} />}
                  </button>
                </div>
              </div>
            ))}
            <button
              className="tree-toggle"
              onClick={() => setShowInactiveScenarios((show) => !show)}
              aria-expanded={showInactiveScenarios}
            >
              {showInactiveScenarios ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
              Inactive Scenarios ({inactiveScenarios.length})
            </button>
            {showInactiveScenarios && (
              <div className="inactive-tree">
                {inactiveScenarios.map((scenario) => (
                  <div className="scenario-row inactive" key={scenario.scenario_id}>
                    <div>
                      <strong>{scenario.name}</strong>
                      <span>{formatCoords(scenario.lat, scenario.lon)} · inactive</span>
                    </div>
                    <div className="row-actions">
                      <button onClick={() => loadScenario(scenario)} title="Load scenario"><MapPin size={16} /></button>
                      <button onClick={() => editScenario(scenario)} title="Edit scenario"><Pencil size={16} /></button>
                      <button className="text-action" title="Inactive scenarios cannot start. Make this scenario active to run it." disabled>
                        Run disabled
                      </button>
                      <button className="text-action" onClick={() => setScenarioStatus(scenario, "active")} title="Make active">
                        Activate
                      </button>
                      <button onClick={() => removeScenario(scenario.scenario_id)} title="Delete scenario">
                        {pendingRemoveScenarioId === scenario.scenario_id ? <Check size={16} /> : <Trash2 size={16} />}
                      </button>
                    </div>
                  </div>
                ))}
                {inactiveScenarios.length === 0 && <div className="empty-state">No inactive scenarios.</div>}
              </div>
            )}
          </div>
          {scenarioStatus && <div className="inline-status">{scenarioStatus}</div>}
          {lastRunSource === "scenario" && renderRunBox(scenarioRun, "Scenario run")}
        </section>

        <section className="panel">
          <h2><FileCheck2 size={18} /> Scenario Runs</h2>
          <button onClick={loadScenarioRuns}>Reload Runs</button>
          <div className="list">
            {scenarioRuns.map((run) => (
              <div className="scenario-row run-history-row" key={run.run_id}>
                <button className="tree-toggle" onClick={() => viewScenarioRun(run.run_id)} aria-expanded={expandedRunIds.has(run.run_id)}>
                  {expandedRunIds.has(run.run_id) ? <ChevronDown size={18} /> : <ChevronRight size={18} />}
                  {run.run_id}
                </button>
                <span>
                  {run.result_count} result(s) · {run.failed_count} failed · {run.changed_count} changed · {run.missing_count} missing
                </span>
                {expandedRunIds.has(run.run_id) && scenarioRun?.run_id === run.run_id && (
                  <div className="scenario-result">
                    <span>{scenarioRun.report_path}</span>
                    {scenarioRun.results.map((result) => (
                      <div className="run-result-row" key={result.scenario_id}>
                        <span>{result.name}: {result.status}, golden {result.golden_status}</span>
                        <button onClick={() => loadScenarioPlan(run.run_id, result.scenario_id)}>
                          <MapPin size={16} /> Show on map
                        </button>
                      </div>
                    ))}
                    <button onClick={() => promoteScenarioRun(run.run_id)} title="Promote run">
                      {pendingPromoteRunId === run.run_id ? <Check size={16} /> : <FileCheck2 size={16} />}
                      Promote Run
                    </button>
                  </div>
                )}
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
            <h2>Plan Review</h2>
            {planMeaning && (
              <div className="explain-box">
                <strong>Recommendation summary</strong>
                <span>{planMeaning.closureText}</span>
                <span>{planMeaning.signText}</span>
                <span>{planMeaning.nextStep}</span>
              </div>
            )}
            <div className="inline">
              <button onClick={addHydrantAndRerun} disabled={!incident || isPlanning || hydrantCount >= 4}>
                <Droplets size={18} /> Add Hydrant
              </button>
              <button
                onClick={() => {
                  setSecondaryIncidentMode(true);
                  setMessage("Click the map to place a secondary incident.");
                  setLoadToast("Click the map to place a secondary incident.");
                }}
                disabled={!incident || isPlanning}
              >
                <MapPin size={18} /> Add Secondary Incident
              </button>
            </div>
            <div className="coords">
              Hydrants requested: {hydrantCount} · secondary incidents: {secondaryIncidents.length}
              {secondaryIncidentMode ? " · click map to place secondary incident" : ""}
            </div>
            <div className="scenario-result">
              <strong>Selected hydrant</strong>
              <span>{String(selectedHydrantProps.name || selectedHydrantProps.source || "Hydrant")} · {selectedHydrant ? formatCoords(selectedHydrant.lat, selectedHydrant.lon) : ""}</span>
              <span>Hose {String(hoseProps.length_ft ?? "n/a")} ft · curvature {String(hoseProps.curvature ?? "n/a")} · elevation {String(hoseProps.elevation_change_ft ?? "n/a")} ft · max grade {String(hoseProps.max_grade ?? "n/a")}</span>
              <span>Map: incident pin in red, recommended hydrant marker, hose path in blue, closures in red, advisory signs in purple.</span>
              {plan.graph_source && <span>Graph: {String(plan.graph_source.source ?? "graph")} · cache {String(plan.graph_source.cache_hit)}</span>}
            </div>
            <h2>Closure Ranking</h2>
            <div className="list">
              {plan.ranked_closures.length === 0 && (
                <div className="empty-state">No closure recommendations returned for this incident.</div>
              )}
              {plan.ranked_closures.map((closure, index) => (
                <div className="closure" key={index}>
                  <strong>
                    {Boolean(closure.deployment_label) && (
                      <span className="priority-badge" title="Field set-up priority (set up first)">{String(closure.deployment_label)}</span>
                    )}
                    #{String(closure.rank)} {String(closure.name)}
                  </strong>
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
                <span>
                  {plan.warning_signs.features.length > 0
                    ? `${plan.warning_signs.features.length} candidate sign location(s)`
                    : "No advisory sign locations returned."}
                </span>
                {plan.warning_signs.features.slice(0, 6).map((feature, index) => (
                  <span key={index}>
                    {Boolean(feature.properties?.deployment_label) && (
                      <span className="priority-badge" title="Field set-up priority (set up first)">{String(feature.properties?.deployment_label)}</span>
                    )}
                    {String(feature.properties?.sequence)} · {String(feature.properties?.approach_road)} · {String(feature.properties?.distance_from_closure_ft)} ft · {String(feature.properties?.placement_status)}
                  </span>
                ))}
              </div>
            )}
          </section>
        )}
      </aside>

      <section className="map-panel">
        {loadToast && <div className="toast">{loadToast}</div>}
        <MapContainer center={CENTER} zoom={12} className="map">
          <TileLayer attribution="&copy; OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
          <IncidentClick
            incident={incident}
            secondaryIncidentMode={secondaryIncidentMode}
            manualHydrantPickMode={manualHydrantPickMode}
            onPick={setIncidentLocation}
            onPickSecondary={addSecondaryIncident}
            onPickManualHydrant={pickManualHydrantLocation}
            onExistingIncident={requestIncidentRemoval}
          />
          <IncidentFocus incident={incident} />
          <PlanFocus plan={plan} version={planVersion} />
          {roads && (
            <GeoJSON
              data={roads}
              style={{ color: "#74808c", weight: 1, opacity: 0.6 }}
              onEachFeature={(feature, layer) => layer.bindTooltip(`Road: ${featureTooltip(feature, "road")}`)}
            />
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
          {plan?.warning_signs && (
            <GeoJSON
              key={`warning-signs-${planVersion}`}
              data={plan.warning_signs}
              pointToLayer={(_, latlng) => L.circleMarker(latlng, { radius: 7, color: "#7c3aed", fillColor: "#a855f7", fillOpacity: 0.9, weight: 2 })}
              onEachFeature={(feature, layer) => layer.bindTooltip(`Advisory sign: ${featureTooltip(feature, "sign")}`)}
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
                    requestIncidentRemoval();
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
          {selectedHydrantFeatures.map((feature, index) => {
            if (feature.geometry.type !== "Point") return null;
            const coords = feature.geometry.coordinates as [number, number];
            const props = feature.properties ?? {};
            return (
              <Marker key={`selected-hydrant-${index}-${planVersion}`} title="Selected hydrant marker" position={[coords[1], coords[0]]}>
                <Tooltip>
                  Selected hydrant {index + 1}: {String(props.name || props.source || "hydrant")}
                </Tooltip>
              </Marker>
            );
          })}
        </MapContainer>
        {plan && (
          <div className="map-legend">
            <span><i className="legend-swatch incident" /> Incident</span>
            <span><i className="legend-swatch hydrant" /> Hydrant</span>
            <span><i className="legend-swatch selected-hydrant" /> Selected hydrant</span>
            <span><i className="legend-line hose" /> Hose path</span>
            <span><i className="legend-line closure" /> Closure</span>
            <span><i className="legend-swatch sign" /> Sign</span>
          </div>
        )}
      </section>
    </main>
  );
}

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
