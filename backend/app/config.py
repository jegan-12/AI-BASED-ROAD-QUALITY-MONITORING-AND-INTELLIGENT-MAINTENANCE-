from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, Field


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "sqlite:///./data/roadscope.db"
    jwt_secret: str = ""
    internal_api_key: str = ""
    media_dir: Path = Path("data/media")
    inference_url: str = "http://inference:8001"
    inference_mode: str = "disabled"
    model_card: Path = Path("models/model-card.json")
    calibration_path: Path | None = None
    demo_mode: bool = False
    access_token_minutes: int = 30
    max_upload_mb: int = 100
    max_video_seconds: int = 300
    max_frames: int = 150
    frame_interval_seconds: float = Field(default=2.0, gt=0, le=60)
    confidence_threshold: float = Field(default=0.35, ge=0, le=1)
    nms_iou: float = Field(default=0.5, gt=0, le=1)
    cors_origins: str = "http://localhost:5173,http://localhost:8080"

    @field_validator("calibration_path", mode="before")
    @classmethod
    def empty_path(cls, value):
        return None if value == "" else value

    def validate_secrets(self):
        if len(self.jwt_secret) < 32 or len(self.internal_api_key) < 32:
            raise RuntimeError("Set JWT_SECRET and INTERNAL_API_KEY to independent random values >=32 characters")
        if self.inference_mode == "demo" and not self.demo_mode:
            raise RuntimeError("Synthetic inference requires DEMO_MODE=true")


@lru_cache
def settings():
    return Settings()

