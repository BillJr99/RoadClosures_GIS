from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response

from app.models import Scenario, ScenarioIn
from app.scenario_store import add_scenario, delete_scenario, list_scenarios, update_scenario
from app.services.scenario_runs import list_scenario_runs, promote_run, read_run_summary, read_scenario_plan
from app.services.scenario_runner import run_scenarios

router = APIRouter(tags=["scenarios"])


@router.get("/scenarios", response_model=list[Scenario])
def list_scenario_records() -> list[Scenario]:
    return list_scenarios()


@router.post("/scenarios", response_model=Scenario, status_code=201)
def create_scenario(payload: ScenarioIn) -> Scenario:
    return add_scenario(payload)


@router.put("/scenarios/{scenario_id}", response_model=Scenario)
def replace_scenario(scenario_id: str, payload: ScenarioIn) -> Scenario:
    updated = update_scenario(scenario_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return updated


@router.delete("/scenarios/{scenario_id}", status_code=204)
def remove_scenario(scenario_id: str) -> Response:
    if not delete_scenario(scenario_id):
        raise HTTPException(status_code=404, detail="Scenario not found")
    return Response(status_code=204)


@router.post("/scenarios/{scenario_id}/run")
def run_single_scenario(scenario_id: str) -> dict:
    result = run_scenarios(scenario_id=scenario_id)
    if not result["results"]:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return result


@router.get("/scenario-runs")
def list_runs() -> list[dict]:
    return list_scenario_runs()


@router.get("/scenario-runs/{run_id}")
def get_run(run_id: str) -> dict:
    try:
        return read_run_summary(run_id)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail="Scenario run not found") from e


@router.get("/scenario-runs/{run_id}/scenarios/{scenario_id}")
def get_run_scenario(run_id: str, scenario_id: str) -> dict:
    try:
        return read_scenario_plan(run_id, scenario_id)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail="Scenario plan not found") from e


@router.post("/scenario-runs/{run_id}/promote")
def promote_scenario_run(run_id: str) -> dict:
    try:
        return promote_run(run_id)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail="Scenario run not found") from e
