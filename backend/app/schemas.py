from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field, AwareDatetime, model_validator

CLASSES = ["pothole", "longitudinal_crack", "transverse_crack", "alligator_cracking", "rutting", "other"]
DefectClass = Literal["pothole", "longitudinal_crack", "transverse_crack", "alligator_cracking", "rutting", "other"]
Status = Literal["new", "confirmed", "scheduled", "repaired", "rejected"]


class GPSPoint(BaseModel):
    offset_seconds: float = Field(ge=0, le=86400)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    uncertainty_m: float = Field(ge=0, le=10000)


class CaptureMetadata(BaseModel):
    captured_at: AwareDatetime
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    gps_uncertainty_m: float | None = Field(default=None, ge=0, le=10000)
    road_name: str = Field(default="Unassigned road", min_length=1, max_length=120)
    gps_track: list[GPSPoint] = Field(default_factory=list, max_length=10000)

    @model_validator(mode="after")
    def ordered(self):
        offsets = [p.offset_seconds for p in self.gps_track]
        if any(b <= a for a, b in zip(offsets, offsets[1:])):
            raise ValueError("GPS offsets must be strictly increasing")
        return self


class Detection(BaseModel):
    defect_class: DefectClass
    confidence: float = Field(ge=0, le=1)
    bbox: list[float] = Field(min_length=4, max_length=4)
    mask_area_ratio: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def box(self):
        x1, y1, x2, y2 = self.bbox
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("bbox must be normalized xyxy with positive area")
        return self


class InferenceResult(BaseModel):
    detections: list[Detection] = Field(max_length=300)
    model_version: str = Field(max_length=120)
    model_sha256: str
    synthetic: bool
    latency_ms: float = Field(ge=0)
    provenance: dict


class ReviewUpdate(BaseModel):
    status: Status
    critical_location: bool = False
    note: str = Field(default="", max_length=2000)
    revision: int = Field(ge=1)


class MergeRequest(BaseModel):
    target_id: str
    revision: int = Field(ge=1)
    reason: str = Field(min_length=5, max_length=1000)


class NewUser(BaseModel):
    username: str = Field(pattern=r"^[a-zA-Z0-9_.@-]{3,80}$")
    password: str = Field(min_length=12, max_length=128)
    role: Literal["viewer", "inspector", "admin"]


class UserUpdate(BaseModel):
    role: Literal["viewer", "inspector", "admin"]
    enabled: bool


class UserResponse(BaseModel):
    id: str
    username: str
    role: Literal["viewer", "inspector", "admin"]
    enabled: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class JobResponse(BaseModel):
    id: str
    kind: Literal["image", "video"]
    status: Literal["queued", "processing", "completed", "failed"]
    progress: int
    attempts: int
    error: str | None
    created_at: datetime
    completed_at: datetime | None
    inference_ms: float | None
    model_info: dict | None
    road_name: str | None
    sha256: str


class ObservationResponse(BaseModel):
    id: str
    job_id: str
    frame_index: int
    captured_at: datetime
    details: dict


class DefectResponse(BaseModel):
    id: str
    job_id: str
    defect_class: DefectClass
    confidence: float
    bbox: list[float]
    latitude: float
    longitude: float
    gps_uncertainty_m: float
    captured_at: datetime
    severity: float
    explanation: dict
    model_version: str
    synthetic: bool
    road_name: str
    status: Status
    critical_location: bool
    note: str
    revision: int
    duplicate_candidate_id: str | None
    merged_into_id: str | None
    priority: float
    priority_reasons: dict[str, float]
    observations: list[ObservationResponse] | None = None


class DefectPage(BaseModel):
    items: list[DefectResponse]
    total: int
    limit: int
    offset: int


class AnalyticsResponse(BaseModel):
    total: int
    active: int
    synthetic: int
    high_severity: int
    observed_health: float | None
    health_method: str
    by_class: dict[str, int]
    by_status: dict[str, int]
    by_day: dict[str, int]
    priorities: list[DefectResponse]

