from __future__ import annotations

import math
from typing import Any, Callable

import requests

from app.config import SOURCES


ElevationFetcher = Callable[[float, float], float | None]


def fetch_epqs_elevation(lon: float, lat: float) -> float | None:
    response = requests.get(
        SOURCES.epqs_url,
        params={"x": lon, "y": lat, "units": "Meters", "output": "json"},
        timeout=15,
    )
    response.raise_for_status()
    data = response.json()
    value = data.get("value")
    if value in (None, "", "null"):
        return None
    try:
        elevation = float(value)
    except (TypeError, ValueError):
        return None
    if elevation <= -100000:
        return None
    return elevation


def _node_lonlat(graph: Any, node: int) -> tuple[float, float]:
    from pyproj import Transformer

    transformer = Transformer.from_crs(graph.graph.get("crs"), "EPSG:4326", always_xy=True)
    data = graph.nodes[node]
    lon, lat = transformer.transform(float(data["x"]), float(data["y"]))
    return float(lon), float(lat)


def enrich_graph_elevation(graph: Any, *, fetcher: ElevationFetcher = fetch_epqs_elevation) -> dict[str, int]:
    node_count = 0
    for node in graph.nodes:
        lon, lat = _node_lonlat(graph, int(node))
        elevation = fetcher(lon, lat)
        if elevation is None:
            continue
        graph.nodes[node]["elevation"] = round(elevation, 3)
        node_count += 1

    edge_count = 0
    for u, v, data in graph.edges(data=True):
        a = graph.nodes[u].get("elevation")
        b = graph.nodes[v].get("elevation")
        length = float(data.get("length", 0.0) or 0.0)
        if a is None or b is None or length <= 0:
            continue
        change = float(b) - float(a)
        grade = change / length
        data["elevation_change_m"] = round(change, 3)
        data["grade"] = round(grade, 5)
        data["abs_grade"] = round(abs(grade), 5)
        edge_count += 1
    return {"nodes_enriched": node_count, "edges_enriched": edge_count}


def path_max_grade(graph: Any, path: list[int]) -> float:
    maximum = 0.0
    for i in range(len(path) - 1):
        data = graph.get_edge_data(path[i], path[i + 1]) or {}
        if isinstance(data, dict) and all(isinstance(k, int) for k in data.keys()):
            values = data.values()
        else:
            values = [data]
        for edge in values:
            maximum = max(maximum, abs(float(edge.get("grade", 0.0) or 0.0)))
    return maximum

