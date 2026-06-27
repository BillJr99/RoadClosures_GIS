import networkx as nx
from networkx.algorithms.flow import preflow_push

from app.services.planner import INF_CAP, _build_flow_graph, _closure_edges


def test_min_cut_respects_hose_edges() -> None:
    graph = nx.DiGraph()
    graph.add_edge(5, 1, length=100, highway="residential")
    graph.add_edge(1, 2, length=100, highway="residential")
    graph.add_edge(2, 3, length=100, highway="residential")
    graph.add_edge(5, 4, length=100, highway="primary")
    graph.add_edge(4, 3, length=100, highway="primary")

    flow = _build_flow_graph(
        graph,
        incident_nodes=[3],
        external_nodes=[5],
        hose_edges={(1, 2), (2, 3)},
    )
    cut_value, (reachable, non_reachable) = nx.minimum_cut(
        flow,
        "__EXTERNAL__",
        "__INCIDENT__",
        capacity="capacity",
    )
    closures = _closure_edges(flow, set(reachable), set(non_reachable))

    assert cut_value < INF_CAP
    assert all((u, v) not in {(1, 2), (2, 3)} for u, v, _ in closures)
    assert closures


def test_preflow_push_matches_default_min_cut() -> None:
    # The planner uses preflow_push for speed; it must respect hose edges and
    # return the same cut value as the default flow algorithm.
    graph = nx.DiGraph()
    graph.add_edge(5, 1, length=100, highway="residential")
    graph.add_edge(1, 2, length=100, highway="residential")
    graph.add_edge(2, 3, length=100, highway="residential")
    graph.add_edge(5, 4, length=100, highway="primary")
    graph.add_edge(4, 3, length=100, highway="primary")
    flow = _build_flow_graph(graph, incident_nodes=[3], external_nodes=[5], hose_edges={(1, 2), (2, 3)})

    default_value, _ = nx.minimum_cut(flow, "__EXTERNAL__", "__INCIDENT__", capacity="capacity")
    pp_value, (reachable, non_reachable) = nx.minimum_cut(
        flow, "__EXTERNAL__", "__INCIDENT__", capacity="capacity", flow_func=preflow_push
    )
    assert pp_value == default_value
    closures = _closure_edges(flow, set(reachable), set(non_reachable))
    assert all((u, v) not in {(1, 2), (2, 3)} for u, v, _ in closures)


def test_distance_weighted_cut_prefers_near_ring() -> None:
    # External -> ... -> incident chain. The edge nearest the external perimeter
    # is the cheapest by road class, so the bare min-cut closes that FAR edge.
    # With distance weighting the near-incident edge becomes the cheapest cut, so
    # the cordon hugs the incident instead.
    #   nodes (x meters from incident at origin): I=0, N=100, F=900, E=1000
    def _chain() -> nx.DiGraph:
        graph = nx.DiGraph()
        graph.graph["crs"] = "EPSG:32618"
        graph.add_node(0, x=0.0, y=0.0)     # incident
        graph.add_node(1, x=100.0, y=0.0)   # near
        graph.add_node(2, x=900.0, y=0.0)   # far
        graph.add_node(3, x=1000.0, y=0.0)  # external
        graph.add_edge(3, 2, length=100.0, county_func_class="local")      # far, cheap class
        graph.add_edge(2, 1, length=800.0, county_func_class="collector")
        graph.add_edge(1, 0, length=100.0, county_func_class="collector")  # near
        return graph

    def _cut(graph: nx.DiGraph, **kwargs) -> set[tuple[int, int]]:
        flow = _build_flow_graph(graph, incident_nodes=[0], external_nodes=[3], hose_edges=set(), **kwargs)
        _, (reachable, non_reachable) = nx.minimum_cut(
            flow, "__EXTERNAL__", "__INCIDENT__", capacity="capacity", flow_func=preflow_push
        )
        return {(u, v) for u, v, _ in _closure_edges(flow, set(reachable), set(non_reachable))}

    # No weighting: closes the far, cheaper-by-class edge near the perimeter.
    assert _cut(_chain()) == {(3, 2)}
    # Distance-weighted: closes the near edge that hugs the incident.
    assert _cut(_chain(), incident_xy=(0.0, 0.0), distance_scale_m=1000.0) == {(1, 0)}
