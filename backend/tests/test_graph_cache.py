import networkx as nx

from app.models import IncidentPlanRequest
from app.services import graph_cache


def _graph() -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = "EPSG:32618"
    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=100.0, y=0.0)
    graph.add_edge(1, 2, length=100.0, highway="residential")
    return graph


def test_graph_cache_fetches_then_reuses(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(graph_cache, "GRAPH_CACHE_DIR", tmp_path)
    req = IncidentPlanRequest(lat=40.2, lon=-75.3, study_radius_ft=2500)
    calls = 0

    def fetcher(_req, _radius_m, _network_type):
        nonlocal calls
        calls += 1
        return _graph()

    _, first = graph_cache.load_or_fetch_graph(req, fetcher=fetcher)
    _, second = graph_cache.load_or_fetch_graph(req, fetcher=fetcher)

    assert calls == 1
    assert first["cache_hit"] is False
    assert second["cache_hit"] is True
    assert first["cache_key"] == second["cache_key"]

