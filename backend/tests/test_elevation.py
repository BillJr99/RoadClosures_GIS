import networkx as nx

from app.services.elevation import enrich_graph_elevation, path_max_grade


def test_enrich_graph_elevation_adds_node_and_edge_grade() -> None:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:4326"
    graph.add_node(1, x=-75.3, y=40.2)
    graph.add_node(2, x=-75.299, y=40.2)
    graph.add_edge(1, 2, length=100.0)

    values = {1: 100.0, 2: 110.0}

    def fetcher(lon: float, lat: float) -> float:
        return values[1] if lon == -75.3 else values[2]

    summary = enrich_graph_elevation(graph, fetcher=fetcher)
    edge = next(iter(graph.edges(data=True)))[2]

    assert summary == {"nodes_enriched": 2, "edges_enriched": 1}
    assert edge["elevation_change_m"] == 10.0
    assert edge["grade"] == 0.1
    assert path_max_grade(graph, [1, 2]) == 0.1

