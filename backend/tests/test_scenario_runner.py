import json
from pathlib import Path
from typing import Any

from app.models import IncidentPlanRequest, Scenario
from app.services import scenario_runner


def _scenario(status: str = "active") -> Scenario:
    return Scenario(
        scenario_id="scenario-test",
        name="Test incident",
        lat=40.2,
        lon=-75.3,
        incident_radius_ft=300,
        study_radius_ft=2500,
        hose_max_ft=500,
        reviewer_notes="",
        expected_hydrant_hint="",
        expected_closure_hint="",
        status=status,
        updated_at="2026-06-24T00:00:00Z",
    )


def _fake_plan(request: IncidentPlanRequest) -> dict[str, Any]:
    assert request.lat == 40.2
    return {
        "cut_value": 2.5,
        "selected_hydrant": {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [-75.3, 40.2]},
            "properties": {
                "source": "test",
                "source_id": "hydrant-1",
                "name": "Hydrant 1",
                "flow_class": "blue",
            },
        },
        "hose_route": {
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": [[-75.3, 40.2], [-75.31, 40.21]]},
            "properties": {"length_ft": 420},
        },
        "ranked_closures": [
            {"rank": 1, "name": "Main St", "capacity": 2.5, "sightline": "limited"},
        ],
    }


def test_run_scenario_writes_plan_summary_and_reports_missing_golden(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(scenario_runner, "SCENARIO_GOLDEN_DIR", tmp_path / "golden")
    monkeypatch.setattr(scenario_runner, "SCENARIO_RUNS_DIR", tmp_path / "runs")
    scenario_runner.SCENARIO_GOLDEN_DIR.mkdir()

    run_dir = tmp_path / "runs" / "run"
    result = scenario_runner.run_scenario(_scenario(), run_dir, planner=_fake_plan)

    assert result.status == "passed"
    assert result.golden_status == "missing"
    assert (run_dir / "scenario-test" / "plan.json").exists()
    summary = json.loads((run_dir / "scenario-test" / "summary.json").read_text(encoding="utf-8"))
    assert summary["selected_hydrant"]["name"] == "Hydrant 1"
    assert summary["closures"][0]["name"] == "Main St"


def test_run_scenarios_filters_inactive_and_compares_golden(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(scenario_runner, "SCENARIO_GOLDEN_DIR", tmp_path / "golden")
    monkeypatch.setattr(scenario_runner, "SCENARIO_RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(scenario_runner, "list_scenarios", lambda: [_scenario("active"), _scenario("inactive")])
    monkeypatch.setattr(scenario_runner, "get_scenario", lambda scenario_id: _scenario("active"))
    scenario_runner.SCENARIO_GOLDEN_DIR.mkdir()
    scenario_runner.SCENARIO_RUNS_DIR.mkdir()
    (scenario_runner.SCENARIO_GOLDEN_DIR / "scenario-test.summary.json").write_text(
        json.dumps(scenario_runner.scenario_summary(_fake_plan(IncidentPlanRequest(lat=40.2, lon=-75.3)))),
        encoding="utf-8",
    )

    result = scenario_runner.run_scenarios(planner=_fake_plan)

    assert len(result["results"]) == 1
    assert result["results"][0]["golden_status"] == "matched"
    assert Path(result["report_path"]).exists()

