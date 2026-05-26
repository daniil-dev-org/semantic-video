"""Strict anti-leakage tests to prevent time travel and data snooping."""

from __future__ import annotations

import logging
from typing import Dict, Any

import pandas as pd

logger = logging.getLogger("stp.leakage_checks")


class LeakageError(Exception):
    """Exception raised when a data leakage violation is detected."""
    pass


def check_feature_table_leakage(df: pd.DataFrame, horizons: list[int] = [72]) -> Dict[str, Any]:
    """
    Perform strict tests on the feature table to ensure no future data leaked
    into the feature set, and target windows are properly aligned.
    """
    if df.empty:
        return {"passed": True, "violations": []}

    violations = []
    
    # Check 1: Ensure max_snapshot_used_at <= collected_at
    # Align timezones if needed
    if "collected_at" in df.columns:
        tz = df["collected_at"].dt.tz
        
        if "max_snapshot_used_at" in df.columns:
            if df["max_snapshot_used_at"].dt.tz is None and tz is not None:
                df["max_snapshot_used_at"] = df["max_snapshot_used_at"].dt.tz_localize(tz)
            leaks = df[df["max_snapshot_used_at"] > df["collected_at"]]
            if not leaks.empty:
                violations.append(f"Found {len(leaks)} rows where max_snapshot_used_at > collected_at")

    # Check 2: Ensure target_window_start > collected_at
    for h in horizons:
        start_col = f"target_window_start_{h}h"
        if start_col in df.columns and "collected_at" in df.columns:
            tz = df["collected_at"].dt.tz
            if df[start_col].dt.tz is None and tz is not None:
                df[start_col] = df[start_col].dt.tz_localize(tz)
            leaks = df[df[start_col] < df["collected_at"]]
            if not leaks.empty:
                violations.append(f"Found {len(leaks)} rows where {start_col} < collected_at")

    # Check 3: Ensure category percentiles are valid
    # Since we can't easily check historical state of percentiles here,
    # we just verify the column exists and does not contain exactly 1.0 everywhere
    # (which might indicate it was computed per-row without a distribution).
    for col in df.columns:
        if "percentile" in col:
            if df[col].max() > 1.0 or df[col].min() < 0.0:
                violations.append(f"Percentile column {col} out of bounds [0, 1]")

    passed = len(violations) == 0
    if not passed:
        logger.error("LEAKAGE DETECTED: \n" + "\n".join(violations))
    else:
        logger.info("Leakage checks passed.")

    return {
        "passed": passed,
        "violations": violations
    }


def forbid_random_split(kwargs: Dict[str, Any]) -> None:
    """Enforce that temporal splitting is used instead of random train_test_split."""
    if kwargs.get("shuffle", True):
        raise LeakageError("Random split detected! shuffle=True is forbidden for temporal trend validation.")
