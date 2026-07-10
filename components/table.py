"""Unified table rendering component.

Replaces all bare `st.dataframe()` calls with a single `render_table()` wrapper
that provides consistent styling, numeric formatting, and optional comparison badges.

Usage:
    from components.table import render_table
    render_table(df, key="campaigns", column_config={
        "Revenue (SAR)": {"format": "%.2f", "unit": "SAR"},
    })
"""
from typing import Any

import pandas as pd
import streamlit as st

from utils import format_metric


def _build_column_config(
    df: pd.DataFrame,
    format_config: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Build Streamlit column_config for numeric columns.

    Args:
        df: DataFrame to display
        format_config: Optional per-column config like
            {"Revenue (SAR)": {"format": "%.2f", "unit": "SAR"}}

    Returns:
        Dict mapping column names to st.column_config objects
    """
    config = {}
    format_config = format_config or {}

    for col in df.columns:
        if pd.api.types.is_numeric_dtype(df[col]):
            fmt_opts = format_config.get(col, {})
            fmt = fmt_opts.get("format", "%.2f")

            config[col] = st.column_config.NumberColumn(
                label=col,
                format=fmt,
            )
        elif pd.api.types.is_datetime64_any_dtype(df[col]):
            config[col] = st.column_config.DatetimeColumn(
                label=col,
                format="MMM DD, YYYY",
            )
    return config


def render_table(
    df: pd.DataFrame,
    key: str | None = None,
    column_config: dict | None = None,
    use_comparison: bool = True,
    height: int = 400,
    use_container_width: bool = True,
    hide_index: bool = True,
    column_order: list[str] | None = None,
) -> None:
    """Render a unified, sort-safe table with consistent styling.

    Args:
        df: DataFrame to display. Must contain only numeric data — no pre-formatted strings.
        key: Streamlit component key (unique per call site).
        column_config: Optional overrides passed through to st.column_config.
        use_comparison: If True and session state has comparison data, show inline deltas.
        height: Table height in px (passed to st.dataframe).
        use_container_width: Stretch to container width.
        hide_index: Hide the DataFrame index column.
        column_order: Optional ordering of columns.
    """
    if column_config is not None:
        resolved_config = column_config
    else:
        resolved_config = _build_column_config(df)

    st.dataframe(
        df,
        column_config=resolved_config,
        hide_index=hide_index,
        height=height,
        use_container_width=use_container_width,
        column_order=column_order,
    )
