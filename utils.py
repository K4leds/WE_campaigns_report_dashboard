"""
Utility functions for formatting, styling, and common operations.
Includes formatting, display helpers, and data transformation utilities.
"""

import streamlit as st
import pandas as pd
import numpy as np
from io import BytesIO, StringIO
import plotly.io as pio
import plotly.graph_objects as go

# Columns that round-trip through `.to_json()`/`read_json()` as epoch-millisecond
# ints rather than real dates -- pandas 3.0 dropped read_json's column-name-based
# date auto-detection, so every @st.cache_data helper that groups/resamples on
# these columns must restore them explicitly after reading the cached JSON back.
_DATE_COLUMNS = ('Reporting Period Start Date', 'Day')


def read_cached_json(json_str: str) -> pd.DataFrame:
    """Reconstructs a DataFrame passed into an `@st.cache_data` function via
    `df.to_json()`. Wraps the string in StringIO (pandas 3.0 removed support for
    passing a literal JSON string directly) and restores known date columns, which
    otherwise come back as plain epoch-millisecond integers.
    """
    df = pd.read_json(StringIO(json_str))
    for col in _DATE_COLUMNS:
        if col in df.columns:
            if pd.api.types.is_numeric_dtype(df[col]):
                df[col] = pd.to_datetime(df[col], unit='ms')
            else:
                df[col] = pd.to_datetime(df[col])
    return df


# Configure Plotly template
def configure_plotly_template(color_sequence, is_dark=False):
    """Configure the default Plotly template for dashboard consistency."""
    text_color = '#F1F5F9' if is_dark else '#1F2937'
    title_color = '#F1F5F9' if is_dark else '#111827'
    grid_color = '#334155' if is_dark else '#F3F4F6'
    line_color = '#475569' if is_dark else '#E5E7EB'
    legend_color = '#94A3B8' if is_dark else '#6B7280'

    _we_template = go.layout.Template()
    _we_template.layout = go.Layout(
        font=dict(family='Inter, Segoe UI, Roboto, sans-serif', size=13, color=text_color),
        title=dict(font=dict(size=18, color=title_color), x=0.02, xanchor='left'),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        colorway=color_sequence,
        xaxis=dict(showgrid=True, gridcolor=grid_color, gridwidth=1, linecolor=line_color, linewidth=1),
        yaxis=dict(gridcolor=grid_color, gridwidth=1, linecolor=line_color, linewidth=1, zerolinecolor=line_color),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1, bgcolor='rgba(0,0,0,0)', font=dict(color=legend_color)),
        margin=dict(l=40, r=20, t=60, b=40),
        hovermode='x unified',
    )
    pio.templates['we_dashboard'] = _we_template
    pio.templates.default = 'we_dashboard'


def format_metric(value, unit="", abbreviate=True):
    """
    Format metric values for display.

    IMPORTANT: This function returns DISPLAY STRINGS and must NEVER be applied
    to DataFrame columns. Use st.column_config.NumberColumn for DataFrame display
    instead, which keeps underlying values numeric for proper sorting.

    Args:
        value: The numeric value to format
        unit: Optional unit label (e.g., "SAR")
        abbreviate: If True, use K/M abbreviations. If False, show full number with commas

    Returns:
        Formatted string representation of the metric, or "N/A" for NaN/None
    """
    if value is None:
        return "N/A"
    if isinstance(value, (int, float, np.integer, np.floating)) and not np.isnan(float(value)):
        if abbreviate:
            abs_val = abs(value)
            if abs_val >= 1e6:
                result = f"{value/1e6:.1f}M"
            elif abs_val >= 1e3:
                result = f"{value/1e3:.1f}K"
            else:
                result = f"{value:,.0f}"
        else:
            result = f"{value:,.0f}"

        if unit:
            return f"{result} {unit}"
        return result
    else:
        return "N/A"


def format_number_with_suffix(value):
    """
    Format a number with K/M suffix for Streamlit column formatting.
    Used as a lambda in st.column_config.NumberColumn formatter.
    
    Args:
        value: The numeric value to format
    
    Returns:
        Formatted string with K/M suffix
    """
    if pd.isna(value):
        return ""
    abs_val = abs(value)
    if abs_val >= 1e6:
        return f"{value/1e6:.1f}M"
    elif abs_val >= 1e3:
        return f"{value/1e3:.1f}K"
    else:
        return f"{value:,.0f}"


def parse_short_number(value):
    """
    Parse a possibly-shortened number string into a float.

    Handles formats like:
      - 54K, 54k, 54.18K
      - 1.2M
      - Arabic abbreviations such as '54 ألف' or '2.5 مليون'
      - plain numeric types (int/float)

    Returns 0.0 for unparseable or NaN-like inputs.
    """
    import re
    import pandas as _pd

    if value is None:
        return 0.0
    # passthrough numeric types
    if isinstance(value, (int, float, np.integer, np.floating)) and not _pd.isna(value):
        return float(value)

    s = str(value).strip()
    if s == '' or s.lower() in {'nan', 'none'}:
        return 0.0

    # Normalize common punctuation
    s = s.replace(',', '').replace('\u00A0', '').replace('\xa0', '')

    # Detect multipliers from suffix text
    multiplier = 1.0
    sl = s.lower()
    # Arabic words
    if 'ألف' in s or 'الف' in s:
        multiplier = 1_000.0
    elif 'مليون' in s or 'ملايين' in s:
        multiplier = 1_000_000.0
    # Latin suffixes
    elif 'k' in sl and 'km' not in sl:
        multiplier = 1_000.0
    elif 'm' in sl:
        multiplier = 1_000_000.0

    # Extract the numeric portion
    m = re.search(r'[-+]?[0-9]*\.?[0-9]+', s)
    if not m:
        return 0.0

    try:
        num = float(m.group())
    except Exception:
        return 0.0

    return num * multiplier


def style_total_row(df):
    """
    Apply bold + light background styling to the last row (Total row) of a DataFrame.
    
    Args:
        df: DataFrame with last row being "Total"
    
    Returns:
        Pandas Styler object suitable for st.dataframe()
    """
    def _highlight_last(row):
        if row.name == len(df) - 1:
            return ['font-weight: bold; background-color: #0EA5E9; color: #FFFFFF'] * len(row)
        return [''] * len(row)
    return df.style.apply(_highlight_last, axis=1)


def export_chart_image(fig, filename='chart', fmt='png', width=1200, height=600):
    """
    Export a Plotly figure as a downloadable image buffer.
    
    Args:
        fig: Plotly figure object
        filename: Name for the exported file
        fmt: Image format ('png', 'jpg', 'pdf')
        width: Image width in pixels
        height: Image height in pixels
    
    Returns:
        BytesIO buffer or None if kaleido is not installed
    """
    try:
        buf = BytesIO()
        fig.write_image(buf, format=fmt, width=width, height=height, scale=2)
        buf.seek(0)
        return buf
    except Exception:
        return None


def month_range_options(start_date, end_date):
    """
    Generate list of month options between start and end dates.
    
    Args:
        start_date: Start date
        end_date: End date
    
    Returns:
        List of datetime objects for each month in range
    """
    if pd.isna(start_date) or pd.isna(end_date):
        return []
    start = pd.Period(pd.to_datetime(start_date), freq='M')
    end = pd.Period(pd.to_datetime(end_date), freq='M')
    months = pd.period_range(start, end, freq='M')
    return [m.to_timestamp() for m in months]


def metric_aggregation_method(metric):
    """
    Determine appropriate aggregation method for a metric (mean vs sum).
    
    Rate/ratio metrics should be averaged, absolute metrics should be summed.
    
    Args:
        metric: Metric name
    
    Returns:
        'mean' for rate/ratio metrics, 'sum' for absolute metrics
    """
    rate_keywords = {'rate', 'ctr', 'roas', 'aov', 'rpc', 'rps', 'engagement rate', 'revenue per'}
    lower = metric.lower()
    if any(kw in lower for kw in rate_keywords):
        return 'mean'
    return 'sum'


def apply_formatting_to_columns(df, columns_by_type):
    """
    Apply type-specific formatting to dataframe columns.
    
    Args:
        df: DataFrame to format
        columns_by_type: Dict with 'numeric', 'currency', 'percentage', 'count' keys
                        mapping to lists of column names
    
    Returns:
        Formatted DataFrame copy
    """
    df_display = df.copy()
    
    # Format count columns
    for col in columns_by_type.get('count', []):
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(format_metric)
    
    # Format currency columns
    for col in columns_by_type.get('currency', []):
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(lambda x: format_metric(x, "SAR"))
    
    # Format percentage columns
    for col in columns_by_type.get('percentage', []):
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(lambda x: f"{x:.2%}")
    
    # Format numeric columns
    for col in columns_by_type.get('numeric', []):
        if col in df_display.columns:
            df_display[col] = df_display[col].apply(lambda x: f"{x:.2f}")
    
    return df_display


def render_kpi_card(
    label: str,
    value: str,
    delta: str | None = None,
    icon: str | None = None,
    progress: float | None = None,
    help_text: str | None = None,
    use_container_width: bool = True,
) -> None:
    """Render a styled KPI metric card with optional icon, delta badge, and progress bar."""
    card_html = '<div style="background: var(--st-secondary-background-color, #1E293B); border-radius: 8px; padding: 16px; margin-bottom: 8px; border: 1px solid var(--st-border-color, #334155);">'

    if icon:
        card_html += f'<div style="font-size: 24px; margin-bottom: 4px;">{icon}</div>'

    card_html += f'<div style="font-size: 13px; color: var(--st-text-muted, #94A3B8); margin-bottom: 4px;">{label}</div>'
    card_html += f'<div style="font-size: 28px; font-weight: 700; color: var(--st-text-color, #F1F5F9); line-height: 1.2;">{value}</div>'

    if delta:
        is_positive = delta.startswith("+")
        delta_color = "#22C55E" if is_positive else "#EF4444"
        card_html += f'<div style="font-size: 14px; color: {delta_color}; margin-top: 4px;">{delta}</div>'

    if progress is not None:
        pct = max(0, min(100, progress * 100))
        card_html += f'''
        <div style="margin-top: 12px; height: 4px; background: var(--st-border-color, #334155); border-radius: 2px; overflow: hidden;">
            <div style="height: 100%; width: {pct:.0f}%; background: var(--st-primary-color, #0EA5E9); border-radius: 2px; transition: width 0.3s;"></div>
        </div>
        '''

    card_html += "</div>"

    st.markdown(card_html, unsafe_allow_html=True)
