from app import config
from app.services import graph_tiles
from app.services.graph_tiles import OperationalTile, find_covering_tile, haversine_m


def test_haversine_known_distance() -> None:
    # ~1 degree of latitude is ~111 km.
    d = haversine_m(40.0, -75.0, 41.0, -75.0)
    assert 110_000 < d < 112_000
    assert haversine_m(40.0, -75.0, 40.0, -75.0) == 0.0


def test_find_covering_tile_requires_full_containment() -> None:
    near = OperationalTile("near", 40.10, -75.34, radius_m=3000.0, graph_file="near.graphml")
    far = OperationalTile("far", 41.00, -75.34, radius_m=3000.0, graph_file="far.graphml")
    tiles = [near, far]

    # Study disc (300 m) centered ~ at the tile center fits inside the 3 km tile.
    assert find_covering_tile(tiles, 40.10, -75.34, 300.0) is near
    # A 5 km study radius cannot fit inside a 3 km tile.
    assert find_covering_tile(tiles, 40.10, -75.34, 5000.0) is None
    # An incident far from every tile center is not covered.
    assert find_covering_tile(tiles, 39.0, -76.0, 300.0) is None


def test_find_covering_tile_prefers_smallest_radius() -> None:
    big = OperationalTile("big", 40.10, -75.34, radius_m=10000.0, graph_file="big.graphml")
    tight = OperationalTile("tight", 40.10, -75.34, radius_m=3000.0, graph_file="tight.graphml")
    assert find_covering_tile([big, tight], 40.10, -75.34, 300.0) is tight


def test_tile_index_round_trip(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "GRAPH_TILES_DIR", tmp_path)
    assert graph_tiles.load_tiles() == []
    tile = OperationalTile("t1", 40.1, -75.3, 3000.0, str(tmp_path / "t1.graphml"), nodes=5, edges=8)
    graph_tiles.save_tiles([tile])
    loaded = graph_tiles.load_tiles()
    assert loaded == [tile]


def test_upsert_tile_replaces_by_id(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(config, "GRAPH_TILES_DIR", tmp_path)
    graph_tiles.upsert_tile(OperationalTile("t1", 40.1, -75.3, 3000.0, "a.graphml"))
    graph_tiles.upsert_tile(OperationalTile("t1", 40.2, -75.4, 5000.0, "b.graphml"))
    tiles = graph_tiles.load_tiles()
    assert len(tiles) == 1
    assert tiles[0].radius_m == 5000.0


def test_planner_tile_lookup_returns_none_without_tiles(tmp_path, monkeypatch) -> None:
    # The planner's tile branch is a no-op (falls through to fetch) when no tiles
    # are prebuilt; verify it does not error and returns None.
    from app.models import IncidentPlanRequest
    from app.services.planner import _load_operational_tile

    monkeypatch.setattr(config, "GRAPH_TILES_DIR", tmp_path)
    req = IncidentPlanRequest(lat=40.1, lon=-75.3)
    assert _load_operational_tile(req) is None
