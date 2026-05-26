"""Configuration loader for STP pipeline."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger("stp.config")

# ── Pydantic config models ──

class ProxyConfig(BaseModel):
    height: int = 144
    fps: int = 5
    codec: str = "libx264"
    crf: int = 38
    preset: str = "veryfast"
    keep_audio: bool = False


class VideoFeaturesConfig(BaseModel):
    sample_fps: int = 5
    keyframe_count: int = 5
    scene_cut_threshold: float = 0.35
    motion_threshold: float = 0.18
    frame_sample_rate: int = 1
    enable_edge_density: bool = True
    enable_text_like_regions: bool = True
    enable_hook_features: bool = True
    enable_color_buckets: bool = True
    enable_visual_tokens: bool = True
    enable_face_detection: bool = True
    min_face_confidence: float = 0.5
    analysis_width: int = 320


class DatasetConfig(BaseModel):
    velocity_windows_hours: list[int] = [1, 6, 24]
    include_audio: bool = True
    include_hashtags: bool = True
    category_percentiles: bool = True


class DataQualityConfig(BaseModel):
    min_days_covered: int = 30
    min_posts: int = 1000
    min_snapshots: int = 3000
    min_median_snapshots_per_post: float = 3.0
    min_positive_cases: int = 100


class ValidationConfig(BaseModel):
    train_window_days: int = 30
    test_horizon_hours: int = 72
    step_days: int = 1
    final_holdout_ratio: float = 0.30
    require_holdout_pass: bool = True
    require_preregistered_for_accept: bool = True


class FeatureGroupsConfig(BaseModel):
    use_metadata_features: bool = True
    use_video_features: bool = True
    use_entity_features: bool = True


class DatasetsConfig(BaseModel):
    normalized_schema_version: str = "0.2"


class ScoringConfig(BaseModel):
    ml_model: str = "hist_gradient_boosting"
    max_iter: int = 100
    learning_rate: float = 0.1


class ReportsConfig(BaseModel):
    include_charts: bool = True
    format: str = "markdown"


class STPConfig(BaseModel):
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    video_features: VideoFeaturesConfig = Field(default_factory=VideoFeaturesConfig)
    dataset: DatasetConfig = Field(default_factory=DatasetConfig)
    data_quality: DataQualityConfig = Field(default_factory=DataQualityConfig)
    validation: ValidationConfig = Field(default_factory=ValidationConfig)
    feature_groups: FeatureGroupsConfig = Field(default_factory=FeatureGroupsConfig)
    datasets_meta: DatasetsConfig = Field(default_factory=DatasetsConfig, alias="datasets")
    scoring: ScoringConfig = Field(default_factory=ScoringConfig)
    reports: ReportsConfig = Field(default_factory=ReportsConfig)


# ── Loader ──

_DEFAULT_CONFIG_PATHS = [
    Path("config.yaml"),
    Path(__file__).parent.parent / "config.yaml",
]


def load_config(path: Optional[Path] = None) -> STPConfig:
    """Load STP config from YAML.  Falls back to defaults if no file found."""
    if path and path.exists():
        return _parse(path)

    for candidate in _DEFAULT_CONFIG_PATHS:
        if candidate.exists():
            return _parse(candidate)

    logger.warning("No config.yaml found  -  using built-in defaults")
    return STPConfig()


def _parse(path: Path) -> STPConfig:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    logger.info("Config loaded from %s", path)
    return STPConfig(**raw)
