from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from app.config import SCENARIO_EXPERT_GOLDEN_DIR, ensure_data_dirs
from app.models import ScenarioGolden, ScenarioGoldenIn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_scenario_id(scenario_id: str) -> str:
    if not scenario_id or "/" in scenario_id or "\\" in scenario_id or scenario_id.startswith("."):
        raise ValueError("Invalid scenario id")
    return scenario_id


def golden_path(scenario_id: str) -> Path:
    return SCENARIO_EXPERT_GOLDEN_DIR / f"{_validate_scenario_id(scenario_id)}.json"


def empty_scenario_golden(scenario_id: str) -> ScenarioGolden:
    return ScenarioGolden(scenario_id=_validate_scenario_id(scenario_id))


def scenario_golden_exists(scenario_id: str) -> bool:
    return golden_path(scenario_id).exists()


def read_scenario_golden(scenario_id: str) -> ScenarioGolden:
    path = golden_path(scenario_id)
    if not path.exists():
        return empty_scenario_golden(scenario_id)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return ScenarioGolden(**data)


def write_scenario_golden(scenario_id: str, payload: ScenarioGoldenIn) -> ScenarioGolden:
    ensure_data_dirs()
    golden = ScenarioGolden(
        scenario_id=_validate_scenario_id(scenario_id),
        updated_at=_now(),
        **payload.model_dump(),
    )
    path = golden_path(scenario_id)
    path.write_text(json.dumps(golden.model_dump(), indent=2), encoding="utf-8")
    return golden


def delete_scenario_golden(scenario_id: str) -> bool:
    path = golden_path(scenario_id)
    if not path.exists():
        return False
    path.unlink()
    return True
