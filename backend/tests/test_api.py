from pathlib import Path

import pytest
from fastapi import HTTPException

from app.main import health
from app.models import ManualHydrantIn
from app.routes.manual_hydrants import (
    create_manual_hydrant,
    list_manual_hydrant_records,
    remove_manual_hydrant,
    replace_manual_hydrant,
)
from app.models import ScenarioIn
from app.routes.scenarios import (
    create_scenario,
    list_scenario_records,
    remove_scenario,
    replace_scenario,
    run_single_scenario,
)


def test_health_route() -> None:
    assert health() == {"status": "ok"}


def test_manual_hydrant_route_crud(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.manual_store.MANUAL_HYDRANTS_CSV", tmp_path / "manual_hydrants.csv")
    payload = ManualHydrantIn(
        name="API Hydrant",
        lat=40.2,
        lon=-75.3,
        flow_class="blue",
        source_note="known local hydrant",
        status="active",
    )

    created = create_manual_hydrant(payload)
    assert created.manual_id.startswith("manual-")
    assert created.name == "API Hydrant"
    assert len(list_manual_hydrant_records()) == 1

    updated = replace_manual_hydrant(
        created.manual_id,
        ManualHydrantIn(
            name="Updated Hydrant",
            lat=40.2,
            lon=-75.3,
            flow_class="green",
            source_note="known local hydrant",
            status="active",
        ),
    )
    assert updated.name == "Updated Hydrant"
    assert updated.flow_class == "green"

    response = remove_manual_hydrant(created.manual_id)
    assert response.status_code == 204
    assert list_manual_hydrant_records() == []


def test_manual_hydrant_route_not_found(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.manual_store.MANUAL_HYDRANTS_CSV", tmp_path / "manual_hydrants.csv")
    payload = ManualHydrantIn(
        name="Missing",
        lat=40.0,
        lon=-75.0,
        flow_class="unknown",
        source_note="",
        status="active",
    )
    with pytest.raises(HTTPException) as update_error:
        replace_manual_hydrant("not-real", payload)
    assert update_error.value.status_code == 404

    with pytest.raises(HTTPException) as delete_error:
        remove_manual_hydrant("not-real")
    assert delete_error.value.status_code == 404


def test_scenario_route_crud_and_run(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.scenario_store.SCENARIOS_CSV", tmp_path / "incidents.csv")
    payload = ScenarioIn(
        name="API Scenario",
        lat=40.2,
        lon=-75.3,
        incident_radius_ft=300,
        study_radius_ft=2500,
        hose_max_ft=500,
        reviewer_notes="note",
        expected_hydrant_hint="hydrant",
        expected_closure_hint="Main St",
        status="active",
    )

    created = create_scenario(payload)
    assert created.scenario_id.startswith("scenario-")
    assert len(list_scenario_records()) == 1

    updated = replace_scenario(
        created.scenario_id,
        ScenarioIn(
            name="Updated Scenario",
            lat=40.21,
            lon=-75.31,
            incident_radius_ft=350,
            study_radius_ft=2600,
            hose_max_ft=550,
            reviewer_notes="updated",
            expected_hydrant_hint="hydrant 2",
            expected_closure_hint="Second St",
            status="active",
        ),
    )
    assert updated.name == "Updated Scenario"

    monkeypatch.setattr(
        "app.routes.scenarios.run_scenarios",
        lambda scenario_id: {
            "run_dir": str(tmp_path / "run"),
            "report_path": str(tmp_path / "run" / "report.html"),
            "results": [{"scenario_id": scenario_id, "status": "passed", "golden_status": "missing"}],
        },
    )
    assert run_single_scenario(created.scenario_id)["results"][0]["status"] == "passed"

    response = remove_scenario(created.scenario_id)
    assert response.status_code == 204
    assert list_scenario_records() == []


def test_scenario_route_not_found(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.scenario_store.SCENARIOS_CSV", tmp_path / "incidents.csv")
    payload = ScenarioIn(
        name="Missing",
        lat=40.0,
        lon=-75.0,
        incident_radius_ft=300,
        study_radius_ft=2500,
        hose_max_ft=500,
        reviewer_notes="",
        expected_hydrant_hint="",
        expected_closure_hint="",
        status="active",
    )

    with pytest.raises(HTTPException) as update_error:
        replace_scenario("not-real", payload)
    assert update_error.value.status_code == 404

    with pytest.raises(HTTPException) as delete_error:
        remove_scenario("not-real")
    assert delete_error.value.status_code == 404

    monkeypatch.setattr(
        "app.routes.scenarios.run_scenarios",
        lambda scenario_id: {"run_dir": "", "report_path": "", "results": []},
    )
    with pytest.raises(HTTPException) as run_error:
        run_single_scenario("not-real")
    assert run_error.value.status_code == 404
