import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric
from components.table import render_table, render_ai_explain, render_chart
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


st.header("Time Series & Correlations")

tab1, tab2 = st.tabs(["📈 Time Series", "🔗 Correlations"])

with tab1:
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
        _, explain_col = st.columns([8, 1])
        with explain_col:
            render_ai_explain(ts_df, key=f"time_series_{ts_metric}", ai_label=f"{_attribution_display(ts_metric)} over time",
                               help_text="Explain this trend with AI")
        st.plotly_chart(fig_ts, width='stretch')
    else:
        st.write("No time series data available.")

with tab2:
    # Focus on key business metrics for a readable correlation matrix
    key_metric_cols = [c for c in [
        'Sent', 'Delivered', 'Unique Impressions', 'Unique Clicks',
        'Unique Conversions', 'Selected Conversions', 'Selected Revenue (SAR)',
        'Revenue (SAR)', 'CTR', 'Conversion Rate', 'Delivery Rate',
        'AOV', 'Revenue Per Click', 'Revenue Per Send', 'ROAS',
        'Campaign Cost', 'Engagement Rate',
    ] if c in filtered_df.columns]

    if key_metric_cols:
        corr = filtered_df[key_metric_cols].corr()
        fig_corr = px.imshow(corr, text_auto='.2f', title="Key Metrics Correlation Matrix",
                             color_continuous_scale='RdBu_r', aspect='auto',
                             zmin=-1, zmax=1)
        fig_corr.update_layout(width=900, height=700)
        corr_matrix_df = corr.reset_index().rename(columns={'index': 'Metric'})
        render_chart(fig_corr, corr_matrix_df, key="correlation_matrix", ai_label="Key Metrics Correlation Matrix", width='stretch')

        # Highlight strongest correlations
        st.subheader("Strongest Correlations")
        corr_pairs = []
        for i in range(len(corr.columns)):
            for j in range(i + 1, len(corr.columns)):
                val = corr.iloc[i, j]
                if abs(val) >= 0.5 and abs(val) < 1.0:
                    corr_pairs.append({
                        'Metric 1': corr.columns[i],
                        'Metric 2': corr.columns[j],
                        'Correlation': val,
                        'Strength': 'Strong' if abs(val) >= 0.7 else 'Moderate'
                    })
        if corr_pairs:
            corr_pairs_df = pd.DataFrame(corr_pairs).sort_values('Correlation', key=abs, ascending=False)
            cc = {
                'Correlation': st.column_config.NumberColumn(label='Correlation', format='+.3f'),
            }
            render_table(corr_pairs_df, key="correlation_pairs", column_config=cc)
        else:
            st.info("No strong correlations (|r| >= 0.5) found between key metrics.")
    else:
        st.write("No numeric data for correlation.")
