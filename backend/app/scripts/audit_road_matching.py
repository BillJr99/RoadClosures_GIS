from __future__ import annotations

import argparse
import csv

import osmnx as ox

from app.config import GENERATED_DIR, ROAD_GRAPH_GRAPHML, ensure_data_dirs
from app.models import IncidentPlanRequest
from app.services.graph_cache import graph_cache_paths, graph_cache_key
from app.services.road_matching import audit_graph_matches, enrich_graph_with_county_roads


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a CSV audit of county road matches on a planner graph.")
    parser.add_argument("--graphml", default=None, help="GraphML path. Defaults to road_graph.graphml or cache key lookup.")
    parser.add_argument("--lat", type=float, default=None, help="Incident latitude for cache lookup.")
    parser.add_argument("--lon", type=float, default=None, help="Incident longitude for cache lookup.")
    parser.add_argument("--study-radius-ft", type=float, default=2500.0, help="Study radius for cache lookup.")
    parser.add_argument("--limit", type=int, default=500, help="Maximum edges to audit.")
    parser.add_argument("--output", default=str(GENERATED_DIR / "road_match_audit.csv"), help="Output CSV path.")
    return parser.parse_args()


def graph_path(args: argparse.Namespace):
    if args.graphml:
        return args.graphml
    if ROAD_GRAPH_GRAPHML.exists():
        return ROAD_GRAPH_GRAPHML
    if args.lat is None or args.lon is None:
        raise SystemExit("Provide --graphml or --lat/--lon for graph cache lookup.")
    req = IncidentPlanRequest(lat=args.lat, lon=args.lon, study_radius_ft=args.study_radius_ft)
    path, _ = graph_cache_paths(graph_cache_key(req))
    if not path.exists():
        raise SystemExit(f"Graph cache entry not found: {path}")
    return path


def main() -> None:
    args = parse_args()
    ensure_data_dirs()
    graph = enrich_graph_with_county_roads(ox.load_graphml(graph_path(args)))
    rows = audit_graph_matches(graph, limit=args.limit)
    output = args.output
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["u", "v", "key"])
        writer.writeheader()
        writer.writerows(rows)
    print(output)


if __name__ == "__main__":
    main()

