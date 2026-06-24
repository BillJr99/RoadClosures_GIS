from __future__ import annotations

from pydantic import BaseModel, Field


class ManualHydrantIn(BaseModel):
    name: str = ""
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    flow_class: str = "unknown"
    source_note: str = ""
    status: str = "active"


class ManualHydrant(ManualHydrantIn):
    manual_id: str
    updated_at: str


class IncidentPlanRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    incident_radius_ft: float = Field(default=300.0, gt=0)
    study_radius_ft: float = Field(default=2500.0, gt=0)
    hose_max_ft: float = Field(default=500.0, gt=0)
    incident_class: str = "minor"
    hydrant_count: int = Field(default=1, ge=1, le=4)
    secondary_incidents: list["IncidentPoint"] = Field(default_factory=list)
    sign_max_distance_ft: float = Field(default=1500.0, gt=0)


class IncidentPoint(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class GeocodeResult(BaseModel):
    label: str
    lat: float
    lon: float


class ScenarioIn(BaseModel):
    name: str
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    incident_radius_ft: float = Field(default=300.0, gt=0)
    study_radius_ft: float = Field(default=2500.0, gt=0)
    hose_max_ft: float = Field(default=500.0, gt=0)
    reviewer_notes: str = ""
    expected_hydrant_hint: str = ""
    expected_closure_hint: str = ""
    status: str = "active"


class Scenario(ScenarioIn):
    scenario_id: str
    updated_at: str


class ScenarioGoldenHydrant(BaseModel):
    name: str = ""
    source: str = ""
    source_id: str = ""
    notes: str = ""


class ScenarioGoldenClosure(BaseModel):
    road: str = ""
    reason: str = ""
    notes: str = ""


class ScenarioGoldenWarningSign(BaseModel):
    road: str = ""
    sign_label: str = ""
    distance_ft: float | None = None
    notes: str = ""


class ScenarioGoldenIn(BaseModel):
    reviewer: str = ""
    reviewed_at: str = ""
    expected_hydrant: ScenarioGoldenHydrant = Field(default_factory=ScenarioGoldenHydrant)
    expected_closures: list[ScenarioGoldenClosure] = Field(default_factory=list)
    expected_warning_signs: list[ScenarioGoldenWarningSign] = Field(default_factory=list)
    notes: str = ""


class ScenarioGolden(ScenarioGoldenIn):
    scenario_id: str
    updated_at: str = ""


class ScenarioRunSummary(BaseModel):
    scenario_id: str
    name: str
    status: str
    output_path: str | None = None
    golden_status: str = "missing"
    differences: list[str] = []
    error: str | None = None
