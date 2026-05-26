"""Hypothesis definition  -  YAML schema and loader."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger("stp.hypothesis")


class FilterCondition(BaseModel):
    op: str                # ">", ">=", "<", "<=", "==", "!="
    value: float


class TargetDefinition(BaseModel):
    name: str = "top_growth_72h"
    metric: str = "views_growth_percentile_within_category"
    op: str = ">="
    value: float = 0.90


class BaselineDefinition(BaseModel):
    type: str = "category_matched_random"


class SuccessCriteria(BaseModel):
    min_sample_size: int = 100
    min_lift: float = 1.2
    min_precision_at_50: float = 0.25


class HypothesisSpec(BaseModel):
    """Single hypothesis specification from hypotheses.yaml."""
    hypothesis_id: str
    name: str
    entity_type: str = "post"
    filter: dict[str, FilterCondition] = Field(default_factory=dict)
    signal_window_hours: int = 24
    prediction_horizon_hours: int = 72
    target: TargetDefinition = Field(default_factory=TargetDefinition)
    baseline: BaselineDefinition = Field(default_factory=BaselineDefinition)
    success_criteria: SuccessCriteria = Field(default_factory=SuccessCriteria)
    
    # Registry metadata
    preregistered: bool = False
    exploratory: bool = True
    created_at: str = ""
    owner: str = "local_poc"
    notes: str = ""


class HypothesesConfig(BaseModel):
    """Top-level hypotheses.yaml schema."""
    hypotheses: list[HypothesisSpec] = Field(default_factory=list)


def load_hypotheses(path: Path) -> list[HypothesisSpec]:
    """Load hypotheses from YAML file."""
    if not path.exists():
        raise FileNotFoundError(f"Hypotheses file not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}

    config = HypothesesConfig(**raw)
    logger.info("Loaded %d hypotheses from %s", len(config.hypotheses), path)
    return config.hypotheses


def apply_filter(
    df,  # pd.DataFrame
    filter_spec: dict[str, FilterCondition],
) -> "pd.Series":
    """
    Apply hypothesis filter conditions to a DataFrame.

    Returns boolean mask.
    """
    import pandas as pd

    mask = pd.Series(True, index=df.index)
    for col, cond in filter_spec.items():
        if col not in df.columns:
            logger.warning("Filter column '%s' not found in DataFrame  -  skipping", col)
            continue
        series = df[col].fillna(0)
        if cond.op == ">":
            mask &= series > cond.value
        elif cond.op == ">=":
            mask &= series >= cond.value
        elif cond.op == "<":
            mask &= series < cond.value
        elif cond.op == "<=":
            mask &= series <= cond.value
        elif cond.op == "==":
            mask &= series == cond.value
        elif cond.op == "!=":
            mask &= series != cond.value
        else:
            logger.warning("Unknown filter op '%s'  -  skipping", cond.op)

    return mask
