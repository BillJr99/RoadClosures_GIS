import json

import networkx as nx

from app.services import road_matching


def test_enrich_graph_with_county_roads(tmp_path, monkeypatch) -> None:
    roads = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[-75.3, 40.2], [-75.299, 40.2]]},
                "properties": {"St_Name": "Main St", "FuncClass": "local", "Owner": "County", "Seg_ID": "seg-1"},
            }
        ],
    }
    roads_path = tmp_path / "roads.geojson"
    roads_path.write_text(json.dumps(roads), encoding="utf-8")
    monkeypatch.setattr(road_matching, "ROADS_GEOJSON", roads_path)
    road_matching._county_index.cache_clear()

    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=-75.3, y=40.2)
    graph.add_node(2, x=-75.299, y=40.2)
    graph.add_edge(1, 2, length=85.0, highway="residential")

    enriched = road_matching.enrich_graph_with_county_roads(graph)
    data = next(iter(enriched.edges(data=True)))[2]

    assert data["county_st_name"] == "Main St"
    assert data["county_seg_id"] == "seg-1"
    assert data["county_match_confidence"] > 0
    rows = road_matching.audit_graph_matches(enriched)
    assert rows[0]["county_st_name"] == "Main St"
    assert rows[0]["match_distance_m"] == 0.0


def test_distant_county_road_match_is_low_confidence(tmp_path, monkeypatch) -> None:
    roads = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": [[0.0, 0.0], [0.001, 0.0]]},
                "properties": {"St_Name": "Far St", "FuncClass": "local"},
            }
        ],
    }
    roads_path = tmp_path / "roads.geojson"
    roads_path.write_text(json.dumps(roads), encoding="utf-8")
    monkeypatch.setattr(road_matching, "ROADS_GEOJSON", roads_path)
    road_matching._county_index.cache_clear()

    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=-75.3, y=40.2)
    graph.add_node(2, x=-75.299, y=40.2)
    graph.add_edge(1, 2, length=85.0, highway="residential")

    enriched = road_matching.enrich_graph_with_county_roads(graph)
    data = next(iter(enriched.edges(data=True)))[2]

    assert "county_st_name" not in data
