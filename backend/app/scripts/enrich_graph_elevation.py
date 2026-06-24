from __future__ import annotations

import argparse
import json
from pathlib import Path

import osmnx as ox

from app.config import GRAPH_CACHE_DIR, ROAD_GRAPH_GRAPHML
from app.services.elevation import enrich_graph_elevation


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich GraphML nodes and edges with USGS EPQS elevation/grade.")
    parser.add_argument("--graphml", action="append", default=[], help="GraphML path to enrich. Repeatable.")
    parser.add_argument("--cache", action="store_true", help="Enrich all graph cache GraphML files.")
    return parser.parse_args()


def graph_paths(args: argparse.Namespace) -> list[Path]:
    paths = [Path(path) for path in args.graphml]
    if args.cache:
        paths.extend(sorted(GRAPH_CACHE_DIR.glob("*.graphml")))
    if not paths and ROAD_GRAPH_GRAPHML.exists():
        paths.append(ROAD_GRAPH_GRAPHML)
    if not paths:
        raise SystemExit("No GraphML files found. Provide --graphml or build graph cache first.")
    return paths


def main() -> None:
    results = []
    for path in graph_paths(parse_args()):
        graph = ox.load_graphml(path)
        summary = enrich_graph_elevation(graph)
        ox.save_graphml(graph, filepath=path)
        results.append({"path": str(path), **summary})
    print(json.dumps({"graphs": results}, indent=2))


if __name__ == "__main__":
    main()

