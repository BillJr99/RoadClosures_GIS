import networkx as nx

from app.services.planner import _closure_feature, _deployment_score, _sightline_penalty


def test_sightline_penalty_increases_with_curvature_and_grade() -> None:
    clear = _sightline_penalty({"curvature": 0.0, "grade": 0.0})
    curvy = _sightline_penalty({"curvature": 0.01, "grade": 0.0})
    steep = _sightline_penalty({"curvature": 0.0, "grade": 0.5})
    assert clear == 1.0
    assert curvy > clear
    assert steep > clear


def test_deployment_score_favors_busy_and_low_visibility_roads() -> None:
    quiet_clear = _deployment_score({"highway": "residential", "curvature": 0.0, "grade": 0.0})
    busy_clear = _deployment_score({"highway": "primary", "curvature": 0.0, "grade": 0.0})
    busy_blind = _deployment_score({"highway": "primary", "curvature": 0.02, "grade": 0.5})

    # A bigger road outranks a quiet one; poor visibility raises urgency further.
    assert busy_clear > quiet_clear
    assert busy_blind > busy_clear


def test_closure_feature_emits_deployment_priority_label() -> None:
    graph = nx.DiGraph()
    graph.graph["crs"] = "EPSG:32618"
    graph.add_node(0, x=1000.0, y=1000.0)
    graph.add_node(1, x=1100.0, y=1000.0)
    data = {"capacity": 7.0, "source_data": {"highway": "primary", "name": "Broad St"}}

    feature = _closure_feature(graph, rank=2, u=0, v=1, data=data, deployment_priority=1)
    props = feature["properties"]
    assert props["rank"] == 2
    assert props["deployment_priority"] == 1
    assert props["deployment_label"] == "P1"

    # Priority is optional; absent priority leaves the fields unset.
    feature_none = _closure_feature(graph, rank=1, u=0, v=1, data=data)
    assert feature_none["properties"]["deployment_priority"] is None
    assert feature_none["properties"]["deployment_label"] is None
