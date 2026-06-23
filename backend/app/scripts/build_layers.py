from __future__ import annotations

import argparse
import json

from app.services.hydrants import generate_hydrant_layers
from app.services.roads import generate_road_layers


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild generated GIS layer artifacts.")
    parser.add_argument(
        "--only",
        choices=["all", "roads", "hydrants"],
        default="all",
        help="Select which artifacts to rebuild.",
    )
    parser.add_argument(
        "--skip-graph",
        action="store_true",
        help="When rebuilding roads, skip the OSMnx GraphML artifact.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result: dict[str, object] = {}

    if args.only in ("all", "roads"):
        result["roads"] = generate_road_layers(include_graph=not args.skip_graph)

    if args.only in ("all", "hydrants"):
        result["hydrants"] = generate_hydrant_layers()

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

