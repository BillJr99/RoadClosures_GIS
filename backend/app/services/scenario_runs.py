from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import SCENARIO_RUNS_DIR, ensure_data_dirs
from app.services.scenario_runner import update_golden_from_run


def _run_path(run_id: str) -> Path:
    if "/" in run_id or "\\" in run_id or run_id.startswith("."):
        raise ValueError("Invalid run id")
    return SCENARIO_RUNS_DIR / run_id


def list_scenario_runs() -> list[dict[str, Any]]:
    ensure_data_dirs()
    runs: list[dict[str, Any]] = []
    for run_dir in sorted(SCENARIO_RUNS_DIR.iterdir(), reverse=True):
        summary_path = run_dir / "run_summary.json"
        if not run_dir.is_dir() or not summary_path.exists():
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        results = summary.get("results", [])
        runs.append(
            {
                "run_id": run_dir.name,
                "run_dir": str(run_dir),
                "report_path": str(run_dir / "report.html"),
                "result_count": len(results),
                "failed_count": sum(1 for item in results if item.get("status") == "failed"),
                "changed_count": sum(1 for item in results if item.get("golden_status") == "changed"),
                "missing_count": sum(1 for item in results if item.get("golden_status") == "missing"),
            }
        )
    return runs


def read_run_summary(run_id: str) -> dict[str, Any]:
    run_dir = _run_path(run_id)
    summary_path = run_dir / "run_summary.json"
    if not summary_path.exists():
        raise FileNotFoundError(run_id)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["run_id"] = run_id
    return summary


def read_run_report_html(run_id: str) -> str:
    """Return the run's report.html contents (the validation summary plus the
    embedded what/where/why placement reports)."""
    run_dir = _run_path(run_id)
    report_path = run_dir / "report.html"
    if not report_path.exists():
        raise FileNotFoundError(run_id)
    return report_path.read_text(encoding="utf-8")


def read_scenario_plan(run_id: str, scenario_id: str) -> dict[str, Any]:
    run_dir = _run_path(run_id)
    if "/" in scenario_id or "\\" in scenario_id or scenario_id.startswith("."):
        raise ValueError("Invalid scenario id")
    plan_path = run_dir / scenario_id / "plan.json"
    if not plan_path.exists():
        raise FileNotFoundError(scenario_id)
    return json.loads(plan_path.read_text(encoding="utf-8"))


def promote_run(run_id: str) -> dict[str, Any]:
    run_dir = _run_path(run_id)
    if not run_dir.exists():
        raise FileNotFoundError(run_id)
    count = update_golden_from_run(run_dir)
    return {"run_id": run_id, "promoted_count": count}

