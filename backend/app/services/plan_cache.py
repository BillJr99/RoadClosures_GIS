from __future__ import annotations

import hashlib
import json
from typing import Any

from app import config


def plan_cache_key(request_dump: dict[str, Any], graph_fingerprint: str) -> str:
    """Stable key for a plan result.

    Depends only on the planner inputs (request parameters), the graph the plan
    was computed over (its fingerprint), and the cache version, so the same
    incident over the same graph returns an identical, instantly-loaded result.
    """
    payload = {
        "version": config.PLAN_CACHE_VERSION,
        "request": request_dump,
        "graph": graph_fingerprint,
    }
    blob = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def graph_fingerprint(graph: Any) -> str:
    """Cheap content signature for a graph (node/edge counts + CRS)."""
    try:
        crs = str(graph.graph.get("crs"))
    except Exception:
        crs = ""
    return f"{graph.number_of_nodes()}:{graph.number_of_edges()}:{crs}"


def load_cached_plan(key: str) -> dict[str, Any] | None:
    path = config.PLAN_CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def save_cached_plan(key: str, result: dict[str, Any]) -> None:
    config.PLAN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = config.PLAN_CACHE_DIR / f"{key}.json"
    try:
        path.write_text(json.dumps(result, default=str))
    except Exception:
        # Caching is best-effort; never fail a plan because the cache write did.
        pass
