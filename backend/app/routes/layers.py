from fastapi import APIRouter, Query

from app.config import RECONCILED_HYDRANTS_GEOJSON, ROADS_GEOJSON, SOURCES
from app.geojson import read_geojson
from app.services.geocode import geocode
from app.services.hydrants import generate_hydrant_layers
from app.services.roads import generate_road_layers

router = APIRouter(tags=["layers"])


@router.get("/layers/roads")
def roads_layer() -> dict:
    return read_geojson(ROADS_GEOJSON)


@router.get("/layers/hydrants")
def hydrants_layer() -> dict:
    return read_geojson(RECONCILED_HYDRANTS_GEOJSON)


@router.post("/layers/build")
def build_layers(include_graph: bool = Query(default=True)) -> dict:
    return {
        "bbox": SOURCES.bbox_wgs84,
        "roads": generate_road_layers(include_graph=include_graph),
        "hydrants": generate_hydrant_layers(),
    }


@router.get("/geocode")
def geocode_address(q: str) -> list[dict]:
    return [item.model_dump() for item in geocode(q)]
