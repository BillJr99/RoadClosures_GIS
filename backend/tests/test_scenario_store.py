from pathlib import Path

from app.models import ScenarioIn
from app.scenario_store import (
    add_scenario,
    delete_scenario,
    ensure_scenarios_csv,
    list_scenarios,
    update_scenario,
)


def test_scenario_csv_round_trip(tmp_path: Path, monkeypatch) -> None:
    csv_path = tmp_path / "incidents.csv"
    monkeypatch.setattr("app.scenario_store.SCENARIOS_CSV", csv_path)
    ensure_scenarios_csv(csv_path)

    created = add_scenario(
        ScenarioIn(
            name="Depot fire",
            lat=40.2,
            lon=-75.3,
            incident_radius_ft=300,
            study_radius_ft=2500,
            hose_max_ft=500,
            reviewer_notes="field review",
            expected_hydrant_hint="blue hydrant",
            expected_closure_hint="Main St",
            status="active",
        )
    )

    records = list_scenarios(csv_path)
    assert len(records) == 1
    assert records[0].scenario_id == created.scenario_id
    assert records[0].expected_closure_hint == "Main St"

    updated = update_scenario(
        created.scenario_id,
        ScenarioIn(
            name="Depot fire revised",
            lat=40.21,
            lon=-75.31,
            incident_radius_ft=350,
            study_radius_ft=2600,
            hose_max_ft=600,
            reviewer_notes="updated",
            expected_hydrant_hint="green hydrant",
            expected_closure_hint="Second St",
            status="inactive",
        ),
    )
    assert updated is not None
    assert updated.name == "Depot fire revised"
    assert list_scenarios(csv_path)[0].status == "inactive"

    assert delete_scenario(created.scenario_id)
    assert list_scenarios(csv_path) == []

