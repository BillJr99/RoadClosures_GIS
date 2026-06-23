from __future__ import annotations

import math
from typing import Any

import requests

from app.config import SOURCES, AUTHORITATIVE_HYDRANTS_GEOJSON, MANUAL_HYDRANTS_GEOJSON, RECONCILED_HYDRANTS_GEOJSON
from app.geojson import point_feature, write_geojson
from app.manual_store import manual_hydrants_geojson
from app.services.arcgis import fetch_geojson_features, layer_info


DEDUP_TOLERANCE_DEG = 0.0001


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def fetch_osm_hydrants(
    bbox: tuple[float, float, float, float] = SOURCES.bbox_wgs84,
    *,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    west, south, east, north = bbox
    query = (
        "[out:json];"
        f'node["emergency"="fire_hydrant"]({south},{west},{north},{east});'
        "out;"
    )
    requester = session.post if session else requests.post
    response = requester(SOURCES.overpass_url, data={"data": query}, timeout=90)
    response.raise_for_status()
    elements = response.json().get("elements", [])
    features: list[dict[str, Any]] = []
    for el in elements:
        tags = el.get("tags", {})
        lat = float(el["lat"])
        lon = float(el["lon"])
        features.append(
            point_feature(
                lon,
                lat,
                {
                    "source_kind": "authoritative",
                    "source": "OSM",
                    "source_id": str(el.get("id", "")),
                    "name": "",
                    "flow_class": _clean(tags.get("colour")) or "unknown",
                    "type": _clean(tags.get("fire_hydrant:type")),
                    "water_source": _clean(tags.get("water_source")),
                },
            )
        )
    return features


def _arcgis_point_from_feature(feature: dict[str, Any]) -> tuple[float, float] | None:
    geom = feature.get("geometry") or {}
    if geom.get("type") == "Point":
        coords = geom.get("coordinates") or []
        if len(coords) >= 2:
            return float(coords[0]), float(coords[1])
    return None


def fetch_npwa_hydrants(
    bbox: tuple[float, float, float, float] = SOURCES.bbox_wgs84,
    *,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for layer_id, label in SOURCES.npwa_hydrant_layers:
        layer_url = f"{SOURCES.npwa_mapserver_base}/{layer_id}"
        try:
            info = layer_info(layer_url, session=session)
            if info.get("type") == "Group Layer":
                for sub in info.get("subLayers", []):
                    sub_url = f"{SOURCES.npwa_mapserver_base}/{sub['id']}"
                    features.extend(_fetch_arcgis_hydrant_layer(sub_url, f"{label}:{sub.get('name', sub['id'])}", bbox, session))
            else:
                features.extend(_fetch_arcgis_hydrant_layer(layer_url, label, bbox, session))
        except Exception:
            continue
    return features


def _fetch_arcgis_hydrant_layer(
    layer_url: str,
    label: str,
    bbox: tuple[float, float, float, float],
    session: requests.Session | None,
) -> list[dict[str, Any]]:
    try:
        raw = fetch_geojson_features(layer_url, bbox=bbox, out_fields="*", session=session)
    except Exception:
        return []
    features: list[dict[str, Any]] = []
    for feature in raw:
        point = _arcgis_point_from_feature(feature)
        if point is None:
            continue
        lon, lat = point
        props = feature.get("properties") or {}
        source_id = props.get("OBJECTID") or props.get("FID") or props.get("ID") or ""
        features.append(
            point_feature(
                lon,
                lat,
                {
                    "source_kind": "authoritative",
                    "source": label,
                    "source_id": str(source_id),
                    "name": _clean(props.get("NAME") or props.get("HYD_ID") or props.get("ID")),
                    "flow_class": _clean(props.get("FLOW_CLASS")) or "unknown",
                    "type": _clean(props.get("TYPE")),
                    "water_source": _clean(props.get("OWNER") or props.get("AUTHORITY")),
                },
            )
        )
    return features


def _feature_point(feature: dict[str, Any]) -> tuple[float, float]:
    coords = feature["geometry"]["coordinates"]
    return float(coords[0]), float(coords[1])


def _near(a: dict[str, Any], b: dict[str, Any], tolerance: float = DEDUP_TOLERANCE_DEG) -> bool:
    ax, ay = _feature_point(a)
    bx, by = _feature_point(b)
    return math.hypot(ax - bx, ay - by) <= tolerance


def reconcile_hydrants(authoritative: list[dict[str, Any]], manual: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reconciled: list[dict[str, Any]] = []
    for feature in authoritative:
        out = dict(feature)
        out["properties"] = {**feature.get("properties", {}), "reconciled_sources": [feature["properties"].get("source")]}
        reconciled.append(out)
    for feature in manual:
        duplicate_idx = next((idx for idx, existing in enumerate(reconciled) if _near(feature, existing)), None)
        if duplicate_idx is None:
            out = dict(feature)
            out["properties"] = {**feature.get("properties", {}), "reconciled_sources": ["manual_csv"]}
            reconciled.append(out)
        else:
            existing = reconciled[duplicate_idx]
            sources = list(existing["properties"].get("reconciled_sources") or [])
            sources.append("manual_csv")
            existing["properties"] = {
                **existing["properties"],
                "manual_match_id": feature["properties"].get("manual_id"),
                "reconciled_sources": sorted(set(sources)),
            }
    return reconciled


def generate_hydrant_layers(bbox: tuple[float, float, float, float] = SOURCES.bbox_wgs84) -> dict[str, int]:
    with requests.Session() as session:
        authoritative = fetch_npwa_hydrants(bbox, session=session) + fetch_osm_hydrants(bbox, session=session)
    write_geojson(AUTHORITATIVE_HYDRANTS_GEOJSON, authoritative)
    manual_payload = manual_hydrants_geojson(MANUAL_HYDRANTS_GEOJSON)
    manual = manual_payload["features"]
    reconciled = reconcile_hydrants(authoritative, manual)
    write_geojson(RECONCILED_HYDRANTS_GEOJSON, reconciled)
    return {
        "authoritative": len(authoritative),
        "manual": len(manual),
        "reconciled": len(reconciled),
    }

