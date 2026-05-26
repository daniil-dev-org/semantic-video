"""Hypothesis registry — tracks exploratory vs preregistered status."""

from __future__ import annotations

import logging

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .hypothesis import HypothesisSpec

logger = logging.getLogger("stp.hypothesis_registry")


def get_hypothesis_status(hyp: HypothesisSpec, dataset_passed_thresholds: bool) -> str:
    """Determine the validation status for the hypothesis based on its flags."""
    if not hyp.preregistered or hyp.exploratory:
        return "DISCOVERY_ONLY"
    
    if not dataset_passed_thresholds:
        return "PARTIAL"
        
    return "ACCEPTED"
