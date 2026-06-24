from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import SCENARIOS_CSV, ensure_data_dirs
from app.models import Scenario, ScenarioIn


FIELDNAMES = [
    "scenario_id",
    "name",
    "lat",
    "lon",
    "incident_radius_ft",
    "study_radius_ft",
    "hose_max_ft",
    "reviewer_notes",
    "expected_hydrant_hint",
    "expected_closure_hint",
    "status",
    "updated_at",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(path: Path | None = None) -> Path:
    return path or SCENARIOS_CSV


def ensure_scenarios_csv(path: Path | None = None) -> None:
    path = _path(path)
    if path == SCENARIOS_CSV:
        ensure_data_dirs()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()


def _coerce(row: dict[str, str]) -> Scenario:
    return Scenario(
        scenario_id=row["scenario_id"],
        name=row.get("name", ""),
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        incident_radius_ft=float(row.get("incident_radius_ft") or 300.0),
        study_radius_ft=float(row.get("study_radius_ft") or 2500.0),
        hose_max_ft=float(row.get("hose_max_ft") or 500.0),
        reviewer_notes=row.get("reviewer_notes", ""),
        expected_hydrant_hint=row.get("expected_hydrant_hint", ""),
        expected_closure_hint=row.get("expected_closure_hint", ""),
        status=row.get("status") or "active",
        updated_at=row.get("updated_at") or "",
    )


def list_scenarios(path: Path | None = None) -> list[Scenario]:
    path = _path(path)
    ensure_scenarios_csv(path)
    with path.open("r", newline="", encoding="utf-8") as f:
        return [_coerce(row) for row in csv.DictReader(f) if row.get("scenario_id")]


def _write_all(records: list[Scenario], path: Path | None = None) -> None:
    path = _path(path)
    ensure_scenarios_csv(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for rec in records:
            writer.writerow(rec.model_dump())


def add_scenario(payload: ScenarioIn) -> Scenario:
    records = list_scenarios()
    scenario = Scenario(
        scenario_id=f"scenario-{uuid4().hex[:12]}",
        updated_at=_now(),
        **payload.model_dump(),
    )
    records.append(scenario)
    _write_all(records)
    return scenario


def update_scenario(scenario_id: str, payload: ScenarioIn) -> Scenario | None:
    records = list_scenarios()
    for idx, rec in enumerate(records):
        if rec.scenario_id == scenario_id:
            updated = Scenario(scenario_id=scenario_id, updated_at=_now(), **payload.model_dump())
            records[idx] = updated
            _write_all(records)
            return updated
    return None


def delete_scenario(scenario_id: str) -> bool:
    records = list_scenarios()
    kept = [rec for rec in records if rec.scenario_id != scenario_id]
    if len(kept) == len(records):
        return False
    _write_all(kept)
    return True


def get_scenario(scenario_id: str) -> Scenario | None:
    return next((scenario for scenario in list_scenarios() if scenario.scenario_id == scenario_id), None)
