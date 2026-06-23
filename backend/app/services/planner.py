from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import networkx as nx

from app.config import RECONCILED_HYDRANTS_GEOJSON, ROAD_GRAPH_GRAPHML
from app.geojson import line_feature, point_feature, read_geojson
from app.models import IncidentPlanRequest


M_TO_FT = 3.28084
FT_TO_M = 1.0 / M_TO_FT
INF_CAP = 1_000_000.0
SUPER_SOURCE = "__EXTERNAL__"
SUPER_SINK = "__INCIDENT__"


ROAD_CLASS_COST = {
    "motorway": 12.0,
    "motorway_link": 10.0,
    "trunk": 10.0,
    "trunk_link": 9.0,
    "primary": 8.0,
    "primary_link": 7.0,
    "secondary": 6.0,
    "secondary_link": 5.5,
    "tertiary": 4.5,
    "tertiary_link": 4.0,
    "residential": 2.0,
    "unclassified": 2.5,
    "living_street": 1.5,
    "service": 1.2,
}


@dataclass(frozen=True)
class HydrantCandidate:
    feature: dict[str, Any]
    node: int
    path: list[int]
    length_m: float
    curvature: float
    elevation_change_m: float
    score: float


def _load_graph_for_incident(req: IncidentPlanRequest) -> Any:
    import osmnx as ox

    if ROAD_GRAPH_GRAPHML.exists():
        return ox.load_graphml(ROAD_GRAPH_GRAPHML)
    dist_m = max(req.study_radius_ft * FT_TO_M, 500.0)
    graph = ox.graph_from_point((req.lat, req.lon), dist=dist_m, network_type="drive", simplify=True)
    return ox.project_graph(graph)


def _transformer_to_graph(graph: Any):
    from pyproj import Transformer

    crs = graph.graph.get("crs")
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True)


def _transformer_from_graph(graph: Any):
    from pyproj import Transformer

    crs = graph.graph.get("crs")
    return Transformer.from_crs(crs, "EPSG:4326", always_xy=True)


def _incident_xy(graph: Any, req: IncidentPlanRequest) -> tuple[float, float]:
    transformer = _transformer_to_graph(graph)
    return transformer.transform(req.lon, req.lat)


def _nearest_node(graph: Any, lon: float, lat: float) -> int:
    import osmnx as ox

    transformer = _transformer_to_graph(graph)
    x, y = transformer.transform(lon, lat)
    return int(ox.nearest_nodes(graph, X=x, Y=y))


def _node_distance_m(graph: Any, node: int, x: float, y: float) -> float:
    data = graph.nodes[node]
    return math.hypot(float(data["x"]) - x, float(data["y"]) - y)


def _nodes_within(graph: Any, x: float, y: float, radius_m: float) -> list[int]:
    return [int(n) for n in graph.nodes if _node_distance_m(graph, int(n), x, y) <= radius_m]


def _perimeter_nodes(graph: Any, x: float, y: float, min_radius_m: float) -> list[int]:
    nodes = [int(n) for n in graph.nodes if _node_distance_m(graph, int(n), x, y) >= min_radius_m]
    return nodes or [int(n) for n in graph.nodes]


def _edge_data(graph: Any, u: int, v: int) -> dict[str, Any]:
    data = graph.get_edge_data(u, v)
    if not data:
        return {}
    if isinstance(data, dict) and all(isinstance(k, int) for k in data.keys()):
        return min(data.values(), key=lambda d: float(d.get("length", 1.0)))
    return data


def _edge_length(graph: Any, u: int, v: int) -> float:
    return float(_edge_data(graph, u, v).get("length", 0.0))


def _path_length(graph: Any, path: list[int]) -> float:
    return sum(_edge_length(graph, path[i], path[i + 1]) for i in range(len(path) - 1))


def _path_edges(path: list[int]) -> set[tuple[int, int]]:
    return {(path[i], path[i + 1]) for i in range(len(path) - 1)}


def _path_curvature(graph: Any, path: list[int]) -> float:
    total = 0.0
    for i in range(1, len(path) - 1):
        a = graph.nodes[path[i - 1]]
        b = graph.nodes[path[i]]
        c = graph.nodes[path[i + 1]]
        v1 = (float(b["x"]) - float(a["x"]), float(b["y"]) - float(a["y"]))
        v2 = (float(c["x"]) - float(b["x"]), float(c["y"]) - float(b["y"]))
        n1 = math.hypot(*v1)
        n2 = math.hypot(*v2)
        if n1 == 0 or n2 == 0:
            continue
        cos_t = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        total += math.acos(cos_t)
    return total


def _path_elevation_change(graph: Any, path: list[int]) -> float:
    total = 0.0
    for i in range(len(path) - 1):
        a = graph.nodes[path[i]].get("elevation")
        b = graph.nodes[path[i + 1]].get("elevation")
        if a is None or b is None:
            continue
        total += abs(float(b) - float(a))
    return total


def _hydrant_features() -> list[dict[str, Any]]:
    return read_geojson(RECONCILED_HYDRANTS_GEOJSON)["features"]


def _hydrant_candidates(graph: Any, req: IncidentPlanRequest, fire_node: int) -> list[HydrantCandidate]:
    max_m = req.hose_max_ft * FT_TO_M
    candidates: list[HydrantCandidate] = []
    for feature in _hydrant_features():
        geom = feature.get("geometry") or {}
        if geom.get("type") != "Point":
            continue
        lon, lat = geom["coordinates"][:2]
        try:
            hydrant_node = _nearest_node(graph, float(lon), float(lat))
            path = nx.shortest_path(graph, hydrant_node, fire_node, weight="length")
            length_m = _path_length(graph, path)
        except Exception:
            continue
        if length_m > max_m:
            continue
        curvature = _path_curvature(graph, path)
        elev_change = _path_elevation_change(graph, path)
        score = length_m + (curvature * 75.0) + (elev_change * 2.0)
        candidates.append(HydrantCandidate(feature, hydrant_node, path, length_m, curvature, elev_change, score))
    return sorted(candidates, key=lambda item: item.score)


def _class_cost(data: dict[str, Any]) -> float:
    highway = data.get("highway", "unclassified")
    if isinstance(highway, list):
        highway = highway[0]
    return ROAD_CLASS_COST.get(str(highway), 3.0)


def _edge_capacity(data: dict[str, Any]) -> float:
    length = float(data.get("length", 0.0))
    highway_cost = _class_cost(data)
    curvature = float(data.get("curvature", 0.0))
    grade = abs(float(data.get("grade", 0.0)))
    sightline_penalty = 1.0 + min(curvature * 500.0, 2.0) + min(grade * 10.0, 2.0)
    return max(0.1, highway_cost * sightline_penalty + 0.15 * (length / 100.0))


def _build_flow_graph(
    graph: Any,
    incident_nodes: list[int],
    external_nodes: list[int],
    hose_edges: set[tuple[int, int]],
) -> nx.DiGraph:
    flow = nx.DiGraph()
    for u, v, data in graph.edges(data=True):
        u_int, v_int = int(u), int(v)
        cap = INF_CAP if (u_int, v_int) in hose_edges else _edge_capacity(data)
        if flow.has_edge(u_int, v_int):
            flow[u_int][v_int]["capacity"] = min(float(flow[u_int][v_int]["capacity"]), cap)
        else:
            flow.add_edge(u_int, v_int, capacity=cap, source_data=data)
    flow.add_node(SUPER_SOURCE)
    flow.add_node(SUPER_SINK)
    for node in external_nodes:
        flow.add_edge(SUPER_SOURCE, node, capacity=INF_CAP)
    for node in incident_nodes:
        flow.add_edge(node, SUPER_SINK, capacity=INF_CAP)
    return flow


def _closure_edges(flow: nx.DiGraph, reachable: set[Any], non_reachable: set[Any]) -> list[tuple[int, int, dict[str, Any]]]:
    closures: list[tuple[int, int, dict[str, Any]]] = []
    for u in reachable:
        for v in flow.successors(u):
            if v in non_reachable:
                data = flow[u][v]
                if float(data.get("capacity", INF_CAP)) < INF_CAP:
                    closures.append((int(u), int(v), dict(data)))
    return closures


def _node_lonlat(graph: Any, node: int) -> tuple[float, float]:
    transformer = _transformer_from_graph(graph)
    data = graph.nodes[node]
    lon, lat = transformer.transform(float(data["x"]), float(data["y"]))
    return float(lon), float(lat)


def _path_coords(graph: Any, path: list[int]) -> list[list[float]]:
    return [[*_node_lonlat(graph, node)] for node in path]


def _closure_feature(graph: Any, rank: int, u: int, v: int, data: dict[str, Any]) -> dict[str, Any]:
    source = data.get("source_data") or {}
    name = source.get("name") or source.get("St_Name") or "Unnamed road"
    if isinstance(name, list):
        name = name[0]
    coords = [[*_node_lonlat(graph, u)], [*_node_lonlat(graph, v)]]
    capacity = float(data.get("capacity", 0.0))
    return line_feature(
        coords,
        {
            "rank": rank,
            "name": name,
            "capacity": round(capacity, 3),
            "highway": source.get("highway", "unclassified"),
            "reason": "Minimum cut closure edge; hose route protected",
            "sightline": "caution" if capacity >= 6 else "good",
        },
    )


def plan_incident(req: IncidentPlanRequest) -> dict[str, Any]:
    graph = _load_graph_for_incident(req)
    x, y = _incident_xy(graph, req)
    fire_node = _nearest_node(graph, req.lon, req.lat)

    candidates = _hydrant_candidates(graph, req, fire_node)
    if not candidates:
        raise ValueError("No reachable hydrants found within hose maximum")

    selected = candidates[0]
    hose_edges = _path_edges(selected.path) | {(v, u) for u, v in _path_edges(selected.path)}
    incident_nodes = _nodes_within(graph, x, y, req.incident_radius_ft * FT_TO_M) or [fire_node]
    external_nodes = _perimeter_nodes(graph, x, y, req.study_radius_ft * FT_TO_M * 0.75)

    flow = _build_flow_graph(graph, incident_nodes, external_nodes, hose_edges)
    cut_value, partition = nx.minimum_cut(flow, SUPER_SOURCE, SUPER_SINK, capacity="capacity")
    reachable, non_reachable = partition
    closures = _closure_edges(flow, set(reachable), set(non_reachable))
    ranked = sorted(closures, key=lambda item: float(item[2].get("capacity", 0.0)), reverse=True)

    closure_features = [
        _closure_feature(graph, rank, u, v, data)
        for rank, (u, v, data) in enumerate(ranked, start=1)
    ]
    hose_feature = line_feature(
        _path_coords(graph, selected.path),
        {
            "kind": "hose_route",
            "length_ft": round(selected.length_m * M_TO_FT, 1),
            "curvature": round(selected.curvature, 4),
            "elevation_change_ft": round(selected.elevation_change_m * M_TO_FT, 1),
        },
    )
    incident_feature = point_feature(req.lon, req.lat, {"kind": "incident"})
    hydrant_feature = dict(selected.feature)
    hydrant_feature["properties"] = {**hydrant_feature.get("properties", {}), "selected": True}

    return {
        "cut_value": round(float(cut_value), 3),
        "selected_hydrant": hydrant_feature,
        "hose_route": hose_feature,
        "closures": {"type": "FeatureCollection", "features": closure_features},
        "overlays": {
            "type": "FeatureCollection",
            "features": [incident_feature, hydrant_feature, hose_feature, *closure_features],
        },
        "ranked_closures": [feature["properties"] for feature in closure_features],
        "hydrant_candidates": [
            {
                "source": item.feature.get("properties", {}).get("source"),
                "name": item.feature.get("properties", {}).get("name", ""),
                "length_ft": round(item.length_m * M_TO_FT, 1),
                "curvature": round(item.curvature, 4),
                "elevation_change_ft": round(item.elevation_change_m * M_TO_FT, 1),
                "score": round(item.score, 3),
            }
            for item in candidates[:10]
        ],
    }

