# Semantic Trend PoC (STP v0.1)

Semantic Trend PoC provides an offline framework to test whether temporal metadata signals and low-cost video sidecar features produce measurable lift over baselines on historical data.

> **Disclaimer:** Semantic Trend PoC does not claim to predict trends out of the box. It is an **offline validation MVP** designed to answer the question: *Do these features actually add predictive value for this specific dataset?*

## Architecture & Workflow

The pipeline consists of isolated CLI steps that can be run on historical datasets:

1. **Proxy Extraction** (`run_proxy_encode.py`): Compresses videos to extremely lightweight 144p/5fps proxies. *Proxies are for algorithmic analysis, not human viewing.*
2. **Feature Extraction** (`run_extract_features.py`): Runs OpenCV-based visual metrics on the proxy to generate an `STP-0.1` sidecar JSON.
3. **Dataset Import** (`run_import_dataset.py`): Imports historical snapshots from Kaggle or generic CSVs.
4. **Dataset Builder** (`run_build_dataset.py`): Merges snapshots and sidecars into a strict anti-leakage `as_of_time` feature table.
5. **Trend Scoring** (`run_score_trends.py`): Runs baseline heuristics and HistGradientBoosting to test feature contribution.
6. **Hypothesis Validation** (`run_validate_hypothesis.py`): Executes a strict temporal walk-forward backtest and final holdout to validate trend hypotheses.

## Datasets

The system distinguishes between dataset modes:
- **Synthetic (Demo):** Used to verify pipeline mechanics. Results are marked as `DEMO_ONLY`.
- **Real:** Used for actual hypothesis testing. Requires minimum coverage thresholds.

### Minimum real dataset requirements
To achieve an `ACCEPTED` verdict on a trend hypothesis, your dataset must meet these thresholds (configurable in `config.yaml`):
- **Duration:** 30–90 days minimum
- **Posts:** 1000+ posts minimum (10,000+ recommended)
- **Snapshots:** 3+ snapshots per post minimum (8–20 recommended)
- **Positives:** Minimum 100 positive target cases for the ML model

Without meeting these, hypotheses will be marked as `INCONCLUSIVE` or `PARTIAL`.

### Recommended first real datasets
You can use `run_import_dataset.py` to import known datasets:
- **YouTube Trending Kaggle Dataset:** Use `--source youtube_trending`
- **Generic CSV:** Use `--source generic_csv` with a `mapping.yaml`

We do not download these automatically. You must procure them yourself.

## Hypothesis Validation Engine

STP uses strict time-based splits:
- **Anti-Leakage Checks:** Enforces that no future data is used in current features. Random shuffles are forbidden.
- **Rolling Walk-Forward:** Tests the model continuously across multiple rolling windows.
- **Final Holdout:** Reserves the last 30% of the timeline as an untouched validation set.
- **Feature Contribution Test:** Compares ML models with metadata only, video features only, and both, calculating incremental lift to prove the sidecar's utility.

## Running the Demo

To test the mechanical pipeline with synthetic data:
```bash
python run_demo.py
```
This generates fake videos, fake growth data, and a full Markdown validation report.

## Using Real Data

1. Import your dataset:
```bash
python run_import_dataset.py --source generic_csv --input my_data.csv --mapping config/mapping.yaml --output samples/input/metadata_snapshots.csv
```
2. Place videos in `samples/input/videos/`
3. Define your hypotheses in `samples/input/hypotheses.yaml`
4. Run the individual CLI scripts in sequence, or use `run_demo.py` to run them all automatically.
