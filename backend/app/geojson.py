from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable


def empty_feature_collection() -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": []}


def read_geojson(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty_feature_collection()
    with path.open("r", encoding="utf-8") as f:
        payload = json.load(f)
    if not isinstance(payload, dict) or payload.get("type") != "FeatureCollection":
        raise ValueError(f"{path} is not a GeoJSON FeatureCollection")
    return payload


def write_geojson(path: Path, features: Iterable[dict[str, Any]]) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"type": "FeatureCollection", "features": list(features)}
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f)
    return payload


def point_feature(lon: float, lat: float, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": properties,
    }

def line_feature(coords: list[list[float]], properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "geometry": {"type": "LineString", "coordinates": coords},
        "properties": properties,
    }

