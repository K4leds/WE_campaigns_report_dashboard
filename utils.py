"""
Utility functions for formatting, styling, and common operations.
Includes formatting, display helpers, and data transformation utilities.
"""

import pandas as pd
import numpy as np
from io import BytesIO
import plotly.io as pio
import plotly.graph_objects as go


# Configure Plotly template
def configure_plotly_template(color_sequence):
    """Configure the default Plotly template for dashboard consistency."""
    _we_template = go.layout.Template()
    _we_template.layout = go.Layout(
        font=dict(family='Inter, Segoe UI, Roboto, sans-serif', size=13, color='#1F2937'),
        title=dict(font=dict(size=18, color='#111827'), x=0, xanchor='left'),
        paper_bgcolor='white',
        plot_bgcolor='white',
        colorway=color_sequence,
        xaxis=dict(showgrid=False, linecolor='#E5E7EB', linewidth=1),
        yaxis=dict(gridcolor='#F3F4F6', gridwidth=1, linecolor='#E5E7EB', linewidth=1, zerolinecolor='#E5E7EB'),
        legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1, bgcolor='rgba(0,0,0,0)'),
        margin=dict(l=40, r=20, t=50, b=40),
        hovermode='x unified',
    )
    pio.templates['we_dashboard'] = _we_template
    pio.templates.default = 'plotly_white+we_dashboard'


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
