from fastapi import APIRouter

router = APIRouter(tags=["planner"])


@router.post("/plan")
def plan_incident() -> dict:
    return {"status": "not_implemented"}

