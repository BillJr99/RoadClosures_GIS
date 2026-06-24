from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = REPO_ROOT / "data"
MANUAL_DIR = DATA_ROOT / "manual"
GENERATED_DIR = DATA_ROOT / "generated"
SCENARIO_DIR = DATA_ROOT / "scenarios"
SCENARIO_RUNS_DIR = DATA_ROOT / "scenario_runs"
SCENARIO_GOLDEN_DIR = DATA_ROOT / "scenario_golden"
GRAPH_CACHE_DIR = GENERATED_DIR / "graph_cache"


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
    SCENARIO_DIR.mkdir(parents=True, exist_ok=True)
    SCENARIO_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    SCENARIO_GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
