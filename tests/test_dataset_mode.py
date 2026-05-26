import pytest
from stp.data_quality import determine_dataset_mode, DatasetMode
import pandas as pd

def test_determine_synthetic():
    df = pd.DataFrame({"is_synthetic": [True, True]})
    assert determine_dataset_mode(df) == DatasetMode.SYNTHETIC

def test_determine_real():
    df = pd.DataFrame({"is_synthetic": [False, False]})
    assert determine_dataset_mode(df) == DatasetMode.REAL

def test_determine_mixed():
    df = pd.DataFrame({"is_synthetic": [True, False]})
    assert determine_dataset_mode(df) == DatasetMode.MIXED
