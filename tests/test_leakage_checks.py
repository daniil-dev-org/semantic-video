import pytest
from stp.leakage_checks import check_feature_table_leakage, forbid_random_split, LeakageError
import pandas as pd

def test_leakage_check_passes():
    df = pd.DataFrame({
        "collected_at": pd.to_datetime(["2023-01-02", "2023-01-03"]),
        "max_snapshot_used_at": pd.to_datetime(["2023-01-01", "2023-01-02"]),
        "target_window_start_72h": pd.to_datetime(["2023-01-03", "2023-01-04"]),
        "category_percentile": [0.5, 0.6]
    })
    res = check_feature_table_leakage(df)
    assert res["passed"] is True

def test_leakage_check_fails_future_snapshot():
    df = pd.DataFrame({
        "collected_at": pd.to_datetime(["2023-01-02"]),
        "max_snapshot_used_at": pd.to_datetime(["2023-01-03"]), # leakage!
    })
    res = check_feature_table_leakage(df)
    assert res["passed"] is False

def test_forbid_random_split():
    with pytest.raises(LeakageError):
        forbid_random_split({"shuffle": True})
    forbid_random_split({"shuffle": False}) # should pass
