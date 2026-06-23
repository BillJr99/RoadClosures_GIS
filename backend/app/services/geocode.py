from __future__ import annotations

import requests

from app.config import SOURCES
from app.models import GeocodeResult


def geocode(query: str, limit: int = 5) -> list[GeocodeResult]:
    response = requests.get(
        SOURCES.nominatim_url,
        params={
            "q": f"{query}, Montgomery County, Pennsylvania",
            "format": "jsonv2",
            "limit": limit,
            "viewbox": ",".join(str(v) for v in (SOURCES.bbox_wgs84[0], SOURCES.bbox_wgs84[3], SOURCES.bbox_wgs84[2], SOURCES.bbox_wgs84[1])),
            "bounded": 1,
        },
        headers={"User-Agent": "fire-police-gis-cordon-planner/0.1"},
        timeout=15,
    )
    response.raise_for_status()
    return [
        GeocodeResult(label=item.get("display_name", ""), lat=float(item["lat"]), lon=float(item["lon"]))
        for item in response.json()
    ]

