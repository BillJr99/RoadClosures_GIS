# Fire Police GIS Cordon Planner

Local development app for Montgomery County fire-police road closure planning.

The project keeps the original course/prototype files at the repository root as
legacy references. New implementation code lives under `backend/` and
`frontend/`.

## Development

Backend:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

The frontend defaults to `http://localhost:8001/api`. Override it with
`VITE_API_BASE` if you run the backend elsewhere.

## Rebuilding GIS Data

Generated road and hydrant artifacts live under `data/generated/` and are
ignored by git because they can be large and are reproducible from the source
services plus `data/manual/manual_hydrants.csv`.

Install backend dependencies first:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cd ..
```

Rebuild everything:

```bash
scripts/rebuild_gis_data.sh all
```

Rebuild only fire hydrants after editing manual hydrants or when authority/OSM
hydrant data should be refreshed:

```bash
scripts/rebuild_gis_data.sh hydrants
```

Rebuild only roads:

```bash
scripts/rebuild_gis_data.sh roads
```

For a faster road layer refresh that skips the OSMnx routing graph:

```bash
scripts/rebuild_gis_data.sh roads --skip-graph
```

The script uses the same prototype data sources documented in the project plan:
Montgomery County Streets, OSMnx/OpenStreetMap roads, OSM Overpass hydrants,
Lansdale/NPWA authority hydrant layers, and the manual hydrant CSV.

## Test Suite

Run the full backend, frontend, and browser orchestration suite:

```bash
scripts/test_all.sh
```

The script runs:

- backend unit/API tests with `pytest`
- frontend unit tests with `vitest`
- frontend production build with Vite/TypeScript
- Playwright browser orchestration tests that mock API responses and exercise
  layer loading, address search, manual hydrant add/remove, rebuild action, and
  scenario CRUD/run controls, and closure recommendation rendering

If Playwright browsers are missing, install them once:

```bash
cd frontend
npx playwright install chromium
```

To include real scenario validation in the full suite:

```bash
RUN_SCENARIOS=1 scripts/test_all.sh
```

To launch a headed browser demonstration that slowly walks through the main app
workflow with mocked API responses:

```bash
scripts/demo_browser.sh
```

Adjust the pace:

```bash
DEMO_STEP_MS=2000 DEMO_SLOW_MO_MS=400 scripts/demo_browser.sh
```

For live scenario validation, build a local GraphML artifact around the active
scenario locations first:

```bash
scripts/build_scenario_graph.sh
```

To warm the incident-local graph cache used by the planner:

```bash
scripts/build_graph_cache.sh
```

## Scenario Validation

Incident scenarios are stored in `data/scenarios/incidents.csv`. They can be
edited by hand or through the app. The repo includes seeded active scenarios for
Norristown, Lansdale, and Limerick.

### Scenario Authoring Guide

A scenario is a repeatable incident example used to validate that the planner
chooses reasonable hydrants, hose routes, and closure recommendations. Add
scenarios from real debriefs, training examples, or expert-selected test
locations.

Each CSV row has these fields:

- `scenario_id`: stable unique ID, such as `scenario-main-st-depot-fire`
- `name`: short human-readable incident name
- `lat`, `lon`: incident center in WGS84 decimal degrees
- `incident_radius_ft`: radius of the scene to isolate
- `study_radius_ft`: surrounding road network radius considered for closure
- `hose_max_ft`: maximum allowed hydrant-to-incident hose route
- `reviewer_notes`: field notes, assumptions, or debrief context
- `expected_hydrant_hint`: optional human expectation for the hydrant choice
- `expected_closure_hint`: optional human expectation for closure roads
- `status`: `active` runs by default; `inactive` remains documented but skipped
- `updated_at`: ISO timestamp for manual tracking

Use the app when you want to create or revise a scenario visually:

1. Start the backend and frontend.
2. Search for an address or click the map to set the incident.
3. In the Scenarios panel, enter a scenario name and distances.
4. Add reviewer notes or expected hydrant/closure hints.
5. Save the scenario.
6. Rebuild the scenario graph before running live validation.

Use the CSV when you are adding several known incidents at once:

1. Edit `data/scenarios/incidents.csv`.
2. Keep `scenario_id` stable once a scenario has a reviewed golden summary.
3. Use `inactive` for examples that are useful documentation but should not run
   in the default suite.
4. Rebuild the scenario graph after adding, moving, or changing the radius of
   active scenarios.

Refresh the local scenario graph after adding or moving scenarios:

```bash
scripts/build_scenario_graph.sh
scripts/build_scenario_graph.sh --scenario-id scenario-norristown-main
scripts/build_graph_cache.sh
```

Run all active scenarios:

```bash
scripts/run_scenarios.sh
```

Run one scenario:

```bash
scripts/run_scenarios.sh --scenario-id scenario-example
```

Scenario outputs are written to `data/scenario_runs/<timestamp>/` and are
ignored by git. To promote a reviewed run to golden summaries:

```bash
scripts/update_scenario_golden.sh data/scenario_runs/<timestamp>
```

Promoting means copying the reviewed `summary.json` files from a scenario run
into `data/scenario_golden/`. After promotion, future scenario runs compare
their hydrant choice, closure count, and closure road names against those golden
summaries. A changed golden comparison makes `scripts/run_scenarios.sh` exit
nonzero so planner regressions are visible in the test suite.

`scripts/run_scenarios.sh` exits nonzero if a scenario planner run fails or if a
previously approved golden summary changes. Missing goldens are reported so the
first reviewed run can be promoted.

### Reviewing Scenario Runs

After running `scripts/run_scenarios.sh` or `RUN_SCENARIOS=1 scripts/test_all.sh`,
review the newest directory under `data/scenario_runs/`. You can review the same
run in the app from the Scenario Runs panel, or directly from the files.

Start with:

```bash
data/scenario_runs/<timestamp>/report.html
```

The report gives a quick pass/fail and golden comparison for each scenario. A
missing golden means the scenario has not been accepted as a baseline yet. A
changed golden means a previously accepted hydrant or closure result changed and
needs review.

For each scenario, open:

```bash
data/scenario_runs/<timestamp>/<scenario_id>/plan.json
```

From a fire police review perspective, check:

- `summary.selected_hydrant`: whether the hydrant source, name, and location
  make sense for the incident.
- `summary.hose_route.length_ft`: whether the hose run is operationally
  reasonable and within the scenario's `hose_max_ft`.
- `summary.hose_route.curvature`: whether the hose route is unusually twisty.
- `summary.hose_route.elevation_change_ft`: whether elevation change might make
  the hose run harder or slower.
- `summary.closures`: whether the recommended closure roads make sense for
  isolating the incident and protecting the hose.
- `plan.ranked_closures`: detailed closure reasons, road class/cost, county road
  match fields, and sightline caution labels.
- `plan.overlays`: the map-ready incident, hydrant, hose, closure, and warning
  sign features.
- `plan.warning_signs`: advisory MUTCD-based advance-warning sign candidate
  locations.

Compare those outputs against `reviewer_notes`, `expected_hydrant_hint`, and
`expected_closure_hint` in `data/scenarios/incidents.csv`. Promote only after a
human reviewer accepts the selected hydrant, hose route, and closure list.

The app review flow is:

1. Click `Reload Runs` in the Scenario Runs panel.
2. Click the review/search button for the run.
3. Click a scenario result to load its saved map overlays.
4. Review status, golden differences, selected hydrant, hose distance, closure
   ranking, and advisory warning signs.
5. Click the promote button once to arm promotion, then again to confirm.

Recommended workflow for adding expert-reviewed scenarios:

```bash
# 1. Add or edit rows in data/scenarios/incidents.csv, or use the app.

# 2. Rebuild the GraphML around the active scenario set.
scripts/build_scenario_graph.sh

# 3. Run live scenario validation.
scripts/run_scenarios.sh

# 4. Review the latest report and plan JSON files.
#    Confirm selected_hydrant, hose_route, ranked_closures, and notes.

# 5. Promote only after a human accepts the current results.
scripts/update_scenario_golden.sh data/scenario_runs/<timestamp>

# 6. Re-run to verify the promoted goldens now match.
scripts/run_scenarios.sh

# 7. Include live scenarios in the full suite when desired.
RUN_SCENARIOS=1 scripts/test_all.sh
```

## How Recommendations Work

This tool is a decision-support prototype. It does not replace incident command,
local fire police judgment, police coordination, DOT requirements, or MUTCD
engineering judgment.

### Hydrant and Hose Route Choice

For an incident location, the planner looks for hydrants that can be reached
through the road graph within the scenario's maximum hose distance. It scores
candidate hydrants using:

- hose route length
- route curviness
- elevation change, when elevation data is present on the graph

Shorter, straighter, and flatter hose routes score better. If a farther hydrant
creates a straighter or more practical route, it can outrank a closer hydrant as
long as it remains within `hose_max_ft`.

### Road Curviness

Curviness is estimated by walking the road path and adding up the turn angles
between consecutive graph segments. A straight run has low curvature. A route
with many bends, sharp turns, or indirect geometry has higher curvature. The
planner uses this both when scoring hose candidates and when road-edge curvature
data is available for closure/sightline cost.

### Elevation and Sight Visibility

The planner supports elevation-aware scoring where graph nodes or edges include
elevation/grade. Current generated graphs do not yet have comprehensive
elevation enrichment, so elevation change is used when present and otherwise
reported as zero. The planned road enrichment work will make this stronger by
adding reliable grade/elevation data to graph edges.

For closure recommendations, the cost model can penalize road edges with higher
grade or curvature because those conditions can reduce sight distance and make a
closure less desirable. In the UI and output, higher-cost closure edges are
flagged with more caution.

### Closure Recommendation Method

The closure engine uses a network min-cut algorithm. In practical terms:

1. The incident area is treated as the zone to isolate.
2. The surrounding road network is treated as outside traffic.
3. The selected hose route is protected so the algorithm avoids recommending
   closures that block the hose.
4. Each road edge receives a closure cost. Higher-capacity or more disruptive
   roads cost more to close than local streets.
5. Min-cut finds the least-cost set of road edges that separates outside traffic
   from the incident area.

The result is a ranked closure list. It is not saying every listed point must be
closed exactly as shown; it is identifying the road edges that mathematically
separate the incident zone while trying to avoid unnecessarily disruptive
closures and protect the hose route.

### MUTCD Advisory Warning Signs

The planner emits advisory advance-warning sign candidates using defaults from
FHWA's MUTCD 11th Edition with Revision 1, Part 6, Table 6B-1. Initial defaults
are:

- urban low speed: A/B/C = 100/100/100 ft
- urban high speed: A/B/C = 350/350/350 ft
- rural: A/B/C = 500/500/500 ft
- expressway/freeway: A/B/C = 1000/1500/2640 ft

These are advisory starting points. Actual sign placement must account for field
conditions, intersections, driveways, sight distance, available shoulders, police
direction, agency policy, and incident command decisions.

## Current Implementation Details

### Routing Graph Strategy

The planner uses a cached incident-local graph strategy. If
`data/generated/road_graph.graphml` exists, the planner uses that explicit graph.
Otherwise it creates or reuses a graph cache entry under
`data/generated/graph_cache/`, keyed by rounded incident location, study radius,
network type, and cache version.

Use this to prebuild active scenario cache entries:

```bash
scripts/build_graph_cache.sh
scripts/build_graph_cache.sh --scenario-id scenario-norristown-main
```

The older `scripts/build_scenario_graph.sh` remains useful for building a single
combined GraphML around active scenarios. The cache path is better for normal
planner operation because it can reuse incident-local graphs by location.

### County Road Attribute Reconciliation

The displayed county road layer and OSMnx routing graph are currently separate.
At planning time, the backend spatially matches graph edges against the generated
Montgomery County road layer and attaches county attributes where confidence is
high enough:

- `county_st_name`
- `county_func_class`
- `county_owner`
- `county_seg_id`
- `county_match_confidence`

Closure names prefer matched county street names. Closure costs use matched
county functional class when available, then fall back to OSM road class.

### Scenario Review UI

Scenario runs are written to files and are also reviewable from the app. Backend
review endpoints are:

- `GET /api/scenario-runs`
- `GET /api/scenario-runs/{run_id}`
- `GET /api/scenario-runs/{run_id}/scenarios/{scenario_id}`
- `POST /api/scenario-runs/{run_id}/promote`

The frontend Scenario Runs panel lists recent runs, loads saved plan overlays,
and uses a two-step promotion action.

### MUTCD Advance-Warning Placement

The planner emits advisory warning-sign candidates as a separate
`warning_signs` GeoJSON layer. Defaults come from FHWA MUTCD 11th Edition with
Revision 1, Part 6, Table 6B-1:

- urban low speed: A/B/C = 100/100/100 ft
- urban high speed: A/B/C = 350/350/350 ft
- rural: A/B/C = 500/500/500 ft
- expressway/freeway: A/B/C = 1000/1500/2640 ft

These are advisory starting points and need local agency/engineering review
before operational use.

The backend serves API endpoints for GIS layer generation, manual hydrant
editing, geocoding, and incident planning. The frontend is a React + Leaflet map
that consumes those APIs.

## Git

This workspace cannot use a normal `.git` directory because the platform
provides a read-only placeholder. Git metadata is stored in `.repo.git`; use:

```bash
git --git-dir=.repo.git --work-tree=. status
```
