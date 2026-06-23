from fastapi import APIRouter

router = APIRouter(tags=["manual hydrants"])


@router.get("/manual-hydrants")
def list_manual_hydrants() -> list[dict]:
    return []

