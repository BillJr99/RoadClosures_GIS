from fastapi import APIRouter, HTTPException

from app.models import IncidentPlanRequest
from app.services.planner import plan_incident as run_plan

router = APIRouter(tags=["planner"])


@router.post("/plan")
def plan_incident(payload: IncidentPlanRequest) -> dict:
    try:
        return run_plan(payload)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
