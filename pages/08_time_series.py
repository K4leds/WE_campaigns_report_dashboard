import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric
from config import COLORS, COLOR_SEQUENCE
from attribution import get_attribution_display_label
from analysis import time_series_analysis

ctx = get_ctx()
df = ctx.df
filtered_df = ctx.filtered_df
comparison_result = ctx.comparison_result
revenue_attribution = ctx.revenue_attribution
conversion_attribution = ctx.conversion_attribution
selected_rev_label = ctx.selected_rev_label
selected_conv_label = ctx.selected_conv_label
date_range = ctx.date_range
comparison_mode = ctx.comparison_mode


def _attribution_display(col_name):
    return get_attribution_display_label(col_name, revenue_attribution, conversion_attribution)


st.header("Time Series Analysis")
# Safe column selection - only use columns that exist in both reports
safe_revenue_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
if 'Selected Revenue (SAR)' in filtered_df.columns:
    safe_revenue_cols.insert(0, 'Selected Revenue (SAR)')
safe_conversion_cols = ['Unique Conversions', 'Unique Clicks']

# Add Total columns if they exist (Monthly report)
if 'Total Conversions' in filtered_df.columns:
    safe_conversion_cols.append('Total Conversions')

all_metrics = safe_conversion_cols + safe_revenue_cols
ts_metric = st.selectbox("Metric", all_metrics, key='ts_metric', format_func=_attribution_display)
ts_df = time_series_analysis(filtered_df, ts_metric)
if not ts_df.empty:
    fig_ts = px.line(ts_df, x='Reporting Period Start Date', y=ts_metric, title=f"{_attribution_display(ts_metric)} Over Time",
                     color_discrete_sequence=[COLORS['primary']])
    fig_ts.update_traces(line_width=2.5)
    st.plotly_chart(fig_ts, width='stretch')
else:
    st.write("No time series data available.")
