import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from components.table import render_table, render_chart
from config import COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import get_attribution_display_label, get_selected_revenue_display_name, get_selected_conversion_display_name
from analysis import top_segments
from utils import render_kpi_card, format_metric

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

# Display-friendly rename map for attribution-selected columns (mirrors app.py prelude)
attribution_rename = {'Selected Revenue (SAR)': selected_rev_label, 'Selected Conversions': selected_conv_label}


def _attribution_display(col_name):
    """Map internal 'Selected Revenue/Conversions' column names to the user-selected attribution label."""
    return get_attribution_display_label(col_name, revenue_attribution, conversion_attribution)


st.header("Segments")

# --- Glance row: the overall picture before picking a metric to rank by ---
rev_col_glance = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
conv_col_glance = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'
if 'Segment Name' in filtered_df.columns:
    # 'nan' is a literal placeholder string for "no segment assigned" (same
    # convention as the sidebar segment filter in app.py), not real data --
    # exclude it so it can't win "Top Segment".
    named_segments = filtered_df[filtered_df['Segment Name'].astype(str) != 'nan']
    n_segments = named_segments['Segment Name'].dropna().nunique()
    seg_totals = named_segments.groupby('Segment Name')[rev_col_glance].sum() if rev_col_glance in named_segments.columns else None
    top_seg_name = seg_totals.idxmax() if seg_totals is not None and not seg_totals.empty else "—"
    top_seg_rev = seg_totals.max() if seg_totals is not None and not seg_totals.empty else 0

    g1, g2, g3 = st.columns(3)
    with g1:
        render_kpi_card("Segments", format_metric(n_segments), icon="👥")
    with g2:
        render_kpi_card("Top Segment", top_seg_name, icon="🏆")
    with g3:
        render_kpi_card("Top Segment Revenue", format_metric(top_seg_rev, "SAR"), icon="💰")

st.subheader("Top Segments")
# Safe column selection - only use columns that exist in both reports
safe_revenue_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
if 'Selected Revenue (SAR)' in filtered_df.columns:
    safe_revenue_cols.insert(0, 'Selected Revenue (SAR)')
safe_conversion_cols = ['Unique Conversions', 'Unique Clicks']

# Add conversion attribution options if they exist
if 'Unique Click-Through Conversions' in filtered_df.columns:
    safe_conversion_cols.append('Unique Click-Through Conversions')
if 'Unique Impression-Through Conversions' in filtered_df.columns:
    safe_conversion_cols.append('Unique Impression-Through Conversions')

# Add Total columns if they exist (Monthly report)
if 'Total Conversions' in filtered_df.columns:
    safe_conversion_cols.append('Total Conversions')

all_metrics = safe_conversion_cols + safe_revenue_cols
seg_metric = st.selectbox("Metric", all_metrics, key='seg_metric', format_func=_attribution_display)
top_seg = top_segments(filtered_df, seg_metric)

# Create display version for table
top_seg_display = top_seg.copy().rename(columns=attribution_rename)
seg_metric_display = _attribution_display(seg_metric)

# Determine format based on metric type
if 'Revenue' in seg_metric:
    cc = {seg_metric_display: st.column_config.NumberColumn(label=seg_metric_display, format="%.2f SAR")}
else:
    cc = {seg_metric_display: st.column_config.NumberColumn(label=seg_metric_display, format="%.0f")}
render_table(top_seg_display, key="top_segments", column_config=cc)

# Create chart with original numeric values
fig3 = px.bar(top_seg, x='Segment Name', y=seg_metric, title=f"Top Segments by {seg_metric_display}",
               color_discrete_sequence=COLOR_SEQUENCE)
render_chart(fig3, top_seg, key="top_segments_chart", ai_label=f"Top Segments by {seg_metric_display}")
