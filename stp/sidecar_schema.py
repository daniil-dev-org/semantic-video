"""STP-0.1 sidecar schema  -  Pydantic models for video_metrics_sidecar.json."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from dataclasses import asdict

from pydantic import BaseModel, Field

from .video_features import FrameMetrics
from .ffmpeg_tools import VideoMeta
from .config import ProxyConfig, VideoFeaturesConfig
from .utils import sha256_file

logger = logging.getLogger("stp.sidecar_schema")


# ── Nested models ──

class AssetInfo(BaseModel):
    asset_id: str
    source_name: str
    duration_ms: int = 0
    source_width: int = 0
    source_height: int = 0
    source_fps: float = 0.0


class ProxyStreamInfo(BaseModel):
    uri: str = "proxy_144p.mp4"
    codec: str = "h264"
    height: int = 144
    fps: int = 5
    purpose: str = "feature_extraction"


class TimebaseInfo(BaseModel):
    unit: str = "ms"


class GlobalFeatures(BaseModel):
    duration_ms: int = 0
    sampled_frames: int = 0
    avg_brightness: float = 0.0
    std_brightness: float = 0.0
    avg_contrast: float = 0.0
    std_contrast: float = 0.0
    avg_saturation: float = 0.0
    std_saturation: float = 0.0
    avg_motion_score: float = 0.0
    max_motion_score: float = 0.0
    cut_count: int = 0
    cuts_per_second: float = 0.0
    visual_change_score: float = 0.0
    dominant_colors: list[list[int]] = Field(default_factory=list)
    face_presence_ratio: float = 0.0
    person_presence_ratio: Optional[float] = None   # reserved
    text_region_ratio: Optional[float] = None        # reserved
    blur_score_avg: float = 0.0
    sharpness_score_avg: float = 0.0
    edge_density_avg: float = 0.0
    text_like_region_ratio: float = 0.0
    
    # Hook features
    hook_motion_0_1s: float = 0.0
    hook_motion_0_3s: float = 0.0
    hook_motion_0_5s: float = 0.0
    hook_cut_count_0_3s: int = 0
    hook_brightness_delta_0_3s: float = 0.0
    hook_saturation_delta_0_3s: float = 0.0
    first_second_visual_change: float = 0.0
    
    # Shot length
    avg_shot_length_sec: float = 0.0
    median_shot_length_sec: float = 0.0
    min_shot_length_sec: float = 0.0
    max_shot_length_sec: float = 0.0


class TimelineItem(BaseModel):
    t: int
    brightness: float = 0.0
    contrast: float = 0.0
    saturation: float = 0.0
    motion_score: float = 0.0
    cut: bool = False
    blur_score: float = 0.0
    dominant_color: list[int] = Field(default_factory=lambda: [0, 0, 0])
    face_detected: bool = False
    face_bbox: Optional[list[float]] = None
    edge_density: float = 0.0
    text_like_region_ratio: float = 0.0


class KeyframeItem(BaseModel):
    index: int
    t: int
    filename: str


class VideoFeatures(BaseModel):
    """Top-level video_features block of the sidecar."""
    global_features: GlobalFeatures = Field(
        default_factory=GlobalFeatures, alias="global"
    )
    timeline: list[TimelineItem] = Field(default_factory=list)
    keyframes: list[KeyframeItem] = Field(default_factory=list)
    visual_tokens: list[Any] = Field(default_factory=list)     # reserved
    detectors: list[Any] = Field(default_factory=list)          # reserved

    model_config = {"populate_by_name": True}


class IntegrityInfo(BaseModel):
    source_sha256: str = ""
    proxy_sha256: str = ""
    sidecar_sha256: str = ""


class SidecarDocument(BaseModel):
    """Full STP v0.1 sidecar document."""
    stp_version: str = "0.1"
    profile: str = "offline_trend_poc"
    created_at: str = ""
    asset: AssetInfo
    proxy_stream: ProxyStreamInfo = Field(default_factory=ProxyStreamInfo)
    timebase: TimebaseInfo = Field(default_factory=TimebaseInfo)
    video_features: VideoFeatures = Field(default_factory=VideoFeatures)
    integrity: IntegrityInfo = Field(default_factory=IntegrityInfo)


# ── Builder ──

def build_sidecar(
    asset_id: str,
    source_name: str,
    meta: VideoMeta,
    metrics: list[FrameMetrics],
    proxy_cfg: ProxyConfig,
    feat_cfg: VideoFeaturesConfig,
    keyframe_files: list[Path] | None = None,
) -> SidecarDocument:
    """Build SidecarDocument from extracted metrics."""
    import numpy as _np

    asset = AssetInfo(
        asset_id=asset_id,
        source_name=source_name,
        duration_ms=meta.duration_ms,
        source_width=meta.width,
        source_height=meta.height,
        source_fps=meta.fps,
    )

    proxy_stream = ProxyStreamInfo(
        codec="h264",
        height=proxy_cfg.height,
        fps=proxy_cfg.fps,
    )

    # ── Global features ──
    n = len(metrics)
    if n == 0:
        gf = GlobalFeatures(duration_ms=meta.duration_ms)
    else:
        brightnesses = [m.brightness for m in metrics]
        contrasts = [m.contrast for m in metrics]
        saturations = [m.saturation for m in metrics]
        motions = [m.motion_score for m in metrics]
        blurs = [m.blur_score for m in metrics]
        sharps = [m.sharpness_score for m in metrics]
        edges = [m.edge_density for m in metrics]
        texts = [m.text_like_region_ratio for m in metrics]
        cuts = [m for m in metrics if m.cut]
        face_frames = [m for m in metrics if m.face_detected]

        duration_sec = meta.duration_ms / 1000.0 if meta.duration_ms > 0 else 1.0

        # Hook features (0-1s, 0-3s, 0-5s)
        hook_1s_metrics = [m for m in metrics if m.timestamp_ms <= 1000]
        hook_3s_metrics = [m for m in metrics if m.timestamp_ms <= 3000]
        hook_5s_metrics = [m for m in metrics if m.timestamp_ms <= 5000]

        hook_motion_0_1s = float(_np.mean([m.motion_score for m in hook_1s_metrics])) if hook_1s_metrics else 0.0
        hook_motion_0_3s = float(_np.mean([m.motion_score for m in hook_3s_metrics])) if hook_3s_metrics else 0.0
        hook_motion_0_5s = float(_np.mean([m.motion_score for m in hook_5s_metrics])) if hook_5s_metrics else 0.0
        hook_cut_count_0_3s = len([m for m in hook_3s_metrics if m.cut])
        
        hook_brightness_delta = 0.0
        hook_saturation_delta = 0.0
        if hook_3s_metrics:
            hook_brightness_delta = float(max(m.brightness for m in hook_3s_metrics) - min(m.brightness for m in hook_3s_metrics))
            hook_saturation_delta = float(max(m.saturation for m in hook_3s_metrics) - min(m.saturation for m in hook_3s_metrics))

        first_sec_change = 0.0
        if len(hook_1s_metrics) > 1:
            first_sec_change = float(_np.mean([abs(hook_1s_metrics[i].brightness - hook_1s_metrics[i-1].brightness) for i in range(1, len(hook_1s_metrics))]))

        # Shot lengths
        shot_lengths = []
        last_cut_t = 0
        for m in metrics:
            if m.cut:
                shot_lengths.append((m.timestamp_ms - last_cut_t) / 1000.0)
                last_cut_t = m.timestamp_ms
        shot_lengths.append((meta.duration_ms - last_cut_t) / 1000.0)
        
        avg_shot_length = float(_np.mean(shot_lengths)) if shot_lengths else duration_sec
        median_shot_length = float(_np.median(shot_lengths)) if shot_lengths else duration_sec
        min_shot_length = float(_np.min(shot_lengths)) if shot_lengths else duration_sec
        max_shot_length = float(_np.max(shot_lengths)) if shot_lengths else duration_sec

        # Visual change score: average absolute delta of brightness between consecutive frames
        if n > 1:
            deltas = [abs(brightnesses[i] - brightnesses[i - 1]) for i in range(1, n)]
            visual_change = round(float(_np.mean(deltas)), 4)
        else:
            visual_change = 0.0

        # Dominant colours: top-3 across all frames
        from collections import Counter
        color_buckets = Counter()
        for m in metrics:
            bucket = tuple((c // 32) * 32 for c in m.dominant_color)
            color_buckets[bucket] += 1
        dominant_colors = [list(c) for c, _ in color_buckets.most_common(3)]

        gf = GlobalFeatures(
            duration_ms=meta.duration_ms,
            sampled_frames=n,
            avg_brightness=round(float(_np.mean(brightnesses)), 4),
            std_brightness=round(float(_np.std(brightnesses)), 4),
            avg_contrast=round(float(_np.mean(contrasts)), 4),
            std_contrast=round(float(_np.std(contrasts)), 4),
            avg_saturation=round(float(_np.mean(saturations)), 4),
            std_saturation=round(float(_np.std(saturations)), 4),
            avg_motion_score=round(float(_np.mean(motions)), 4),
            max_motion_score=round(float(max(motions)), 4),
            cut_count=len(cuts),
            cuts_per_second=round(len(cuts) / duration_sec, 4),
            visual_change_score=visual_change,
            dominant_colors=dominant_colors,
            face_presence_ratio=round(len(face_frames) / n, 4),
            blur_score_avg=round(float(_np.mean(blurs)), 4),
            sharpness_score_avg=round(float(_np.mean(sharps)), 4),
            edge_density_avg=round(float(_np.mean(edges)), 4),
            text_like_region_ratio=round(float(_np.mean(texts)), 4),
            hook_motion_0_1s=round(hook_motion_0_1s, 4),
            hook_motion_0_3s=round(hook_motion_0_3s, 4),
            hook_motion_0_5s=round(hook_motion_0_5s, 4),
            hook_cut_count_0_3s=hook_cut_count_0_3s,
            hook_brightness_delta_0_3s=round(hook_brightness_delta, 4),
            hook_saturation_delta_0_3s=round(hook_saturation_delta, 4),
            first_second_visual_change=round(first_sec_change, 4),
            avg_shot_length_sec=round(avg_shot_length, 4),
            median_shot_length_sec=round(median_shot_length, 4),
            min_shot_length_sec=round(min_shot_length, 4),
            max_shot_length_sec=round(max_shot_length, 4),
        )

    # ── Timeline ──
    timeline = [
        TimelineItem(
            t=m.timestamp_ms,
            brightness=m.brightness,
            contrast=m.contrast,
            saturation=m.saturation,
            motion_score=m.motion_score,
            cut=m.cut,
            blur_score=m.blur_score,
            dominant_color=m.dominant_color,
            face_detected=m.face_detected,
            face_bbox=m.face_bbox,
            edge_density=m.edge_density,
            text_like_region_ratio=m.text_like_region_ratio,
        )
        for m in metrics
    ]

    # ── Keyframes ──
    kf_items = []
    if keyframe_files:
        for i, kf_path in enumerate(keyframe_files):
            idx = i
            t = metrics[idx].timestamp_ms if idx < len(metrics) else 0
            kf_items.append(KeyframeItem(
                index=idx,
                t=t,
                filename=kf_path.name,
            ))

    video_features = VideoFeatures(**{
        "global": gf,
        "timeline": timeline,
        "keyframes": kf_items,
        "visual_tokens": [],
        "detectors": [{"name": "opencv_haar", "type": "face"}],
    })

    doc = SidecarDocument(
        created_at=datetime.now(timezone.utc).isoformat(),
        asset=asset,
        proxy_stream=proxy_stream,
        video_features=video_features,
    )
    return doc


# ── IO ──

def save_sidecar(doc: SidecarDocument, path: Path) -> None:
    """Save sidecar document to JSON."""
    data = doc.model_dump(by_alias=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info("Sidecar saved: %s (%.1f KB)", path.name, path.stat().st_size / 1024)


def load_sidecar(path: Path) -> SidecarDocument:
    """Load sidecar document from JSON."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return SidecarDocument(**data)
