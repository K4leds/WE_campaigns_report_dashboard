import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from components.table import render_table, render_chart
from config import COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import get_attribution_display_label, get_selected_revenue_display_name, get_selected_conversion_display_name
from analysis import attribution_analysis
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

attribution_rename = {'Selected Revenue (SAR)': selected_rev_label, 'Selected Conversions': selected_conv_label}

def _attribution_display(col_name):
    return get_attribution_display_label(col_name, revenue_attribution, conversion_attribution)

st.header("Attribution Analysis")
attr_df = attribution_analysis(filtered_df)

# --- Glance row ---
total_conv_attr = attr_df['Conversions'].sum()
if not attr_df.empty and total_conv_attr > 0:
    top_source_row = attr_df.loc[attr_df['Conversions'].idxmax()]
    top_source_share = top_source_row['Conversions'] / total_conv_attr * 100
    g1, g2, g3 = st.columns(3)
    with g1:
        render_kpi_card("Total Conversions", format_metric(total_conv_attr), icon="🎯")
    with g2:
        render_kpi_card("Top Source", top_source_row['Source'], icon="🏆")
    with g3:
        render_kpi_card("Top Source Share", f"{top_source_share:.1f}%", icon="📊")

attr_df_display = attr_df.copy().rename(columns=attribution_rename)
col_config = {"Conversions": st.column_config.NumberColumn(label="Conversions", format="%.0f")}
st.subheader("Attribution Breakdown")
render_table(attr_df_display, key="attribution", column_config=col_config)

# Create chart with original numeric values
fig_attr = px.pie(attr_df, names='Source', values='Conversions', title="Conversions by Attribution Source",
                  color_discrete_sequence=COLOR_SEQUENCE)
render_chart(fig_attr, attr_df, key="attribution_chart", ai_label="Conversions by Attribution Source")
