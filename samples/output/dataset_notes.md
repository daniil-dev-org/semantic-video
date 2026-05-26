# Dataset Notes

## 1. YouTube Trending Video Dataset (Kaggle)
- **Source:** Kaggle (`rsrishav/youtube-trending-video-dataset`)
- **Suitability:** 95/100 (Primary Candidate)
- **Description:** Contains daily records of top trending YouTube videos across multiple countries. Perfect for STP because a single video appears on multiple consecutive days, providing a natural temporal snapshot series (collected_at = trending_date).
- **Limitations:** Only daily granularity. Does not include actual video files (must be downloaded separately if needed, though STP can run in metadata-only mode).

## 2. KuaiRand / KuaiRec
- **Source:** Academic Releases (Kuaishou)
- **Suitability:** 75/100 (Usable for validation)
- **Description:** Extremely detailed, millisecond-level interaction logs for short-form videos. Excellent for temporal dynamics and ranking.
- **Limitations:** These are recommendation logs, not public trend metrics (like global views/likes). Requires heavy aggregation to convert interactions into synthetic "snapshots" of views over time.

## 3. Meta Content Library
- **Source:** Meta API
- **Suitability:** 65/100 (Access-Gated)
- **Description:** The ultimate source for Instagram Reels and Facebook video trends.
- **Limitations:** Strictly gated. Requires an approved academic research application. Cannot be used for public/commercial MVP testing.

## 4. TikTok Trending Videos (Kaggle)
- **Source:** Kaggle
- **Suitability:** 45/100 (Schema Test Only)
- **Description:** Contains metadata for TikTok videos.
- **Limitations:** Only provides a single snapshot per video. Since STP requires temporal growth targets (`top_growth_72h`), single-snapshot datasets are unusable for the core pipeline.
