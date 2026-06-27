import json
from pathlib import Path

from app.services import scenario_runs
from app.services.field_report import (
    MUTCD_SIGN_REF,
    build_field_report,
    render_field_report_html,
    render_field_report_markdown,
)


def _sample_plan() -> dict:
    return {
        "feasible": True,
        "feasibility_note": None,
        "selected_hydrant": {
            "geometry": {"type": "Point", "coordinates": [-75.34, 40.11]},
            "properties": {
                "name": "Hydrant 7",
                "source": "authority",
                "score_breakdown": {"length": 0.4, "curvature": 0.1},
            },
        },
        "hose_route": {
            "geometry": {"type": "LineString", "coordinates": [[-75.34, 40.11], [-75.341, 40.111]]},
            "properties": {"length_ft": 420.0, "curvature": 0.3, "elevation_change_ft": 12.0, "max_grade": 0.04},
        },
        "closures": {
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "LineString", "coordinates": [[-75.34, 40.11], [-75.345, 40.112]]},
                    "properties": {
                        "rank": 1,
                        "name": "Main St",
                        "county_st_name": "MAIN ST",
                        "county_func_class": "minor arterial",
                        "capacity": 5.0,
                        "sightline": "caution",
                        "grade": 0.06,
                        "elevation_change_m": 3.2,
                        "deployment_label": "P1",
                    },
                }
            ],
        },
        "warning_signs": {
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [-75.346, 40.113]},
                    "properties": {
                        "approach_road": "Main St",
                        "sequence": "A",
                        "mutcd_sign_code": "W20-3",
                        "sign_label": "ROAD CLOSED AHEAD",
                        "road_type": "urban_low_speed",
                        "road_type_basis": "highway=residential",
                        "speed_source": "missing",
                        "spacing_ft": 100,
                        "distance_from_closure_ft": 100,
                        "closure_rank": 1,
                        "closure_side": "u",
                        "placement_status": "placed",
                        "deployment_label": "P1A",
                    },
                }
            ],
        },
        "devices": {
            "type": "FeatureCollection",
            "features": [
                {
                    "geometry": {"type": "Point", "coordinates": [-75.343, 40.111]},
                    "properties": {
                        "kind": "barricade",
                        "approach_road": "Main St",
                        "mutcd_sign_code": "R11-2",
                        "sign_label": "ROAD CLOSED",
                        "deployment_label": "P1",
                    },
                },
                {
                    "geometry": {"type": "Point", "coordinates": [-75.344, 40.1115]},
                    "properties": {
                        "kind": "channelizing_device",
                        "approach_road": "Main St",
                        "taper_length_ft": 125.0,
                        "spacing_ft": 25.0,
                        "device_index": 1,
                        "device_count": 6,
                        "speed_mph": 25.0,
                        "speed_source": "missing",
                    },
                },
            ],
        },
    }


def test_build_field_report_captures_what_where_why() -> None:
    report = build_field_report({"scenario_id": "s1", "name": "Test Incident"}, _sample_plan())

    # What + where (road-level naming + coordinates).
    assert report["hydrant"]["name"] == "Hydrant 7"
    assert report["hydrant"]["where"] == "40.110000, -75.340000"
    assert report["closures"][0]["name"] == "MAIN ST"
    assert report["closures"][0]["where"]  # has a coordinate

    # Why: MUTCD reference present on signs, traffic/sightline reasons on closures.
    assert any("Table 6B-1" in reason for reason in report["warning_signs"][0]["why"])
    assert any("minor arterial" in reason for reason in report["closures"][0]["why"])
    assert any("Sightline caution" in reason for reason in report["closures"][0]["why"])
    assert report["mutcd_references"]["advance_warning_signs"] == MUTCD_SIGN_REF


def test_render_markdown_and_html() -> None:
    report = build_field_report({"scenario_id": "s1", "name": "Test Incident"}, _sample_plan())
    md = render_field_report_markdown(report)
    assert "# Field placement report — Test Incident" in md
    assert "MAIN ST" in md and "W20-3" in md
    html = render_field_report_html(report)
    assert "field-report" in html and "Main St" in html


def test_read_run_report_html_serves_file(tmp_path: Path, monkeypatch) -> None:
    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "20260101T000000Z"
    run_dir.mkdir(parents=True)
    (run_dir / "report.html").write_text("<html><body>hello</body></html>", encoding="utf-8")
    monkeypatch.setattr(scenario_runs, "SCENARIO_RUNS_DIR", runs_dir)

    assert "hello" in scenario_runs.read_run_report_html("20260101T000000Z")
