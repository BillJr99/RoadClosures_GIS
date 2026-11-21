# Fire Police GIS Cordon Planner

Local development app for Montgomery County fire-police road closure planning.

> **Experimental software.** This is a research and teaching prototype provided as is, with no warranty of any kind. It is not intended for production use, and its recommendations (hydrant selection, hose routing, road closures, warning signs and channelizing devices) must not be relied on for actual emergency response or traffic-control decisions. Always follow your agency's procedures, the MUTCD, and the judgment of trained personnel.

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

## Start/stop scripts

Once dependencies are installed (the backend virtualenv and `frontend/node_modules`,
per the Quickstart above), two helper scripts start and stop both servers together
from the repository root:

```bash
./run.sh    # start backend + frontend in the background
./stop.sh   # stop both
```

`run.sh`:

- Starts the backend with `PYTHONPATH=backend uvicorn app.main:app --host <host> --port <port>`,
  using the repo-root `.venv/bin/uvicorn` if present (otherwise `uvicorn` from `PATH`).
- Starts the frontend with `npm run dev -- --host <host> --port <port>`.
- Runs both in the background, recording process IDs in `backend.pid` / `frontend.pid`
  and redirecting output to `backend.log` / `frontend.log` (all gitignored). It refuses
  to start if a recorded process is still running — run `./stop.sh` first.

`stop.sh` reads the PID files, terminates each process group (cleaning up the uvicorn
reloader and Vite's child processes), escalates from `TERM` to `KILL` after a few
seconds if needed, and removes the PID files.

Host and port default to backend `0.0.0.0:8001` and frontend `0.0.0.0:5173`, and are
overridable via environment variables:

```bash
BACKEND_HOST=127.0.0.1 BACKEND_PORT=9000 FRONTEND_PORT=3000 ./run.sh
```

| Variable        | Default   | Purpose                         |
| --------------- | --------- | ------------------------------- |
| `BACKEND_HOST`  | `0.0.0.0` | Backend uvicorn bind address    |
| `BACKEND_PORT`  | `8001`    | Backend uvicorn port            |
| `FRONTEND_HOST` | `0.0.0.0` | Frontend Vite bind address      |
| `FRONTEND_PORT` | `5173`    | Frontend Vite dev server port   |

> **Note:** `VITE_API_BASE` is baked into the frontend bundle at build/dev time, so if
> you move the backend to a non-default host/port, set `VITE_API_BASE` accordingly (see
> [Configuring server locations](#configuring-server-locations-non-localhost-deployments)).

To run the servers manually instead (e.g. in separate terminals with `--reload`), see
the [Development](#development) section below.

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

### Configuring server locations (non-localhost deployments)

Both sides assume `localhost` by default but are configurable for deployment.

**Frontend API base — `VITE_API_BASE`.** The frontend reads
`import.meta.env.VITE_API_BASE` (see `frontend/src/api.ts`), defaulting to
`http://localhost:8001/api`. This is **baked in at build time** (Vite inlines the
value during `npm run build`/`npm run dev`), so set it *before* building the bundle
you deploy — editing the served files afterward will not change it. A
`frontend/.env.example` documents it; copy it to `frontend/.env` (or
`.env.production`) and set the value, or pass it inline:

```bash
VITE_API_BASE=https://gis.example.org/api npm run build
```

**Backend CORS — `CORS_ALLOW_ORIGINS`.** The backend only accepts cross-origin
browser requests from allowed origins (`cors_allow_origins()` in
`backend/app/config.py`). Behavior:

- **unset (default):** localhost only — `http://localhost:5173` and
  `http://127.0.0.1:5173` (the assumed local setup).
- **`*`:** all sources.
- **a comma-separated list of origins:** those exact origins are allowed — *unless*
  any of them is non-localhost (a real deployment elsewhere), in which case CORS is
  opened to **all sources** so the frontend can be served from anywhere without
  enumerating its exact origin.

```bash
# Local default — nothing to set.
# Deploy elsewhere: any non-localhost origin opens CORS to all sources.
CORS_ALLOW_ORIGINS=https://gis.example.org uvicorn app.main:app --host 0.0.0.0 --port 8001
```

When CORS is opened to all sources, credentialed requests are disabled
automatically (the CORS spec forbids `*` with credentials; the frontend uses plain
fetches, so this is fine).

### Backend logging

The backend logs comprehensively to a rotating log file for after-the-fact
debugging: `data/logs/backend.log` (5 MB per file, 5 rotated backups kept,
ignored by git). Logging is configured in `backend/app/logging_setup.py` at
app startup and also mirrors uvicorn's server/access logs into the same file,
so one file tells the whole story of a request:

- every `/plan` request with its parameters, duration, and outcome (success
  with closure/warning counts, 422 with the reason, or an unexpected-crash
  traceback)
- which road graph was used (configured artifact, tile, cache, or fresh OSM
  fetch) and why a fallback was taken
- the hydrant filter counters (total checked, accepted, rejected by
  straight-line distance / route length / no road path) and the
  envelope-exceeded fallback when it triggers
- min-cut results and infeasibility warnings, background job start/finish/
  failure (with tracebacks), and GIS data-source fetch progress/failures

Environment overrides:

```bash
LOG_LEVEL=DEBUG   # default INFO
LOG_FILE=/var/log/firepolice/backend.log   # default data/logs/backend.log
```

Per-run planner failure details also continue to be written under
`data/scenario_runs/<run>/planner_debug.{json,log}`, and every plan response
carries a `_debug` block with the same diagnostics the log records.

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

- backend unit/API tests with `pytest`, including hydrant reachability over
  one-way streets (undirected hose routing) and the envelope-exceeded fallback
  path (`backend/tests/test_planner_hydrant_routing.py`)
- frontend unit tests with `vitest`
- frontend production build with Vite/TypeScript
- Playwright browser orchestration tests that mock API responses and exercise
  layer loading, address search, manual hydrant add/edit/remove, the background
  rebuild job, scenario CRUD/run controls, closure recommendation rendering with
  deployment-priority badges and MUTCD codes, hydrant explainability, CSV
  export, and the hose-envelope warning banner with the amber fallback hydrant
  legend

All of these run offline (no live GIS services needed) and run in CI on every
push and pull request (`.github/workflows/ci.yml`).

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

> **Where runs are saved (and how to delete them).** Every scenario run —
> whether started from `scripts/run_scenarios.sh`, the test suite, or the app —
> is saved as a timestamped folder under **`data/scenario_runs/`** (relative to
> the repository root, i.e. `RoadManagement-GIS/data/scenario_runs/`). Ad-hoc
> runs triggered from the app are prefixed `adhoc-`. This directory is listed in
> `.gitignore`, so runs are **never committed** and stay local to whichever
> machine produced them. They are safe to remove by hand at any time when you
> want to reclaim space or clear old results, e.g. delete individual
> `data/scenario_runs/<timestamp>/` folders, or clear them all with
> `rm -rf data/scenario_runs/*`. Promoted goldens live separately under
> `data/scenario_golden/` and are **not** removed by deleting runs.

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

Hose routes are computed over an **undirected** view of the road graph: a hose
is laid on the ground and does not obey one-way restrictions, so a hydrant on a
one-way street pointing away from the incident is still reachable. (Closure
recommendations still use the directed graph, because traffic does obey one-way
restrictions.)

### When No Hydrant Fits the Hose Envelope

If no hydrant's hose run fits within `hose_max_ft`, the planner does not fail.
It falls back to the nearest road-reachable hydrant(s) — crews still need the
closest water source for relay pumping or tanker shuttle — and:

- returns the full plan with a `warnings` list explaining what was checked
  (how many hydrants, how many were too far in a straight line, how many had
  hose routes that were too long, how many were unreachable by road) and how
  far the closest hose run exceeds the envelope;
- flags the fallback hydrants and hose routes with `exceeds_envelope: true`
  and a `hose_deficit_ft` value;
- shows an amber warning banner in the sidebar and draws the selected hydrant
  ring amber instead of light blue (see the map legend entry "Hydrant beyond
  hose envelope").

The request only fails (HTTP 422) when there is no road-reachable hydrant at
all within the study radius, or when no road graph covers the incident
location.

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

### Multiple (Secondary) Incidents

A single scene can have more than one point to isolate. After placing the primary
incident, use **Add secondary incident** and click the map to add another. All
incident dots are red and **numbered** (1 = primary, 2, 3, … in placement order).
Adding a secondary incident **re-runs the recommendations automatically** for the
whole set: the closure min-cut isolates *all* incident areas at once (each is a
sink in the same cut) while still protecting the hose route, and advance signs and
devices are generated for the combined closure set. The Resource Availability
counts scale to the larger plan automatically when you have not capped them, and
otherwise stay at the limits you set (see
[Resource Availability](#resource-availability-limited-resource-deployment)).

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

### Hydrant Selection Algorithm

The planner does **not** simply take the nearest hydrant. It takes the best
hydrant **whose full hose run fits within the hose envelope** (`hose_max_ft`,
configurable from the UI Configuration pulldown), and among those it **favors a
straighter run** — preferring a farther but straight hydrant over a closer one
reached only through sharp turns.

**Reachability — the hose envelope is the only distance limit.** For each
hydrant the planner snaps the hydrant and the incident to their nearest graph
nodes and computes the NetworkX shortest path over edge `length`. The full hose
run is

```text
hose_run = road_path_length + hydrant_to_road_gap + road_to_incident_gap
```

i.e. the on-road path plus the short off-road "snap" gap at each end. A hydrant
is reachable **iff `hose_run <= hose_max_ft`**. There is no separate hard-coded
maximum snap/standoff distance — the snap gaps are simply part of the hose run,
so the single configurable hose envelope governs reachability. (Earlier versions
applied a hidden 250 ft snap cap that could reject a perfectly reachable hydrant
whenever the incident or hydrant sat more than 250 ft from a mapped road; that
cap has been removed.)

**Selection — straighter is better.** Among reachable hydrants, the planner picks
the lowest score, a weighted sum of **normalized** terms (lower is better):

```text
score = w_length    * (hose_run / hose_max)        # shorter is better
      + w_curvature  * (curvature_radians / pi)     # straighter is better
      + w_grade      * (max_grade / MAX_GRADE)       # flatter is better
```

Each term is normalized to roughly 0..1 so the weights are unit-free and
comparable. Curvature is weighted **as heavily as length** (`w_curvature == w_length`),
which is what lets a longer-but-straight run beat a shorter-but-twisty one; raise
`curvature` further in `ScoringWeights` (`backend/app/config.py`) to favor
straightness even more. The off-road snap gaps are already inside `hose_run`, so
they are not scored a second time. The planner returns a per-candidate
`score_breakdown` (the normalized contribution of each term) so a reviewer can see
*why* one hydrant beat another.

**Which road graph is used.** Snapping and routing need a road graph that
actually covers the incident. The planner uses the configured
`data/generated/road_graph.graphml` only when the incident snaps within
`CONFIGURED_GRAPH_SNAP_TOLERANCE_FT` (default 300 ft, `backend/app/config.py`) of a
road in it — a *data-coverage* check, distinct from hose reach. If the incident is
outside that artifact's coverage (the artifact may only cover one municipality),
the planner falls through to a prebuilt operational-area tile or a freshly fetched
incident-local graph (see [Routing Graph Strategy](#routing-graph-strategy)) so a
small artifact is never misused for incidents it does not cover.

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
  present, then **distance-weighted** (see below)

NetworkX `minimum_cut` finds the least-cost edge set separating outside traffic
from the incident area. Those cut edges become closure recommendations.

**Distance-weighted cordon.** A plain min-cut minimizes total cost with no notion
of *where* the cut sits, so on some road networks the cheapest separating set is a
scatter of cheap local streets far from the incident rather than a tight ring
around it. To fix that, each road's cut cost is multiplied by

```text
1 + CLOSURE_DISTANCE_WEIGHT * (distance_from_incident / study_radius)
```

(`CLOSURE_DISTANCE_WEIGHT` in `backend/app/config.py`, default 8.0). Closing a road
far from the incident is therefore much more expensive than closing one nearby, so
the minimum cut forms the tightest sensible cordon hugging the incident. The
weighting only changes outcomes where a scattered cheaper cut existed; where the
tight ring was already optimal (as in the seeded Norristown scenario) the result is
unchanged. The distance multiplier drives only the cut; the **road-class cost**
(`base_capacity`) is what is reported and used for ranking, so a near major road
still ranks above a far minor one and the displayed closure cost reflects the road,
not how far away it is.

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

Each advance-warning sign now carries an MUTCD designation: the closest sign is
`W20-3` (ROAD CLOSED AHEAD) and the further advance signs are `W20-1`, with a
standard `sign_size_in`. Signs also report `road_type_basis` (which rule chose
the spacing band) and `speed_source` (`maxspeed` vs `missing`) so the chosen
Table 6B-1 row is auditable when posted speed data is absent.

### Channelizing Devices and Barricades

For each closure the planner also emits field hardware (`plan.devices`):

- a **Type III barricade** (`kind:"barricade"`) at the closure midpoint, carrying
  the `R11-2` ROAD CLOSED sign; and
- a **cone/drum taper** (`kind:"channelizing_device"`) on each approach.

Taper length follows MUTCD Part 6: `L = W·S²/60` below 45 mph, else `L = W·S`
(lane width `W` defaults to 12 ft; speed `S` from `maxspeed`, else a per–road-type
default). Device spacing along the taper is the posted speed in feet. Devices
inherit the parent closure's `deployment_priority`.

### Approach Coverage (compliance)

`plan.compliance` summarizes advance-warning coverage: each closure has two
approach sides, and a side counts as covered only when an advance sign was
actually placed on the graph (not merely projected). The UI shows covered vs
total sides so reviewers can spot approaches that still need signs.

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

### Resource Availability (limited-resource deployment)

Real incidents rarely have unlimited barriers, cones, signs, or people. The
**Resource Availability** controls in the Configuration pulldown let the planner
show only what can actually be staged, using the deployment priority above to
decide *which* items make the cut. Each control is a number stepper (−/＋ or
type-in):

- **Road closures**, **Barricades**, **Channelizing devices**, and **Signs** —
  how many of each you have available.

The counts are a **sticky inventory**: they initialize from the current plan's
totals (so everything shows by default) and then persist across subsequent plans
instead of resetting, so "I have 4 barricades" stays set. The map updates in real
time as you change them; each control shows "N of TOTAL shown".

Filtering is hierarchical and cascades, matching how crews actually scale back:

1. **Road closures** are limited first. The deployed set is the top-N closures by
   deployment priority; the **lowest-priority closures are dropped first**.
2. Dropping a closure **frees the resources tied to it** — its advance-warning
   signs, channelizing-device taper, and barricade (matched by `closure_rank`)
   are removed from the map along with the closure itself.
3. The per-type caps (barricades / channelizing / signs) then apply to whatever
   remains on the still-deployed closures, again keeping the highest-priority
   items.

Raising the closure count **restores** a closure and re-deploys its associated
resources, up to the per-type maxima still set in the panel. This is a display/
planning aid built from the plan the UI already holds; it does not change the
underlying plan or the CSV/print exports.

### Performance

- **Hydrant pre-filter**: hydrants are projected once (batched) and culled with a
  SciPy KD-tree (`_within_radius_indices`) before any routing work, and the
  survivors are snapped to graph nodes in a single batched `nearest_nodes` call
  (`_nearest_nodes_xy`) instead of one call per hydrant.
- **Min-cut**: the closure cut uses the `preflow_push` flow function, which is
  typically much faster than the default on road-sized graphs (the min-cut value
  is unique, so results are unchanged).
- **Plan-result cache**: identical incident + parameters over the same graph
  return a cached result instantly (`backend/app/services/plan_cache.py`, stored
  under `data/generated/plan_cache/`, versioned by `PLAN_CACHE_VERSION`). Cached
  responses are flagged with `graph_source.plan_cache_hit`.
- **Map rendering**: the map uses Leaflet canvas rendering (`preferCanvas`) and
  only draws the county-wide road layer at zoom ≥ 11 (`ZoomGate`).

### Background Jobs

Long operations run as background jobs so the UI stays responsive:

- `POST /api/jobs/build?include_graph=true` starts a layer rebuild and returns
  `{ job_id }`.
- `GET /api/jobs/{job_id}` returns `{ status: pending|running|done|error, result,
  error }`.

The frontend submits the build job and polls until completion, showing a
"Building…" state. Jobs are in-memory and process-local
(`backend/app/services/jobs.py`).

### GIS Data Controls (Layers panel)

The sidebar Layers panel has three distinct data actions plus a browser-side
cache. They are easy to confuse, so here is exactly what each does:

- **Refresh Layers** — re-fetches the displayed map layers, scenarios, and runs
  from the server into the view. The large road and hydrant layers are served
  from the **local browser cache** when a recent copy exists (see below), so this
  is fast and does not necessarily hit the network for them. Use it to pull in
  edits (e.g. new scenarios/manual hydrants) without a full re-download.
- **Update Cache** — forces a fresh **re-download** of the road and hydrant
  layers from the server and overwrites the local browser cache. Use it when you
  know the server-side data changed and you want the newest copy now (it bypasses
  the cache rather than waiting for it to expire).
- **Rebuild GIS Data** — regenerates the road, hydrant, and routing-graph data on
  the **server** from the upstream sources (OSM + county layers) via the
  background build job above. This is the heavy operation that changes the
  underlying data; afterwards the frontend force-refreshes so the new data is not
  masked by the cache.

**Browser layer cache.** The road and hydrant layers (the hydrants GeoJSON is
~2 MB) are cached in the browser using **IndexedDB** so a page reload reuses a
recent copy instead of re-downloading (`frontend/src/layerCache.ts`). The cache
has a hard **7-day** expiration (`LAYER_CACHE_TTL_MS`); after that an entry is
considered stale and re-fetched. When layers are served from this cache, the
data-load status toast notes it and how old the cached copy is. "Update Cache"
and "Rebuild GIS Data" both bypass/replace the cache. The cache is resilient: if
IndexedDB is unavailable it silently falls back to a normal network fetch.

### Field-Deployment Exports and Explainability

The Plan Review panel can export the current plan for field use, built entirely
from the plan the UI already holds (no server round-trip, no extra dependencies,
`frontend/src/export.ts`):

- **Signs & devices CSV** — every advance-warning sign and channelizing device,
  ordered by deployment priority, with MUTCD code, approach, distance, placement
  status, and lat/lon.
- **Closures CSV** — ranked closures with priority, cost, sightline, and reason.
- **Print report** — a print-friendly HTML view (browser print-to-PDF).

The panel also explains *why* the recommended hydrant won, showing the normalized
`score_breakdown` contributions, and surfaces the infeasibility banner and
approach-coverage compliance.

### Frontend Module Layout

`frontend/src/` is split into focused modules: `types.ts` (shared types),
`api.ts` (API base + `jsonFetch`), `export.ts` (CSV/printable exports),
`mapView.tsx` (the Leaflet map and its sub-components), and `main.tsx` (the app
shell, sidebar panels, and state).

## Current Implementation Details

### Routing Graph Strategy

The planner resolves a routing graph in this order:

1. **Configured GraphML** — `data/generated/road_graph.graphml`, when present and
   it covers the incident.
2. **Operational-area tile** — a prebuilt larger graph that fully contains the
   incident's study area (see below). This enables offline planning across a
   whole response area.
3. **Incident-local cache** — a graph cache entry under
   `data/generated/graph_cache/`, keyed by rounded incident location, study
   radius, network type, and cache version (fetched from OSM on first use).

Use this to prebuild active scenario cache entries:

```bash
scripts/build_graph_cache.sh
scripts/build_graph_cache.sh --scenario-id scenario-norristown-main
```

### Operational-Area Tiles (offline planning)

A tile is a larger road graph (e.g. a municipality or response district) saved
once to GraphML under `data/generated/graph_tiles/`, with an `index.json` listing
each tile's center and radius. When an incident's study disc fits entirely inside
a tile (`distance(center, incident) + study_radius <= tile.radius`), the planner
loads the tile instead of fetching a fresh incident-local graph — so after a
one-time prebuild the whole area can be planned with no network. The tightest
covering tile is chosen for speed. See `backend/app/services/graph_tiles.py`.

Prebuild tiles (requires network at build time only):

```bash
# One tile per active scenario, 8000 ft radius (default)
scripts/build_operational_tiles.sh
# Explicit centers / radius
scripts/build_operational_tiles.sh --center 40.115,-75.343 --radius-ft 10000
scripts/build_operational_tiles.sh --scenario-id scenario-norristown-main
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

## Graph Theory and Its Applications

This chapter explains the graph theory the planner rests on and how each concept
maps to a concrete fire-police decision. None of it requires prior graph theory;
each idea is introduced before it is used.

### Why a graph at all

A road network is naturally a **graph**: a set of **nodes** (vertices) connected by
**edges**. In this app:

- **Nodes** are intersections and the endpoints of road segments. Each node has a
  projected coordinate (`x`, `y`) in meters (UTM), and optionally an `elevation`.
- **Edges** are the road segments between nodes. Each edge carries attributes:
  `length` (meters), road class (`highway`, `county_func_class`), an optional
  curved `geometry` (the real road polyline), and — when elevation enrichment has
  run — `grade` and `elevation_change_m`.

The graph is **directed** (a `DiGraph`/`MultiDiGraph` from OSMnx): an edge `u → v`
models travel in one direction, so one-way streets and asymmetric turns are
representable. Parallel edges between the same pair of nodes (a divided road, a
service lane) are collapsed to the shortest one where a single edge is needed.

Representing roads as a graph is what makes the four core questions answerable with
standard, well-understood algorithms instead of ad-hoc geometry:

1. *Which hydrant can feed the scene?* → **shortest path**.
2. *What route would the hose follow?* → the **path** itself.
3. *Which roads isolate the scene?* → **minimum cut / maximum flow**.
4. *Where do advance signs go?* → a **bounded walk** along predecessor edges.

### Shortest paths (hydrant reachability and hose routing)

To decide whether a hydrant can reach the incident within the hose envelope, the
planner snaps both the hydrant and the incident to their nearest graph nodes and
computes the **shortest path** over edge `length` using NetworkX (Dijkstra's
algorithm). The path's total length is the estimated hose run; candidates longer
than `hose_max_ft` are rejected.

Shortest path is the right model because hose is laid *along roads*, not as the
crow flies. A hydrant that is closer in straight-line distance can lose to a
slightly farther one whose road path is shorter, straighter, or flatter. The graph
makes "distance along the road network" a first-class, computable quantity.

> Dijkstra's algorithm runs in `O(E + V log V)` time on a graph with `V` nodes and
> `E` edges; on incident-local road graphs this is effectively instantaneous.

### Curvature (a geometric property of a path)

**Curvature** is a property of a *path through the graph*, not of a single edge. For
each interior node on a path the planner measures the turn angle between the
incoming and outgoing direction vectors and sums those angles:

```text
total_curvature = Σ turn_angle_radians   (over consecutive node triples)
```

A straight run accumulates ~0; a path with many bends accumulates more. This is a
standard geometric proxy for how indirect or bend-heavy a polyline is. It feeds the
hydrant score (a curvier hose run is penalized) and the closure **sightline** label
(a curvier approach is harder to see and is flagged `caution`).

### Maximum flow and minimum cut (road closures)

Isolating an incident is a **graph separation** problem, solved with the classic
**max-flow / min-cut** duality:

- A **cut** is a set of edges whose removal disconnects one group of nodes from
  another. Here it disconnects *outside traffic* from the *incident area*.
- The **minimum cut** is the cheapest such set, where each edge has a **capacity**
  (its closure cost). By the **max-flow/min-cut theorem**, the value of the minimum
  cut equals the value of the maximum flow between the two sides, which is what lets
  NetworkX compute it efficiently.

The construction (see `_build_flow_graph`):

- a **super-source** connected to all *perimeter* nodes (beyond `PERIMETER_FRACTION`
  of the study radius) — "outside traffic";
- a **super-sink** connected to all *incident-area* nodes — the scene to isolate;
- **protected edges**: every edge on the chosen hose route is given (effectively)
  infinite capacity, so the cut can never sever the hose line;
- **closure cost** per edge: road-class cost × sightline penalty, then
  distance-weighted toward the incident (see
  [Closure Min-Cut Algorithm](#closure-min-cut-algorithm)).

The minimum cut is then exactly "the least-disruptive set of road closures that
separates through-traffic from the incident without cutting the hose." If even the
cheapest cut is infinite (the only separators cross the protected hose), the scene
is reported **infeasible** rather than returning a misleading list. The planner uses
the `preflow_push` max-flow algorithm, which is fast on road-sized graphs and
returns the same (unique) min-cut value as the default solver.

### Connectivity, components, and feasibility

Whether a finite cut even exists is a **connectivity** question. If the incident
area and the perimeter live in different connected components, or the only paths
between them are protected hose edges, no finite separating set exists — surfaced as
`feasible: false`. Reasoning about the network as a graph makes these structural
edge cases explicit instead of silent.

### Spatial indexing (making the graph usable at scale)

Two non-graph steps make the graph practical:

- **Nearest-node snapping** maps a lat/lon (incident, hydrant) to the closest graph
  node. Hydrants are projected once in a batch and culled with a **SciPy KD-tree**
  (`_within_radius_indices`) before any routing, so only plausibly-reachable
  hydrants are ever routed — turning an `O(hydrants × path)` scan into a fast
  spatial query plus a handful of shortest paths.
- **Operational-area tiles** and an **incident-local cache** store prebuilt graphs
  so planning can run offline after a one-time fetch (see
  [Routing Graph Strategy](#routing-graph-strategy)).

### How the pieces compose

A single plan threads all of the above: snap incident → KD-tree cull hydrants →
shortest-path each survivor (length, curvature, grade) → score and pick → protect
that path's edges → distance-weighted min-cut for closures → bounded upstream walk
for advance signs and channelizing tapers. Every step is a standard graph or
computational-geometry operation, which is what keeps the recommendations auditable
and reproducible.

## MUTCD Standards and Resource Placement

Every field resource the app proposes is **advisory** and derived from published
**MUTCD** defaults (the FHWA *Manual on Uniform Traffic Control Devices*, 11th
Edition with Revision 1). The app applies the standard's default spacings and sizes;
it does **not** replace engineering judgment, the authority having jurisdiction,
police direction, or field conditions (intersections, driveways, sightlines, grade,
weather). The citations below are the specific provisions each placement is based
on, and where in the code they live.

### Resources considered in this app (glossary)

- **Advance-warning sign** — a sign placed *upstream* of a closure to warn
  approaching drivers before they reach it. The app emits an A/B/C sequence (the
  closest sign first, then farther ones). MUTCD codes used:
  - **`W20-3` "ROAD CLOSED AHEAD"** — the nearest advance-warning sign (sequence A).
  - **`W20-1`** — the farther advance-warning signs (sequences B/C).
  - Reference: warning-sign series, MUTCD Part 2C / Part 6; sizes from the
    conventional-road standard (Table 2C-2). See `ADVANCE_SIGN_SPECS` in
    `backend/app/services/warning_signs.py`.
- **`R11-2` "ROAD CLOSED" sign** — a *regulatory* sign mounted at the closure point
  itself, carried on the barricade. Reference: MUTCD Part 2B / Part 6 (`R11`
  series). See `CLOSURE_POINT_SIGN`.
- **Type III barricade** — a full-width barricade (three reflectorized rails on
  supports) used to physically close a road. The app places one at each closure's
  midpoint, carrying the `R11-2` sign. Reference: MUTCD Part 6 channelizing/barricade
  provisions.
- **Channelizing device** — a **cone, tubular marker, or drum** used to form a
  *taper* that guides (channelizes) traffic away from the closed area. Channelizing
  devices *guide*; the barricade *blocks*. The app places a cone/drum taper on each
  approach to a closure. Reference: MUTCD Part 6 channelizing-device and taper
  provisions. See `device_features`.

### Advance-warning sign spacing — Table 6B-1

Advance-warning sign distances come from **MUTCD 11th Edition, Rev. 1, Part 6,
Table 6B-1** (recommended advance-warning sign spacing), keyed by road type:

| Road type            | A    | B    | C    |
|----------------------|------|------|------|
| urban low speed      | 100  | 100  | 100  |
| urban high speed     | 350  | 350  | 350  |
| rural                | 500  | 500  | 500  |
| expressway/freeway   | 1000 | 1500 | 2640 |

(distances in feet). The road type is chosen from posted speed (`maxspeed`) when
available, else the road class; the choice is recorded on each sign as
`road_type_basis` and `speed_source` so the selected Table 6B-1 row is auditable
even when posted speed is missing. Spacing values live in `MUTCD_TABLE_6B1`.

### Channelizing-device tapers — Part 6 taper formula

Taper **length** `L` for one lane width `W` at speed `S` follows the MUTCD Part 6
merging-taper formulas:

```text
L = W · S² / 60      for S < 45 mph
L = W · S            for S ≥ 45 mph
```

with `W` defaulting to a 12 ft lane and `S` from `maxspeed` (else a per–road-type
default). Channelizing-device **spacing** along the taper is taken as the posted
speed in feet (MUTCD guidance that device spacing in a taper should not exceed a
distance in feet equal to the speed in mph). See `_taper_length_ft` and
`device_features`.

### Placement, deployment priority, and compliance

- Signs and tapers are traced **upstream along the actual road geometry**, preferring
  the straightest continuation through intersections so a sign stays on the intended
  approach. When the graph runs out of upstream road, the sign is flagged `limited`
  with a `shortfall_ft` so a reviewer can see the graph fell short.
- Each closure and its signs/devices carry a **deployment priority** (traffic
  exposure × visibility) telling crews the order to stage things under limited
  resources. The Resource Availability controls use this priority to decide which
  items to show when you tell the app how many barricades, channelizing devices, or
  signs you actually have.
- `plan.compliance` summarizes advance-warning **coverage**: each closure has two
  approach sides, and a side counts as covered only when an advance sign was actually
  placed on the graph (not merely projected).

All of the above are MUTCD-derived **starting points** and must be reviewed against
field conditions and agency policy before use.

## Creating and Uploading Golden Reports

A **golden report** is an accepted, expert-reviewed expectation for a scenario. Once
a scenario has a golden, every future run is compared against it, so the app — and
its automated test suite — can flag when a planner change alters a previously
accepted result. There are two complementary kinds of golden, and both can be
created from any run, scenario, or ad-hoc incident.

### The two kinds of golden

1. **Promoted-run golden (regression baseline).** The reviewed `summary.json` from a
   specific run, copied into `data/scenario_golden/`. It captures *what the planner
   produced and a human accepted*: selected hydrant, closure count, and closure road
   names. Future runs that differ from it are reported as `changed`.
2. **Expert golden (human expectation).** A hand-authored statement of what a domain
   expert *expects* — expected hydrant, expected closure roads, expected advance
   signs, plus reviewer name and notes — stored as a `ScenarioGolden`
   (`data/scenarios/goldens/`). It encodes ground truth independent of the current
   algorithm and is compared first (`compare_to_expert_golden`).

### Creating a golden from a run (promotion)

Any run — a scenario run *or* an ad-hoc "Recommend Closures" incident — can become a
golden once a reviewer accepts it:

1. Run the scenario (or save an ad-hoc incident from the map).
2. Open the run's **View report** (the what/where/why HTML report) and review the
   selected hydrant, hose route, ranked closures, and advance signs against your
   field judgment and the scenario's `reviewer_notes` /
   `expected_hydrant_hint` / `expected_closure_hint`.
3. In the **Scenario Runs** panel, expand the run and click **Promote Run** once to
   arm, then again to confirm (two-step to prevent accidental promotion). This calls
   `POST /api/scenario-runs/{run_id}/promote`, which copies the reviewed summaries
   into `data/scenario_golden/`.

From the command line the same promotion is:

```bash
scripts/update_scenario_golden.sh data/scenario_runs/<timestamp>
```

After promotion, re-run the scenario to confirm the golden now matches.

### Creating / uploading an expert golden through the UI

To record a human expectation (independent of what the planner currently does), use
the scenario's **golden editor** in the app:

1. Select the scenario.
2. Open its golden editor and fill in the expected hydrant (name/source), the
   expected closure roads (one per line, `road | reason | notes`), the expected
   advance signs (`road | sign label | distance_ft | notes`), and reviewer name /
   notes.
3. Save. The UI sends `PUT /api/scenarios/{scenario_id}/golden` (model
   `ScenarioGolden`), persisting it to `data/scenarios/goldens/`. `DELETE` removes
   it; `GET` re-loads it for editing.

Because the expert golden is plain structured text, it can also be authored or
bulk-edited in the goldens files directly and picked up by the app on reload.

### How goldens inform the app and its tests

- **In the app:** when you review a run, the Scenario Runs panel shows the golden
  comparison — `matched`, `expert_matched`, `missing` (no golden yet), or `changed`
  (a previously accepted result moved and needs review).
- **In the test suite:** `scripts/run_scenarios.sh` (and
  `RUN_SCENARIOS=1 scripts/test_all.sh`) runs every active scenario and **exits
  nonzero** if a run fails or if a previously approved golden changes. Promoting a
  reviewed run therefore turns it into a regression test; authoring an expert golden
  turns expert judgment into an automated check. Missing goldens are reported (not
  failures) so the first reviewed run can be promoted.

Promote or author goldens **only after a human accepts** the hydrant, hose route,
and closure list — a golden is a commitment that "this result is correct," so the
quality of the regression suite is exactly the quality of the reviews behind it.

## Git

The maintained application repository lives in `RoadManagement-GIS/` and uses a
normal `.git` directory. From inside this directory, use standard Git commands:

```bash
git status
```

Original source/reference materials such as packet DOCX files, scanned PDFs,
prototype notebooks, and early Python scripts are kept in the parent directory
outside the repo.

## License

Released under the MIT License. See [LICENSE](LICENSE).
