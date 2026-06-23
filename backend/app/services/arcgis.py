from __future__ import annotations

from typing import Any

import requests


def request_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    timeout: int = 60,
    session: requests.Session | None = None,
) -> dict[str, Any]:
    requester = session.get if session else requests.get
    response = requester(url, params=params, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError(f"Expected JSON object from {url}")
    return payload


def layer_info(layer_url: str, session: requests.Session | None = None) -> dict[str, Any]:
    return request_json(layer_url, {"f": "json"}, session=session)


def fetch_geojson_features(
    layer_url: str,
    *,
    bbox: tuple[float, float, float, float],
    out_fields: str = "*",
    where: str = "1=1",
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    west, south, east, north = bbox
    query_url = f"{layer_url}/query"
    info = layer_info(layer_url, session=session)
    page_size = int(info.get("maxRecordCount") or 2000)
    count_payload = request_json(
        query_url,
        {
            "geometry": f"{west},{south},{east},{north}",
            "geometryType": "esriGeometryEnvelope",
            "inSR": 4326,
            "spatialRel": "esriSpatialRelIntersects",
            "where": where,
            "returnCountOnly": "true",
            "f": "json",
        },
        session=session,
    )
    total = int(count_payload.get("count") or 0)
    features: list[dict[str, Any]] = []
    for offset in range(0, max(total, 1), page_size):
        payload = request_json(
            query_url,
            {
                "geometry": f"{west},{south},{east},{north}",
                "geometryType": "esriGeometryEnvelope",
                "inSR": 4326,
                "spatialRel": "esriSpatialRelIntersects",
                "where": where,
                "outFields": out_fields,
                "outSR": 4326,
                "f": "geojson",
                "orderByFields": "OBJECTID",
                "resultOffset": offset,
                "resultRecordCount": page_size,
            },
            session=session,
        )
        if "error" in payload:
            raise RuntimeError(f"ArcGIS query failed for {layer_url}: {payload['error']}")
        if payload.get("type") != "FeatureCollection":
            raise RuntimeError(f"ArcGIS query did not return GeoJSON for {layer_url}: {str(payload)[:300]}")
        page = payload.get("features") or []
        if not page:
            break
        features.extend(page)
    return features
