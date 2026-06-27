from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import cors_allow_origins
from app.routes import jobs, layers, manual_hydrants, planner, scenarios


app = FastAPI(title="Fire Police GIS Cordon Planner")

# Allowed origins default to localhost and are overridable via CORS_ALLOW_ORIGINS.
# A wildcard ("*") cannot be combined with credentials per the CORS spec, and the
# frontend uses plain (credential-less) fetches, so disable credentials in that case.
_cors_origins = cors_allow_origins()
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_origins != ["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(layers.router, prefix="/api")
app.include_router(manual_hydrants.router, prefix="/api")
app.include_router(planner.router, prefix="/api")
app.include_router(scenarios.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
