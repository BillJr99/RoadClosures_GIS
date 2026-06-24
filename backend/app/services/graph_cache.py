from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.config import GRAPH_CACHE_DIR, ensure_data_dirs
from app.models import IncidentPlanRequest


GRAPH_CACHE_VERSION = "v1"
FT_TO_M = 1.0 / 3.28084


def graph_cache_key(req: IncidentPlanRequest, network_type: str = "drive") -> str:
    payload = {
        "version": GRAPH_CACHE_VERSION,
        "lat": round(req.lat, 4),
        "lon": round(req.lon, 4),
        "study_radius_ft": round(req.study_radius_ft),
        "network_type": network_type,
    }
    digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:12]
    return f"{payload['version']}-{network_type}-{digest}"


def graph_cache_paths(key: str) -> tuple[Path, Path]:
    return GRAPH_CACHE_DIR / f"{key}.graphml", GRAPH_CACHE_DIR / f"{key}.json"


def graph_radius_m(req: IncidentPlanRequest) -> float:
    return max(req.study_radius_ft * FT_TO_M, 500.0)


def load_or_fetch_graph(
    req: IncidentPlanRequest,
    *,
    fetcher: Callable[[IncidentPlanRequest, float, str], Any] | None = None,
    network_type: str = "drive",
) -> tuple[Any, dict[str, Any]]:
    import osmnx as ox

    ensure_data_dirs()
    key = graph_cache_key(req, network_type=network_type)
    graph_path, meta_path = graph_cache_paths(key)
    if graph_path.exists():
        graph = ox.load_graphml(graph_path)
        metadata = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
        metadata.update({"cache_hit": True, "cache_key": key, "graph_path": str(graph_path)})
        return graph, metadata

    radius_m = graph_radius_m(req)
    if fetcher is None:
        graph = ox.graph_from_point((req.lat, req.lon), dist=radius_m, network_type=network_type, simplify=True)
        graph = ox.project_graph(graph)
    else:
        graph = fetcher(req, radius_m, network_type)

    ox.save_graphml(graph, filepath=graph_path)
    metadata = {
        "cache_hit": False,
        "cache_key": key,
        "graph_path": str(graph_path),
        "source": "OSMnx/OpenStreetMap incident-local graph cache",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "center": {"lat": req.lat, "lon": req.lon},
        "radius_m": radius_m,
        "network_type": network_type,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "crs": str(graph.graph.get("crs")),
    }
    meta_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return graph, metadata

