from __future__ import annotations

import argparse
import json
from pathlib import Path

import networkx as nx

from app.config import ROAD_GRAPH_GRAPHML, ROAD_GRAPH_SUMMARY_JSON, ensure_data_dirs
from app.scenario_store import get_scenario, list_scenarios


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a local OSMnx GraphML artifact around scenario incidents.")
    parser.add_argument("--scenario-id", action="append", default=[], help="Scenario ID to include. Repeatable.")
    parser.add_argument("--include-inactive", action="store_true", help="Include inactive scenarios when no IDs are supplied.")
    parser.add_argument(
        "--buffer-ft",
        type=float,
        default=1000.0,
        help="Extra graph radius beyond each scenario study radius.",
    )
    return parser.parse_args()


def selected_scenarios(args: argparse.Namespace):
    if args.scenario_id:
        scenarios = [get_scenario(scenario_id) for scenario_id in args.scenario_id]
        missing = [scenario_id for scenario_id, scenario in zip(args.scenario_id, scenarios) if scenario is None]
        if missing:
            raise SystemExit(f"Unknown scenario id(s): {', '.join(missing)}")
        return [scenario for scenario in scenarios if scenario is not None]
    scenarios = list_scenarios()
    if not args.include_inactive:
        scenarios = [scenario for scenario in scenarios if scenario.status == "active"]
    return scenarios


def main() -> None:
    import osmnx as ox

    args = parse_args()
    scenarios = selected_scenarios(args)
    if not scenarios:
        raise SystemExit("No scenarios selected.")

    ensure_data_dirs()
    graph = None
    pieces = []
    for scenario in scenarios:
        dist_m = max((scenario.study_radius_ft + args.buffer_ft) / 3.28084, 500.0)
        local = ox.graph_from_point((scenario.lat, scenario.lon), dist=dist_m, network_type="drive", simplify=True)
        local = ox.project_graph(local)
        graph = local if graph is None else nx.compose(graph, local)
        pieces.append(
            {
                "scenario_id": scenario.scenario_id,
                "name": scenario.name,
                "lat": scenario.lat,
                "lon": scenario.lon,
                "dist_m": dist_m,
                "nodes": local.number_of_nodes(),
                "edges": local.number_of_edges(),
            }
        )

    assert graph is not None
    ox.save_graphml(graph, filepath=ROAD_GRAPH_GRAPHML)
    summary = {
        "source": "OSMnx/OpenStreetMap scenario-local graph",
        "scenarios": pieces,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "crs": str(graph.graph.get("crs")),
        "path": str(ROAD_GRAPH_GRAPHML),
    }
    ROAD_GRAPH_SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    ROAD_GRAPH_SUMMARY_JSON.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

