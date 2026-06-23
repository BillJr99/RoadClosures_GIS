from __future__ import annotations

import json
from typing import Any

import requests

from app.config import ROAD_GRAPH_SUMMARY_JSON, ROADS_GEOJSON, ROAD_GRAPH_GRAPHML, SOURCES
from app.geojson import write_geojson
from app.services.arcgis import fetch_geojson_features


def generate_county_roads_layer(
    bbox: tuple[float, float, float, float] = SOURCES.bbox_wgs84,
) -> int:
    with requests.Session() as session:
        features = fetch_geojson_features(
            SOURCES.streets_url,
            bbox=bbox,
            out_fields="OBJECTID,Status,FuncClass,Owner,Seg_ID,St_Name,St_PosTyp,St_PosDir,HwyNum",
            progress_label="roads",
            session=session,
        )
    for feature in features:
        props = feature.setdefault("properties", {})
        props["source"] = "Montgomery County Streets"
        props["source_kind"] = "authoritative"
    write_geojson(ROADS_GEOJSON, features)
    return len(features)


def generate_osmnx_graph(
    bbox: tuple[float, float, float, float] = SOURCES.bbox_wgs84,
) -> dict[str, Any]:
    import osmnx as ox

    west, south, east, north = bbox
    graph = ox.graph_from_bbox((north, south, east, west), network_type="drive", simplify=True)
    graph = ox.project_graph(graph)
    ox.save_graphml(graph, filepath=ROAD_GRAPH_GRAPHML)
    summary = {
        "source": "OSMnx/OpenStreetMap",
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "crs": str(graph.graph.get("crs")),
    }
    ROAD_GRAPH_SUMMARY_JSON.parent.mkdir(parents=True, exist_ok=True)
    with ROAD_GRAPH_SUMMARY_JSON.open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    return summary


def generate_road_layers(
    bbox: tuple[float, float, float, float] = SOURCES.bbox_wgs84,
    *,
    include_graph: bool = True,
) -> dict[str, Any]:
    road_count = generate_county_roads_layer(bbox)
    graph_summary: dict[str, Any] | None = None
    if include_graph:
        graph_summary = generate_osmnx_graph(bbox)
    return {"roads": road_count, "graph": graph_summary}
