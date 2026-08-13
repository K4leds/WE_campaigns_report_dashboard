"""Tests for the unified table component (ag-Grid backed)."""
import sys
from pathlib import Path

# Ensure project root is on sys.path so components can be imported
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import pytest
import pandas as pd
import numpy as np
import streamlit as st
from components.table import render_table, _build_grid_options, _column_config_to_aggrid


class TestColumnConfigToAggrid:
    def test_extracts_format_and_label(self):
        cc = st.column_config.NumberColumn(label="Revenue (SAR)", format="compact")
        result = _column_config_to_aggrid(cc)
        assert result["format"] == "compact"
        assert result["label"] == "Revenue (SAR)"

    def test_non_dict_input_returns_empty(self):
        assert _column_config_to_aggrid(None) == {}
        assert _column_config_to_aggrid("not a config") == {}


class TestBuildGridOptions:
    def test_returns_dataframe_and_dict(self):
        df = pd.DataFrame({"A": [1, 2], "B": [3.0, 4.0]})
        display_df, grid_options = _build_grid_options(df, None, None, None, 400, None, None)
        assert isinstance(display_df, pd.DataFrame)
        assert isinstance(grid_options, dict)

    def test_numeric_columns_get_compact_formatter_by_default(self):
        df = pd.DataFrame({"Revenue (SAR)": [1000.0, 2000.0]})
        _, grid_options = _build_grid_options(df, None, None, None, 400, None, None)
        col_defs = {c["field"]: c for c in grid_options["columnDefs"]}
        assert "valueFormatter" in col_defs["Revenue (SAR)"]

    def test_comparison_df_adds_hidden_shadow_column(self):
        df = pd.DataFrame({"Channel": ["Email"], "Revenue (SAR)": [1000.0]})
        comp_df = pd.DataFrame({"Channel": ["Email"], "Revenue (SAR)": [500.0]})
        display_df, grid_options = _build_grid_options(
            df, None, comp_df, "Channel", 400, None, None
        )
        assert "Revenue (SAR)__comp" in display_df.columns
        col_defs = {c["field"]: c for c in grid_options["columnDefs"]}
        assert col_defs["Revenue (SAR)__comp"]["hide"] is True

    def test_total_row_becomes_pinned_bottom_row(self):
        df = pd.DataFrame({"Channel": ["Email"], "Revenue (SAR)": [1000.0]})
        total_row = {"Channel": "Total", "Revenue (SAR)": 1000.0}
        _, grid_options = _build_grid_options(df, None, None, None, 400, None, total_row)
        assert grid_options["pinnedBottomRowData"] == [total_row]

    def test_total_row_with_numpy_types_is_json_safe(self):
        """numpy int64/float64 in the total row must be cast to plain Python types."""
        df = pd.DataFrame({"Channel": ["Email", "SMS"], "Sent": [10, 20]})
        total_row = {"Channel": "Total", "Sent": df["Sent"].sum()}  # numpy.int64
        _, grid_options = _build_grid_options(df, None, None, None, 400, None, total_row)
        pinned = grid_options["pinnedBottomRowData"][0]
        assert type(pinned["Sent"]) is float

    def test_exact_value_tooltip_is_wired_up(self):
        """Compact cells ("10.34M") must expose the exact number on hover.

        The tooltip lives in defaultColDef so it covers every column of every
        table; the number-vs-string guard is inside the JS itself.
        """
        df = pd.DataFrame({"Channel": ["Email"], "Revenue (SAR)": [10342881.0]})
        _, grid_options = _build_grid_options(df, None, None, None, 400, None, None)
        getter = grid_options["defaultColDef"]["tooltipValueGetter"]
        js = getattr(getter, "js_code", str(getter))
        assert "toLocaleString" in js
        assert "typeof params.value !== 'number'" in js  # no tooltips on text cells
        assert "__comp" in js  # comparison columns also show the prior value
        assert grid_options["enableBrowserTooltips"] is True

    def test_empty_dataframe_does_not_crash(self):
        df = pd.DataFrame()
        display_df, grid_options = _build_grid_options(df, None, None, None, 400, None, None)
        assert isinstance(display_df, pd.DataFrame)
        assert isinstance(grid_options, dict)


class TestRenderTable:
    def test_is_callable(self):
        """render_table should be callable with expected args."""
        assert callable(render_table)
