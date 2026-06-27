from __future__ import annotations

import argparse
import json

from app.scenario_store import get_scenario, list_scenarios
from app.services.graph_tiles import build_tile, upsert_tile

# Prebuild operational-area graph tiles so an entire response area can be planned
# offline. Build one tile per active scenario location (or explicit centers),
# using a radius large enough to cover nearby incidents, not just one point.


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prebuild operational-area graph tiles for offline planning.")
    parser.add_argument("--scenario-id", action="append", default=[], help="Scenario ID to build a tile around. Repeatable.")
    parser.add_argument("--include-inactive", action="store_true", help="Include inactive scenarios when no IDs are supplied.")
    parser.add_argument(
        "--center",
        action="append",
        default=[],
        metavar="LAT,LON",
        help="Explicit tile center as 'lat,lon'. Repeatable. Used instead of scenarios when provided.",
    )
    parser.add_argument("--radius-ft", type=float, default=8000.0, help="Tile radius in feet (default 8000).")
    parser.add_argument("--network-type", default="drive", help="OSMnx network type (default drive).")
    return parser.parse_args()


def _tile_specs(args: argparse.Namespace) -> list[tuple[str, float, float]]:
    if args.center:
        specs: list[tuple[str, float, float]] = []
        for index, center in enumerate(args.center):
            lat_str, lon_str = center.split(",")
            specs.append((f"tile-{index}-{lat_str.strip()}-{lon_str.strip()}", float(lat_str), float(lon_str)))
        return specs
    if args.scenario_id:
        scenarios = [get_scenario(scenario_id) for scenario_id in args.scenario_id]
        missing = [sid for sid, sc in zip(args.scenario_id, scenarios) if sc is None]
        if missing:
            raise SystemExit(f"Unknown scenario id(s): {', '.join(missing)}")
        chosen = [sc for sc in scenarios if sc is not None]
    else:
        chosen = list_scenarios()
        if not args.include_inactive:
            chosen = [sc for sc in chosen if sc.status == "active"]
    return [(f"tile-{sc.scenario_id}", sc.lat, sc.lon) for sc in chosen]


def main() -> None:
    args = parse_args()
    radius_m = args.radius_ft / 3.28084
    built = []
    for tile_id, lat, lon in _tile_specs(args):
        tile = build_tile(tile_id, lat, lon, radius_m, network_type=args.network_type)
        upsert_tile(tile)
        built.append({"tile_id": tile.tile_id, "nodes": tile.nodes, "edges": tile.edges, "graph_file": tile.graph_file})
    print(json.dumps({"tiles": built}, indent=2))


if __name__ == "__main__":
    main()
