from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import layers, manual_hydrants, planner


app = FastAPI(title="Fire Police GIS Cordon Planner")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(layers.router, prefix="/api")
app.include_router(manual_hydrants.router, prefix="/api")
app.include_router(planner.router, prefix="/api")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}

