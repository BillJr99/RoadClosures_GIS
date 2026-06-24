from pathlib import Path

from app.manual_store import (
    add_manual_hydrant,
    delete_manual_hydrant,
    ensure_manual_csv,
    list_manual_hydrants,
    update_manual_hydrant,
)
from app.models import ManualHydrantIn


def test_manual_hydrant_csv_round_trip(tmp_path: Path, monkeypatch) -> None:
    csv_path = tmp_path / "manual_hydrants.csv"
    monkeypatch.setattr("app.manual_store.MANUAL_HYDRANTS_CSV", csv_path)
    ensure_manual_csv(csv_path)

    created = add_manual_hydrant(
        ManualHydrantIn(
            name="Test Hydrant",
            lat=40.1,
            lon=-75.2,
            flow_class="green",
            source_note="field note",
            status="active",
        )
    )

    records = list_manual_hydrants(csv_path)
    assert len(records) == 1
    assert records[0].manual_id == created.manual_id
    assert records[0].flow_class == "green"

    updated = update_manual_hydrant(
        created.manual_id,
        ManualHydrantIn(
            name="Updated",
            lat=40.2,
            lon=-75.3,
            flow_class="blue",
            source_note="corrected",
            status="active",
        ),
    )
    assert updated is not None
    assert updated.name == "Updated"
    assert list_manual_hydrants(csv_path)[0].flow_class == "blue"

    assert delete_manual_hydrant(created.manual_id)
    assert list_manual_hydrants(csv_path) == []

