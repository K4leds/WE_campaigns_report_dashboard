"""Unified table rendering component, backed by ag-Grid (st_aggrid).

Replaces bare `st.dataframe()` calls with a single `render_table()` wrapper
that provides consistent styling, compact numeric formatting, and optional
comparison-period deltas — all while keeping cells numerically typed so
sorting operates on the real value, not the displayed string.

Usage:
    from components.table import render_table

    # Plain table, auto-detected numeric columns shown compact (e.g. "125.23K")
    render_table(df, key="campaigns")

    # With explicit per-column st.column_config overrides (format string is
    # reused for ag-Grid's printf-style formatting; "compact" is supported)
    render_table(df, key="campaigns", column_config={
        "Revenue (SAR)": st.column_config.NumberColumn(format="compact"),
    })

    # With a comparison period: pass a same-shape `comparison_df` (matched by
    # the `compare_on` key column, e.g. "Channel"). Numeric columns present in
    # both frames render as "125.23K ▲12.0%" while sorting on the raw current
    # value.
    render_table(df, key="channels", comparison_df=prior_period_df, compare_on="Channel")
"""
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import JsCode

from utils import format_metric

# Mirrors utils.format_metric's K/M thresholds so the client-rendered value
# and any server-rendered fallback never disagree.
_COMPACT_FORMATTER_JS = """
function(params) {
    if (params.value === null || params.value === undefined || isNaN(params.value)) {
        return '';
    }
    var value = params.value;
    var abs = Math.abs(value);
    var formatted;
    if (abs >= 1e6) {
        formatted = (value / 1e6).toFixed(2) + 'M';
    } else if (abs >= 1e3) {
        formatted = (value / 1e3).toFixed(2) + 'K';
    } else {
        formatted = value.toLocaleString(undefined, {maximumFractionDigits: 0});
    }
    return formatted;
}
"""

# Renders "<compact current> <arrow><pct>%" using a hidden "<field>__comp"
# column for the comparison value, sorting/filtering still on the visible
# (current) numeric value.
_COMPACT_WITH_DELTA_JS = """
function(params) {
    if (params.value === null || params.value === undefined || isNaN(params.value)) {
        return '';
    }
    var value = params.value;
    var abs = Math.abs(value);
    var formatted;
    if (abs >= 1e6) {
        formatted = (value / 1e6).toFixed(2) + 'M';
    } else if (abs >= 1e3) {
        formatted = (value / 1e3).toFixed(2) + 'K';
    } else {
        formatted = value.toLocaleString(undefined, {maximumFractionDigits: 0});
    }
    var compField = params.colDef.field + '__comp';
    var comp = params.data ? params.data[compField] : undefined;
    if (comp === undefined || comp === null) {
        return formatted;
    }
    if (comp > 0) {
        var pct = ((value - comp) / comp) * 100;
        if (pct > 0) {
            return formatted + ' ▲' + pct.toFixed(1) + '%';
        } else if (pct < 0) {
            return formatted + ' ▼' + Math.abs(pct).toFixed(1) + '%';
        }
        return formatted + ' → 0%';
    } else if (value > 0) {
        return formatted + ' NEW';
    }
    return formatted;
}
"""

# Colors the delta portion green/red to match the dashboard's existing
# up/down convention (previously hand-coded per page as inline HTML spans).
_DELTA_CELL_STYLE_JS = """
function(params) {
    var compField = params.colDef.field + '__comp';
    var comp = params.data ? params.data[compField] : undefined;
    if (comp === undefined || comp === null || params.value === null || params.value === undefined) {
        return null;
    }
    if (comp > 0) {
        var pct = ((params.value - comp) / comp) * 100;
        if (pct > 0) return {color: '#28a745', fontWeight: '600'};
        if (pct < 0) return {color: '#dc3545', fontWeight: '600'};
        return {color: '#6c757d'};
    } else if (params.value > 0) {
        return {color: '#17a2b8', fontWeight: '600'};
    }
    return null;
}
"""

_PERCENT_JS = """
function(params) {
    if (params.value === null || params.value === undefined || isNaN(params.value)) {
        return '';
    }
    return params.value.toFixed(2) + '%';
}
"""


def _column_config_to_aggrid(col_cfg: Any) -> dict:
    """Extract a printf/predefined format string from an st.column_config object.

    st.column_config.NumberColumn(...) returns a plain dict with a
    'type_config' key holding {'type': 'number', 'format': ..., ...}.
    """
    if not isinstance(col_cfg, dict):
        return {}
    type_config = col_cfg.get("type_config", {})
    return {
        "format": type_config.get("format"),
        "label": col_cfg.get("label"),
    }


_TOTAL_ROW_STYLE_JS = JsCode("""
function(params) {
    if (params.node.rowPinned) {
        return {fontWeight: '700', backgroundColor: 'rgba(14, 165, 233, 0.15)', borderTop: '2px solid #0EA5E9'};
    }
    return null;
}
""")


def _build_grid_options(
    df: pd.DataFrame,
    column_config: dict | None,
    comparison_df: pd.DataFrame | None,
    compare_on: str | None,
    height: int,
    column_order: list[str] | None,
    total_row: dict | None,
) -> tuple[pd.DataFrame, dict]:
    column_config = column_config or {}
    display_df = df.copy()

    comp_lookup: dict[str, pd.Series] = {}
    if comparison_df is not None and compare_on and compare_on in df.columns:
        comp_indexed = comparison_df.set_index(compare_on)
        for col in df.columns:
            if col == compare_on:
                continue
            if col in comp_indexed.columns and pd.api.types.is_numeric_dtype(df[col]):
                shadow_col = f"{col}__comp"
                display_df[shadow_col] = display_df[compare_on].map(comp_indexed[col]).astype(float)
                comp_lookup[col] = shadow_col

    gb = GridOptionsBuilder.from_dataframe(display_df)
    gb.configure_default_column(resizable=True, sortable=True, filter=True, minWidth=110)

    for col in df.columns:
        cfg = _column_config_to_aggrid(column_config.get(col))
        fmt = cfg.get("format")
        header_name = cfg.get("label") or col
        is_numeric = pd.api.types.is_numeric_dtype(df[col])

        if not is_numeric:
            gb.configure_column(field=col, header_name=header_name)
            continue

        if col in comp_lookup:
            gb.configure_column(
                field=col,
                header_name=header_name,
                type=["numericColumn"],
                valueFormatter=JsCode(_COMPACT_WITH_DELTA_JS),
                cellStyle=JsCode(_DELTA_CELL_STYLE_JS),
                minWidth=150,
            )
            gb.configure_column(field=comp_lookup[col], hide=True)
        elif fmt == "compact" or fmt is None:
            gb.configure_column(
                field=col,
                header_name=header_name,
                type=["numericColumn"],
                valueFormatter=JsCode(_COMPACT_FORMATTER_JS),
            )
        elif fmt in ("%.2f%%", "percent") or "Rate" in col or "%" in col:
            gb.configure_column(
                field=col,
                header_name=header_name,
                type=["numericColumn"],
                valueFormatter=JsCode(_PERCENT_JS),
            )
        else:
            gb.configure_column(field=col, header_name=header_name, type=["numericColumn"])

    if column_order:
        gb.configure_columns(column_order, hide=False)

    grid_options_kwargs = {"domLayout": "normal" if len(display_df) > 8 else "autoHeight"}
    grid_options_kwargs["getRowStyle"] = _TOTAL_ROW_STYLE_JS

    if total_row is not None:
        pinned_row = {
            k: (float(v) if isinstance(v, (int, float, np.integer, np.floating)) else v)
            for k, v in total_row.items()
        }
        if comp_lookup:
            for col, shadow_col in comp_lookup.items():
                comp_total_key = f"{col}__total_comp"
                if comp_total_key in pinned_row:
                    pinned_row[shadow_col] = pinned_row.pop(comp_total_key)
        grid_options_kwargs["pinnedBottomRowData"] = [pinned_row]

    gb.configure_grid_options(**grid_options_kwargs)
    return display_df, gb.build()


def render_table(
    df: pd.DataFrame,
    key: str | None = None,
    column_config: dict | None = None,
    comparison_df: pd.DataFrame | None = None,
    compare_on: str | None = None,
    height: int = 400,
    use_container_width: bool = True,
    hide_index: bool = True,
    column_order: list[str] | None = None,
    total_row: dict | None = None,
) -> None:
    """Render a unified, sort-safe table with consistent styling via ag-Grid.

    Args:
        df: DataFrame to display. Must contain only numeric data — no pre-formatted strings.
            Do NOT concatenate a manual "Total" row into df — pass it via `total_row` instead,
            so it stays pinned and out of sort/filter.
        key: Streamlit component key (unique per call site).
        column_config: Optional st.column_config overrides (format string honored:
            "compact" renders "125.23K"-style values while keeping the cell numeric for sorting).
        comparison_df: Optional prior-period DataFrame with the same columns as `df`.
            When provided (with `compare_on`), numeric columns render as
            "<compact current> <arrow><pct>%" while still sorting on the current value.
        compare_on: Column name used to match rows between `df` and `comparison_df`
            (e.g. "Channel"). Required if `comparison_df` is provided.
        height: Table height in px.
        use_container_width: Stretch to container width.
        hide_index: Hide the DataFrame index column (index is never included by
            GridOptionsBuilder.from_dataframe when this is True).
        column_order: Optional ordering of columns.
        total_row: Optional dict of {column: value} rendered as a pinned, highlighted
            bottom row (via ag-Grid pinnedBottomRowData) — excluded from sort/filter.
            For comparison columns, also include f"{col}__total_comp" with the prior-period
            total so the pinned row shows a delta too.
    """
    display_df, grid_options = _build_grid_options(
        df, column_config, comparison_df, compare_on, height, column_order, total_row,
    )

    # fit_columns_on_grid_load is intentionally NOT used here: with many columns it
    # compresses everything below a readable width. Columns keep their natural/minWidth
    # size and the grid scrolls horizontally instead (ag-Grid default, matches how wide
    # Streamlit tables already behave in this dashboard).
    AgGrid(
        display_df,
        gridOptions=grid_options,
        height=height,
        allow_unsafe_jscode=True,
        key=key,
    )
