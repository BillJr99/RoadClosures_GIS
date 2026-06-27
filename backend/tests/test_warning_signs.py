import networkx as nx

from app.services.warning_signs import MUTCD_TABLE_6B1, road_type_for_edge, warning_sign_features


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
    # Without a priority list, deployment fields are present but unset.
    assert signs["features"][0]["properties"]["deployment_priority"] is None
    assert signs["features"][0]["properties"]["deployment_label"] is None


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
