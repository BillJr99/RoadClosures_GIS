import json
from pathlib import Path

from app.services import scenario_runs


def test_scenario_run_listing_detail_and_promote(tmp_path: Path, monkeypatch) -> None:
    runs_dir = tmp_path / "runs"
    golden_dir = tmp_path / "golden"
    run_dir = runs_dir / "20260624T120000Z"
    scenario_dir = run_dir / "scenario-test"
    scenario_dir.mkdir(parents=True)
    golden_dir.mkdir()
    (scenario_dir / "summary.json").write_text(json.dumps({"closure_count": 1}), encoding="utf-8")
    (scenario_dir / "plan.json").write_text(json.dumps({"scenario": {"name": "Test"}, "plan": {}}), encoding="utf-8")
    (run_dir / "run_summary.json").write_text(
        json.dumps(
            {
                "run_dir": str(run_dir),
                "report_path": str(run_dir / "report.html"),
                "results": [
                    {"scenario_id": "scenario-test", "status": "passed", "golden_status": "missing"},
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(scenario_runs, "SCENARIO_RUNS_DIR", runs_dir)
    monkeypatch.setattr("app.services.scenario_runner.SCENARIO_GOLDEN_DIR", golden_dir)

    listed = scenario_runs.list_scenario_runs()
    assert listed[0]["run_id"] == "20260624T120000Z"
    assert scenario_runs.read_run_summary("20260624T120000Z")["results"][0]["scenario_id"] == "scenario-test"
    assert scenario_runs.read_scenario_plan("20260624T120000Z", "scenario-test")["scenario"]["name"] == "Test"
    assert scenario_runs.promote_run("20260624T120000Z")["promoted_count"] == 1
    assert (golden_dir / "scenario-test.summary.json").exists()

