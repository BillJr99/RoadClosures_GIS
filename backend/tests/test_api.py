from pathlib import Path

import pytest
from fastapi import HTTPException

from app.main import health
from app.models import ManualHydrantIn
from app.routes.manual_hydrants import (
    create_manual_hydrant,
    list_manual_hydrant_records,
    remove_manual_hydrant,
    replace_manual_hydrant,
)


def test_health_route() -> None:
    assert health() == {"status": "ok"}


def test_manual_hydrant_route_crud(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.manual_store.MANUAL_HYDRANTS_CSV", tmp_path / "manual_hydrants.csv")
    payload = ManualHydrantIn(
        name="API Hydrant",
        lat=40.2,
        lon=-75.3,
        flow_class="blue",
        source_note="known local hydrant",
        status="active",
    )

    created = create_manual_hydrant(payload)
    assert created.manual_id.startswith("manual-")
    assert created.name == "API Hydrant"
    assert len(list_manual_hydrant_records()) == 1

    updated = replace_manual_hydrant(
        created.manual_id,
        ManualHydrantIn(
            name="Updated Hydrant",
            lat=40.2,
            lon=-75.3,
            flow_class="green",
            source_note="known local hydrant",
            status="active",
        ),
    )
    assert updated.name == "Updated Hydrant"
    assert updated.flow_class == "green"

    response = remove_manual_hydrant(created.manual_id)
    assert response.status_code == 204
    assert list_manual_hydrant_records() == []


def test_manual_hydrant_route_not_found(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("app.manual_store.MANUAL_HYDRANTS_CSV", tmp_path / "manual_hydrants.csv")
    payload = ManualHydrantIn(
        name="Missing",
        lat=40.0,
        lon=-75.0,
        flow_class="unknown",
        source_note="",
        status="active",
    )
    with pytest.raises(HTTPException) as update_error:
        replace_manual_hydrant("not-real", payload)
    assert update_error.value.status_code == 404

    with pytest.raises(HTTPException) as delete_error:
        remove_manual_hydrant("not-real")
    assert delete_error.value.status_code == 404

