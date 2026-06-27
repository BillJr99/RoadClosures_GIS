# Fire Police GIS Cordon Planner

Local development app for Montgomery County fire-police road closure planning.

The project keeps the original course/prototype files at the repository root as
legacy references. New implementation code lives under `backend/` and
`frontend/`.

## Quickstart

Start the backend API:

```bash
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8001
```

Access the backend API docs at:

```text
http://127.0.0.1:8001/docs
```

Start the frontend in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Access the frontend app at:

```text
http://localhost:5173/
```

Quick manual test flow:

1. Confirm the backend is healthy at `http://127.0.0.1:8001/api/health`.
2. Open `http://localhost:5173/` and confirm the map loads.
3. Search for a Montgomery County address or click the map to set an incident.
4. Run the incident planner and confirm hydrant, hose route, closure, and
   warning sign results appear.
5. Use the Scenarios panel to view seeded scenarios such as Norristown,
   Lansdale, and Limerick.

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

`frontend/node_modules/` is intentionally ignored by git and is not committed.
If it is missing or was removed after a failed folder move, recreate it from the
lockfile:

```bash
cd frontend
npm install
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
Norristown, Lansdale, and Limerick, plus inactive synthetic edge cases for
algorithm demonstration.

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
  match fields, sightline caution labels, and a `deployment_priority`/
  `deployment_label` (e.g. `P1`) giving the field set-up order (see
  [Deployment Priority](#deployment-priority)).
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

## User Guide: How Recommendations Work

This tool is decision support for fire police planning. It does not replace
incident command, local fire police judgment, police coordination, DOT
requirements, MUTCD engineering judgment, or field conditions observed on scene.

### What the Planner Is Trying To Do

Given an incident point, the app tries to answer four practical questions:

1. Which hydrant is a reasonable source for the hose line?
2. What road path would the hose probably follow from that hydrant?
3. Which roads should be closed to isolate the incident and protect the hose?
4. Where should advance warning signs be considered before drivers reach the
   closure?

### Hydrant and Hose Route Choice

The planner looks for hydrants that can reach the incident through the road
network within `hose_max_ft`. It does not simply pick the closest hydrant by
straight-line distance. It scores reachable hydrants by:

- hose route length
- hose route curviness
- hose route elevation change, when elevation data exists

A farther hydrant can win if it gives a straighter, flatter, more practical hose
run within the maximum hose distance.

### Curvy Roads and Hose Runs

Curviness is a turn-by-turn measure. A straight road segment has little or no
curviness. A road path with many bends or sharp turns has higher curviness.

For a fire police reviewer, higher hose-route curviness means:

- the hose route may be harder to protect
- the hose may cross more complex road geometry
- drivers may have less intuitive sightline to the hazard or closure
- the planner may prefer another hydrant if it gives a straighter route

### Hills, Elevation, and Sight Visibility

Elevation enrichment can add node elevation, edge grade, and elevation change to
the graph. When that data is present, the planner reports hose elevation change
and maximum hose grade. Closure edges can also include grade and elevation
change.

For a fire police reviewer, higher grade or elevation change means:

- hose deployment may be slower or more difficult
- drivers may have less visibility over a crest or around a vertical curve
- closure or warning sign placement may need more conservative field review

The app currently treats sight visibility as a caution signal from available
curve and grade data. It is not yet a full optical line-of-sight simulation.

### Road Closure Recommendations

The app uses a min-cut closure model. In plain language:

1. The incident is the area to isolate.
2. The surrounding road network is outside traffic.
3. The selected hose route is protected.
4. Roads are assigned closure costs. Major roads generally cost more to close
   than local streets.
5. The algorithm finds the least-disruptive set of road edges that separates
   outside traffic from the incident area without cutting the hose route.

The ranked closure list is not an order from the app. It is a suggested set of
control points for review by incident command, fire police, police, and any
agency with roadway authority.

### MUTCD Advisory Warning Signs

The planner emits advisory advance-warning sign candidates using defaults from
FHWA's MUTCD 11th Edition with Revision 1, Part 6, Table 6B-1:

- urban low speed: A/B/C = 100/100/100 ft
- urban high speed: A/B/C = 350/350/350 ft
- rural: A/B/C = 500/500/500 ft
- expressway/freeway: A/B/C = 1000/1500/2640 ft

The app places candidate warning signs along the upstream approach path when the
graph has enough road geometry. If there is not enough upstream graph path, the
sign is flagged with a placement warning. Actual sign placement must account for
intersections, driveways, shoulders, curves, hills, visibility, police direction,
agency policy, and field conditions.

### Synthetic Edge-Case Scenarios

The CSV includes inactive synthetic scenarios for demonstration and algorithm
coverage. They are not expert-reviewed incident examples. They are intended to
exercise cases such as:

- curvy hose routing
- steep-grade routing
- arterial versus local closure tradeoffs
- farther hydrant but straighter hose route
- sparse rural road graph
- high-speed MUTCD approach

Keep synthetic cases inactive until they pass live data and have been reviewed.

## Technical Deep Dive: Algorithms

### Graph Model

Roads are represented as a directed NetworkX graph, usually loaded from OSMnx.
The planner uses an explicit `data/generated/road_graph.graphml` when present.
If that file is absent, it uses an incident-local cache under
`data/generated/graph_cache/`.

Hydrants are loaded from the reconciled hydrant GeoJSON, which combines
authority, OSM, and manual sources.

### Hydrant Routing Algorithm

For each hydrant, the planner snaps the hydrant and incident to nearest graph
nodes. It then uses NetworkX shortest path over edge `length` to estimate the
hose route. Candidates over `hose_max_ft` are rejected.

The hydrant score is a weighted sum of **normalized** terms (lower is better):

```text
score = w_length   * (length_m / hose_max_m)
      + w_curvature * (curvature_radians / pi)
      + w_grade     * (max_grade / MAX_GRADE)
      + w_snap      * (hydrant_snap_m / max_snap_m)
```

Normalizing each term to roughly 0..1 before weighting keeps the weights
unit-free and comparable (instead of mixing raw meters with radians). The
weights live in `ScoringWeights` in `backend/app/config.py`. The planner returns
a per-candidate `score_breakdown` (the normalized contribution of each term) so a
reviewer can see *why* one hydrant beat another.

### Curvature Algorithm

Curvature is computed along a graph path by looking at triples of consecutive
nodes. For each turn, the planner computes the angle between the incoming and
outgoing vectors and adds it to the route's total curvature.

```text
total_curvature = sum(turn_angle_radians)
```

This is a standard geometric proxy for how indirect or bend-heavy a polyline is.
It is not a roadway design-speed calculation.

### Elevation and Grade Algorithm

`scripts/enrich_graph_elevation.sh` enriches GraphML files using USGS EPQS.
Nodes receive `elevation`. Edges receive:

- `elevation_change_m`
- `grade`
- `abs_grade`

Hose elevation change is the sum of absolute elevation differences along the
hose route. Maximum hose grade is the largest absolute edge grade on that path.

### Road Matching Algorithm

The county road layer and OSMnx routing graph are separate data sources. The
road matching service spatially compares each graph edge to nearby Montgomery
County road geometries. The match score combines:

- geometric distance
- bearing difference

High-confidence matches attach county street name, functional class, owner,
segment ID, match confidence, match distance, and bearing difference to graph
edges. Use `scripts/audit_road_matching.sh` to generate a CSV for review.

### Closure Min-Cut Algorithm

The closure problem is modeled as a graph cut:

- super-source: outside traffic/perimeter nodes (nodes beyond
  `PERIMETER_FRACTION` of the study radius, configured in `backend/app/config.py`)
- super-sink: incident-area nodes
- protected edges: hose route edges get very high capacity
- closure cost: road class plus sightline penalties from grade/curvature where
  present

NetworkX `minimum_cut` finds the least-cost edge set separating outside traffic
from the incident area. Those cut edges become closure recommendations.

Each closure's `sightline` label (`good`/`caution`) is derived from the edge's
geometry penalty (`_sightline_penalty`, curvature + grade), not from the road
class, so a sharp or steep approach reads as caution regardless of size. If the
cheapest cut still costs near-infinity (no finite closure set can isolate the
incident without crossing the protected hose route), the response sets
`feasible: false` with a `feasibility_note`, and the UI shows a warning banner
instead of a misleading closure list.

### MUTCD Warning Sign Algorithm

For each closure edge, the planner classifies the road approach as urban low
speed, urban high speed, rural, or expressway/freeway. It then applies MUTCD
Table 6B-1 A/B/C distances and traces upstream along predecessor edges to place
candidate signs. The upstream walk prefers the edge that best continues the
closure's heading (straightest continuation by bearing) so a sign stays on the
intended approach through complex intersections. Outputs include placement status
and warning fields, plus a `shortfall_ft` value showing how far short the graph
fell when a sign is `limited`, so a reviewer can see whether the graph had enough
upstream path.

### Deployment Priority

Closures and signs carry a `deployment_priority` (1 = stage first) so crews with
limited people and barriers know the order to set things up. This is independent
of `rank` (which reflects min-cut cost). The priority score combines:

- **traffic exposure** — the road class cost (`_class_cost`), so busier/higher
  class roads are staged earlier; and
- **visibility** — the sightline penalty from curvature and grade
  (`_sightline_penalty`), so a closure drivers see late is treated as more urgent.

Score is `class_cost * sightline_penalty`, tie-broken by cut capacity. Each
closure feature gets `deployment_priority` and a `deployment_label` like `P1`.
Each advance-warning sign inherits its parent closure's priority and gets a
combined label such as `P1A`/`P1B`/`P1C` (priority + MUTCD sequence). The
frontend shows these as badges in the closure and sign lists and in map
tooltips, and they are intended to carry through to field deployment exports.

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

Enrich graph elevation:

```bash
scripts/enrich_graph_elevation.sh
scripts/enrich_graph_elevation.sh --cache
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

Write a road match audit CSV:

```bash
scripts/audit_road_matching.sh
scripts/audit_road_matching.sh --limit 1000 --output data/generated/road_match_audit.csv
```

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

The maintained application repository lives in `RoadManagement-GIS/` and uses a
normal `.git` directory. From inside this directory, use standard Git commands:

```bash
git status
```

Original source/reference materials such as packet DOCX files, scanned PDFs,
prototype notebooks, and early Python scripts are kept in the parent directory
outside the repo.
