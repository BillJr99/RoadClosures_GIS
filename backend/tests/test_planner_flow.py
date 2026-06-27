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
