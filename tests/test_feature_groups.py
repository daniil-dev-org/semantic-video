import pytest
from stp.trend_scoring import METADATA_FEATURES, VIDEO_FEATURES

def test_feature_lists():
    assert "views_now" in METADATA_FEATURES
    assert "edge_density_avg" in VIDEO_FEATURES
    assert "hook_motion_0_3s" in VIDEO_FEATURES
    
    # Ensure mutually exclusive
    overlap = set(METADATA_FEATURES).intersection(set(VIDEO_FEATURES))
    assert len(overlap) == 0
