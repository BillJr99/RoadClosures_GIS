import math

import networkx as nx

from app.services.warning_signs import (
    MUTCD_TABLE_6B1,
    _bearing_diff,
    _taper_length_ft,
    coverage_summary,
    device_features,
    road_type_for_edge,
    road_type_with_basis,
    warning_sign_features,
)


def _simple_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.graph["crs"] = "EPSG:32618"
    graph.add_node(0, x=960.0, y=1000.0)
    graph.add_node(1, x=1000.0, y=1000.0)
    graph.add_node(2, x=1100.0, y=1000.0)
    graph.add_edge(0, 1, length=100.0)
    return graph


def test_mutcd_table_defaults_and_warning_sign_output() -> None:
    assert MUTCD_TABLE_6B1["urban_low_speed"] == {"A": 100, "B": 100, "C": 100}
    assert MUTCD_TABLE_6B1["expressway_freeway"] == {"A": 1000, "B": 1500, "C": 2640}
    assert road_type_for_edge({"highway": "motorway"}) == "expressway_freeway"
    assert road_type_for_edge({"highway": "residential"}) == "urban_low_speed"

    graph = nx.DiGraph()
    graph.graph["crs"] = "EPSG:32618"
    graph.add_node(0, x=960.0, y=1000.0)
    graph.add_node(1, x=1000.0, y=1000.0)
    graph.add_node(2, x=1100.0, y=1000.0)
    graph.add_edge(0, 1, length=100.0)
    signs = warning_sign_features(graph, [(1, 2, {"source_data": {"highway": "residential", "name": "Main St"}})])

    assert len(signs["features"]) == 6
    assert {feature["properties"]["closure_side"] for feature in signs["features"]} == {"u", "v"}
    assert signs["features"][0]["properties"]["sequence"] == "A"
    assert signs["features"][0]["properties"]["mutcd_table"] == "MUTCD 11th Edition Revision 1 Table 6B-1"
    assert signs["features"][0]["properties"]["placement_status"] == "placed"
    assert any(feature["properties"]["placement_status"] == "limited" for feature in signs["features"])
    # Placed signs report zero shortfall; limited signs report how far short the graph fell.
    placed = next(f for f in signs["features"] if f["properties"]["placement_status"] == "placed")
    limited = next(f for f in signs["features"] if f["properties"]["placement_status"] == "limited")
    assert placed["properties"]["shortfall_ft"] == 0.0
    assert limited["properties"]["shortfall_ft"] > 0.0
    # Without a priority list, deployment fields are present but unset.
    assert signs["features"][0]["properties"]["deployment_priority"] is None
    assert signs["features"][0]["properties"]["deployment_label"] is None


def test_signs_emit_mutcd_codes_and_basis() -> None:
    graph = _simple_graph()
    signs = warning_sign_features(graph, [(1, 2, {"source_data": {"highway": "residential", "name": "Main St"}})])
    first = signs["features"][0]["properties"]
    assert first["sequence"] == "A"
    assert first["mutcd_sign_code"] == "W20-3"
    assert first["sign_size_in"] == "48x48"
    # No maxspeed on a residential edge -> speed_source is flagged missing.
    assert first["speed_source"] == "missing"
    assert "highway=residential" in first["road_type_basis"]


def test_road_type_with_basis_uses_maxspeed_when_present() -> None:
    road_type, basis, speed_source = road_type_with_basis({"highway": "secondary", "maxspeed": "45 mph"})
    assert road_type == "urban_high_speed"
    assert speed_source == "maxspeed"
    assert "maxspeed" in basis


def test_taper_length_matches_mutcd_formulas() -> None:
    # Below 45 mph: L = W*S^2/60. W=12, S=30 -> 180 ft.
    assert _taper_length_ft(30.0, 12.0) == 12.0 * 30.0 ** 2 / 60.0
    # 45 mph and above: L = W*S. W=12, S=50 -> 600 ft.
    assert _taper_length_ft(50.0, 12.0) == 12.0 * 50.0


def test_device_features_emit_barricade_and_taper_with_priority() -> None:
    graph = _simple_graph()
    closures = [(1, 2, {"source_data": {"highway": "residential", "name": "Main St"}})]
    devices = device_features(graph, closures, deployment_priorities=[2])
    kinds = {f["properties"]["kind"] for f in devices["features"]}
    assert "barricade" in kinds
    assert "channelizing_device" in kinds
    barricade = next(f for f in devices["features"] if f["properties"]["kind"] == "barricade")
    assert barricade["properties"]["mutcd_sign_code"] == "R11-2"
    assert barricade["properties"]["deployment_priority"] == 2
    cone = next(f for f in devices["features"] if f["properties"]["kind"] == "channelizing_device")
    assert cone["properties"]["taper_length_ft"] > 0
    assert cone["properties"]["deployment_priority"] == 2


def test_coverage_summary_counts_placed_sides() -> None:
    graph = _simple_graph()
    closures = [(1, 2, {"source_data": {"highway": "residential", "name": "Main St"}})]
    signs = warning_sign_features(graph, closures)
    summary = coverage_summary(closures, signs)
    assert summary["closures"] == 1
    assert summary["approach_sides_total"] == 2
    assert 0 <= summary["approach_sides_covered"] <= 2
    assert summary["approach_sides_covered"] + summary["approach_sides_uncovered"] == 2


def test_bearing_diff_is_symmetric_and_wraps() -> None:
    assert _bearing_diff(0.0, 0.0) == 0.0
    assert math.isclose(_bearing_diff(0.0, math.pi), math.pi)
    # 350deg vs 10deg are 20deg apart, not 340.
    assert math.isclose(_bearing_diff(math.radians(350), math.radians(10)), math.radians(20), abs_tol=1e-9)


def test_warning_signs_inherit_deployment_priority() -> None:
    graph = nx.DiGraph()
    graph.graph["crs"] = "EPSG:32618"
    graph.add_node(0, x=960.0, y=1000.0)
    graph.add_node(1, x=1000.0, y=1000.0)
    graph.add_node(2, x=1100.0, y=1000.0)
    graph.add_edge(0, 1, length=100.0)
    closures = [(1, 2, {"source_data": {"highway": "residential", "name": "Main St"}})]

    signs = warning_sign_features(graph, closures, deployment_priorities=[3])

    assert signs["features"], "expected at least one sign"
    for feature in signs["features"]:
        props = feature["properties"]
        assert props["deployment_priority"] == 3
        # Label combines parent closure priority with the A/B/C sequence.
        assert props["deployment_label"] == f"P3{props['sequence']}"
