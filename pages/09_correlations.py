import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric
from config import COLORS, COLOR_SEQUENCE

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


st.header("Correlations")
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
    st.plotly_chart(fig_corr, width='stretch')

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
        corr_pairs_df['Correlation'] = corr_pairs_df['Correlation'].apply(lambda x: f"{x:+.3f}")
        st.dataframe(corr_pairs_df, width='stretch')
    else:
        st.info("No strong correlations (|r| >= 0.5) found between key metrics.")
else:
    st.write("No numeric data for correlation.")
