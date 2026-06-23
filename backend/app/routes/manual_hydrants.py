from fastapi import APIRouter, HTTPException, Response

from app.manual_store import (
    add_manual_hydrant,
    delete_manual_hydrant,
    list_manual_hydrants,
    update_manual_hydrant,
)
from app.models import ManualHydrant, ManualHydrantIn

router = APIRouter(tags=["manual hydrants"])


@router.get("/manual-hydrants", response_model=list[ManualHydrant])
def list_manual_hydrant_records() -> list[ManualHydrant]:
    return list_manual_hydrants()


@router.post("/manual-hydrants", response_model=ManualHydrant, status_code=201)
def create_manual_hydrant(payload: ManualHydrantIn) -> ManualHydrant:
    return add_manual_hydrant(payload)


@router.put("/manual-hydrants/{manual_id}", response_model=ManualHydrant)
def replace_manual_hydrant(manual_id: str, payload: ManualHydrantIn) -> ManualHydrant:
    updated = update_manual_hydrant(manual_id, payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Manual hydrant not found")
    return updated


@router.delete("/manual-hydrants/{manual_id}", status_code=204)
def remove_manual_hydrant(manual_id: str) -> Response:
    if not delete_manual_hydrant(manual_id):
        raise HTTPException(status_code=404, detail="Manual hydrant not found")
    return Response(status_code=204)
