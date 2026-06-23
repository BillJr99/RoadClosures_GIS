from fastapi import APIRouter

router = APIRouter(tags=["layers"])


@router.get("/layers/roads")
def roads_layer() -> dict:
    return {"type": "FeatureCollection", "features": []}


@router.get("/layers/hydrants")
def hydrants_layer() -> dict:
    return {"type": "FeatureCollection", "features": []}

