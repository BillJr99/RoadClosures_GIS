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

For live scenario validation, build a local GraphML artifact around the active
scenario locations first:

```bash
scripts/build_scenario_graph.sh
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

## Implementation Plan

### Routing Graph Strategy

The current full-county GraphML build is too slow through Overpass, while the
scenario-local graph builder is practical for validation. The production path
should move to cached incident-local or tiled GraphML artifacts:

1. Add a graph cache keyed by rounded incident location, study radius, and
   network type.
2. Store cache metadata with bbox, source timestamp, node/edge counts, and
   scenario coverage.
3. Prefer cached graphs in the planner and fetch OSMnx only on cache miss.
4. Add a tile prebuild command for operational areas that should work offline.
5. Add tests that verify planner behavior is identical when using a fresh graph
   and a cached graph.

### County Road Attribute Reconciliation

The displayed county road layer and OSMnx routing graph are currently separate.
Reconciliation should transfer county `St_Name`, `FuncClass`, `Owner`, and
related fields onto graph edges:

1. Build a spatial index over Montgomery County road geometries.
2. For each OSMnx edge, find nearby county segments by distance and bearing.
3. Attach the best county match and confidence score to the graph edge.
4. Use matched `FuncClass` and ownership to tune closure cost.
5. Surface matched road names and confidence in planner outputs and reports.

### Scenario Review UI

Scenario runs are currently written to files. The frontend should support review
without leaving the app:

1. Add backend endpoints to list run directories, read run summaries, and read a
   scenario plan output.
2. Add a Scenario Runs panel with status, golden comparison, and report links.
3. Render selected hydrant, hose distance, closure list, and golden differences.
4. Add a guarded "promote run" action that calls the golden update workflow.
5. Add Playwright coverage for reviewing a run and promoting accepted results.

### MUTCD Advance-Warning Placement

MUTCD support should be added after closure recommendations are validated:

1. Start with a rule table for minor, intermediate, and major incidents.
2. Derive advance-warning candidate points along inbound approaches to each
   closure.
3. Include road speed/class, sight distance, curvature, intersections, and
   available shoulder/placement constraints where data exists.
4. Render sign placement candidates as a separate map layer and planner output.
5. Add scenario expectations for sign spacing and blocked/invalid placements.

The backend serves API endpoints for GIS layer generation, manual hydrant
editing, geocoding, and incident planning. The frontend is a React + Leaflet map
that consumes those APIs.

## Git

This workspace cannot use a normal `.git` directory because the platform
provides a read-only placeholder. Git metadata is stored in `.repo.git`; use:

```bash
git --git-dir=.repo.git --work-tree=. status
```
