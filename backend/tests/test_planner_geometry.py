import math

import networkx as nx
from shapely.geometry import LineString

from app.services.planner import (
    _closure_distance_factor,
    _edge_xy_coords,
)


def _curved_graph() -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.graph["crs"] = "EPSG:32618"
    graph.add_node(0, x=0.0, y=0.0)
    graph.add_node(1, x=100.0, y=0.0)
    graph.add_node(2, x=200.0, y=0.0)
    # A curved edge 0->1 carrying an explicit OSMnx-style geometry polyline.
    graph.add_edge(0, 1, length=120.0, geometry=LineString([(0.0, 0.0), (50.0, 30.0), (100.0, 0.0)]))
    # A straight edge 1->2 with no geometry attribute.
    graph.add_edge(1, 2, length=100.0)
    return graph


def test_edge_xy_coords_follows_curved_geometry() -> None:
    graph = _curved_graph()
    coords = _edge_xy_coords(graph, 0, 1)
    # Should trace the stored polyline (3 vertices incl. the mid bend), not a
    # straight 2-point line between the endpoints.
    assert coords == [(0.0, 0.0), (50.0, 30.0), (100.0, 0.0)]


def test_edge_xy_coords_orients_u_to_v() -> None:
    graph = _curved_graph()
    # Requesting the reverse direction yields the same polyline reversed so it
    # always runs from the first node to the second.
    coords = _edge_xy_coords(graph, 1, 0)
    assert coords[0] == (100.0, 0.0)
    assert coords[-1] == (0.0, 0.0)


def test_edge_xy_coords_falls_back_to_straight_line() -> None:
    graph = _curved_graph()
    # No geometry on edge 1->2: straight node-to-node line.
    assert _edge_xy_coords(graph, 1, 2) == [(100.0, 0.0), (200.0, 0.0)]


def test_closure_distance_factor_increases_with_distance() -> None:
    graph = _curved_graph()
    incident_xy = (0.0, 0.0)
    scale_m = 200.0
    near = _closure_distance_factor(graph, 0, 1, incident_xy, scale_m)  # midpoint ~ (50,..)
    far = _closure_distance_factor(graph, 1, 2, incident_xy, scale_m)   # midpoint (150,0)
    assert near >= 1.0
    assert far > near  # farther closure costs more, biasing the cut toward the incident


def test_closure_distance_factor_disabled_without_incident() -> None:
    graph = _curved_graph()
    assert _closure_distance_factor(graph, 0, 1, None, None) == 1.0
