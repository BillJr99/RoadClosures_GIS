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
  closure recommendation rendering

If Playwright browsers are missing, install them once:

```bash
cd frontend
npx playwright install chromium
```

The backend serves API endpoints for GIS layer generation, manual hydrant
editing, geocoding, and incident planning. The frontend is a React + Leaflet map
that consumes those APIs.

## Git

This workspace cannot use a normal `.git` directory because the platform
provides a read-only placeholder. Git metadata is stored in `.repo.git`; use:

```bash
git --git-dir=.repo.git --work-tree=. status
```
