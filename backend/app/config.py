from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


# Default CORS origins: the local dev/preview frontend on localhost:5173.
DEFAULT_CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173"]


def cors_allow_origins() -> list[str]:
    """Browser origins the API accepts cross-origin requests from.

    Configured by the ``CORS_ALLOW_ORIGINS`` environment variable:

    - **unset/empty** -> the localhost default (local development), which is the
      assumed setup.
    - **``*``** -> all sources.
    - a comma-separated list of origins -> those exact origins, UNLESS any of them
      is non-localhost (i.e. a real deployment elsewhere), in which case CORS is
      opened to all sources so the frontend can be served from anywhere.
    """
    raw = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
    if not raw:
        return list(DEFAULT_CORS_ORIGINS)
    if raw == "*":
        return ["*"]
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if not origins:
        return list(DEFAULT_CORS_ORIGINS)
    if any("localhost" not in origin and "127.0.0.1" not in origin for origin in origins):
        return ["*"]
    return origins


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"
MANUAL_DIR = DATA_ROOT / "manual"
GENERATED_DIR = DATA_ROOT / "generated"
SCENARIO_DIR = DATA_ROOT / "scenarios"
SCENARIO_RUNS_DIR = DATA_ROOT / "scenario_runs"
SCENARIO_GOLDEN_DIR = DATA_ROOT / "scenario_golden"
SCENARIO_EXPERT_GOLDEN_DIR = SCENARIO_DIR / "goldens"
GRAPH_CACHE_DIR = GENERATED_DIR / "graph_cache"
GRAPH_TILES_DIR = GENERATED_DIR / "graph_tiles"
PLAN_CACHE_DIR = GENERATED_DIR / "plan_cache"
LOGS_DIR = DATA_ROOT / "logs"
BACKEND_LOG_FILE = LOGS_DIR / "backend.log"

# Bump to invalidate cached plan results after a scoring/algorithm change.
# v2: overlay geometry now follows the road polyline (closures, hose, signs,
# devices) instead of straight node-to-node lines.
# v3: closure min-cut is distance-weighted toward the incident (tight cordon).
# v4: hose routing is undirected (one-way streets no longer block hoses) and
# plans fall back to the nearest road-reachable hydrants beyond the envelope.
PLAN_CACHE_VERSION = 4


@dataclass(frozen=True)
class SourceConfig:
    streets_url: str = (
        "https://gis.montcopa.org/arcgis/rest/services/"
        "Streets/Montgomery_County_Streets/FeatureServer/9"
    )
    municipal_boundaries_url: str = (
        "https://gis.montcopa.org/arcgis/rest/services/"
        "Voters/Montgomery_County_Voting_Districts/FeatureServer/1"
    )
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    overpass_fallback_url: str = "https://overpass.kumi.systems/api/interpreter"
    npwa_mapserver_base: str = "https://gis.lansdale.org/arcgis/rest/services/NPWA/MapServer"
    epqs_url: str = "https://epqs.nationalmap.gov/v1/json"
    nominatim_url: str = "https://nominatim.openstreetmap.org/search"
    bbox_wgs84: tuple[float, float, float, float] = (
        -75.7644072,
        39.9441641,
        -74.9469984,
        40.4732320,
    )
    npwa_hydrant_layers: tuple[tuple[int, str], ...] = (
        (2, "NPWA"),
        (7, "NWWA"),
        (8, "SBA"),
    )


SOURCES = SourceConfig()


@dataclass(frozen=True)
class ScoringWeights:
    """Weights for the normalized hydrant/hose-route score (lower is better).

    Each scored term is normalized to roughly 0..1 before weighting so the
    weights are unit-free and directly comparable. See
    ``planner._hydrant_candidates``.
    """

    length: float = 1.0
    # Curvature is weighted as heavily as length so a straighter hose run is
    # preferred even when it is somewhat longer: a farther but straight hydrant
    # beats a closer one reached only through sharp turns.
    curvature: float = 1.0
    grade: float = 0.4
    # Normalization references.
    max_grade: float = 0.15  # ~15% grade treated as the practical worst case


SCORING_WEIGHTS = ScoringWeights()

# Fraction of the study radius beyond which nodes are treated as the outside
# (perimeter) traffic source for the closure min-cut.
PERIMETER_FRACTION = 0.75

# Distance weighting for the closure min-cut. A road's cut cost is multiplied by
# (1 + CLOSURE_DISTANCE_WEIGHT * distance_to_incident / study_radius), so closing
# a road far from the incident is much more expensive than closing one nearby.
# This biases the minimum cut toward a tight cordon hugging the incident instead
# of a cheap-but-scattered separating set on distant streets. 0 disables it.
CLOSURE_DISTANCE_WEIGHT = 8.0

MANUAL_HYDRANTS_CSV = MANUAL_DIR / "manual_hydrants.csv"
SCENARIOS_CSV = SCENARIO_DIR / "incidents.csv"
AUTHORITATIVE_HYDRANTS_GEOJSON = GENERATED_DIR / "authoritative_hydrants.geojson"
MANUAL_HYDRANTS_GEOJSON = GENERATED_DIR / "manual_hydrants.geojson"
RECONCILED_HYDRANTS_GEOJSON = GENERATED_DIR / "reconciled_hydrants.geojson"
ROADS_GEOJSON = GENERATED_DIR / "roads.geojson"
ROAD_GRAPH_GRAPHML = GENERATED_DIR / "road_graph.graphml"
ROAD_GRAPH_SUMMARY_JSON = GENERATED_DIR / "road_graph_summary.json"


def ensure_data_dirs() -> None:
    MANUAL_DIR.mkdir(parents=True, exist_ok=True)
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    GRAPH_TILES_DIR.mkdir(parents=True, exist_ok=True)
    PLAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    SCENARIO_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    SCENARIO_GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    SCENARIO_EXPERT_GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
