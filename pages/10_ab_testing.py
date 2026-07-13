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
    # Rates arrive as 0-1 fractions; scale to 0-100 for render_table's percent
    # formatters, which append '%' to the raw cell value.
    ab_display = ab_df.copy()
    for _c in ['Test Conversion Rate', 'Control Conversion Rate', 'Lift']:
        if _c in ab_display.columns:
            ab_display[_c] = ab_display[_c] * 100
    cc = {
        'Test Conversion Rate': st.column_config.NumberColumn(label='Test Conversion Rate', format='%.2f%%'),
        'Control Conversion Rate': st.column_config.NumberColumn(label='Control Conversion Rate', format='%.2f%%'),
        'Lift': st.column_config.NumberColumn(label='Lift', format='%+.2f%%'),
        'P-Value': st.column_config.NumberColumn(label='P-Value', format='%.4f'),
    }
    render_table(ab_display, key="ab_testing_results", column_config=cc)
    # Horizontal diverging bars anchored at zero: sign carries the meaning, so
    # color by sign (status green/red) instead of a ramp whose midpoint floats
    # at the data-range middle rather than at lift = 0.
    # Chart only the 20 biggest movers by |Lift| -- with every test in one chart
    # it grows several screens tall; the full list stays in the table above.
    ab_sorted = ab_df.reindex(
        ab_df['Lift'].abs().sort_values(ascending=False).head(20).index
    ).sort_values('Lift')
    fig_ab = px.bar(ab_sorted, x='Lift', y='Campaign Name', orientation='h',
                    title="Conversion Lift by Campaign (20 biggest movers)",
                    color=(ab_sorted['Lift'] >= 0).map({True: 'Positive', False: 'Negative'}),
                    color_discrete_map={'Positive': COLORS['success'], 'Negative': COLORS['danger']})
    fig_ab.update_layout(showlegend=False, yaxis_title=None, xaxis_tickformat='+.1%',
                         height=max(400, 36 * len(ab_sorted)))
    render_chart(fig_ab, ab_df, key="ab_testing_chart", ai_label="Conversion Lift by Campaign")
else:
    st.write("No A/B testing data available (no control groups).")
