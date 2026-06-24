from fastapi import APIRouter, HTTPException

from app.models import IncidentPlanRequest
from app.services.planner import plan_incident as run_plan
from app.services.scenario_runner import save_ad_hoc_failure, save_ad_hoc_plan

router = APIRouter(tags=["planner"])


@router.post("/plan")
def plan_incident(payload: IncidentPlanRequest) -> dict:
    try:
        plan = run_plan(payload)
        saved_run = save_ad_hoc_plan(payload, plan)
        return {**plan, **saved_run}
    except ValueError as e:
        save_ad_hoc_failure(payload, str(e))
        raise HTTPException(status_code=422, detail=str(e)) from e
