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

# MUTCD advance-warning sign designations for the A/B/C sequence. The first
# (closest) sign warns ROAD CLOSED AHEAD (W20-3); the further advance signs use
# the general warning (W20-1, repurposed legend "INCIDENT AHEAD"). Sizes are the
# conventional-road standard from MUTCD Table 2C-2.
ADVANCE_SIGN_SPECS = {
    "A": {"code": "W20-3", "legend": "ROAD CLOSED AHEAD", "size_in": "48x48"},
    "B": {"code": "W20-1", "legend": "INCIDENT AHEAD", "size_in": "48x48"},
    "C": {"code": "W20-1", "legend": "INCIDENT AHEAD", "size_in": "48x48"},
}

# Sign mounted at the closure point itself, on the Type III barricade.
CLOSURE_POINT_SIGN = {"code": "R11-2", "legend": "ROAD CLOSED", "size_in": "48x30"}

# Default posted speed (mph) by road type when `maxspeed` is missing, used for
# taper-length math and to keep advance-warning spacing auditable.
DEFAULT_SPEED_MPH = {
    "urban_low_speed": 25.0,
    "urban_high_speed": 45.0,
    "rural": 50.0,
    "expressway_freeway": 60.0,
}


def road_type_for_edge(data: dict[str, Any]) -> str:
    return road_type_with_basis(data)[0]


def road_type_with_basis(data: dict[str, Any]) -> tuple[str, str, str]:
    """Return (road_type, basis, speed_source).

    `basis` explains which rule chose the type; `speed_source` is "maxspeed"
    when posted speed was available, else "missing" (the type fell back to road
    class), so the chosen advance-warning band is auditable.
    """
    highway = data.get("highway")
    if isinstance(highway, list):
        highway = highway[0]
    highway = str(highway or "")
    speed = _speed_mph(data.get("maxspeed"))
    speed_source = "maxspeed" if speed is not None else "missing"
    county_class = str(data.get("county_func_class") or "").lower()
    if highway in {"motorway", "motorway_link", "trunk", "trunk_link"}:
        return "expressway_freeway", f"highway={highway}", speed_source
    if speed and speed > 40:
        return "urban_high_speed", f"maxspeed={speed:g} mph", speed_source
    if "rural" in county_class:
        return "rural", f"county_func_class={county_class}", speed_source
    if highway in {"primary", "secondary", "tertiary", "primary_link", "secondary_link", "tertiary_link"}:
        return "urban_high_speed", f"highway={highway}", speed_source
    return "urban_low_speed", f"highway={highway or 'unknown'}", speed_source


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


def _xy(graph: Any, node: int) -> tuple[float, float]:
    data = graph.nodes[node]
    return float(data["x"]), float(data["y"])


def _interpolate(a: tuple[float, float], b: tuple[float, float], distance_from_a_m: float) -> tuple[float, float]:
    ax, ay = a
    bx, by = b
    length = math.hypot(bx - ax, by - ay) or 1.0
    ratio = max(0.0, min(1.0, distance_from_a_m / length))
    return ax + (bx - ax) * ratio, ay + (by - ay) * ratio


def _lonlat_from_xy(graph: Any, x: float, y: float) -> tuple[float, float]:
    from pyproj import Transformer

    transformer = Transformer.from_crs(graph.graph.get("crs"), "EPSG:4326", always_xy=True)
    lon, lat = transformer.transform(x, y)
    return float(lon), float(lat)


def _edge_source(graph: Any, u: int, v: int) -> dict[str, Any]:
    data = graph.get_edge_data(u, v) or graph.get_edge_data(v, u) or {}
    if isinstance(data, dict) and all(isinstance(key, int) for key in data.keys()):
        data = min(data.values(), key=lambda item: float(item.get("length", 1.0)))
    return data.get("source_data") or data


def _road_name(data: dict[str, Any]) -> str:
    name = data.get("county_st_name") or data.get("name") or data.get("St_Name") or ""
    if isinstance(name, list):
        name = name[0] if name else ""
    return str(name or "").strip().lower()


def _bearing(graph: Any, a: int, b: int) -> float:
    ax, ay = _xy(graph, a)
    bx, by = _xy(graph, b)
    return math.atan2(by - ay, bx - ax)


def _bearing_diff(a: float, b: float) -> float:
    """Smallest absolute angle between two bearings, in radians (0..pi)."""
    diff = abs(a - b) % (2 * math.pi)
    return min(diff, 2 * math.pi - diff)


def _approach_candidates(graph: Any, current: int, previous: int, closure_name: str) -> list[int]:
    nodes = {
        int(node)
        for node in [*graph.predecessors(current), *graph.successors(current)]
        if int(node) != int(previous)
    }
    # Heading of the segment we just travelled (previous -> current); the
    # straightest continuation keeps an advance sign on the same approach
    # through a complex intersection rather than veering onto a side street.
    incoming = _bearing(graph, previous, current)
    return sorted(
        nodes,
        key=lambda node: (
            _road_name(_edge_source(graph, current, node)) != closure_name,
            round(_bearing_diff(incoming, _bearing(graph, current, node)), 3),
            float(_edge_source(graph, current, node).get("length", 0.0) or 0.0),
        ),
    )


def _approach_point(
    graph: Any,
    u: int,
    v: int,
    distance_ft: float,
    closure_name: str,
) -> tuple[float, float, list[int], str, str, float]:
    remaining_m = distance_ft * FT_TO_M
    current = u
    previous = v
    path = [v, u]
    while True:
        candidates = _approach_candidates(graph, current, previous, closure_name)
        if not candidates:
            lon, lat = _point_upstream(graph, u, v, distance_ft)
            shortfall_ft = round(remaining_m * M_TO_FT, 1)
            return lon, lat, path, "limited", "insufficient upstream graph path; projected from closure segment", shortfall_ft
        next_node = candidates[0]
        a = _xy(graph, current)
        b = _xy(graph, next_node)
        segment_m = math.hypot(b[0] - a[0], b[1] - a[1])
        if remaining_m <= segment_m:
            x, y = _interpolate(a, b, remaining_m)
            lon, lat = _lonlat_from_xy(graph, x, y)
            return lon, lat, [*path, next_node], "placed", "", 0.0
        remaining_m -= segment_m
        previous = current
        current = next_node
        path.append(current)
        if len(path) > 20:
            lon, lat = _point_upstream(graph, u, v, distance_ft)
            shortfall_ft = round(remaining_m * M_TO_FT, 1)
            return lon, lat, path, "limited", "approach path search limit reached", shortfall_ft


def warning_sign_features(
    graph: Any,
    closures: list[tuple[int, int, dict[str, Any]]],
    *,
    max_distance_ft: float | None = None,
    deployment_priorities: list[int | None] | None = None,
) -> dict[str, Any]:
    features = []
    placed_keys: set[tuple[str, str, int, int]] = set()
    for closure_rank, (u, v, data) in enumerate(closures, start=1):
        deployment_priority = (
            deployment_priorities[closure_rank - 1]
            if deployment_priorities is not None and closure_rank - 1 < len(deployment_priorities)
            else None
        )
        source = data.get("source_data") or data
        road_type, road_type_basis, speed_source = road_type_with_basis(source)
        spacing = MUTCD_TABLE_6B1[road_type]
        name = source.get("county_st_name") or source.get("name") or source.get("St_Name") or "closure"
        if isinstance(name, list):
            name = name[0]
        closure_name = _road_name(source)
        for side, start, previous in (("u", u, v), ("v", v, u)):
            cumulative = 0.0
            for sequence in ("A", "B", "C"):
                cumulative += spacing[sequence]
                if max_distance_ft is not None and cumulative > max_distance_ft:
                    continue
                lon, lat, approach_path, placement_status, placement_warning, shortfall_ft = _approach_point(
                    graph,
                    start,
                    previous,
                    cumulative,
                    closure_name,
                )
                dedupe_key = (str(name).lower(), sequence, round(lon, 4), round(lat, 4))
                if dedupe_key in placed_keys:
                    continue
                placed_keys.add(dedupe_key)
                features.append(
                    point_feature(
                        lon,
                        lat,
                        {
                            "kind": "warning_sign",
                            "closure_rank": closure_rank,
                            "deployment_priority": deployment_priority,
                            "deployment_label": (
                                f"P{deployment_priority}{sequence}" if deployment_priority else None
                            ),
                            "closure_side": side,
                            "sequence": sequence,
                            "sign_label": ADVANCE_SIGN_SPECS[sequence]["legend"],
                            "mutcd_sign_code": ADVANCE_SIGN_SPECS[sequence]["code"],
                            "sign_size_in": ADVANCE_SIGN_SPECS[sequence]["size_in"],
                            "approach_road": name,
                            "road_type": road_type,
                            "road_type_basis": road_type_basis,
                            "speed_source": speed_source,
                            "spacing_ft": spacing[sequence],
                            "distance_from_closure_ft": cumulative,
                            "mutcd_table": "MUTCD 11th Edition Revision 1 Table 6B-1",
                            "mutcd_spacing_source": "Table 6B-1",
                            "placement_status": placement_status,
                            "placement_warning": placement_warning,
                            "shortfall_ft": shortfall_ft,
                            "approach_path": approach_path,
                            "advisory": True,
                            "confidence": "draft",
                        },
                    )
                )
    return {"type": "FeatureCollection", "features": features}


def _taper_length_ft(speed_mph: float, lane_width_ft: float) -> float:
    """MUTCD Part 6 merging-taper length L (ft) for one lane width W at speed S."""
    if speed_mph >= 45:
        return lane_width_ft * speed_mph
    return lane_width_ft * (speed_mph ** 2) / 60.0


def device_features(
    graph: Any,
    closures: list[tuple[int, int, dict[str, Any]]],
    *,
    deployment_priorities: list[int | None] | None = None,
    lane_width_ft: float = 12.0,
) -> dict[str, Any]:
    """Channelizing devices and barricades for each closure.

    Emits a Type III barricade (with the R11-2 ROAD CLOSED sign) at the closure
    midpoint, plus a cone/drum taper of channelizing devices on each approach.
    Taper length follows MUTCD Part 6 (L = W*S^2/60 below 45 mph, else W*S) and
    device spacing along a taper is the posted speed in feet. Devices inherit the
    parent closure's deployment priority.
    """
    features: list[dict[str, Any]] = []
    for closure_rank, (u, v, data) in enumerate(closures, start=1):
        deployment_priority = (
            deployment_priorities[closure_rank - 1]
            if deployment_priorities is not None and closure_rank - 1 < len(deployment_priorities)
            else None
        )
        source = data.get("source_data") or data
        road_type, _, speed_source = road_type_with_basis(source)
        speed = _speed_mph(source.get("maxspeed")) or DEFAULT_SPEED_MPH[road_type]
        name = source.get("county_st_name") or source.get("name") or source.get("St_Name") or "closure"
        if isinstance(name, list):
            name = name[0]

        taper_ft = _taper_length_ft(speed, lane_width_ft)
        spacing_ft = max(20.0, speed)  # MUTCD: taper device spacing ~= speed (ft)
        device_count = max(2, int(taper_ft // spacing_ft) + 1)

        # Type III barricade across the roadway at the closure midpoint.
        ax, ay = _xy(graph, u)
        bx, by = _xy(graph, v)
        mid_lon, mid_lat = _lonlat_from_xy(graph, (ax + bx) / 2.0, (ay + by) / 2.0)
        features.append(
            point_feature(
                mid_lon,
                mid_lat,
                {
                    "kind": "barricade",
                    "device_type": "Type III barricade",
                    "closure_rank": closure_rank,
                    "deployment_priority": deployment_priority,
                    "deployment_label": f"P{deployment_priority}" if deployment_priority else None,
                    "mutcd_sign_code": CLOSURE_POINT_SIGN["code"],
                    "sign_label": CLOSURE_POINT_SIGN["legend"],
                    "sign_size_in": CLOSURE_POINT_SIGN["size_in"],
                    "approach_road": name,
                    "advisory": True,
                    "confidence": "draft",
                },
            )
        )

        # Cone/drum taper on each approach, leading up to the barricade.
        for side, start, other in (("u", u, v), ("v", v, u)):
            for i in range(1, device_count + 1):
                distance_ft = min(i * spacing_ft, taper_ft)
                lon, lat = _point_upstream(graph, start, other, distance_ft)
                features.append(
                    point_feature(
                        lon,
                        lat,
                        {
                            "kind": "channelizing_device",
                            "device_type": "cone/drum",
                            "closure_rank": closure_rank,
                            "closure_side": side,
                            "deployment_priority": deployment_priority,
                            "deployment_label": f"P{deployment_priority}" if deployment_priority else None,
                            "approach_road": name,
                            "taper_length_ft": round(taper_ft, 1),
                            "spacing_ft": round(spacing_ft, 1),
                            "device_index": i,
                            "device_count": device_count,
                            "speed_mph": speed,
                            "speed_source": speed_source,
                            "advisory": True,
                            "confidence": "draft",
                        },
                    )
                )
    return {"type": "FeatureCollection", "features": features}


def coverage_summary(
    closures: list[tuple[int, int, dict[str, Any]]],
    sign_features: dict[str, Any],
) -> dict[str, Any]:
    """Per-approach advance-warning coverage for a compliance checklist.

    Each closure has two approach sides (u, v). A side is "covered" when at least
    one advance-warning sign on that side was actually placed on the graph (not
    merely projected). Reports covered vs total so reviewers can see gaps.
    """
    total_sides = 2 * len(closures)
    covered: set[tuple[int, str]] = set()
    for feature in sign_features.get("features", []):
        props = feature.get("properties", {})
        if props.get("placement_status") == "placed":
            covered.add((props.get("closure_rank"), props.get("closure_side")))
    covered_sides = len([key for key in covered if key[0] is not None and key[1] is not None])
    return {
        "closures": len(closures),
        "approach_sides_total": total_sides,
        "approach_sides_covered": covered_sides,
        "approach_sides_uncovered": max(0, total_sides - covered_sides),
        "fully_covered": total_sides > 0 and covered_sides == total_sides,
    }
