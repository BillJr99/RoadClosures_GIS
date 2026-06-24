from __future__ import annotations

import argparse
from pathlib import Path

from app.services.scenario_runner import update_golden_from_run


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote a scenario run to golden summaries.")
    parser.add_argument("run_dir", help="Path under data/scenario_runs containing scenario outputs.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    count = update_golden_from_run(Path(args.run_dir))
    print(f"Updated {count} golden scenario summaries.")


if __name__ == "__main__":
    main()

