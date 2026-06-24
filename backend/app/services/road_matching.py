from __future__ import annotations

import math
from functools import lru_cache
from typing import Any

from pyproj import Transformer
from shapely.geometry import LineString, shape
from shapely.strtree import STRtree

from app.config import ROADS_GEOJSON
from app.geojson import read_geojson


MAX_MATCH_DISTANCE_M = 35.0


def _bearing(line: LineString) -> float:
    coords = list(line.coords)
    if len(coords) < 2:
        return 0.0
    x1, y1 = coords[0]
    x2, y2 = coords[-1]
    return math.atan2(y2 - y1, x2 - x1)


def _bearing_delta(a: float, b: float) -> float:
    diff = abs(a - b) % math.pi
    return min(diff, math.pi - diff)


@lru_cache(maxsize=8)
def _county_index(graph_crs: str) -> tuple[STRtree, list[LineString], list[dict[str, Any]]]:
    if not ROADS_GEOJSON.exists():
        return STRtree([]), [], []
    transformer = Transformer.from_crs("EPSG:4326", graph_crs, always_xy=True)
    geoms: list[LineString] = []
    props: list[dict[str, Any]] = []
    for feature in read_geojson(ROADS_GEOJSON).get("features", []):
        geom = feature.get("geometry")
        if not geom:
            continue
        line = shape(geom)
        if line.is_empty:
            continue
        if line.geom_type == "MultiLineString":
            parts = list(line.geoms)
        elif line.geom_type == "LineString":
            parts = [line]
        else:
            continue
        for part in parts:
            projected = LineString([transformer.transform(x, y) for x, y in part.coords])
            if projected.length <= 0:
                continue
            geoms.append(projected)
            props.append(dict(feature.get("properties", {})))
    return STRtree(geoms), geoms, props


def _edge_line(graph: Any, u: int, v: int, data: dict[str, Any]) -> LineString:
    geom = data.get("geometry")
    if geom is not None and hasattr(geom, "coords"):
        return LineString(geom.coords)
    a = graph.nodes[u]
    b = graph.nodes[v]
    return LineString([(float(a["x"]), float(a["y"])), (float(b["x"]), float(b["y"]))])


def _iter_edges(graph: Any):
    if graph.is_multigraph():
        yield from graph.edges(keys=True, data=True)
    else:
        for u, v, data in graph.edges(data=True):
            yield u, v, 0, data


def _best_county_match(graph: Any, u: int, v: int, data: dict[str, Any]) -> dict[str, Any] | None:
    crs = str(graph.graph.get("crs"))
    tree, geoms, props = _county_index(crs)
    if not geoms:
        return None
    edge = _edge_line(graph, int(u), int(v), data)
    candidates = list(tree.query(edge.buffer(MAX_MATCH_DISTANCE_M)))
    if not candidates:
        nearest = tree.nearest(edge)
        candidates = [nearest] if nearest is not None else []
    best: tuple[float, int, float, float] | None = None
    edge_bearing = _bearing(edge)
    for candidate in candidates:
        idx = int(candidate)
        distance = edge.distance(geoms[idx])
        bearing_diff = _bearing_delta(edge_bearing, _bearing(geoms[idx]))
        score = distance + bearing_diff * 20.0
        if best is None or score < best[0]:
            best = (score, idx, distance, bearing_diff)
    if best is None:
        return None
    score, idx, distance, bearing_diff = best
    confidence = max(0.0, min(1.0, 1.0 - (score / 80.0)))
    return {
        "properties": props[idx],
        "score": score,
        "distance_m": distance,
        "bearing_diff_deg": math.degrees(bearing_diff),
        "confidence": round(confidence, 3),
    }


def enrich_graph_with_county_roads(graph: Any) -> Any:
    for u, v, key, data in _iter_edges(graph):
        match = _best_county_match(graph, int(u), int(v), data)
        if match is None or match["confidence"] < 0.35:
            continue
        county = match["properties"]
        data["county_st_name"] = county.get("St_Name") or county.get("FULL_NAME") or county.get("name")
        data["county_func_class"] = county.get("FuncClass")
        data["county_owner"] = county.get("Owner")
        data["county_seg_id"] = county.get("Seg_ID") or county.get("OBJECTID")
        data["county_match_confidence"] = match["confidence"]
        data["county_match_distance_m"] = round(match["distance_m"], 2)
        data["county_match_bearing_diff_deg"] = round(match["bearing_diff_deg"], 1)
    return graph


def audit_graph_matches(graph: Any, *, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for idx, (u, v, key, data) in enumerate(_iter_edges(graph)):
        if limit is not None and idx >= limit:
            break
        match = _best_county_match(graph, int(u), int(v), data)
        county = match["properties"] if match else {}
        rows.append(
            {
                "u": u,
                "v": v,
                "key": key,
                "osm_name": data.get("name", ""),
                "osm_highway": data.get("highway", ""),
                "county_st_name": county.get("St_Name", ""),
                "county_func_class": county.get("FuncClass", ""),
                "county_owner": county.get("Owner", ""),
                "county_seg_id": county.get("Seg_ID") or county.get("OBJECTID", ""),
                "match_confidence": match["confidence"] if match else 0.0,
                "match_distance_m": round(match["distance_m"], 2) if match else "",
                "bearing_diff_deg": round(match["bearing_diff_deg"], 1) if match else "",
            }
        )
    return rows
