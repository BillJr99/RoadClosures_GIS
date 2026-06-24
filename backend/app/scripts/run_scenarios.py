from __future__ import annotations

import argparse
import json

from app.services.scenario_runner import run_scenarios


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run planner validation scenarios.")
    parser.add_argument("--scenario-id", default=None, help="Run one scenario by ID.")
    parser.add_argument("--include-inactive", action="store_true", help="Include inactive scenarios.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = run_scenarios(scenario_id=args.scenario_id, active_only=not args.include_inactive)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

