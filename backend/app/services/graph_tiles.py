from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app import config

# Prebuilt operational-area graph tiles. A tile is a larger road graph (e.g. a
# whole municipality or response district) saved once to GraphML. When an
# incident's study area fits entirely inside a tile, the planner loads the tile
# instead of fetching a fresh incident-local graph — so an operational area can
# be planned fully offline after a one-time prebuild.

EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class OperationalTile:
    tile_id: str
    lat: float
    lon: float
    radius_m: float
    graph_file: str
    network_type: str = "drive"
    nodes: int = 0
    edges: int = 0
    created_at: str = ""


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(math.sqrt(a))


def tile_index_path():
    return config.GRAPH_TILES_DIR / "index.json"


def load_tiles() -> list[OperationalTile]:
    path = tile_index_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    tiles: list[OperationalTile] = []
    for item in raw.get("tiles", []):
        try:
            tiles.append(OperationalTile(**item))
        except TypeError:
            continue
    return tiles


def save_tiles(tiles: list[OperationalTile]) -> None:
    config.GRAPH_TILES_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"tiles": [asdict(tile) for tile in tiles]}
    tile_index_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")


def find_covering_tile(
    tiles: list[OperationalTile], lat: float, lon: float, study_radius_m: float
) -> OperationalTile | None:
    """Smallest tile whose disc fully contains the incident's study disc.

    A tile covers the incident when ``distance(center, incident) + study_radius
    <= tile.radius``, guaranteeing no edges inside the study area are missing.
    The tightest (smallest-radius) covering tile is preferred for speed.
    """
    covering = [
        tile
        for tile in tiles
        if haversine_m(tile.lat, tile.lon, lat, lon) + study_radius_m <= tile.radius_m
    ]
    if not covering:
        return None
    return min(covering, key=lambda tile: tile.radius_m)


def load_tile_graph(tile: OperationalTile) -> Any:
    import osmnx as ox

    return ox.load_graphml(tile.graph_file)


def build_tile(tile_id: str, lat: float, lon: float, radius_m: float, network_type: str = "drive") -> OperationalTile:
    """Fetch and persist one operational-area tile graph (requires network)."""
    import osmnx as ox

    config.GRAPH_TILES_DIR.mkdir(parents=True, exist_ok=True)
    graph = ox.graph_from_point((lat, lon), dist=radius_m, network_type=network_type, simplify=True)
    graph = ox.project_graph(graph)
    graph_file = str(config.GRAPH_TILES_DIR / f"{tile_id}.graphml")
    ox.save_graphml(graph, filepath=graph_file)
    return OperationalTile(
        tile_id=tile_id,
        lat=lat,
        lon=lon,
        radius_m=radius_m,
        graph_file=graph_file,
        network_type=network_type,
        nodes=graph.number_of_nodes(),
        edges=graph.number_of_edges(),
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def upsert_tile(tile: OperationalTile) -> list[OperationalTile]:
    """Add or replace a tile (by tile_id) in the saved index; return the list."""
    tiles = [existing for existing in load_tiles() if existing.tile_id != tile.tile_id]
    tiles.append(tile)
    save_tiles(tiles)
    return tiles
