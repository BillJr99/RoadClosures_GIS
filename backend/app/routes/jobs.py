from fastapi import APIRouter, HTTPException, Query

from app.config import SOURCES
from app.services import jobs
from app.services.hydrants import generate_hydrant_layers
from app.services.roads import generate_road_layers

router = APIRouter(tags=["jobs"])


@router.post("/jobs/build")
def start_build_job(include_graph: bool = Query(default=True)) -> dict:
    """Start a layer rebuild in the background and return a job handle to poll."""

    def _build() -> dict:
        return {
            "bbox": SOURCES.bbox_wgs84,
            "roads": generate_road_layers(include_graph=include_graph),
            "hydrants": generate_hydrant_layers(),
        }

    job_id = jobs.start_job("build", _build)
    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job
