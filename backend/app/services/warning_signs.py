from __future__ import annotations

import math
from typing import Any

from app.geojson import point_feature


M_TO_FT = 3.28084
FT_TO_M = 1.0 / M_TO_FT

MUTCD_TABLE_6B1 = {
    "urban_low_speed": {"A": 100, "B": 100, "C": 100},
    "urban_high_speed": {"A": 350, "B": 350, "C": 350},
    "rural": {"A": 500, "B": 500, "C": 500},
    "expressway_freeway": {"A": 1000, "B": 1500, "C": 2640},
}


def road_type_for_edge(data: dict[str, Any]) -> str:
    highway = data.get("highway")
    if isinstance(highway, list):
        highway = highway[0]
    highway = str(highway or "")
    if highway in {"motorway", "motorway_link", "trunk", "trunk_link"}:
        return "expressway_freeway"
    speed = _speed_mph(data.get("maxspeed"))
    county_class = str(data.get("county_func_class") or "").lower()
    if speed and speed > 40:
        return "urban_high_speed"
    if "rural" in county_class:
        return "rural"
    if highway in {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link"}:
        return "urban_high_speed"
    return "urban_low_speed"


def _speed_mph(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    text = str(value or "").lower().replace("mph", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def _node_lonlat(graph: Any, node: int) -> tuple[float, float]:
    from pyproj import Transformer

    transformer = Transformer.from_crs(graph.graph.get("crs"), "EPSG:4326", always_xy=True)
    data = graph.nodes[node]
    lon, lat = transformer.transform(float(data["x"]), float(data["y"]))
    return float(lon), float(lat)


def _point_upstream(graph: Any, u: int, v: int, distance_ft: float) -> tuple[float, float]:
    from pyproj import Transformer

    transformer = Transformer.from_crs(graph.graph.get("crs"), "EPSG:4326", always_xy=True)
    a = graph.nodes[u]
    b = graph.nodes[v]
    ux, uy = float(a["x"]), float(a["y"])
    vx, vy = float(b["x"]), float(b["y"])
    dx, dy = ux - vx, uy - vy
    norm = math.hypot(dx, dy) or 1.0
    distance_m = distance_ft * FT_TO_M
    x = ux + (dx / norm) * distance_m
    y = uy + (dy / norm) * distance_m
    lon, lat = transformer.transform(x, y)
    return float(lon), float(lat)


def warning_sign_features(graph: Any, closures: list[tuple[int, int, dict[str, Any]]]) -> dict[str, Any]:
    features = []
    for closure_rank, (u, v, data) in enumerate(closures, start=1):
        source = data.get("source_data") or data
        road_type = road_type_for_edge(source)
        spacing = MUTCD_TABLE_6B1[road_type]
        name = source.get("county_st_name") or source.get("name") or source.get("St_Name") or "closure"
        if isinstance(name, list):
            name = name[0]
        cumulative = 0.0
        for sequence in ("A", "B", "C"):
            cumulative += spacing[sequence]
            lon, lat = _point_upstream(graph, u, v, cumulative)
            features.append(
                point_feature(
                    lon,
                    lat,
                    {
                        "kind": "warning_sign",
                        "closure_rank": closure_rank,
                        "sequence": sequence,
                        "sign_label": "ROAD CLOSED AHEAD" if sequence == "A" else "INCIDENT AHEAD",
                        "approach_road": name,
                        "road_type": road_type,
                        "spacing_ft": spacing[sequence],
                        "distance_from_closure_ft": cumulative,
                        "mutcd_table": "MUTCD 11th Edition Revision 1 Table 6B-1",
                        "advisory": True,
                        "confidence": "draft",
                    },
                )
            )
    return {"type": "FeatureCollection", "features": features}

