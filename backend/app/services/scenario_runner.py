from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.config import SCENARIO_GOLDEN_DIR, SCENARIO_RUNS_DIR, ensure_data_dirs
from app.models import IncidentPlanRequest, Scenario, ScenarioRunSummary
from app.scenario_store import get_scenario, list_scenarios
from app.services.planner import plan_incident


PlannerFn = Callable[[IncidentPlanRequest], dict[str, Any]]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def request_from_scenario(scenario: Scenario) -> IncidentPlanRequest:
    return IncidentPlanRequest(
        lat=scenario.lat,
        lon=scenario.lon,
        incident_radius_ft=scenario.incident_radius_ft,
        study_radius_ft=scenario.study_radius_ft,
        hose_max_ft=scenario.hose_max_ft,
    )


def scenario_summary(plan: dict[str, Any]) -> dict[str, Any]:
    selected = plan.get("selected_hydrant", {}).get("properties", {})
    return {
        "cut_value": plan.get("cut_value"),
        "selected_hydrant": {
            "source": selected.get("source"),
            "source_id": selected.get("source_id"),
            "name": selected.get("name"),
            "flow_class": selected.get("flow_class"),
        },
        "closure_count": len(plan.get("ranked_closures", [])),
        "closures": [
            {
                "rank": item.get("rank"),
                "name": item.get("name"),
                "capacity": item.get("capacity"),
                "sightline": item.get("sightline"),
            }
            for item in plan.get("ranked_closures", [])
        ],
        "hose_route": plan.get("hose_route", {}).get("properties", {}),
    }


def compare_to_golden(scenario_id: str, summary: dict[str, Any]) -> tuple[str, list[str]]:
    golden_path = SCENARIO_GOLDEN_DIR / f"{scenario_id}.summary.json"
    if not golden_path.exists():
        return "missing", ["No golden summary exists yet"]
    with golden_path.open("r", encoding="utf-8") as f:
        golden = json.load(f)
    differences: list[str] = []
    if golden.get("selected_hydrant") != summary.get("selected_hydrant"):
        differences.append("selected_hydrant changed")
    if golden.get("closure_count") != summary.get("closure_count"):
        differences.append("closure_count changed")
    golden_closures = [item.get("name") for item in golden.get("closures", [])]
    current_closures = [item.get("name") for item in summary.get("closures", [])]
    if golden_closures != current_closures:
        differences.append("closure road names changed")
    return ("changed" if differences else "matched"), differences


def write_html_report(run_dir: Path, results: list[ScenarioRunSummary]) -> Path:
    report_path = run_dir / "report.html"
    rows = []
    for result in results:
        status_class = "ok" if result.status == "passed" and result.golden_status in ("matched", "missing") else "warn"
        rows.append(
            "<tr>"
            f"<td>{result.scenario_id}</td>"
            f"<td>{result.name}</td>"
            f"<td class='{status_class}'>{result.status}</td>"
            f"<td>{result.golden_status}</td>"
            f"<td>{'; '.join(result.differences) or ''}</td>"
            f"<td>{result.error or ''}</td>"
            "</tr>"
        )
    report_path.write_text(
        """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Scenario Validation Report</title>
  <style>
    body { font-family: system-ui, sans-serif; margin: 24px; color: #1f2933; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #cbd5df; padding: 8px; text-align: left; vertical-align: top; }
    th { background: #f5f7fa; }
    .ok { color: #166534; font-weight: 700; }
    .warn { color: #b45309; font-weight: 700; }
  </style>
</head>
<body>
  <h1>Scenario Validation Report</h1>
  <table>
    <thead><tr><th>ID</th><th>Name</th><th>Status</th><th>Golden</th><th>Differences</th><th>Error</th></tr></thead>
    <tbody>
"""
        + "\n".join(rows)
        + """
    </tbody>
  </table>
</body>
</html>
""",
        encoding="utf-8",
    )
    return report_path


def run_scenario(
    scenario: Scenario,
    run_dir: Path,
    *,
    planner: PlannerFn = plan_incident,
) -> ScenarioRunSummary:
    scenario_dir = run_dir / scenario.scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    try:
        plan = planner(request_from_scenario(scenario))
        if not plan.get("selected_hydrant"):
            raise ValueError("Planner output missing selected_hydrant")
        if not plan.get("hose_route"):
            raise ValueError("Planner output missing hose_route")
        if "ranked_closures" not in plan:
            raise ValueError("Planner output missing ranked_closures")
        summary = scenario_summary(plan)
        output = {
            "scenario": scenario.model_dump(),
            "summary": summary,
            "plan": plan,
        }
        output_path = scenario_dir / "plan.json"
        output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        summary_path = scenario_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        golden_status, differences = compare_to_golden(scenario.scenario_id, summary)
        return ScenarioRunSummary(
            scenario_id=scenario.scenario_id,
            name=scenario.name,
            status="passed",
            output_path=str(output_path),
            golden_status=golden_status,
            differences=differences,
        )
    except Exception as e:
        return ScenarioRunSummary(
            scenario_id=scenario.scenario_id,
            name=scenario.name,
            status="failed",
            golden_status="not_checked",
            differences=[],
            error=str(e),
        )


def run_scenarios(
    *,
    scenario_id: str | None = None,
    active_only: bool = True,
    planner: PlannerFn = plan_incident,
) -> dict[str, Any]:
    ensure_data_dirs()
    scenarios = [get_scenario(scenario_id)] if scenario_id else list_scenarios()
    selected = [scenario for scenario in scenarios if scenario is not None]
    if active_only:
        selected = [scenario for scenario in selected if scenario.status == "active"]
    run_dir = SCENARIO_RUNS_DIR / _timestamp()
    run_dir.mkdir(parents=True, exist_ok=True)
    results = [run_scenario(scenario, run_dir, planner=planner) for scenario in selected]
    report_path = write_html_report(run_dir, results)
    summary = {
        "run_dir": str(run_dir),
        "report_path": str(report_path),
        "results": [result.model_dump() for result in results],
    }
    (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def update_golden_from_run(run_dir: Path) -> int:
    ensure_data_dirs()
    count = 0
    for summary_path in run_dir.glob("scenario-*/summary.json"):
        scenario_id = summary_path.parent.name
        target = SCENARIO_GOLDEN_DIR / f"{scenario_id}.summary.json"
        target.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
    return count
