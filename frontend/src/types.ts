export type FeatureCollection = GeoJSON.FeatureCollection;

export type ManualHydrant = {
  manual_id: string;
  name: string;
  lat: number;
  lon: number;
  flow_class: string;
  source_note: string;
  status: string;
  updated_at: string;
};

export type Incident = { lat: number; lon: number };

export type Scenario = {
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

export type PlanResponse = {
  cut_value: number;
  feasible?: boolean;
  feasibility_note?: string;
  selected_hydrant: GeoJSON.Feature;
  selected_hydrants?: FeatureCollection;
  hose_route: GeoJSON.Feature;
  hose_routes?: FeatureCollection;
  closures: FeatureCollection;
  incidents?: FeatureCollection;
  overlays: FeatureCollection;
  warning_signs?: FeatureCollection;
  devices?: FeatureCollection;
  compliance?: Record<string, unknown>;
  graph_source?: Record<string, unknown>;
  ranked_closures: Array<Record<string, unknown>>;
  hydrant_candidates: Array<Record<string, unknown>>;
  run_id?: string;
  scenario_id?: string;
  report_path?: string;
};

export type ScenarioRunResult = {
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

export type ScenarioRunListItem = {
  run_id: string;
  report_path: string;
  result_count: number;
  failed_count: number;
  changed_count: number;
  missing_count: number;
};

export type ScenarioGolden = {
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

export type GoldenDraft = {
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

export type PlanMeaning = {
  closureText: string;
  signText: string;
  nextStep: string;
};

export type PlanLayers = {
  hose: FeatureCollection;
  closures: FeatureCollection;
  other: FeatureCollection;
};
