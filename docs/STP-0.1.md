# STP-0.1 — Semantic Trend Protocol

## Overview

**STP-0.1** (Semantic Trend Protocol, version 0.1) is a formalised specification for storing
video-derived metrics alongside metadata snapshots to enable early trend detection and
hypothesis validation.

The protocol defines the structure of **`video_metrics_sidecar.json`** — a compact JSON
document that accompanies a lightweight 144p video proxy and serves as a rich feature source
for trend prediction pipelines.

## Design Principles

1. **Sidecar, not codec** — STP is a metadata protocol, not a video compression format.
2. **Feature-first** — Every field exists to enable downstream ML/analytics.
3. **Temporal safety** — All features must be computable at a known point in time.
4. **Offline-compatible** — No external API calls required for feature extraction.
5. **Extensible** — Reserved fields for future detectors (OCR, object detection).
6. **Integrity** — SHA-256 hashes ensure provenance.

## Document Structure

```json
{
  "stp_version": "0.1",
  "profile": "offline_trend_poc",
  "created_at": "2024-01-15T12:00:00+00:00",
  "asset": { ... },
  "proxy_stream": { ... },
  "timebase": { ... },
  "video_features": {
    "global": { ... },
    "timeline": [ ... ],
    "keyframes": [ ... ],
    "visual_tokens": [],
    "detectors": []
  },
  "integrity": { ... }
}
```

## Sections

### `asset`

Source video identity and metadata.

| Field | Type | Description |
|-------|------|-------------|
| `asset_id` | string | Unique identifier for the video asset |
| `source_name` | string | Original filename |
| `duration_ms` | int | Duration in milliseconds |
| `source_width` | int | Source video width in pixels |
| `source_height` | int | Source video height in pixels |
| `source_fps` | float | Source frame rate |

### `proxy_stream`

Information about the compressed analysis proxy.

| Field | Type | Description |
|-------|------|-------------|
| `uri` | string | Relative path to proxy file |
| `codec` | string | Video codec (e.g. `h264`) |
| `height` | int | Proxy height in pixels |
| `fps` | int | Proxy frame rate |
| `purpose` | string | Always `feature_extraction` |

### `timebase`

Temporal unit specification.

| Field | Type | Description |
|-------|------|-------------|
| `unit` | string | Time unit, always `ms` |

### `video_features.global`

Aggregated metrics across all sampled frames.

| Field | Type | Range | Description |
|-------|------|-------|-------------|
| `duration_ms` | int | ≥0 | Total duration |
| `sampled_frames` | int | ≥0 | Number of frames analysed |
| `avg_brightness` | float | 0–1 | Mean brightness |
| `std_brightness` | float | ≥0 | Brightness standard deviation |
| `avg_contrast` | float | 0–1+ | Mean contrast |
| `std_contrast` | float | ≥0 | Contrast standard deviation |
| `avg_saturation` | float | 0–1 | Mean colour saturation |
| `std_saturation` | float | ≥0 | Saturation standard deviation |
| `avg_motion_score` | float | 0–1 | Mean frame-to-frame motion |
| `max_motion_score` | float | 0–1 | Peak motion score |
| `cut_count` | int | ≥0 | Detected scene cuts |
| `cuts_per_second` | float | ≥0 | Cut frequency |
| `visual_change_score` | float | ≥0 | Average visual delta between frames |
| `dominant_colors` | array | — | Top-3 dominant BGR colour buckets |
| `face_presence_ratio` | float | 0–1 | Fraction of frames with detected faces |
| `person_presence_ratio` | float? | 0–1 | Reserved for person detection |
| `text_like_region_ratio` | float | 0–1 | Ratio of high-frequency edge regions |
| `blur_score_avg` | float | 0–1 | Average blur score (Laplacian variance) |
| `sharpness_score_avg` | float | 0–1 | Average sharpness score |
| `edge_density_avg` | float | 0–1 | Average edge density ratio |
| `hook_motion_0_3s` | float | 0–1 | Motion score in first 3 seconds |
| `hook_cut_count_0_3s` | int | ≥0 | Scene cuts in first 3 seconds |
| `hook_brightness_delta_0_3s` | float | ≥0 | Max brightness delta in first 3 seconds |
| `hook_saturation_delta_0_3s` | float | ≥0 | Max saturation delta in first 3 seconds |
| `first_second_visual_change` | float | ≥0 | Visual change score in first second |
| `avg_shot_length_sec` | float | ≥0 | Mean duration of shots between cuts |
| `median_shot_length_sec` | float | ≥0 | Median shot duration |

### `video_features.timeline`

Per-frame metrics at each sampled timestamp.

```json
{
  "t": 0,
  "brightness": 0.52,
  "contrast": 0.41,
  "saturation": 0.62,
  "motion_score": 0.08,
  "cut": false,
  "blur_score": 0.31,
  "dominant_color": [23, 40, 81],
  "face_detected": true,
  "face_bbox": [0.34, 0.18, 0.22, 0.31],
  "edge_density": 0.12,
  "text_like_region_ratio": 0.05
}
```

**Coordinate system:**
- All bounding boxes use **normalised coordinates** in range `[0.0, 1.0]`.
- Format: `[x, y, w, h]` where `(x, y)` is top-left corner.

### `video_features.keyframes`

Selected representative frames.

| Field | Type | Description |
|-------|------|-------------|
| `index` | int | Keyframe index |
| `t` | int | Timestamp in ms |
| `filename` | string | Saved keyframe filename |

### `video_features.visual_tokens`

*Reserved for v0.2.* Will contain visual embedding tokens.

### `video_features.detectors`

List of detectors used for feature extraction.

```json
[{"name": "opencv_haar", "type": "face"}]
```

### `integrity`

Provenance hashes.

| Field | Type | Description |
|-------|------|-------------|
| `source_sha256` | string | SHA-256 of original video |
| `proxy_sha256` | string | SHA-256 of proxy video |
| `sidecar_sha256` | string | SHA-256 of sidecar JSON itself |

## Versioning

- **0.1** — Initial PoC version. Core metrics, face detection via Haar Cascade.
- **0.2** (planned) — Visual tokens, MediaPipe faces, text/OCR regions.
- **0.3** (planned) — Object detection, audio features, embedding vectors.

## Usage in Trend Prediction

The sidecar is designed as an **additional feature layer** for trend prediction:

1. **Not a standalone predictor** — Video features alone cannot predict trends.
2. **Complementary signal** — Visual patterns (motion, cuts, faces) add signal
   to temporal metadata features (velocity, engagement growth).
3. **Hypothesis-driven** — Specific visual hypotheses (e.g., "high motion correlates
   with virality") can be tested via walk-forward validation.

## Anti-Leakage Contract

When using STP sidecars in ML pipelines:

1. Features extracted from the sidecar are **time-invariant** (computed once at proxy creation).
2. They can safely be joined with any `as_of_time` metadata snapshot.
3. The sidecar itself does **not** contain performance metrics (views, likes, etc.).
4. Temporal targets must be computed separately from future metadata snapshots.
