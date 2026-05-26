# STP Validation Report
**Generated:** 2026-05-25 07:56:48 UTC

## 1. Executive Summary

> [!CAUTION]
> **Data is real, but insufficient for strong conclusions.**
> Several data quality thresholds were not met.

- **Total Hypotheses:** 2
- **Accepted:** 0
- **Rejected:** 0
- **Inconclusive:** 2
- **Discovery Only:** 0

## 2. Dataset Validity
- **Dataset Mode:** REAL
- **Prediction Validity:** REAL

## 3. Data Coverage
- **Posts:** 100
- **Snapshots:** 1000
- **Days Covered:** 17
- **Median Snapshots/Post:** 10.0

**Failed Thresholds:**
- days_covered (17 < 30)
- posts_count (100 < 1000)
- snapshots_count (1000 < 3000)

## 4. Leakage Check
**Status:** ✅ PASSED

## 5. Model Comparison
| Model | Precision@50 | Lift |
|---|---|---|

## 6. Video Feature Contribution
**Incremental Lift from Video Features:** 1.0000x
> [!WARNING]
> Video sidecar features did not add meaningful predictive lift over metadata-only model.

## 7. Hypothesis Results
### h_001: High motion videos grow faster
- **Verdict:** ❓ **INCONCLUSIVE**
- **Reason:** No valid walk-forward windows
- **Rolling Lift:** 0.0000
- **Rolling P@50:** 0.0000
- **Holdout Lift:** 0.0000

### h_002: High comments growth correlate with breakout
- **Verdict:** ❓ **INCONCLUSIVE**
- **Reason:** No valid walk-forward windows
- **Rolling Lift:** 0.0000
- **Rolling P@50:** 0.0000
- **Holdout Lift:** 1.0000

## 8. Multiple Testing Warnings
- **Exploratory Tests:** 0

## 9. Limitations
- This is a technical Proof of Concept.
- Features are bounded by what is visible in 144p proxies.

## 10. Next Actions
- Replace synthetic data with a real dataset.
- Run `run_import_dataset.py` with the appropriate adapter.