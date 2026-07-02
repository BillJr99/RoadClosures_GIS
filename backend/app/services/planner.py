from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
from networkx.algorithms.flow import preflow_push

from app.config import (
    CLOSURE_DISTANCE_WEIGHT,
    PERIMETER_FRACTION,
    RECONCILED_HYDRANTS_GEOJSON,
    ROAD_GRAPH_GRAPHML,
    SCORING_WEIGHTS,
)
from app.geojson import line_feature, point_feature, read_geojson
from app.models import IncidentPlanRequest
from app.services.elevation import path_max_grade
from app.services.graph_cache import graph_radius_m, load_or_fetch_graph
from app.services.plan_cache import graph_fingerprint, load_cached_plan, plan_cache_key, save_cached_plan
from app.services.road_matching import enrich_graph_with_county_roads
from app.services.warning_signs import coverage_summary, device_features, warning_sign_features


logger = logging.getLogger("app.services.planner")

M_TO_FT = 3.28084
FT_TO_M = 1.0 / M_TO_FT
INF_CAP = 1_000_000.0
SUPER_SOURCE = "__EXTERNAL__"
SUPER_SINK = "__INCIDENT__"

# How close (ft) the incident must snap to the configured GraphML artifact for
# that artifact to be used. This is a DATA-COVERAGE check ("is the incident on a
# road in this map?"), independent of hose reach: a small single-municipality
# artifact must not be used for incidents outside its coverage, where the
# incident snaps hundreds of feet away and every hydrant then fails. Roads in
# developed areas are typically well under this apart, so a true in-coverage
# incident snaps far closer than this.
CONFIGURED_GRAPH_SNAP_TOLERANCE_FT = 300.0


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
    score_breakdown: dict[str, float] = field(default_factory=dict)


def _load_graph_for_incident(req: IncidentPlanRequest) -> tuple[Any, dict[str, Any]]:
    import osmnx as ox

    if ROAD_GRAPH_GRAPHML.exists():
        graph = ox.load_graphml(ROAD_GRAPH_GRAPHML)
        graph = enrich_graph_with_county_roads(graph)
        snap_m = _graph_point_snap_distance_m(graph, req.lon, req.lat)
        # Only use the configured GraphML when the incident actually snaps onto a
        # road in it. The old threshold (study radius, ~2500 ft) let a small
        # artifact (e.g. a single-municipality graph) be used for incidents far
        # outside its coverage, where the incident node is hundreds of feet away.
        # This is a data-coverage check (not a hose-reach limit), so out-of-coverage
        # incidents fall through to a prebuilt tile or a freshly fetched local graph.
        if snap_m <= CONFIGURED_GRAPH_SNAP_TOLERANCE_FT * FT_TO_M:
            return graph, {
                "cache_hit": False,
                "cache_key": None,
                "graph_path": str(ROAD_GRAPH_GRAPHML),
                "source": "configured GraphML artifact",
                "radius_m": graph_radius_m(req),
                "incident_snap_ft": round(snap_m * M_TO_FT, 1),
            }
        tile_result = _load_operational_tile(req)
        if tile_result is not None:
            graph, metadata = tile_result
            metadata["fallback_reason"] = (
                f"configured GraphML nearest node was {round(snap_m * M_TO_FT, 1)} ft from incident"
            )
            return graph, metadata
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
    # No single configured artifact: prefer a prebuilt operational-area tile
    # (offline) before fetching a fresh incident-local graph.
    tile_result = _load_operational_tile(req)
    if tile_result is not None:
        return tile_result
    try:
        graph, metadata = load_or_fetch_graph(req)
    except Exception as e:
        # Surface fetch failures (e.g. OSM unreachable, offline deployment) as a
        # clear 422 with guidance instead of an opaque 500.
        raise ValueError(
            "No road graph covers this incident location and a fresh graph could "
            "not be fetched from OpenStreetMap. Rebuild the layers/graph for this "
            f"area or check network access. ({e.__class__.__name__}: {e})"
        ) from e
    graph = enrich_graph_with_county_roads(graph)
    return graph, metadata


def _load_operational_tile(req: IncidentPlanRequest) -> tuple[Any, dict[str, Any]] | None:
    from app.services.graph_tiles import find_covering_tile, load_tile_graph, load_tiles

    tiles = load_tiles()
    if not tiles:
        return None
    study_radius_m = req.study_radius_ft * FT_TO_M
    tile = find_covering_tile(tiles, req.lat, req.lon, study_radius_m)
    if tile is None:
        return None
    graph = load_tile_graph(tile)
    graph = enrich_graph_with_county_roads(graph)
    return graph, {
        "cache_hit": True,
        "cache_key": tile.tile_id,
        "graph_path": tile.graph_file,
        "source": "prebuilt operational-area tile",
        "tile_id": tile.tile_id,
        "radius_m": tile.radius_m,
    }


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


def _nearest_nodes_xy(graph: Any, xs: list[float], ys: list[float]) -> list[int]:
    """Nearest graph node for each (x, y) in graph coordinates, in one call.

    Batching the snap across all surviving hydrants is far cheaper than one
    ``nearest_nodes`` call per hydrant.
    """
    if not xs:
        return []
    import osmnx as ox

    result = ox.nearest_nodes(graph, X=xs, Y=ys)
    try:
        return [int(n) for n in result]
    except TypeError:  # single scalar when only one point was requested
        return [int(result)]


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
    from collections.abc import Mapping

    data = graph.get_edge_data(u, v)
    if not data:
        return {}
    # Multigraph edge data is keyed by integer edge keys. Test for Mapping, not
    # dict: graph views (e.g. to_undirected(as_view=True)) return AtlasView
    # mappings, which are not dict instances.
    if isinstance(data, Mapping) and all(isinstance(k, int) for k in data.keys()):
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


def _hydrant_score(
    length_m: float,
    max_m: float,
    curvature: float,
    max_grade: float,
) -> tuple[float, dict[str, float]]:
    """Composite hydrant/hose score (lower is better) from normalized terms.

    Only hydrants whose full hose run (road path plus the off-road gaps at each
    end) fits within the hose envelope are scored; this picks the best among
    them. Each term is normalized to ~0..1 against a sensible reference so the
    weights in ``SCORING_WEIGHTS`` are unit-free and comparable, instead of
    mixing raw meters with radians on one additive scale. The off-road snap gaps
    are already part of ``length_m``, so they are not scored separately.
    """
    w = SCORING_WEIGHTS
    n_length = length_m / max_m if max_m else 0.0
    n_curvature = curvature / math.pi
    n_grade = (abs(max_grade) / w.max_grade) if w.max_grade else 0.0
    breakdown = {
        "length": round(w.length * n_length, 4),
        "curvature": round(w.curvature * n_curvature, 4),
        "grade": round(w.grade * n_grade, 4),
    }
    return sum(breakdown.values()), breakdown


def _within_radius_indices(
    xs: list[float], ys: list[float], cx: float, cy: float, radius: float
) -> list[int]:
    """Indices of points within ``radius`` of (cx, cy).

    Uses a KD-tree when SciPy is available (O(log n) spatial cull over the full
    hydrant set) and falls back to a linear scan otherwise. Behavior is
    identical either way; only the speed differs.
    """
    if not xs:
        return []
    try:
        from scipy.spatial import cKDTree

        tree = cKDTree(list(zip(xs, ys)))
        return sorted(int(i) for i in tree.query_ball_point([cx, cy], radius))
    except Exception:
        return [i for i in range(len(xs)) if math.hypot(xs[i] - cx, ys[i] - cy) <= radius]


def _hydrant_features() -> list[dict[str, Any]]:
    return read_geojson(RECONCILED_HYDRANTS_GEOJSON)["features"]


def _hydrant_candidates(
    graph: Any,
    req: IncidentPlanRequest,
    fire_node: int,
    debug: dict[str, Any] | None = None,
    *,
    search_radius_m: float | None = None,
    max_length_m: float | None = None,
) -> list[HydrantCandidate]:
    max_m = req.hose_max_ft * FT_TO_M
    if search_radius_m is None:
        search_radius_m = max_m * 1.35
    if max_length_m is None:
        max_length_m = max_m
    # Hoses are laid on the ground and do not obey one-way restrictions, so
    # route and measure over an undirected view. (On the directed graph a
    # one-way street makes a nearby hydrant "unreachable", and get_edge_data
    # returns nothing for a reverse-traversed edge so its length reads as 0.)
    hose_graph = graph.to_undirected(as_view=True)
    incident_x, incident_y = _incident_xy(graph, req)
    incident_snap_m = _node_distance_m(graph, fire_node, incident_x, incident_y)
    if debug is not None:
        debug["hydrant_filter"] = {
            "hose_max_ft": req.hose_max_ft,
            "incident_snap_ft": round(incident_snap_m * M_TO_FT, 1),
            "total_features": 0,
            "accepted": 0,
            "rejected_direct_distance": 0,
            "rejected_route_length": 0,
            "rejected_no_path": 0,
            "rejected_non_point": 0,
        }
    # Project every hydrant once (batched), then spatially cull to the ones
    # near the incident before doing any expensive snapping/routing work.
    features = _hydrant_features()
    transformer = _transformer_to_graph(graph)
    lons: list[float] = []
    lats: list[float] = []
    kept: list[dict[str, Any]] = []
    non_point = 0
    for feature in features:
        lonlat = _feature_lonlat(feature)
        if lonlat is None:
            non_point += 1
            continue
        lons.append(lonlat[0])
        lats.append(lonlat[1])
        kept.append(feature)
    if lons:
        xs_arr, ys_arr = transformer.transform(lons, lats)
        xs = [float(v) for v in xs_arr]
        ys = [float(v) for v in ys_arr]
    else:
        xs, ys = [], []
    within = _within_radius_indices(xs, ys, incident_x, incident_y, search_radius_m)
    if debug is not None:
        debug["hydrant_filter"]["total_features"] = len(features)
        debug["hydrant_filter"]["rejected_non_point"] = non_point
        debug["hydrant_filter"]["rejected_direct_distance"] = len(kept) - len(within)
        # Source diagnostics: where the hydrant data came from and where the
        # nearest hydrant actually is (straight-line, regardless of the hose
        # envelope). This lets a "0 hydrants" failure in the log be told apart
        # from a "hydrants exist but out of range" one without a debugger: an
        # empty/mis-built data file shows loaded=0, while a far incident shows
        # the nearest hydrant's coordinates and distance.
        source_info: dict[str, Any] = {
            "path": str(RECONCILED_HYDRANTS_GEOJSON),
            "loaded": len(kept),
            "non_point": non_point,
            "within_search_radius": len(within),
            "search_radius_ft": round(search_radius_m * M_TO_FT, 1),
        }
        if lons:
            source_info["extent_lonlat"] = [
                round(min(lons), 6),
                round(min(lats), 6),
                round(max(lons), 6),
                round(max(lats), 6),
            ]
            nearest_i = min(
                range(len(kept)),
                key=lambda i: math.hypot(xs[i] - incident_x, ys[i] - incident_y),
            )
            nearest_m = math.hypot(xs[nearest_i] - incident_x, ys[nearest_i] - incident_y)
            nearest_props = kept[nearest_i].get("properties", {})
            source_info["nearest_hydrant"] = {
                "lon": round(lons[nearest_i], 6),
                "lat": round(lats[nearest_i], 6),
                "straight_line_ft": round(nearest_m * M_TO_FT, 1),
                "name": nearest_props.get("name", ""),
                "source": nearest_props.get("source", ""),
            }
        debug["hydrant_source"] = source_info

    survivor_xs = [xs[i] for i in within]
    survivor_ys = [ys[i] for i in within]
    survivor_nodes = _nearest_nodes_xy(graph, survivor_xs, survivor_ys)

    candidates: list[HydrantCandidate] = []
    for idx, hydrant_node in zip(within, survivor_nodes):
        feature = kept[idx]
        hydrant_x, hydrant_y = xs[idx], ys[idx]
        direct_distance_m = math.hypot(hydrant_x - incident_x, hydrant_y - incident_y)
        try:
            hydrant_snap_m = _node_distance_m(graph, hydrant_node, hydrant_x, hydrant_y)
            path = nx.shortest_path(hose_graph, hydrant_node, fire_node, weight="length")
            graph_length_m = _path_length(hose_graph, path)
            # Full hose run = road path + the off-road gap at each end (hydrant
            # to road, road to incident). The hose envelope is the ONLY distance
            # limit (no separate hard-coded snap cap): a hydrant is reachable iff
            # this total fits within the configurable hose_max_ft.
            length_m = graph_length_m + hydrant_snap_m + incident_snap_m
        except Exception:
            if debug is not None:
                debug["hydrant_filter"]["rejected_no_path"] += 1
            continue
        if length_m > max_length_m:
            if debug is not None:
                debug["hydrant_filter"]["rejected_route_length"] += 1
            continue
        curvature = _path_curvature(graph, path)
        elev_change = _path_elevation_change(graph, path)
        max_grade = path_max_grade(hose_graph, path)
        score, breakdown = _hydrant_score(length_m, max_m, curvature, max_grade)
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
                breakdown,
            )
        )
        if debug is not None:
            debug["hydrant_filter"]["accepted"] += 1
    return sorted(candidates, key=lambda item: item.score)


def _fallback_hydrant_candidates(
    graph: Any, req: IncidentPlanRequest, fire_node: int, debug: dict[str, Any]
) -> list[HydrantCandidate]:
    """Nearest road-reachable hydrants regardless of the hose envelope.

    Used only when no hydrant fits within hose_max_ft: crews still need the
    nearest water source (relay pumping, tanker shuttle), so the plan proceeds
    with these flagged as exceeding the envelope instead of failing outright.
    """
    search_radius_m = max(req.hose_max_ft * FT_TO_M * 1.35, req.study_radius_ft * FT_TO_M)
    fallback_debug: dict[str, Any] = {}
    candidates = _hydrant_candidates(
        graph,
        req,
        fire_node,
        fallback_debug,
        search_radius_m=search_radius_m,
        max_length_m=math.inf,
    )
    debug["hydrant_filter_fallback"] = fallback_debug.get("hydrant_filter", {})
    return sorted(candidates, key=lambda item: item.length_m)[: req.hydrant_count]


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


def _sightline_penalty(data: dict[str, Any]) -> float:
    """Visibility penalty for a road edge: 1.0 (clear) up to 5.0 (very curvy and steep).

    Higher values mean drivers see the closure later, so a closure here is more
    urgent to set up and stage with advance devices.
    """
    curvature = float(data.get("curvature", 0.0))
    grade = abs(float(data.get("grade", 0.0)))
    return 1.0 + min(curvature * 500.0, 2.0) + min(grade * 10.0, 2.0)


def _edge_capacity(data: dict[str, Any]) -> float:
    length = float(data.get("length", 0.0))
    highway_cost = _class_cost(data)
    sightline_penalty = _sightline_penalty(data)
    return max(0.1, highway_cost * sightline_penalty + 0.15 * (length / 100.0))


def _deployment_score(data: dict[str, Any]) -> float:
    """Field set-up urgency for a closure edge (higher = stage first).

    Combines traffic exposure (road class cost) with poor visibility
    (sightline penalty): a busy road where the closure is hard to see is the
    most dangerous and should be staffed and signed first.
    """
    return _class_cost(data) * _sightline_penalty(data)


def _closure_distance_factor(
    graph: Any,
    u: int,
    v: int,
    incident_xy: tuple[float, float] | None,
    scale_m: float | None,
) -> float:
    """Multiplier (>= 1) applied to a road's cut cost based on how far the edge
    sits from the incident. Closing a far road costs more, so the minimum cut
    forms a tight cordon around the incident instead of a scattered cheap set.

    Returns 1.0 (no weighting) when the incident location or scale is unknown,
    which keeps the bare min-cut behavior used by the unit tests.
    """
    if incident_xy is None or not scale_m or scale_m <= 0 or CLOSURE_DISTANCE_WEIGHT <= 0:
        return 1.0
    ux, uy = _node_xy(graph, u)
    vx, vy = _node_xy(graph, v)
    mid_x, mid_y = (ux + vx) / 2.0, (uy + vy) / 2.0
    distance_m = math.hypot(mid_x - incident_xy[0], mid_y - incident_xy[1])
    return 1.0 + CLOSURE_DISTANCE_WEIGHT * (distance_m / scale_m)


def _build_flow_graph(
    graph: Any,
    incident_nodes: list[int],
    external_nodes: list[int],
    hose_edges: set[tuple[int, int]],
    incident_xy: tuple[float, float] | None = None,
    distance_scale_m: float | None = None,
) -> nx.DiGraph:
    flow = nx.DiGraph()
    for u, v, data in graph.edges(data=True):
        u_int, v_int = int(u), int(v)
        base = _edge_capacity(data)
        if (u_int, v_int) in hose_edges:
            cap = INF_CAP
        else:
            cap = base * _closure_distance_factor(graph, u_int, v_int, incident_xy, distance_scale_m)
        if flow.has_edge(u_int, v_int):
            if cap < float(flow[u_int][v_int]["capacity"]):
                flow[u_int][v_int]["capacity"] = cap
                flow[u_int][v_int]["base_capacity"] = base
                flow[u_int][v_int]["source_data"] = data
        else:
            # `capacity` drives the min-cut (distance-weighted); `base_capacity`
            # is the road-class cost kept for ranking and display so distance does
            # not distort how closures are ranked or what cost is reported.
            flow.add_edge(u_int, v_int, capacity=cap, base_capacity=base, source_data=data)
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


def _node_xy(graph: Any, node: int) -> tuple[float, float]:
    data = graph.nodes[node]
    return float(data["x"]), float(data["y"])


def _edge_attr(graph: Any, u: int, v: int) -> dict[str, Any]:
    """Edge attribute dict for u->v (falling back to v->u), collapsing a
    multigraph's parallel edges to the shortest one. Empty dict when absent."""
    data = graph.get_edge_data(u, v)
    if data is None:
        data = graph.get_edge_data(v, u)
    if not isinstance(data, dict) or not data:
        return {}
    if all(isinstance(key, int) for key in data.keys()):
        data = min(data.values(), key=lambda item: float(item.get("length", 1.0)))
    return data if isinstance(data, dict) else {}


def _edge_xy_coords(
    graph: Any, u: int, v: int, source: dict[str, Any] | None = None
) -> list[tuple[float, float]]:
    """Projected (x, y) vertices along the road from node u to node v.

    Follows the stored OSMnx edge geometry (the curved road polyline) when it is
    present, otherwise falls back to the straight node-to-node line. Always
    oriented u -> v so callers can concatenate consecutive segments.
    """
    if source is None:
        source = _edge_attr(graph, u, v)
    geom = source.get("geometry") if isinstance(source, dict) else None
    ux, uy = _node_xy(graph, u)
    vx, vy = _node_xy(graph, v)
    pts: list[tuple[float, float]] = []
    if geom is not None and hasattr(geom, "coords"):
        pts = [(float(x), float(y)) for x, y in geom.coords]
    if len(pts) < 2:
        return [(ux, uy), (vx, vy)]
    # Orient the polyline u -> v regardless of how the geometry was stored.
    if (pts[-1][0] - ux) ** 2 + (pts[-1][1] - uy) ** 2 < (pts[0][0] - ux) ** 2 + (pts[0][1] - uy) ** 2:
        pts.reverse()
    return pts


def _path_coords(graph: Any, path: list[int]) -> list[list[float]]:
    """Lon/lat polyline for a node path, following each edge's road geometry so
    the line traces the actual (possibly curved) road rather than cutting
    straight between intersections."""
    transformer = _transformer_from_graph(graph)
    coords: list[list[float]] = []
    for u, v in zip(path, path[1:]):
        for x, y in _edge_xy_coords(graph, u, v):
            lon, lat = transformer.transform(x, y)
            point = [float(lon), float(lat)]
            if not coords or point != coords[-1]:
                coords.append(point)
    if not coords and path:
        coords = [[*_node_lonlat(graph, path[0])]]
    return coords


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


def _closure_feature(
    graph: Any,
    rank: int,
    u: int,
    v: int,
    data: dict[str, Any],
    deployment_priority: int | None = None,
) -> dict[str, Any]:
    source = data.get("source_data") or {}
    name = source.get("county_st_name") or source.get("name") or source.get("St_Name") or "Unnamed road"
    if isinstance(name, list):
        name = name[0]
    transformer = _transformer_from_graph(graph)
    coords = [
        [float(lon), float(lat)]
        for lon, lat in (transformer.transform(x, y) for x, y in _edge_xy_coords(graph, u, v, source))
    ]
    # Report the road-class closure cost (base_capacity), not the distance-weighted
    # cut capacity, so the displayed cost reflects the road, not how far it is.
    capacity = float(data.get("base_capacity", data.get("capacity", 0.0)))
    return line_feature(
        coords,
        {
            "rank": rank,
            "deployment_priority": deployment_priority,
            "deployment_label": f"P{deployment_priority}" if deployment_priority else None,
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
            "sightline": "caution" if _sightline_penalty(source) > 1.5 else "good",
        },
    )


def plan_incident(req: IncidentPlanRequest) -> dict[str, Any]:
    debug: dict[str, Any] = {
        "request": req.model_dump(),
    }
    graph, graph_source = _load_graph_for_incident(req)
    debug["graph_source"] = graph_source
    logger.info(
        "Graph loaded: source=%s nodes=%d edges=%d fallback_reason=%s",
        graph_source.get("source") or graph_source.get("graph_path"),
        graph.number_of_nodes(),
        graph.number_of_edges(),
        graph_source.get("fallback_reason"),
    )

    # Plan-result cache: same incident + parameters over the same graph returns
    # the identical result instantly, skipping the hydrant scan and min-cut.
    cache_key = plan_cache_key(req.model_dump(), graph_fingerprint(graph))
    cached = load_cached_plan(cache_key)
    if cached is not None:
        cached["graph_source"] = {**(cached.get("graph_source") or {}), "plan_cache_hit": True}
        logger.info("Plan cache hit: key=%s", cache_key)
        return cached

    x, y = _incident_xy(graph, req)
    fire_node = _nearest_node(graph, req.lon, req.lat)
    incident_snap_m = _node_distance_m(graph, fire_node, x, y)
    debug["incident"] = {
        "lat": req.lat,
        "lon": req.lon,
        "nearest_node": fire_node,
        "snap_ft": round(incident_snap_m * M_TO_FT, 1),
    }
    # Log where the incident landed relative to the street network: the snap
    # distance to the nearest road node plus the lon/lat extent of the loaded
    # streets, so an incident placed outside the graph's coverage is obvious in
    # the log. Node x/y are in the graph's projected CRS, so unproject the
    # bounding corners back to WGS84 for a human-readable extent.
    node_xs = [data["x"] for _, data in graph.nodes(data=True) if data.get("x") is not None]
    node_ys = [data["y"] for _, data in graph.nodes(data=True) if data.get("y") is not None]
    street_extent = None
    if node_xs and node_ys:
        to_wgs84 = _transformer_from_graph(graph)
        (min_lon, max_lon), (min_lat, max_lat) = to_wgs84.transform(
            [min(node_xs), max(node_xs)], [min(node_ys), max(node_ys)]
        )
        street_extent = [round(min_lon, 6), round(min_lat, 6), round(max_lon, 6), round(max_lat, 6)]
    logger.info(
        "Incident placed: lat=%.6f lon=%.6f snapped %.1f ft to nearest road node %s; "
        "street graph nodes=%d edges=%d extent_lonlat=%s",
        req.lat,
        req.lon,
        incident_snap_m * M_TO_FT,
        fire_node,
        graph.number_of_nodes(),
        graph.number_of_edges(),
        street_extent,
    )

    candidates = _hydrant_candidates(graph, req, fire_node, debug)
    logger.info("Hydrant filter: %s", debug.get("hydrant_filter"))
    logger.info("Hydrant source: %s", debug.get("hydrant_source"))
    plan_warnings: list[str] = []
    envelope_satisfied = bool(candidates)
    if not candidates:
        filter_details = debug.get("hydrant_filter", {})
        counter_text = (
            f"Checked {filter_details.get('total_features', 0)} hydrant feature(s): "
            f"{filter_details.get('rejected_direct_distance', 0)} beyond straight-line range, "
            f"{filter_details.get('rejected_route_length', 0)} with hose routes too long, "
            f"{filter_details.get('rejected_no_path', 0)} unreachable by road."
        )
        # No hydrant fits the hose envelope. Fall back to the nearest hydrants
        # reachable by road at all, flagged as exceeding the envelope, so the
        # plan still gives crews closures and the closest water source.
        logger.warning(
            "No hydrant within %g ft hose envelope; trying nearest-reachable fallback. %s",
            req.hose_max_ft,
            counter_text,
        )
        candidates = _fallback_hydrant_candidates(graph, req, fire_node, debug)
        logger.info("Hydrant fallback filter: %s", debug.get("hydrant_filter_fallback"))
        if not candidates:
            raise ValueError(
                f"No reachable hydrants found within {req.hose_max_ft:g} ft hose envelope, "
                f"and none reachable by road within the {req.study_radius_ft:g} ft study radius. "
                f"{counter_text} "
                f"Increase the hose envelope (Configuration → hose envelope feet) or move the "
                f"incident closer to a hydrant."
            )
        nearest_ft = round(candidates[0].length_m * M_TO_FT, 1)
        plan_warnings.append(
            f"No hydrant is reachable within the {req.hose_max_ft:g} ft hose envelope. "
            f"{counter_text} "
            f"Showing the {len(candidates)} nearest road-reachable hydrant(s) instead; the closest "
            f"hose run is {nearest_ft:g} ft ({round(nearest_ft - req.hose_max_ft, 1):g} ft over the envelope)."
        )

    selected_hydrants = candidates[: req.hydrant_count]
    selected = selected_hydrants[0]
    logger.info(
        "Selected %d hydrant(s) (envelope_satisfied=%s); best: name=%s source=%s hose_run_ft=%.1f",
        len(selected_hydrants),
        envelope_satisfied,
        selected.feature.get("properties", {}).get("name", ""),
        selected.feature.get("properties", {}).get("source"),
        selected.length_m * M_TO_FT,
    )
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
            "score_breakdown": item.score_breakdown,
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
    external_nodes = _perimeter_nodes(graph, x, y, req.study_radius_ft * FT_TO_M * PERIMETER_FRACTION)

    flow = _build_flow_graph(
        graph,
        incident_nodes,
        external_nodes,
        hose_edges,
        incident_xy=(x, y),
        distance_scale_m=req.study_radius_ft * FT_TO_M,
    )
    # preflow_push is typically much faster than the default edmonds_karp on
    # road-sized graphs; the min-cut value is unique and float capacities make
    # tied partitions vanishingly rare.
    cut_value, partition = nx.minimum_cut(
        flow, SUPER_SOURCE, SUPER_SINK, capacity="capacity", flow_func=preflow_push
    )
    reachable, non_reachable = partition
    # If the cheapest cut still has near-infinite cost, no finite set of
    # closures can isolate the incident without cutting the protected hose
    # route. Surface that instead of returning a misleading closure list.
    feasible = float(cut_value) < INF_CAP
    feasibility_note = (
        ""
        if feasible
        else "No finite closure set isolates the incident without crossing the protected hose route; widen the study radius or review the hose path."
    )
    closures = _closure_edges(flow, set(reachable), set(non_reachable))
    logger.info(
        "Min-cut done: cut_value=%.3f feasible=%s closures=%d",
        float(cut_value),
        feasible,
        len(closures),
    )
    if not feasible:
        logger.warning("Closure set infeasible: %s", feasibility_note)
    # Rank by road-class closure cost (base_capacity), not the distance-weighted
    # cut capacity, so a near major road still ranks above a far minor one.
    ranked = sorted(
        closures,
        key=lambda item: float(item[2].get("base_capacity", item[2].get("capacity", 0.0))),
        reverse=True,
    )

    # Deployment priority: order closures by field set-up urgency (traffic
    # exposure x poor visibility), tie-broken by cut capacity. This is a
    # separate ordering from `rank` (which reflects cut cost) and tells crews
    # which barriers and signs to stage first under limited resources.
    deploy_order = sorted(
        ranked,
        key=lambda item: (
            _deployment_score(item[2].get("source_data") or {}),
            float(item[2].get("base_capacity", item[2].get("capacity", 0.0))),
        ),
        reverse=True,
    )
    priority_by_edge = {(u, v): index for index, (u, v, _) in enumerate(deploy_order, start=1)}

    closure_features = [
        _closure_feature(graph, rank, u, v, data, priority_by_edge.get((u, v)))
        for rank, (u, v, data) in enumerate(ranked, start=1)
    ]
    deployment_priorities = [priority_by_edge.get((u, v)) for (u, v, _) in ranked]
    warning_signs = warning_sign_features(
        graph,
        ranked,
        max_distance_ft=req.sign_max_distance_ft,
        deployment_priorities=deployment_priorities,
    )
    devices = device_features(graph, ranked, deployment_priorities=deployment_priorities)
    compliance = coverage_summary(ranked, warning_signs)
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
                    "exceeds_envelope": not envelope_satisfied,
                    "hose_deficit_ft": round(max(0.0, hydrant.length_m * M_TO_FT - req.hose_max_ft), 1),
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
        feature["properties"] = {
            **feature.get("properties", {}),
            "selected": True,
            "sequence": index,
            "exceeds_envelope": not envelope_satisfied,
            "hose_deficit_ft": round(max(0.0, hydrant.length_m * M_TO_FT - req.hose_max_ft), 1),
        }
        hydrant_features.append(feature)
    hydrant_feature = hydrant_features[0]
    debug["selected_hydrants"] = debug["top_hydrant_candidates"][: len(selected_hydrants)]
    debug["closure_count"] = len(closure_features)
    debug["warning_sign_count"] = len(warning_signs["features"])

    result = {
        "cut_value": round(float(cut_value), 3),
        "feasible": feasible,
        "feasibility_note": feasibility_note,
        "warnings": plan_warnings,
        "hose_envelope": {
            "satisfied": envelope_satisfied,
            "hose_max_ft": req.hose_max_ft,
            # Shortest hose run among the candidates (they are sorted by score
            # on the normal path, so candidates[0] is not necessarily nearest).
            "nearest_hydrant_ft": round(min(item.length_m for item in candidates) * M_TO_FT, 1),
            "hydrant_filter": debug.get("hydrant_filter", {}),
        },
        "selected_hydrant": hydrant_feature,
        "selected_hydrants": {"type": "FeatureCollection", "features": hydrant_features},
        "hose_route": hose_feature,
        "hose_routes": {"type": "FeatureCollection", "features": hose_features},
        "closures": {"type": "FeatureCollection", "features": closure_features},
        "incidents": {"type": "FeatureCollection", "features": incident_features},
        "overlays": {
            "type": "FeatureCollection",
            "features": [
                *incident_features,
                *hydrant_features,
                *hose_features,
                *closure_features,
                *warning_signs["features"],
                *devices["features"],
            ],
        },
        "warning_signs": warning_signs,
        "devices": devices,
        "compliance": compliance,
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
                "score_breakdown": item.score_breakdown,
            }
            for item in candidates[:10]
        ],
        "_debug": debug,
    }
    save_cached_plan(cache_key, result)
    return result
