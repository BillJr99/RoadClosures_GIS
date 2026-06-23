from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from app.config import MANUAL_HYDRANTS_CSV, ensure_data_dirs
from app.geojson import point_feature, write_geojson
from app.models import ManualHydrant, ManualHydrantIn


FIELDNAMES = [
    "manual_id",
    "name",
    "lat",
    "lon",
    "flow_class",
    "source_note",
    "status",
    "updated_at",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(path: Path | None = None) -> Path:
    return path or MANUAL_HYDRANTS_CSV


def ensure_manual_csv(path: Path | None = None) -> None:
    path = _path(path)
    if path == MANUAL_HYDRANTS_CSV:
        ensure_data_dirs()
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()


def _coerce(row: dict[str, str]) -> ManualHydrant:
    return ManualHydrant(
        manual_id=row["manual_id"],
        name=row.get("name", ""),
        lat=float(row["lat"]),
        lon=float(row["lon"]),
        flow_class=row.get("flow_class") or "unknown",
        source_note=row.get("source_note", ""),
        status=row.get("status") or "active",
        updated_at=row.get("updated_at") or "",
    )


def list_manual_hydrants(path: Path | None = None) -> list[ManualHydrant]:
    path = _path(path)
    ensure_manual_csv(path)
    with path.open("r", newline="", encoding="utf-8") as f:
        return [_coerce(row) for row in csv.DictReader(f) if row.get("manual_id")]


def _write_all(records: list[ManualHydrant], path: Path | None = None) -> None:
    path = _path(path)
    ensure_manual_csv(path)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for rec in records:
            writer.writerow(rec.model_dump())


def add_manual_hydrant(payload: ManualHydrantIn) -> ManualHydrant:
    records = list_manual_hydrants()
    rec = ManualHydrant(manual_id=f"manual-{uuid4().hex[:12]}", updated_at=_now(), **payload.model_dump())
    records.append(rec)
    _write_all(records)
    return rec


def update_manual_hydrant(manual_id: str, payload: ManualHydrantIn) -> ManualHydrant | None:
    records = list_manual_hydrants()
    for idx, rec in enumerate(records):
        if rec.manual_id == manual_id:
            updated = ManualHydrant(manual_id=manual_id, updated_at=_now(), **payload.model_dump())
            records[idx] = updated
            _write_all(records)
            return updated
    return None


def delete_manual_hydrant(manual_id: str) -> bool:
    records = list_manual_hydrants()
    kept = [rec for rec in records if rec.manual_id != manual_id]
    if len(kept) == len(records):
        return False
    _write_all(kept)
    return True


def manual_hydrants_geojson(path: Path) -> dict:
    records = list_manual_hydrants()
    features = [
        point_feature(
            rec.lon,
            rec.lat,
            {
                **rec.model_dump(),
                "source_kind": "manual",
                "source": "manual_csv",
            },
        )
        for rec in records
        if rec.status == "active"
    ]
    return write_geojson(path, features)
