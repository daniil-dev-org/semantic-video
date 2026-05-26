"""Video feature extraction  -  rich metrics from proxy frames via OpenCV."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .config import VideoFeaturesConfig

logger = logging.getLogger("stp.video_features")


# ── Data classes ──

@dataclass
class FaceDetection:
    """Detected face with normalised bounding box [x, y, w, h] in 0..1."""
    bbox: list[float]
    confidence: float
    track_id: str = "face_001"


@dataclass
class FrameMetrics:
    """Rich metrics extracted from a single sampled frame."""
    timestamp_ms: int
    frame_index: int
    brightness: float
    contrast: float
    saturation: float
    motion_score: float
    cut: bool
    blur_score: float
    sharpness_score: float
    dominant_color: list[int]          # [B, G, R] or [R, G, B]
    face_detected: bool
    face_bbox: Optional[list[float]]   # [x, y, w, h] normalised, or None
    faces: list[FaceDetection] = field(default_factory=list)
    edge_density: float = 0.0
    text_like_region_ratio: float = 0.0


# ── Face detection ──

class HaarFaceDetector:
    """OpenCV Haar Cascade  -  always available."""

    def __init__(self, min_confidence: float = 0.5):
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(cascade_path)
        self._min_confidence = min_confidence
        if self._cascade.empty():
            raise RuntimeError(f"Failed to load Haar cascade from {cascade_path}")
        logger.info("Initialized Haar Cascade face detector")

    def detect(self, frame: np.ndarray) -> list[FaceDetection]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape[:2]
        detections = self._cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(int(w * 0.05), int(h * 0.05)),
        )
        faces: list[FaceDetection] = []
        for i, (fx, fy, fw, fh) in enumerate(detections):
            bbox = [
                round(fx / w, 4),
                round(fy / h, 4),
                round(fw / w, 4),
                round(fh / h, 4),
            ]
            faces.append(FaceDetection(
                bbox=bbox,
                confidence=0.8,
                track_id=f"face_{i + 1:03d}",
            ))
        return faces


def create_face_detector(cfg: VideoFeaturesConfig):
    """Create face detector based on config."""
    return HaarFaceDetector(cfg.min_face_confidence)


# ── Per-frame metric functions ──

def compute_brightness(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return round(float(gray.mean()) / 255.0, 4)


def compute_contrast(frame: np.ndarray) -> float:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return round(float(gray.std()) / 128.0, 4)


def compute_saturation(frame: np.ndarray) -> float:
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    return round(float(hsv[:, :, 1].mean()) / 255.0, 4)


def compute_motion_score(prev: np.ndarray, curr: np.ndarray) -> float:
    prev_gray = cv2.cvtColor(prev, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(curr, cv2.COLOR_BGR2GRAY)
    diff = cv2.absdiff(prev_gray, curr_gray)
    return round(float(diff.mean()) / 255.0, 4)


def compute_blur_score(frame: np.ndarray) -> float:
    """Variance of Laplacian  -  lower = blurrier."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    lap = cv2.Laplacian(gray, cv2.CV_64F)
    var = float(lap.var())
    # Normalise: typical range 0-2000+, map to 0-1 roughly
    return round(min(var / 1000.0, 1.0), 4)


def compute_sharpness_score(frame: np.ndarray) -> float:
    """Sharpness = inverse of blur.  High = sharp."""
    return compute_blur_score(frame)


def compute_dominant_color(frame: np.ndarray, k: int = 1) -> list[int]:
    """Find dominant colour using k-means on a small sample."""
    pixels = frame.reshape(-1, 3).astype(np.float32)
    # Subsample for speed
    if len(pixels) > 5000:
        indices = np.random.choice(len(pixels), 5000, replace=False)
        pixels = pixels[indices]
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, _, centers = cv2.kmeans(pixels, k, None, criteria, 3, cv2.KMEANS_RANDOM_CENTERS)
    dominant = centers[0].astype(int).tolist()  # BGR
    return dominant


def compute_color_histogram(frame: np.ndarray, bins: int = 16) -> list[list[float]]:
    """Compute normalised colour histogram per channel (BGR)."""
    histograms = []
    for ch in range(3):
        hist = cv2.calcHist([frame], [ch], None, [bins], [0, 256])
        hist = (hist / hist.sum()).flatten().tolist()
        histograms.append([round(v, 4) for v in hist])
    return histograms


def compute_edge_density(frame: np.ndarray) -> float:
    """Compute ratio of edge pixels using Canny edge detection."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 100, 200)
    density = np.count_nonzero(edges) / (edges.shape[0] * edges.shape[1])
    return round(float(density), 4)


def compute_text_like_regions(frame: np.ndarray) -> float:
    """Estimate text-like regions using Sobel gradients and thresholding."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    sobel_x = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
    sobel_y = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
    gradient_mag = np.sqrt(sobel_x**2 + sobel_y**2)
    # High frequency gradients often indicate text
    text_like = np.count_nonzero(gradient_mag > 150) / (gray.shape[0] * gray.shape[1])
    return round(float(text_like), 4)


# ── Main extraction ──

def extract_features(
    video_path: Path,
    cfg: VideoFeaturesConfig,
    source_fps: float,
    duration_ms: int,
) -> list[FrameMetrics]:
    """
    Extract rich per-frame metrics from sparse-sampled frames.

    Returns list of FrameMetrics, one per sampled frame.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {video_path}")

    detector = create_face_detector(cfg) if cfg.enable_face_detection else None

    frame_interval = max(1, int(round(source_fps / cfg.sample_fps)))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

    logger.info(
        "Extracting features: %d total frames, sampling every %d (~%d fps)",
        total_frames, frame_interval, cfg.sample_fps,
    )

    results: list[FrameMetrics] = []
    prev_frame: Optional[np.ndarray] = None
    frame_idx = 0
    sampled = 0

    try:
        from tqdm import tqdm
        pbar = tqdm(
            total=max(1, total_frames // frame_interval),
            desc="Extracting features",
            unit="frame",
        )
    except ImportError:
        pbar = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % frame_interval == 0:
            h, w = frame.shape[:2]
            scale = cfg.analysis_width / w if w > 0 else 1.0
            analysis_frame = cv2.resize(
                frame,
                (cfg.analysis_width, max(1, int(h * scale))),
                interpolation=cv2.INTER_AREA,
            )

            timestamp_ms = int((frame_idx / source_fps) * 1000) if source_fps > 0 else 0
            brightness = compute_brightness(analysis_frame)
            contrast = compute_contrast(analysis_frame)
            saturation = compute_saturation(analysis_frame)

            # Motion & cut
            motion = 0.0
            is_cut = False
            if prev_frame is not None:
                motion = compute_motion_score(prev_frame, analysis_frame)
                is_cut = motion > cfg.scene_cut_threshold

            blur = compute_blur_score(analysis_frame)
            sharpness = compute_sharpness_score(analysis_frame)
            dominant = compute_dominant_color(analysis_frame)
            
            edge_density = 0.0
            if getattr(cfg, "enable_edge_density", False):
                edge_density = compute_edge_density(analysis_frame)
                
            text_like = 0.0
            if getattr(cfg, "enable_text_like_regions", False):
                text_like = compute_text_like_regions(analysis_frame)

            # Face detection
            faces: list[FaceDetection] = []
            face_detected = False
            face_bbox: Optional[list[float]] = None
            if detector is not None:
                faces = detector.detect(analysis_frame)
                if faces:
                    face_detected = True
                    face_bbox = faces[0].bbox

            results.append(FrameMetrics(
                timestamp_ms=timestamp_ms,
                frame_index=frame_idx,
                brightness=brightness,
                contrast=contrast,
                saturation=saturation,
                motion_score=motion,
                cut=is_cut,
                blur_score=blur,
                sharpness_score=sharpness,
                dominant_color=dominant,
                face_detected=face_detected,
                face_bbox=face_bbox,
                faces=faces,
                edge_density=edge_density,
                text_like_region_ratio=text_like,
            ))

            prev_frame = analysis_frame.copy()
            sampled += 1
            if pbar:
                pbar.update(1)

        frame_idx += 1

    if pbar:
        pbar.close()
    cap.release()

    logger.info("Extracted features from %d sampled frames", sampled)
    return results


def select_keyframes(
    metrics: list[FrameMetrics],
    count: int = 5,
) -> list[int]:
    """
    Select *count* keyframe indices  -  evenly spaced with bias
    towards scene cuts and high-motion frames.
    """
    if not metrics:
        return []

    # Prioritise cuts
    cut_indices = [i for i, m in enumerate(metrics) if m.cut]
    # Evenly spaced fallback
    step = max(1, len(metrics) // count)
    even = list(range(0, len(metrics), step))[:count]

    # Merge: cuts first, fill with evenly spaced
    selected = list(dict.fromkeys(cut_indices[:count] + even))[:count]
    selected.sort()
    return selected


def save_keyframes(
    video_path: Path,
    metrics: list[FrameMetrics],
    keyframe_indices: list[int],
    output_dir: Path,
    source_fps: float,
) -> list[Path]:
    """Extract and save keyframe images from the video."""
    output_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video for keyframes: {video_path}")

    saved: list[Path] = []
    for ki in keyframe_indices:
        if ki >= len(metrics):
            continue
        frame_idx = metrics[ki].frame_index
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        if not ret:
            continue
        fname = output_dir / f"frame_{ki + 1:06d}.jpg"
        cv2.imwrite(str(fname), frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        saved.append(fname)

    cap.release()
    logger.info("Saved %d keyframes to %s", len(saved), output_dir)
    return saved
