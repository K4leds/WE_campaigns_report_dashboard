"""Unified table rendering component, backed by ag-Grid (st_aggrid).

Replaces bare `st.dataframe()` calls with a single `render_table()` wrapper
that provides consistent styling, compact numeric formatting, and optional
comparison-period deltas — all while keeping cells numerically typed so
sorting operates on the real value, not the displayed string.

Usage:
    from components.table import render_table

    # Plain table, auto-detected numeric columns shown compact (e.g. "125.23K")
    render_table(df, key="campaigns")

    # With explicit per-column st.column_config overrides. Supported `format`
    # values: "compact" (K/M abbreviation), "%.2f%%"/"percent" (or any column
    # whose name contains "Rate"/"%"), and printf-style decimal formats like
    # "%.1f", "%+.2f", "%.2f SAR" (see _printf_js_formatter). Anything else
    # renders as a plain, unformatted numeric column.
    render_table(df, key="campaigns", column_config={
        "Revenue (SAR)": st.column_config.NumberColumn(format="compact"),
    })

    # With a comparison period: pass a same-shape `comparison_df` (matched by
    # the `compare_on` key column, e.g. "Channel"). Numeric columns present in
    # both frames render as "125.23K ▲12.0%" while sorting on the raw current
    # value.
    render_table(df, key="channels", comparison_df=prior_period_df, compare_on="Channel")
"""
import re
from typing import Any

import numpy as np
import pandas as pd
import streamlit as st
from st_aggrid import AgGrid, GridOptionsBuilder
from st_aggrid.shared import GridUpdateMode, JsCode, StAggridTheme

from config import PALETTE
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
# Hexes mirror config.COLORS success/danger/muted/info.
_DELTA_CELL_STYLE_JS = """
function(params) {
    var compField = params.colDef.field + '__comp';
    var comp = params.data ? params.data[compField] : undefined;
    if (comp === undefined || comp === null || params.value === null || params.value === undefined) {
        return null;
    }
    if (comp > 0) {
        var pct = ((params.value - comp) / comp) * 100;
        if (pct > 0) return {color: '#22C55E', fontWeight: '600'};
        if (pct < 0) return {color: '#EF4444', fontWeight: '600'};
        return {color: '#6B7280'};
    } else if (params.value > 0) {
        return {color: '#6366F1', fontWeight: '600'};
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

# Matches printf-style decimal formats like '%.1f', '%+.2f', '%.2f%%', '%.2f SAR'
_PRINTF_RE = re.compile(r'^%(?P<sign>\+)?\.(?P<prec>\d+)f(?P<suffix>.*)$')


def _printf_js_formatter(fmt: str) -> str | None:
    """Build a JS valueFormatter for a printf-style decimal format string.

    Handles the common '%.Nf'-family formats used across the dashboard's
    column_config calls (e.g. '%.1f', '%.2f SAR', '%+.2f') that aren't
    "compact" or the dedicated percent format. Returns None if `fmt` doesn't
    match, so the caller can fall back to an unformatted numeric column.
    """
    m = _PRINTF_RE.match(fmt)
    if not m:
        return None
    prec = int(m.group('prec'))
    suffix = m.group('suffix').replace('%%', '%')
    sign_prefix = "(value >= 0 ? '+' : '') + " if m.group('sign') else ""
    suffix_js = f" + {suffix!r}" if suffix else ""
    return f"""
function(params) {{
    if (params.value === null || params.value === undefined || isNaN(params.value)) {{
        return '';
    }}
    var value = params.value;
    return {sign_prefix}value.toFixed({prec}){suffix_js};
}}
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
        return {
            fontWeight: '700',
            backgroundColor: 'rgba(14, 165, 233, 0.22)',
            color: '#0EA5E9',
            borderTop: '2px solid #0EA5E9',
        };
    }
    return null;
}
""")


def _get_aggrid_theme() -> StAggridTheme:
    """Builds an ag-Grid theme from the dashboard's own light/dark palette
    (config.PALETTE) so tables read as part of the same design system instead
    of ag-Grid's default green-accented "streamlit" theme.
    """
    is_dark = getattr(getattr(st.context, "theme", None), "type", "dark") == "dark"
    p = PALETTE["dark" if is_dark else "light"]
    return StAggridTheme(base="balham").withParams(
        backgroundColor=p["surface"],
        foregroundColor=p["text"],
        headerBackgroundColor=p["background"],
        headerTextColor=p["text_muted"],
        borderColor=p["border"],
        oddRowBackgroundColor=p["background"],
        accentColor=p["primary"],
        rowHoverColor="rgba(14, 165, 233, 0.10)",
        selectedRowBackgroundColor="rgba(14, 165, 233, 0.18)",
        fontFamily="Inter, Segoe UI, Roboto, sans-serif",
    )


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
    gb.configure_default_column(
        resizable=True, sortable=True, filter=True, minWidth=110,
        wrapHeaderText=True,
    )

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
            printf_js = _printf_js_formatter(fmt) if fmt else None
            if printf_js:
                gb.configure_column(
                    field=col,
                    header_name=header_name,
                    type=["numericColumn"],
                    valueFormatter=JsCode(printf_js),
                )
            else:
                gb.configure_column(field=col, header_name=header_name, type=["numericColumn"])

    if column_order:
        gb.configure_columns(column_order, hide=False)

    grid_options_kwargs = {"domLayout": "normal" if len(display_df) > 8 else "autoHeight"}
    grid_options_kwargs["getRowStyle"] = _TOTAL_ROW_STYLE_JS
    # Lets users click-drag to select and copy cell text like a normal table
    # (ag-Grid's own cell selection otherwise intercepts the mouse instead).
    grid_options_kwargs["enableCellTextSelection"] = True
    grid_options_kwargs["ensureDomOrder"] = True
    # Multi-line headers: wrap long column names (e.g. "Impression-Through Revenue (SAR)")
    # instead of requiring wide columns. ag-Grid computes header height automatically.
    grid_options_kwargs["autoHeaderHeight"] = True

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


def render_ai_explain(df: pd.DataFrame, key: str, ai_label: str | None = None, help_text: str = "Explain this with AI") -> None:
    """Small, tertiary "explain" popover, lazily evaluated: the DeepSeek call only
    fires once the popover is actually opened (on_change="rerun" + .open), so it
    costs nothing until a user deliberately asks for it, and is cached per
    table/chart content afterward. Renders nothing if no DEEPSEEK_API_KEY is
    configured.

    Reused both internally by render_table() and directly by pages that want the
    same affordance next to a chart -- always pass the chart's *source* DataFrame
    (e.g. the per-channel data feeding a bar chart), never a rendered image.
    """
    import llm_narrative

    if not llm_narrative.is_configured():
        return

    label = ai_label or key
    pop = st.popover(
        "✨",
        help=help_text,
        type="tertiary",
        on_change="rerun",
        key=f"{key}__ai_explain_popover",
    )
    if pop.open:
        with pop:
            with st.spinner("Thinking through the numbers..."):
                fact_sheet = llm_narrative.build_table_fact_sheet(df, label)
                insights = llm_narrative.explain_table_data(fact_sheet, label)
            if insights:
                st.markdown(insights)
            else:
                st.caption("AI insights aren't available right now.")


def render_chart(fig, df: pd.DataFrame, key: str, ai_label: str | None = None, **plotly_kwargs) -> None:
    """st.plotly_chart() plus two popovers above the chart: "📋" showing the
    chart's source data as a table (the Vega-editor-style "view data" affordance
    Plotly lacks natively), and the same "✨ Explain" popover used by
    render_table(). `df` must be the chart's *source* data (whatever DataFrame
    was passed to px.bar/px.line/etc.), never the figure itself --
    explain_table_data() reasons over those already-computed numbers, not pixels.
    """
    _, data_col, explain_col = st.columns([10, 1, 1])
    with data_col:
        with st.popover("📋", help="View the data behind this chart", type="tertiary"):
            st.dataframe(df, hide_index=True)
    with explain_col:
        render_ai_explain(df, key, ai_label, help_text="Explain this chart with AI")
    st.plotly_chart(fig, **plotly_kwargs)


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
    enable_ai_explain: bool = True,
    ai_label: str | None = None,
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
        enable_ai_explain: Show a small "✨ Explain" popover that generates on-demand
            AI insights for this table (only when DEEPSEEK_API_KEY is configured —
            otherwise the control doesn't render at all). Set False to opt a table out.
        ai_label: Human-readable name for this table, used in the AI prompt and to
            key the popover. Defaults to `key`.
    """
    if enable_ai_explain:
        _, explain_col = st.columns([8, 1])
        with explain_col:
            render_ai_explain(df, key or ai_label or "this table", ai_label, help_text="Explain this table with AI")

    display_df, grid_options = _build_grid_options(
        df, column_config, comparison_df, compare_on, height, column_order, total_row,
    )

    # fit_columns_on_grid_load is intentionally NOT used here: with many columns it
    # compresses everything below a readable width. Columns keep their natural/minWidth
    # size and the grid scrolls horizontally instead (ag-Grid default, matches how wide
    # Streamlit tables already behave in this dashboard).
    #
    # Stamp the ag-Grid key with a short hash of the column names. When attribution
    # settings change, column names change (e.g. "Unique Conversions" → "Click-Through
    # Conversions"), and ag-Grid needs a fresh component instance — otherwise it tries
    # to update columns in-place and renders blank cells for the renamed columns.
    import hashlib
    cols_fingerprint = hashlib.md5(",".join(df.columns).encode()).hexdigest()[:8]
    # Data fingerprint: row count + head/tail sample. Ensures ag-Grid gets a
    # fresh component when filter changes don't rename columns but change data.
    n_rows = len(df)
    if n_rows > 0:
        sample = df.head(min(3, n_rows)).to_json() + df.tail(min(2, n_rows)).to_json()
    else:
        sample = ""
    data_fp = hashlib.md5(f"{n_rows}|{sample}".encode()).hexdigest()[:8]
    stamped_key = f"{key}_c_{cols_fingerprint}_d_{data_fp}"
    AgGrid(
        display_df,
        gridOptions=grid_options,
        height=height,
        allow_unsafe_jscode=True,
        key=stamped_key,
        # Forces st_aggrid's JSON serialization path instead of its default pyarrow/Arrow
        # IPC path. With this pandas/pyarrow version, string columns serialize as Arrow's
        # LargeUtf8 type, which the frontend's bundled arrow-js decoder doesn't recognize
        # ("Unrecognized type: LargeUtf8 (20)") -- the grid iframe loads, then silently
        # renders nothing. st_aggrid's own auto-fallback only catches *Python-side* pyarrow
        # errors, not this client-side decode failure, so it must be forced explicitly.
        use_json_serialization=True,
        # update_mode=NO_UPDATE alone does nothing: st_aggrid's update_on defaults to
        # ["cellValueChanged", "selectionChanged", "filterChanged", "sortChanged"] and the
        # library only *adds* to that list for other update_mode values, never clears it for
        # NO_UPDATE. Without update_on=[] here, every client-side sort/filter click still
        # reports back to Streamlit and triggers a full script rerun.
        update_mode=GridUpdateMode.NO_UPDATE,
        update_on=[],
        theme=_get_aggrid_theme(),
    )
