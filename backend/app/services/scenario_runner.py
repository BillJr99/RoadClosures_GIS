from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.config import SCENARIO_GOLDEN_DIR, SCENARIO_RUNS_DIR, ensure_data_dirs
from app.models import IncidentPlanRequest, Scenario, ScenarioRunSummary
from app.scenario_golden_store import read_scenario_golden, scenario_golden_exists
from app.scenario_store import get_scenario, list_scenarios
from app.services.field_report import (
    build_field_report,
    render_field_report_html,
    render_field_report_markdown,
)
from app.services.planner import plan_incident


logger = logging.getLogger("app.services.scenario_runner")

PlannerFn = Callable[[IncidentPlanRequest], dict[str, Any]]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _run_dir(prefix: str = "") -> Path:
    base = f"{prefix}{_timestamp()}"
    run_dir = SCENARIO_RUNS_DIR / base
    suffix = 1
    while run_dir.exists():
        run_dir = SCENARIO_RUNS_DIR / f"{base}-{suffix}"
        suffix += 1
    return run_dir


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
    warning_features = plan.get("warning_signs", {}).get("features", [])
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
        "warning_signs": [
            {
                "road": feature.get("properties", {}).get("approach_road"),
                "sign_label": feature.get("properties", {}).get("sign_label")
                or feature.get("properties", {}).get("sequence"),
                "distance_ft": feature.get("properties", {}).get("distance_from_closure_ft"),
                "placement_status": feature.get("properties", {}).get("placement_status"),
            }
            for feature in warning_features
        ],
    }


def write_planner_debug_logs(target_dir: Path, plan: dict[str, Any]) -> None:
    debug = plan.get("_debug")
    if not isinstance(debug, dict):
        return
    (target_dir / "planner_debug.json").write_text(json.dumps(debug, indent=2), encoding="utf-8")
    hydrant_filter = debug.get("hydrant_filter", {})
    selected = debug.get("selected_hydrants", [])
    lines = [
        "Planner debug",
        f"request: {debug.get('request')}",
        f"graph_source: {debug.get('graph_source')}",
        f"hydrant_filter: {hydrant_filter}",
        f"closure_count: {debug.get('closure_count')}",
        f"warning_sign_count: {debug.get('warning_sign_count')}",
        "selected_hydrants:",
    ]
    for item in selected:
        lines.append(
            "  "
            f"{item.get('source') or ''} {item.get('name') or ''} "
            f"coords={item.get('coordinates')} "
            f"length_ft={item.get('length_ft')} "
            f"direct_ft={item.get('direct_distance_ft')} "
            f"snap_ft={item.get('hydrant_snap_ft')}/{item.get('incident_snap_ft')} "
            f"path_nodes={item.get('path_node_count')}"
        )
    lines.append("top_hydrant_candidates:")
    for item in debug.get("top_hydrant_candidates", []):
        lines.append(
            "  "
            f"{item.get('source') or ''} {item.get('name') or ''} "
            f"coords={item.get('coordinates')} "
            f"length_ft={item.get('length_ft')} "
            f"direct_ft={item.get('direct_distance_ft')} "
            f"snap_ft={item.get('hydrant_snap_ft')}/{item.get('incident_snap_ft')} "
            f"path_nodes={item.get('path_node_count')}"
        )
    (target_dir / "planner_debug.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_field_report(target_dir: Path, scenario: Any, plan: dict[str, Any]) -> dict[str, Any]:
    """Write the what/where/why field report (JSON + Markdown) for a planner
    result and return the structured report."""
    report = build_field_report(scenario, plan)
    (target_dir / "field_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (target_dir / "field_report.md").write_text(render_field_report_markdown(report), encoding="utf-8")
    return report


def write_planner_failure_log(target_dir: Path, request: IncidentPlanRequest, error: str) -> None:
    logger.error("Planner failure recorded in %s: %s", target_dir, error)
    target_dir.mkdir(parents=True, exist_ok=True)
    debug = {
        "request": request.model_dump(),
        "error": error,
    }
    (target_dir / "planner_debug.json").write_text(json.dumps(debug, indent=2), encoding="utf-8")
    (target_dir / "planner_debug.log").write_text(
        "Planner failed\n"
        f"request: {debug['request']}\n"
        f"error: {error}\n",
        encoding="utf-8",
    )


def _matches_text(expected: str, current: str | None) -> bool:
    if not expected.strip():
        return True
    if not current:
        return False
    expected_norm = expected.strip().lower()
    current_norm = current.strip().lower()
    return expected_norm in current_norm or current_norm in expected_norm


def compare_to_expert_golden(scenario_id: str, summary: dict[str, Any]) -> tuple[str, list[str]] | None:
    if not scenario_golden_exists(scenario_id):
        return None
    golden = read_scenario_golden(scenario_id)
    differences: list[str] = []
    selected = summary.get("selected_hydrant", {})
    hydrant = golden.expected_hydrant
    if hydrant.source_id and hydrant.source_id != selected.get("source_id"):
        differences.append("expert expected hydrant source_id changed")
    if hydrant.source and not _matches_text(hydrant.source, selected.get("source")):
        differences.append("expert expected hydrant source changed")
    if hydrant.name and not _matches_text(hydrant.name, selected.get("name")):
        differences.append("expert expected hydrant name changed")

    current_closures = [str(item.get("name") or "") for item in summary.get("closures", [])]
    for closure in golden.expected_closures:
        if closure.road.strip() and not any(_matches_text(closure.road, current) for current in current_closures):
            differences.append(f"expert expected closure missing: {closure.road}")

    current_signs = summary.get("warning_signs", [])
    for sign in golden.expected_warning_signs:
        if not sign.road.strip() and not sign.sign_label.strip():
            continue
        found = False
        for current in current_signs:
            road_matches = _matches_text(sign.road, current.get("road"))
            label_matches = _matches_text(sign.sign_label, current.get("sign_label"))
            found = road_matches and label_matches
            if found:
                break
        if not found:
            label = sign.sign_label or "sign"
            road = sign.road or "unspecified road"
            differences.append(f"expert expected warning sign missing: {label} on {road}")

    return ("expert_changed" if differences else "expert_matched"), differences


def compare_to_golden(scenario_id: str, summary: dict[str, Any]) -> tuple[str, list[str]]:
    expert_result = compare_to_expert_golden(scenario_id, summary)
    if expert_result is not None:
        return expert_result
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
    report_sections = []
    for result in results:
        ok_golden_statuses = ("matched", "missing", "expert_matched")
        status_class = "ok" if result.status == "passed" and result.golden_status in ok_golden_statuses else "warn"
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
        # Embed the per-scenario what/where/why placement report when available.
        report_file = run_dir / result.scenario_id / "field_report.json"
        if report_file.exists():
            try:
                report = json.loads(report_file.read_text(encoding="utf-8"))
                report_sections.append(
                    f"<details open><summary>{result.scenario_id}</summary>"
                    + render_field_report_html(report)
                    + "</details>"
                )
            except (json.JSONDecodeError, OSError):
                pass
    placement_block = ""
    if report_sections:
        placement_block = "<h2>Placement reports — what / where / why</h2>" + "\n".join(report_sections)
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
    details { margin: 12px 0; border: 1px solid #cbd5df; border-radius: 6px; padding: 8px 12px; }
    summary { font-weight: 700; cursor: pointer; }
    .field-report h3 { margin: 8px 0 4px; }
    .field-report h4 { margin: 12px 0 4px; color: #334155; }
    .report-list { list-style: none; padding-left: 0; }
    .report-list > li { margin: 6px 0; padding: 6px 8px; background: #f8fafc; border-radius: 4px; }
    .item-head { font-weight: 600; }
    .where { color: #475569; font-size: 0.9em; }
    .why { margin: 2px 0 0; color: #475569; font-size: 0.9em; }
    .badge { background: #1d4ed8; color: #fff; border-radius: 4px; padding: 0 6px; font-size: 0.8em; }
    .infeasible { color: #b45309; font-weight: 700; }
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
"""
        + placement_block
        + """
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
    request = request_from_scenario(scenario)
    try:
        plan = planner(request)
        if not plan.get("selected_hydrant"):
            raise ValueError("Planner output missing selected_hydrant")
        if not plan.get("hose_route"):
            raise ValueError("Planner output missing hose_route")
        if "ranked_closures" not in plan:
            raise ValueError("Planner output missing ranked_closures")
        summary = scenario_summary(plan)
        field_report = write_field_report(scenario_dir, scenario, plan)
        output = {
            "scenario": scenario.model_dump(),
            "summary": summary,
            "field_report": field_report,
            "plan": plan,
        }
        output_path = scenario_dir / "plan.json"
        output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
        summary_path = scenario_dir / "summary.json"
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        write_planner_debug_logs(scenario_dir, plan)
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
        write_planner_failure_log(scenario_dir, request, str(e))
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
    run_dir = _run_dir()
    run_dir.mkdir(parents=True, exist_ok=True)
    results = [run_scenario(scenario, run_dir, planner=planner) for scenario in selected]
    report_path = write_html_report(run_dir, results)
    summary = {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "report_path": str(report_path),
        "results": [result.model_dump() for result in results],
    }
    (run_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def save_ad_hoc_plan(req: IncidentPlanRequest, plan: dict[str, Any]) -> dict[str, str]:
    ensure_data_dirs()
    run_dir = _run_dir("adhoc-")
    run_dir.mkdir(parents=True, exist_ok=True)
    scenario_id = f"adhoc-{run_dir.name.removeprefix('adhoc-')}"
    scenario = Scenario(
        scenario_id=scenario_id,
        name="Ad hoc incident",
        lat=req.lat,
        lon=req.lon,
        incident_radius_ft=req.incident_radius_ft,
        study_radius_ft=req.study_radius_ft,
        hose_max_ft=req.hose_max_ft,
        reviewer_notes=(
            "Saved from Recommend Closures (hose envelope exceeded)"
            if plan.get("warnings")
            else "Saved from Recommend Closures"
        ),
        expected_hydrant_hint="",
        expected_closure_hint="",
        status="active",
        updated_at=datetime.now(timezone.utc).isoformat(),
    )
    scenario_dir = run_dir / scenario_id
    scenario_dir.mkdir(parents=True, exist_ok=True)
    summary = scenario_summary(plan)
    field_report = write_field_report(scenario_dir, scenario, plan)
    output_path = scenario_dir / "plan.json"
    output_path.write_text(
        json.dumps(
            {"scenario": scenario.model_dump(), "summary": summary, "field_report": field_report, "plan": plan},
            indent=2,
        ),
        encoding="utf-8",
    )
    (scenario_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_planner_debug_logs(scenario_dir, plan)
    result = ScenarioRunSummary(
        scenario_id=scenario_id,
        name=scenario.name,
        status="passed",
        output_path=str(output_path),
        golden_status="not_checked",
        differences=["Ad hoc incident run"],
    )
    report_path = write_html_report(run_dir, [result])
    run_summary = {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "report_path": str(report_path),
        "results": [result.model_dump()],
    }
    (run_dir / "run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    return {"run_id": run_dir.name, "scenario_id": scenario_id, "report_path": str(report_path)}


def save_ad_hoc_failure(req: IncidentPlanRequest, error: str) -> dict[str, str]:
    ensure_data_dirs()
    run_dir = _run_dir("adhoc-")
    run_dir.mkdir(parents=True, exist_ok=True)
    scenario_id = f"adhoc-{run_dir.name.removeprefix('adhoc-')}"
    scenario_dir = run_dir / scenario_id
    write_planner_failure_log(scenario_dir, req, error)
    result = ScenarioRunSummary(
        scenario_id=scenario_id,
        name="Ad hoc incident",
        status="failed",
        golden_status="not_checked",
        differences=[],
        error=error,
    )
    report_path = write_html_report(run_dir, [result])
    run_summary = {
        "run_id": run_dir.name,
        "run_dir": str(run_dir),
        "report_path": str(report_path),
        "results": [result.model_dump()],
    }
    (run_dir / "run_summary.json").write_text(json.dumps(run_summary, indent=2), encoding="utf-8")
    return {"run_id": run_dir.name, "scenario_id": scenario_id, "report_path": str(report_path)}


def update_golden_from_run(run_dir: Path) -> int:
    ensure_data_dirs()
    count = 0
    for summary_path in run_dir.glob("scenario-*/summary.json"):
        scenario_id = summary_path.parent.name
        target = SCENARIO_GOLDEN_DIR / f"{scenario_id}.summary.json"
        target.write_text(summary_path.read_text(encoding="utf-8"), encoding="utf-8")
        count += 1
    return count
