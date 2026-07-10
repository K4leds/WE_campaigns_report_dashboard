import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric, style_total_row
from config import COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import get_attribution_display_label, get_selected_revenue_display_name, get_selected_conversion_display_name
from analysis import attribution_analysis

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
# Create display version for table
attr_df_display = attr_df.copy()
attr_df_display['Conversions'] = attr_df_display['Conversions'].apply(format_metric)
st.dataframe(attr_df_display)

# Create chart with original numeric values
fig_attr = px.pie(attr_df, names='Source', values='Conversions', title="Conversions by Attribution Source",
                  color_discrete_sequence=COLOR_SEQUENCE)
st.plotly_chart(fig_attr, width='stretch')
