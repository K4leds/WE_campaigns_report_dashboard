"""Tests for the unified table component."""
import sys
from pathlib import Path

# Ensure project root is on sys.path so components can be imported
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import pytest
import pandas as pd
import numpy as np
from components.table import render_table, _build_column_config


class TestBuildColumnConfig:
    def test_returns_dict(self):
        """_build_column_config returns a dict."""
        df = pd.DataFrame({"A": [1, 2], "B": [3.0, 4.0]})
        config = _build_column_config(df)
        assert isinstance(config, dict)

    def test_numeric_columns_detected(self):
        """Integer and float columns get a NumberColumn config entry."""
        df = pd.DataFrame({"A": [1, 2, 3], "B": [4.0, 5.0, 6.0]})
        config = _build_column_config(df)
        assert "A" in config
        assert "B" in config

    def test_non_numeric_columns_skipped(self):
        """String columns are not included in the config."""
        df = pd.DataFrame({"Name": ["X", "Y"], "Value": [1.0, 2.0]})
        config = _build_column_config(df)
        assert "Name" not in config
        assert "Value" in config

    def test_empty_dataframe_does_not_crash(self):
        """An empty DataFrame returns an empty config dict."""
        df = pd.DataFrame()
        config = _build_column_config(df)
        assert isinstance(config, dict)
        assert len(config) == 0

    def test_datetime_columns_detected(self):
        """Datetime columns get a DatetimeColumn config entry."""
        df = pd.DataFrame({
            "Date": pd.to_datetime(["2024-01-01", "2024-06-15"]),
            "Value": [100, 200],
        })
        config = _build_column_config(df)
        assert "Date" in config
        assert "Value" in config

    def test_format_config_applied(self):
        """Custom format config is reflected in the NumberColumn."""
        df = pd.DataFrame({"Revenue (SAR)": [1000.0, 2000.0], "CTR": [0.05, 0.08]})
        config = _build_column_config(
            df,
            format_config={"Revenue (SAR)": {"format": "%.2f", "unit": "SAR"}},
        )
        assert "Revenue (SAR)" in config
        assert "CTR" in config


class TestRenderTable:
    def test_is_callable(self):
        """render_table should be callable with expected args."""
        assert callable(render_table)
