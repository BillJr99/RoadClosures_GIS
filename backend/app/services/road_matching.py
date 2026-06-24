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


def enrich_graph_with_county_roads(graph: Any) -> Any:
    crs = str(graph.graph.get("crs"))
    tree, geoms, props = _county_index(crs)
    if not geoms:
        return graph

    for u, v, key, data in graph.edges(keys=True, data=True):
        edge = _edge_line(graph, int(u), int(v), data)
        candidates = list(tree.query(edge.buffer(MAX_MATCH_DISTANCE_M)))
        if not candidates:
            nearest = tree.nearest(edge)
            candidates = [nearest] if nearest is not None else []
        best: tuple[float, int] | None = None
        edge_bearing = _bearing(edge)
        for candidate in candidates:
            idx = int(candidate)
            distance = edge.distance(geoms[idx])
            bearing_penalty = _bearing_delta(edge_bearing, _bearing(geoms[idx])) * 20.0
            score = distance + bearing_penalty
            if best is None or score < best[0]:
                best = (score, idx)
        if best is None:
            continue
        score, idx = best
        confidence = max(0.0, min(1.0, 1.0 - (score / 80.0)))
        if confidence < 0.35:
            continue
        county = props[idx]
        data["county_st_name"] = county.get("St_Name") or county.get("FULL_NAME") or county.get("name")
        data["county_func_class"] = county.get("FuncClass")
        data["county_owner"] = county.get("Owner")
        data["county_seg_id"] = county.get("Seg_ID") or county.get("OBJECTID")
        data["county_match_confidence"] = round(confidence, 3)
    return graph

