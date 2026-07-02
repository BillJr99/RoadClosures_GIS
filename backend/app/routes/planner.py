import logging
import time

from fastapi import APIRouter, HTTPException

from app.models import IncidentPlanRequest
from app.services.planner import plan_incident as run_plan
from app.services.scenario_runner import save_ad_hoc_failure, save_ad_hoc_plan

router = APIRouter(tags=["planner"])
logger = logging.getLogger("app.routes.planner")


@router.post("/plan")
def plan_incident(payload: IncidentPlanRequest) -> dict:
    logger.info(
        "Plan requested: lat=%.6f lon=%.6f hose_max_ft=%g study_radius_ft=%g "
        "hydrant_count=%d secondary_incidents=%d",
        payload.lat,
        payload.lon,
        payload.hose_max_ft,
        payload.study_radius_ft,
        payload.hydrant_count,
        len(payload.secondary_incidents),
    )
    started = time.perf_counter()
    try:
        plan = run_plan(payload)
        saved_run = save_ad_hoc_plan(payload, plan)
        logger.info(
            "Plan succeeded in %.1fs: %d closure(s), %d warning(s), run_id=%s",
            time.perf_counter() - started,
            len(plan.get("ranked_closures", [])),
            len(plan.get("warnings", [])),
            saved_run.get("run_id"),
        )
        for warning in plan.get("warnings", []):
            logger.warning("Plan warning: %s", warning)
        return {**plan, **saved_run}
    except ValueError as e:
        logger.error(
            "Plan failed (422) after %.1fs: %s", time.perf_counter() - started, e
        )
        save_ad_hoc_failure(payload, str(e))
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception:
        logger.exception("Plan crashed unexpectedly (500)")
        raise
