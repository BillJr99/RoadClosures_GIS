"""Hydrant reachability over one-way streets and the envelope-exceeded fallback.

These tests run fully offline: the road graph is a tiny synthetic MultiDiGraph
and the hydrant layer / graph loading / plan cache are monkeypatched.
"""

from typing import Any

import networkx as nx
import pytest
from pyproj import Transformer

import app.services.planner as planner
from app.models import IncidentPlanRequest
from app.services.planner import (
    FT_TO_M,
    M_TO_FT,
    _hydrant_candidates,
    plan_incident,
)

CRS = "EPSG:32618"
BASE_LON = -75.4
BASE_LAT = 40.2

_to_utm = Transformer.from_crs("EPSG:4326", CRS, always_xy=True)
_to_lonlat = Transformer.from_crs(CRS, "EPSG:4326", always_xy=True)

BASE_X, BASE_Y = _to_utm.transform(BASE_LON, BASE_LAT)


def _node_lonlat(offset_east_m: float) -> tuple[float, float]:
    lon, lat = _to_lonlat.transform(BASE_X + offset_east_m, BASE_Y)
    return float(lon), float(lat)


def _one_way_graph() -> nx.MultiDiGraph:
    """A single one-way road running AWAY from the incident.

    incident @ node 0 --> node 1 --> node 2 (hydrant) --> node 3

    On the directed graph there is no path from the hydrant back to the
    incident, so hoses were falsely rejected; undirected routing must accept
    it with a 200 m road run.
    """
    graph = nx.MultiDiGraph()
    graph.graph["crs"] = CRS
    for node, offset in ((0, 0.0), (1, 100.0), (2, 200.0), (3, 300.0)):
        graph.add_node(node, x=BASE_X + offset, y=BASE_Y)
    graph.add_edge(0, 1, length=100.0, highway="residential", oneway=True)
    graph.add_edge(1, 2, length=100.0, highway="residential", oneway=True)
    graph.add_edge(2, 3, length=100.0, highway="residential", oneway=True)
    return graph


def _hydrant_at(offset_east_m: float) -> dict[str, Any]:
    lon, lat = _node_lonlat(offset_east_m)
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {"source": "test", "name": "Test Hydrant"},
    }


def _request(**overrides: Any) -> IncidentPlanRequest:
    params: dict[str, Any] = {
        "lat": BASE_LAT,
        "lon": BASE_LON,
        "incident_radius_ft": 300.0,
        "study_radius_ft": 1200.0,
        "hose_max_ft": 800.0,
        "hydrant_count": 1,
    }
    params.update(overrides)
    return IncidentPlanRequest(**params)


def test_one_way_only_hydrant_is_accepted(monkeypatch) -> None:
    graph = _one_way_graph()
    monkeypatch.setattr(planner, "_hydrant_features", lambda: [_hydrant_at(200.0)])
    debug: dict[str, Any] = {}

    candidates = _hydrant_candidates(graph, _request(), fire_node=0, debug=debug)

    assert len(candidates) == 1
    assert debug["hydrant_filter"]["accepted"] == 1
    assert debug["hydrant_filter"]["rejected_no_path"] == 0


def test_reverse_edge_path_length_is_measured(monkeypatch) -> None:
    graph = _one_way_graph()
    monkeypatch.setattr(planner, "_hydrant_features", lambda: [_hydrant_at(200.0)])

    candidates = _hydrant_candidates(graph, _request(), fire_node=0)

    # Every hop of the hose path traverses a one-way edge in reverse; the
    # directed graph measured such paths as 0 m.
    assert candidates[0].graph_length_m == pytest.approx(200.0, rel=1e-3)


def test_path_length_on_undirected_view_counts_reversed_edges() -> None:
    graph = _one_way_graph()
    hose_graph = graph.to_undirected(as_view=True)
    assert planner._path_length(hose_graph, [2, 1, 0]) == pytest.approx(200.0, rel=1e-3)


def _plan_with_patches(monkeypatch, req: IncidentPlanRequest, hydrants: list[dict[str, Any]]) -> dict[str, Any]:
    graph = _one_way_graph()
    monkeypatch.setattr(planner, "_load_graph_for_incident", lambda _req: (graph, {"source": "test"}))
    monkeypatch.setattr(planner, "_hydrant_features", lambda: hydrants)
    monkeypatch.setattr(planner, "load_cached_plan", lambda _key: None)
    monkeypatch.setattr(planner, "save_cached_plan", lambda _key, _plan: None)
    return plan_incident(req)


def test_zero_in_envelope_returns_warning_plan(monkeypatch) -> None:
    # 300 ft (~91 m) hose envelope cannot reach the 200 m route, so the plan
    # must fall back to the nearest road-reachable hydrant with a warning
    # instead of raising (which the API turned into a 422).
    req = _request(hose_max_ft=300.0)
    plan = _plan_with_patches(monkeypatch, req, [_hydrant_at(300.0), _hydrant_at(200.0)])

    assert plan["warnings"]
    assert "hose envelope" in plan["warnings"][0]
    assert plan["hose_envelope"]["satisfied"] is False
    assert plan["hose_envelope"]["nearest_hydrant_ft"] > req.hose_max_ft
    # Nearest = the 200 m hydrant, not the 300 m one.
    assert plan["hose_envelope"]["nearest_hydrant_ft"] == pytest.approx(200.0 * M_TO_FT, abs=0.5)
    props = plan["selected_hydrant"]["properties"]
    assert props["exceeds_envelope"] is True
    hose_props = plan["hose_route"]["properties"]
    assert hose_props["exceeds_envelope"] is True
    assert hose_props["hose_deficit_ft"] > 0


def test_within_envelope_plan_has_no_warnings(monkeypatch) -> None:
    req = _request(hose_max_ft=800.0)
    plan = _plan_with_patches(monkeypatch, req, [_hydrant_at(200.0)])

    assert plan["warnings"] == []
    assert plan["hose_envelope"]["satisfied"] is True
    assert plan["selected_hydrant"]["properties"]["exceeds_envelope"] is False
    assert plan["hose_route"]["properties"]["hose_deficit_ft"] == 0


def test_no_hydrants_at_all_still_raises(monkeypatch) -> None:
    with pytest.raises(ValueError) as error:
        _plan_with_patches(monkeypatch, _request(), [])
    message = str(error.value)
    assert "No reachable hydrants" in message
    assert "unreachable by road" in message


def test_fallback_prefers_nearest_by_route_length(monkeypatch) -> None:
    graph = _one_way_graph()
    monkeypatch.setattr(
        planner, "_hydrant_features", lambda: [_hydrant_at(300.0), _hydrant_at(200.0)]
    )
    debug: dict[str, Any] = {}

    candidates = planner._fallback_hydrant_candidates(
        graph, _request(hose_max_ft=300.0), fire_node=0, debug=debug
    )

    assert candidates
    assert candidates[0].graph_length_m == pytest.approx(200.0, rel=1e-3)
    assert debug["hydrant_filter_fallback"]["accepted"] == 2


def test_plan_route_maps_value_error_to_422(monkeypatch) -> None:
    from fastapi import HTTPException

    from app.routes import planner as planner_route

    failures: list[str] = []

    def _boom(_payload: IncidentPlanRequest) -> dict[str, Any]:
        raise ValueError("No reachable hydrants found")

    monkeypatch.setattr(planner_route, "run_plan", _boom)
    monkeypatch.setattr(
        planner_route, "save_ad_hoc_failure", lambda _req, error: failures.append(error)
    )

    with pytest.raises(HTTPException) as error:
        planner_route.plan_incident(_request())
    assert error.value.status_code == 422
    assert failures == ["No reachable hydrants found"]


def test_plan_route_returns_warning_plan_without_error(monkeypatch) -> None:
    from app.routes import planner as planner_route

    warned_plan = {"warnings": ["No hydrant is reachable within the 300 ft hose envelope."]}
    monkeypatch.setattr(planner_route, "run_plan", lambda _payload: dict(warned_plan))
    monkeypatch.setattr(
        planner_route,
        "save_ad_hoc_plan",
        lambda _req, _plan: {"run_id": "adhoc-test", "scenario_id": "adhoc-test", "report_path": ""},
    )

    response = planner_route.plan_incident(_request())

    assert response["warnings"] == warned_plan["warnings"]
    assert response["run_id"] == "adhoc-test"


def test_hose_length_units_round_trip() -> None:
    assert 100.0 * M_TO_FT * FT_TO_M == pytest.approx(100.0)
