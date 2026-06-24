from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import networkx as nx

from app.config import RECONCILED_HYDRANTS_GEOJSON, ROAD_GRAPH_GRAPHML
from app.geojson import line_feature, point_feature, read_geojson
from app.models import IncidentPlanRequest
from app.services.elevation import path_max_grade
from app.services.graph_cache import graph_radius_m, load_or_fetch_graph
from app.services.road_matching import enrich_graph_with_county_roads
from app.services.warning_signs import warning_sign_features


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
    graph_length_m: float
    hydrant_snap_m: float
    incident_snap_m: float
    direct_distance_m: float
    curvature: float
    elevation_change_m: float
    max_grade: float
    score: float


def _load_graph_for_incident(req: IncidentPlanRequest) -> tuple[Any, dict[str, Any]]:
    import osmnx as ox

    if ROAD_GRAPH_GRAPHML.exists():
        graph = ox.load_graphml(ROAD_GRAPH_GRAPHML)
        graph = enrich_graph_with_county_roads(graph)
        snap_m = _graph_point_snap_distance_m(graph, req.lon, req.lat)
        max_snap_m = max(req.study_radius_ft * FT_TO_M, 1000.0 * FT_TO_M)
        if snap_m <= max_snap_m:
            return graph, {
                "cache_hit": False,
                "cache_key": None,
                "graph_path": str(ROAD_GRAPH_GRAPHML),
                "source": "configured GraphML artifact",
                "radius_m": graph_radius_m(req),
                "incident_snap_ft": round(snap_m * M_TO_FT, 1),
            }
        try:
            graph, metadata = load_or_fetch_graph(req)
            graph = enrich_graph_with_county_roads(graph)
            metadata["fallback_reason"] = (
                f"configured GraphML nearest node was {round(snap_m * M_TO_FT, 1)} ft from incident"
            )
            return graph, metadata
        except Exception as e:
            raise ValueError(
                "Configured GraphML artifact does not cover this incident location "
                f"(nearest graph node is {round(snap_m * M_TO_FT, 1)} ft away), "
                "and a local incident graph could not be loaded or fetched. Rebuild layers/graph for this area."
            ) from e
    graph, metadata = load_or_fetch_graph(req)
    graph = enrich_graph_with_county_roads(graph)
    return graph, metadata


def _transformer_to_graph(graph: Any):
    from pyproj import Transformer

    crs = graph.graph.get("crs")
    return Transformer.from_crs("EPSG:4326", crs, always_xy=True)


def _graph_point_snap_distance_m(graph: Any, lon: float, lat: float) -> float:
    import osmnx as ox

    transformer = _transformer_to_graph(graph)
    x, y = transformer.transform(lon, lat)
    node = int(ox.nearest_nodes(graph, X=x, Y=y))
    return _node_distance_m(graph, node, x, y)


def _transformer_from_graph(graph: Any):
    from pyproj import Transformer

    crs = graph.graph.get("crs")
    return Transformer.from_crs(crs, "EPSG:4326", always_xy=True)


def _incident_xy(graph: Any, req: IncidentPlanRequest) -> tuple[float, float]:
    transformer = _transformer_to_graph(graph)
    return transformer.transform(req.lon, req.lat)


def _lonlat_xy(graph: Any, lon: float, lat: float) -> tuple[float, float]:
    transformer = _transformer_to_graph(graph)
    return transformer.transform(lon, lat)


def _nearest_node(graph: Any, lon: float, lat: float) -> int:
    import osmnx as ox

    transformer = _transformer_to_graph(graph)
    x, y = transformer.transform(lon, lat)
    return int(ox.nearest_nodes(graph, X=x, Y=y))


def _node_distance_m(graph: Any, node: int, x: float, y: float) -> float:
    data = graph.nodes[node]
    return math.hypot(float(data["x"]) - x, float(data["y"]) - y)


def _feature_lonlat(feature: dict[str, Any]) -> tuple[float, float] | None:
    geom = feature.get("geometry") or {}
    if geom.get("type") != "Point":
        return None
    lon, lat = geom["coordinates"][:2]
    return float(lon), float(lat)


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


def _hydrant_candidates(graph: Any, req: IncidentPlanRequest, fire_node: int, debug: dict[str, Any] | None = None) -> list[HydrantCandidate]:
    max_m = req.hose_max_ft * FT_TO_M
    incident_x, incident_y = _incident_xy(graph, req)
    incident_snap_m = _node_distance_m(graph, fire_node, incident_x, incident_y)
    max_snap_m = min(250.0 * FT_TO_M, max_m * 0.5)
    if debug is not None:
        debug["hydrant_filter"] = {
            "hose_max_ft": req.hose_max_ft,
            "max_snap_ft": round(max_snap_m * M_TO_FT, 1),
            "incident_snap_ft": round(incident_snap_m * M_TO_FT, 1),
            "total_features": 0,
            "accepted": 0,
            "rejected_direct_distance": 0,
            "rejected_snap_distance": 0,
            "rejected_route_length": 0,
            "rejected_no_path": 0,
            "rejected_non_point": 0,
        }
    candidates: list[HydrantCandidate] = []
    for feature in _hydrant_features():
        if debug is not None:
            debug["hydrant_filter"]["total_features"] += 1
        lonlat = _feature_lonlat(feature)
        if lonlat is None:
            if debug is not None:
                debug["hydrant_filter"]["rejected_non_point"] += 1
            continue
        lon, lat = lonlat
        hydrant_x, hydrant_y = _lonlat_xy(graph, lon, lat)
        direct_distance_m = math.hypot(hydrant_x - incident_x, hydrant_y - incident_y)
        if direct_distance_m > max_m * 1.35:
            if debug is not None:
                debug["hydrant_filter"]["rejected_direct_distance"] += 1
            continue
        try:
            hydrant_node = _nearest_node(graph, lon, lat)
            hydrant_snap_m = _node_distance_m(graph, hydrant_node, hydrant_x, hydrant_y)
            if hydrant_snap_m > max_snap_m or incident_snap_m > max_snap_m:
                if debug is not None:
                    debug["hydrant_filter"]["rejected_snap_distance"] += 1
                continue
            path = nx.shortest_path(graph, hydrant_node, fire_node, weight="length")
            graph_length_m = _path_length(graph, path)
            length_m = graph_length_m + hydrant_snap_m + incident_snap_m
        except Exception:
            if debug is not None:
                debug["hydrant_filter"]["rejected_no_path"] += 1
            continue
        if length_m > max_m:
            if debug is not None:
                debug["hydrant_filter"]["rejected_route_length"] += 1
            continue
        curvature = _path_curvature(graph, path)
        elev_change = _path_elevation_change(graph, path)
        max_grade = path_max_grade(graph, path)
        score = length_m + (curvature * 75.0) + (elev_change * 2.0) + (hydrant_snap_m * 2.0)
        candidates.append(
            HydrantCandidate(
                feature,
                hydrant_node,
                path,
                length_m,
                graph_length_m,
                hydrant_snap_m,
                incident_snap_m,
                direct_distance_m,
                curvature,
                elev_change,
                max_grade,
                score,
            )
        )
        if debug is not None:
            debug["hydrant_filter"]["accepted"] += 1
    return sorted(candidates, key=lambda item: item.score)


def _class_cost(data: dict[str, Any]) -> float:
    county_class = str(data.get("county_func_class") or "").lower()
    if county_class:
        if any(token in county_class for token in ("interstate", "freeway", "expressway")):
            return 12.0
        if "arterial" in county_class or county_class in {"1", "2", "3"}:
            return 8.0
        if "collector" in county_class or county_class in {"4", "5"}:
            return 5.0
        if "local" in county_class or county_class in {"6", "7"}:
            return 2.0
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


def _hose_coords(graph: Any, hydrant: HydrantCandidate, incident_lon: float, incident_lat: float) -> list[list[float]]:
    coords: list[list[float]] = []
    hydrant_lonlat = _feature_lonlat(hydrant.feature)
    if hydrant_lonlat is not None:
        coords.append([hydrant_lonlat[0], hydrant_lonlat[1]])
    for lon, lat in _path_coords(graph, hydrant.path):
        if not coords or [lon, lat] != coords[-1]:
            coords.append([lon, lat])
    incident_coord = [incident_lon, incident_lat]
    if not coords or incident_coord != coords[-1]:
        coords.append(incident_coord)
    return coords


def _closure_feature(graph: Any, rank: int, u: int, v: int, data: dict[str, Any]) -> dict[str, Any]:
    source = data.get("source_data") or {}
    name = source.get("county_st_name") or source.get("name") or source.get("St_Name") or "Unnamed road"
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
            "county_st_name": source.get("county_st_name"),
            "county_func_class": source.get("county_func_class"),
            "county_owner": source.get("county_owner"),
            "county_seg_id": source.get("county_seg_id"),
            "county_match_confidence": source.get("county_match_confidence"),
            "county_match_distance_m": source.get("county_match_distance_m"),
            "county_match_bearing_diff_deg": source.get("county_match_bearing_diff_deg"),
            "grade": source.get("grade"),
            "abs_grade": source.get("abs_grade"),
            "elevation_change_m": source.get("elevation_change_m"),
            "reason": "Minimum cut closure edge; hose route protected",
            "sightline": "caution" if capacity >= 6 else "good",
        },
    )


def plan_incident(req: IncidentPlanRequest) -> dict[str, Any]:
    debug: dict[str, Any] = {
        "request": req.model_dump(),
    }
    graph, graph_source = _load_graph_for_incident(req)
    debug["graph_source"] = graph_source
    x, y = _incident_xy(graph, req)
    fire_node = _nearest_node(graph, req.lon, req.lat)
    debug["incident"] = {
        "lat": req.lat,
        "lon": req.lon,
        "nearest_node": fire_node,
    }

    candidates = _hydrant_candidates(graph, req, fire_node, debug)
    if not candidates:
        filter_details = debug.get("hydrant_filter", {})
        raise ValueError(
            f"No reachable hydrants found within {req.hose_max_ft:g} ft hose envelope. "
            f"Checked {filter_details.get('total_features', 0)} hydrant feature(s); "
            f"{filter_details.get('accepted', 0)} passed distance, snap, and route checks."
        )

    selected_hydrants = candidates[: req.hydrant_count]
    selected = selected_hydrants[0]
    debug["top_hydrant_candidates"] = [
        {
            "source": item.feature.get("properties", {}).get("source"),
            "name": item.feature.get("properties", {}).get("name", ""),
            "coordinates": item.feature.get("geometry", {}).get("coordinates"),
            "length_ft": round(item.length_m * M_TO_FT, 1),
            "graph_length_ft": round(item.graph_length_m * M_TO_FT, 1),
            "hydrant_snap_ft": round(item.hydrant_snap_m * M_TO_FT, 1),
            "incident_snap_ft": round(item.incident_snap_m * M_TO_FT, 1),
            "direct_distance_ft": round(item.direct_distance_m * M_TO_FT, 1),
            "score": round(item.score, 3),
            "path_node_count": len(item.path),
        }
        for item in candidates[:10]
    ]
    hose_edges: set[tuple[int, int]] = set()
    for hydrant in selected_hydrants:
        hose_edges |= _path_edges(hydrant.path) | {(v, u) for u, v in _path_edges(hydrant.path)}
    incident_points = [(req.lat, req.lon), *[(item.lat, item.lon) for item in req.secondary_incidents]]
    incident_nodes: list[int] = []
    for incident_lat, incident_lon in incident_points:
        incident_x, incident_y = _lonlat_xy(graph, incident_lon, incident_lat)
        incident_node = _nearest_node(graph, incident_lon, incident_lat)
        incident_nodes.extend(_nodes_within(graph, incident_x, incident_y, req.incident_radius_ft * FT_TO_M) or [incident_node])
    incident_nodes = sorted(set(incident_nodes))
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
    warning_signs = warning_sign_features(graph, ranked, max_distance_ft=req.sign_max_distance_ft)
    hose_features = []
    for index, hydrant in enumerate(selected_hydrants, start=1):
        hose_features.append(
            line_feature(
                _hose_coords(graph, hydrant, req.lon, req.lat),
                {
                    "kind": "hose_route",
                    "sequence": index,
                    "length_ft": round(hydrant.length_m * M_TO_FT, 1),
                    "graph_length_ft": round(hydrant.graph_length_m * M_TO_FT, 1),
                    "hydrant_snap_ft": round(hydrant.hydrant_snap_m * M_TO_FT, 1),
                    "incident_snap_ft": round(hydrant.incident_snap_m * M_TO_FT, 1),
                    "direct_distance_ft": round(hydrant.direct_distance_m * M_TO_FT, 1),
                    "curvature": round(hydrant.curvature, 4),
                    "elevation_change_ft": round(hydrant.elevation_change_m * M_TO_FT, 1),
                    "max_grade": round(hydrant.max_grade, 5),
                },
            )
        )
    hose_feature = hose_features[0]
    incident_features = [
        point_feature(incident_lon, incident_lat, {"kind": "incident", "sequence": index})
        for index, (incident_lat, incident_lon) in enumerate(incident_points, start=1)
    ]
    hydrant_features = []
    for index, hydrant in enumerate(selected_hydrants, start=1):
        feature = dict(hydrant.feature)
        feature["properties"] = {**feature.get("properties", {}), "selected": True, "sequence": index}
        hydrant_features.append(feature)
    hydrant_feature = hydrant_features[0]
    debug["selected_hydrants"] = debug["top_hydrant_candidates"][: len(selected_hydrants)]
    debug["closure_count"] = len(closure_features)
    debug["warning_sign_count"] = len(warning_signs["features"])

    return {
        "cut_value": round(float(cut_value), 3),
        "selected_hydrant": hydrant_feature,
        "selected_hydrants": {"type": "FeatureCollection", "features": hydrant_features},
        "hose_route": hose_feature,
        "hose_routes": {"type": "FeatureCollection", "features": hose_features},
        "closures": {"type": "FeatureCollection", "features": closure_features},
        "incidents": {"type": "FeatureCollection", "features": incident_features},
        "overlays": {
            "type": "FeatureCollection",
            "features": [*incident_features, *hydrant_features, *hose_features, *closure_features, *warning_signs["features"]],
        },
        "warning_signs": warning_signs,
        "graph_source": graph_source,
        "ranked_closures": [feature["properties"] for feature in closure_features],
        "hydrant_candidates": [
            {
                "source": item.feature.get("properties", {}).get("source"),
                "name": item.feature.get("properties", {}).get("name", ""),
                "length_ft": round(item.length_m * M_TO_FT, 1),
                "direct_distance_ft": round(item.direct_distance_m * M_TO_FT, 1),
                "hydrant_snap_ft": round(item.hydrant_snap_m * M_TO_FT, 1),
                "incident_snap_ft": round(item.incident_snap_m * M_TO_FT, 1),
                "curvature": round(item.curvature, 4),
                "elevation_change_ft": round(item.elevation_change_m * M_TO_FT, 1),
                "max_grade": round(item.max_grade, 5),
                "score": round(item.score, 3),
            }
            for item in candidates[:10]
        ],
        "_debug": debug,
    }
