"""Human-readable "what / where / why" field report for a planned incident.

Turns a planner result into an operational placement report. For every placed
element — the selected hydrant, the hose route, each road closure, each
advance-warning sign, each channelizing device, and the barricade — it records:

* **what** it is (element type and MUTCD designation where applicable),
* **where** it is, using road-level naming (county/OSM street name) plus a
  ``lat, lon`` location, and
* **why** it was placed, citing the governing MUTCD table/part for signs and
  devices, and the curvature / traffic (road-class cost) / elevation factors
  that drove the hydrant, hose, and closure decisions.

The report is emitted alongside each scenario run as ``field_report.json``
(structured) and ``field_report.md`` (readable), and is summarized in the run
``report.html``.
"""

from __future__ import annotations

import html
from typing import Any

# MUTCD provenance strings reused across elements so the citations stay
# consistent and auditable.
MUTCD_SIGN_REF = "MUTCD 11th Edition, Rev. 1, Part 6, Table 6B-1 (advance-warning sign spacing)"
MUTCD_BARRICADE_REF = "MUTCD Part 6 (Temporary Traffic Control) — Type III barricade, R11-2 ROAD CLOSED"
MUTCD_TAPER_REF = "MUTCD Part 6 — channelizing-device taper (L = W·S²/60 below 45 mph, else L = W·S)"


def _coord_text(coordinates: Any) -> str | None:
    """Format a GeoJSON [lon, lat] (or the first vertex of a line) as 'lat, lon'."""
    if not isinstance(coordinates, (list, tuple)) or not coordinates:
        return None
    first = coordinates
    # Walk into nested coordinate arrays (LineString / MultiPoint) to the first point.
    while first and isinstance(first[0], (list, tuple)):
        first = first[0]
    if len(first) < 2:
        return None
    lon, lat = float(first[0]), float(first[1])
    return f"{lat:.6f}, {lon:.6f}"


def _feature_coord(feature: dict[str, Any]) -> str | None:
    geom = feature.get("geometry") or {}
    return _coord_text(geom.get("coordinates"))


def _round(value: Any, digits: int = 1) -> Any:
    try:
        return round(float(value), digits)
    except (TypeError, ValueError):
        return value


def _hydrant_section(plan: dict[str, Any]) -> dict[str, Any]:
    hydrant = plan.get("selected_hydrant") or {}
    props = hydrant.get("properties", {}) if isinstance(hydrant, dict) else {}
    hose = (plan.get("hose_route") or {}).get("properties", {})
    breakdown = props.get("score_breakdown") or {}
    reasons = []
    if breakdown:
        terms = ", ".join(f"{key} {(_round(val, 3))}" for key, val in breakdown.items())
        reasons.append(f"Lowest weighted score (normalized terms: {terms}); lower is better")
    if hose:
        reasons.append(
            f"Hose run {_round(hose.get('length_ft'))} ft, curvature {_round(hose.get('curvature'), 4)} rad, "
            f"elevation change {_round(hose.get('elevation_change_ft'))} ft, max grade {_round(hose.get('max_grade'), 4)}"
        )
    return {
        "what": "Selected hydrant",
        "name": props.get("name") or props.get("source") or "hydrant",
        "source": props.get("source"),
        "where": _feature_coord(hydrant) if isinstance(hydrant, dict) else None,
        "why": reasons or ["Reachable hydrant within the hose envelope"],
    }


def _hose_section(plan: dict[str, Any]) -> dict[str, Any]:
    hose = plan.get("hose_route") or {}
    props = hose.get("properties", {}) if isinstance(hose, dict) else {}
    return {
        "what": "Hose route (hydrant → incident)",
        "where": _feature_coord(hose) if isinstance(hose, dict) else None,
        "length_ft": _round(props.get("length_ft")),
        "why": [
            f"Shortest protected road path; {_round(props.get('length_ft'))} ft along the road network",
            f"Curvature {_round(props.get('curvature'), 4)} rad, elevation change "
            f"{_round(props.get('elevation_change_ft'))} ft, max grade {_round(props.get('max_grade'), 4)}",
        ],
    }


def _closure_sections(plan: dict[str, Any]) -> list[dict[str, Any]]:
    closures = plan.get("closures", {}).get("features", [])
    sections: list[dict[str, Any]] = []
    for feature in closures:
        props = feature.get("properties", {})
        road_class = props.get("county_func_class") or props.get("highway") or "unclassified"
        why = [
            "Minimum-cut closure edge that isolates the incident while protecting the hose route",
            f"Traffic/road class: {road_class} (closure cost {_round(props.get('capacity'), 2)})",
            f"Sightline {props.get('sightline')} "
            f"(grade {_round(props.get('grade'), 4)}, elevation change {_round(props.get('elevation_change_m'), 1)} m)",
        ]
        if props.get("deployment_label"):
            why.append(f"Deployment order {props.get('deployment_label')} (stage by traffic exposure × visibility)")
        sections.append(
            {
                "what": f"Road closure (rank {props.get('rank')})",
                "name": props.get("county_st_name") or props.get("name") or "Unnamed road",
                "where": _feature_coord(feature),
                "deployment_label": props.get("deployment_label"),
                "why": why,
            }
        )
    return sections


def _sign_sections(plan: dict[str, Any]) -> list[dict[str, Any]]:
    signs = plan.get("warning_signs", {}).get("features", [])
    sections: list[dict[str, Any]] = []
    for feature in signs:
        props = feature.get("properties", {})
        why = [
            f"{MUTCD_SIGN_REF}; {props.get('road_type')} spacing band "
            f"({_round(props.get('spacing_ft'))} ft, basis: {props.get('road_type_basis')}, "
            f"speed source: {props.get('speed_source')})",
            f"Advance sign {props.get('sequence')} at {_round(props.get('distance_from_closure_ft'))} ft "
            f"upstream of closure rank {props.get('closure_rank')} (side {props.get('closure_side')})",
        ]
        if props.get("placement_status") == "limited":
            why.append(
                f"Placement limited — graph fell {_round(props.get('shortfall_ft'))} ft short "
                f"({props.get('placement_warning')})"
            )
        sections.append(
            {
                "what": f"Advance-warning sign {props.get('mutcd_sign_code')} ({props.get('sign_label')})",
                "name": props.get("approach_road"),
                "where": _feature_coord(feature),
                "deployment_label": props.get("deployment_label"),
                "placement_status": props.get("placement_status"),
                "why": why,
            }
        )
    return sections


def _device_sections(plan: dict[str, Any]) -> list[dict[str, Any]]:
    devices = plan.get("devices", {}).get("features", [])
    sections: list[dict[str, Any]] = []
    for feature in devices:
        props = feature.get("properties", {})
        kind = props.get("kind")
        if kind == "barricade":
            what = f"Type III barricade ({props.get('mutcd_sign_code')} {props.get('sign_label')})"
            why = [MUTCD_BARRICADE_REF, f"Placed at the closure midpoint of {props.get('approach_road')}"]
        else:
            what = "Channelizing device (cone/drum taper)"
            why = [
                MUTCD_TAPER_REF,
                f"Taper {_round(props.get('taper_length_ft'))} ft at {_round(props.get('spacing_ft'))} ft spacing "
                f"(device {props.get('device_index')}/{props.get('device_count')}, "
                f"{_round(props.get('speed_mph'))} mph, speed source: {props.get('speed_source')})",
            ]
        sections.append(
            {
                "what": what,
                "name": props.get("approach_road"),
                "where": _feature_coord(feature),
                "deployment_label": props.get("deployment_label"),
                "why": why,
            }
        )
    return sections


def build_field_report(scenario: Any, plan: dict[str, Any]) -> dict[str, Any]:
    """Build the structured what/where/why report for a planner result.

    ``scenario`` may be a Scenario model, a dict, or None; only its id/name are
    used for the header.
    """
    scenario_id = getattr(scenario, "scenario_id", None)
    name = getattr(scenario, "name", None)
    if isinstance(scenario, dict):
        scenario_id = scenario.get("scenario_id", scenario_id)
        name = scenario.get("name", name)
    return {
        "scenario_id": scenario_id,
        "scenario_name": name,
        "feasible": plan.get("feasible", True),
        "feasibility_note": plan.get("feasibility_note"),
        "hydrant": _hydrant_section(plan),
        "hose": _hose_section(plan),
        "closures": _closure_sections(plan),
        "warning_signs": _sign_sections(plan),
        "devices": _device_sections(plan),
        "mutcd_references": {
            "advance_warning_signs": MUTCD_SIGN_REF,
            "barricade": MUTCD_BARRICADE_REF,
            "channelizing_taper": MUTCD_TAPER_REF,
        },
    }


def _render_item(item: dict[str, Any]) -> list[str]:
    name = item.get("name")
    where = item.get("where")
    head = item.get("what", "")
    if name:
        head += f" — {name}"
    if item.get("deployment_label"):
        head += f" [{item['deployment_label']}]"
    lines = [f"- **{head}**"]
    if where:
        lines.append(f"  - Where: {where}")
    for reason in item.get("why", []):
        lines.append(f"  - Why: {reason}")
    return lines


def _item_html(item: dict[str, Any]) -> str:
    head = html.escape(str(item.get("what", "")))
    if item.get("name"):
        head += f" — {html.escape(str(item['name']))}"
    if item.get("deployment_label"):
        head += f" <span class='badge'>{html.escape(str(item['deployment_label']))}</span>"
    parts = [f"<li><div class='item-head'>{head}</div>"]
    if item.get("where"):
        parts.append(f"<div class='where'>Where: {html.escape(str(item['where']))}</div>")
    whys = "".join(f"<li>{html.escape(str(reason))}</li>" for reason in item.get("why", []))
    if whys:
        parts.append(f"<ul class='why'>{whys}</ul>")
    parts.append("</li>")
    return "".join(parts)


def render_field_report_html(report: dict[str, Any]) -> str:
    """Render the structured report as an HTML fragment (a section with lists),
    suitable for embedding in the run report.html."""
    title = html.escape(str(report.get("scenario_name") or report.get("scenario_id") or "Incident"))
    blocks = [f"<h3>{title} — placement report</h3>"]
    if not report.get("feasible", True):
        blocks.append(
            f"<p class='infeasible'>⚠️ Closure infeasible: {html.escape(str(report.get('feasibility_note')))}</p>"
        )

    def section(name: str, items: list[dict[str, Any]]) -> str:
        body = "".join(_item_html(item) for item in items) or "<li>(none)</li>"
        return f"<h4>{html.escape(name)} ({len(items)})</h4><ul class='report-list'>{body}</ul>"

    blocks.append(
        "<h4>Hydrant &amp; hose</h4><ul class='report-list'>"
        + _item_html(report["hydrant"])
        + _item_html(report["hose"])
        + "</ul>"
    )
    blocks.append(section("Road closures", report["closures"]))
    blocks.append(section("Advance-warning signs", report["warning_signs"]))
    blocks.append(section("Channelizing devices & barricades", report["devices"]))
    refs = "".join(
        f"<li>{html.escape(label.replace('_', ' '))}: {html.escape(str(ref))}</li>"
        for label, ref in report["mutcd_references"].items()
    )
    blocks.append(f"<h4>MUTCD references</h4><ul class='why'>{refs}</ul>")
    return "<section class='field-report'>" + "".join(blocks) + "</section>"


def render_field_report_markdown(report: dict[str, Any]) -> str:
    """Render the structured report as readable Markdown."""
    lines: list[str] = []
    title = report.get("scenario_name") or report.get("scenario_id") or "Incident"
    lines.append(f"# Field placement report — {title}")
    lines.append("")
    lines.append("_What was placed where, and why (road-level naming with MUTCD and "
                 "curvature / traffic / elevation rationale)._")
    lines.append("")
    if not report.get("feasible", True):
        lines.append(f"> ⚠️ **Closure infeasible:** {report.get('feasibility_note')}")
        lines.append("")

    lines.append("## Hydrant & hose")
    lines.extend(_render_item(report["hydrant"]))
    lines.extend(_render_item(report["hose"]))
    lines.append("")

    lines.append(f"## Road closures ({len(report['closures'])})")
    for item in report["closures"]:
        lines.extend(_render_item(item))
    if not report["closures"]:
        lines.append("- (none)")
    lines.append("")

    lines.append(f"## Advance-warning signs ({len(report['warning_signs'])})")
    for item in report["warning_signs"]:
        lines.extend(_render_item(item))
    if not report["warning_signs"]:
        lines.append("- (none)")
    lines.append("")

    lines.append(f"## Channelizing devices & barricades ({len(report['devices'])})")
    for item in report["devices"]:
        lines.extend(_render_item(item))
    if not report["devices"]:
        lines.append("- (none)")
    lines.append("")

    lines.append("## MUTCD references")
    for label, ref in report["mutcd_references"].items():
        lines.append(f"- {label.replace('_', ' ')}: {ref}")
    lines.append("")
    return "\n".join(lines)
