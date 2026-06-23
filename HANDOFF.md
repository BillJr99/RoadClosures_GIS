# Fire Police GIS Cordon Planner Handoff

## Current State

The repository contains a functional MVP implementation:

- FastAPI backend in `backend/`
- React + Leaflet frontend in `frontend/`
- Manual hydrants CSV at `data/manual/manual_hydrants.csv`
- GIS rebuild tooling in `scripts/rebuild_gis_data.sh`
- Full test runner in `scripts/test_all.sh`
- Legacy prototype scripts and planning documents preserved at the repo root

Git metadata is stored in `.repo.git` because this environment provides a
read-only `.git` placeholder. Use:

```bash
git --git-dir=.repo.git --work-tree=. status
git --git-dir=.repo.git --work-tree=. log --oneline --decorate -10
```

Latest known clean commit before this handoff note:

```text
5e578e5 chore: ignore osmnx cache
```

## Generated Data

Generated artifacts are intentionally ignored by git and live in
`data/generated/`.

Last successful live rebuild produced:

- `authoritative_hydrants.geojson`: 7,579 hydrants
- `reconciled_hydrants.geojson`: 7,579 hydrants
- `manual_hydrants.geojson`: 0 manual hydrants
- `roads.geojson`: 92,808 road features

Rebuild commands:

```bash
scripts/rebuild_gis_data.sh hydrants
scripts/rebuild_gis_data.sh roads --skip-graph
scripts/rebuild_gis_data.sh all
```

The full county OSMnx GraphML build was attempted but stopped because Overpass
subdivided Montgomery County into many slow subqueries. The planner currently
falls back to fetching an incident-local OSMnx graph when no GraphML artifact is
available.

## Verification

The full suite passed with:

```bash
scripts/test_all.sh
```

This runs:

- backend unit/route tests with `pytest`
- frontend unit tests with `vitest`
- frontend TypeScript/Vite production build
- Playwright browser orchestration test

In the Codex sandbox, Playwright/Vite server binding may require elevated
execution. In a normal local shell, the script should run directly.

## Run Locally

Backend:

```bash
PYTHONPATH=backend uvicorn app.main:app --host 0.0.0.0 --port 8001
```

Frontend:

```bash
cd frontend
npm run dev -- --port 5173
```

Open:

```text
http://localhost:5173/
```

## What Is Done

- Git repo initialized with frequent milestone commits.
- Prototype data sources ported into backend services:
  - Montgomery County Streets ArcGIS FeatureServer
  - OSMnx/OpenStreetMap road graph source
  - OSM Overpass fire hydrants
  - Lansdale/NPWA authority hydrant layers
  - manual hydrant CSV
  - Nominatim geocoder
- Manual hydrant CSV CRUD implemented in backend.
- Manual hydrants can be added/removed from frontend.
- Reconciled hydrant layer is regenerated from authoritative + manual sources.
- Road and hydrant layer endpoints are implemented.
- Min-cut planner MVP is implemented:
  - picks reachable hydrant candidates
  - scores hose paths by length, curvature, and elevation if available
  - protects hose-route edges
  - computes closure cut edges
- Frontend map shows layers, incident selection, manual hydrants, and closure ranking.

## Recommended Next Work

1. Validate planner behavior against real incident examples.
   Use several known Montgomery County locations and compare selected hydrants,
   hose routes, and closure recommendations against expert expectations.

2. Improve routing graph strategy.
   Full county GraphML via Overpass is too slow. Prefer incident-local graph
   caching or tiled prebuilds instead of one county-wide Overpass job.

3. Reconcile county road attributes onto OSMnx graph edges.
   The current display road layer and routing graph are still mostly separate.
   Matching county `St_Name`, `FuncClass`, and ownership attributes to graph
   edges will improve explainability and closure costs.

4. Add real elevation/curvature enrichment to planner graph edges.
   The old prototypes compute this for road geometries, but the current planner
   only uses these values if already present on graph edges.

5. Expand manual hydrant UI.
   Backend supports update; frontend currently exposes add/remove but not full
   inline edit.

6. Add progress/error UI for long rebuilds.
   Current rebuilds are script/API driven, but frontend feedback is minimal.

7. Add MUTCD advance-warning sign placement after core closure recommendations
   are validated.

