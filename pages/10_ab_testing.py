import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from components.table import render_table, render_chart
from config import COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import get_attribution_display_label, get_selected_revenue_display_name, get_selected_conversion_display_name
from analysis import ab_testing_analysis

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

st.header("A/B Testing Analysis")
ab_df = ab_testing_analysis(filtered_df)
if not ab_df.empty:
    cc = {
        'Test Conversion Rate': st.column_config.NumberColumn(label='Test Conversion Rate', format='.2%'),
        'Control Conversion Rate': st.column_config.NumberColumn(label='Control Conversion Rate', format='.2%'),
        'Lift': st.column_config.NumberColumn(label='Lift', format='+.2%'),
        'P-Value': st.column_config.NumberColumn(format='.4f'),
    }
    render_table(ab_df, key="ab_testing_results", column_config=cc)
    fig_ab = px.bar(ab_df, x='Campaign Name', y='Lift', title="Conversion Lift by Campaign",
                    color='Lift', color_continuous_scale=[[0, COLORS['danger']], [0.5, COLORS['warning']], [1, COLORS['success']]])
    render_chart(fig_ab, ab_df, key="ab_testing_chart", ai_label="Conversion Lift by Campaign", width='stretch')
else:
    st.write("No A/B testing data available (no control groups).")
