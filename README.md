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

The backend serves API endpoints for GIS layer generation, manual hydrant
editing, geocoding, and incident planning. The frontend is a React + Leaflet map
that consumes those APIs.

## Git

This workspace cannot use a normal `.git` directory because the platform
provides a read-only placeholder. Git metadata is stored in `.repo.git`; use:

```bash
git --git-dir=.repo.git --work-tree=. status
```
