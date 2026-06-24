from __future__ import annotations

import argparse
import json

from app.models import IncidentPlanRequest
from app.scenario_store import get_scenario, list_scenarios
from app.services.graph_cache import load_or_fetch_graph
from app.services.scenario_runner import request_from_scenario


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prebuild incident-local graph cache entries.")
    parser.add_argument("--scenario-id", action="append", default=[], help="Scenario ID to include. Repeatable.")
    parser.add_argument("--include-inactive", action="store_true", help="Include inactive scenarios when no IDs are supplied.")
    return parser.parse_args()


def selected_requests(args: argparse.Namespace) -> list[IncidentPlanRequest]:
    if args.scenario_id:
        scenarios = [get_scenario(scenario_id) for scenario_id in args.scenario_id]
        missing = [scenario_id for scenario_id, scenario in zip(args.scenario_id, scenarios) if scenario is None]
        if missing:
            raise SystemExit(f"Unknown scenario id(s): {', '.join(missing)}")
        return [request_from_scenario(scenario) for scenario in scenarios if scenario is not None]
    scenarios = list_scenarios()
    if not args.include_inactive:
        scenarios = [scenario for scenario in scenarios if scenario.status == "active"]
    return [request_from_scenario(scenario) for scenario in scenarios]


def main() -> None:
    results = []
    for request in selected_requests(parse_args()):
        _, metadata = load_or_fetch_graph(request)
        results.append(metadata)
    print(json.dumps({"graphs": results}, indent=2))


if __name__ == "__main__":
    main()

