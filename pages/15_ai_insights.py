import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from sklearn.cluster import KMeans

from dashboard.state import get_ctx
from components.table import render_table
from config import COLORS, COLOR_SEQUENCE
from attribution import get_attribution_display_label
from analysis import top_campaigns
from insights_engine import predict_revenue_forecast

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


st.header("🤖 AI-Powered Insights")

# Forecasting
# Uses the same Prophet model as Automated Insights' forecast (insights_engine.predict_revenue_forecast)
# so the two pages never show contradictory numbers for the same data.
st.subheader("📈 Revenue Forecasting")
if not filtered_df.empty:
    forecast = predict_revenue_forecast(filtered_df, forecast_days=90)
    if forecast:
        insight = forecast.get('insight', {})
        severity = insight.get('severity', 'info')
        message = f"{insight.get('emoji', '📊')} {insight.get('message', '')}"
        if severity == 'positive':
            st.success(message)
        elif severity == 'warning':
            st.warning(message)
        else:
            st.info(message)

        actual_df = filtered_df.copy()
        actual_df['date'] = pd.to_datetime(actual_df['Reporting Period Start Date'])
        actual_rev = actual_df.groupby('date')['Revenue (SAR)'].sum().reset_index()

        forecast_df = forecast['forecast_df']
        fig_forecast = go.Figure()
        fig_forecast.add_trace(go.Scatter(
            x=actual_rev['date'], y=actual_rev['Revenue (SAR)'],
            mode='markers', name='Actual', marker=dict(color=COLORS['primary'], size=6)
        ))
        fig_forecast.add_trace(go.Scatter(
            x=forecast_df['ds'], y=forecast_df['yhat'],
            mode='lines', name='Forecast', line=dict(color=COLORS['success'], width=2)
        ))
        fig_forecast.add_trace(go.Scatter(
            x=pd.concat([forecast_df['ds'], forecast_df['ds'][::-1]]),
            y=pd.concat([forecast_df['yhat_upper'], forecast_df['yhat_lower'][::-1]]),
            fill='toself', fillcolor='rgba(5,150,105,0.15)', line=dict(width=0),
            name='95% Confidence Interval'
        ))
        fig_forecast.update_layout(
            title=f"{forecast.get('forecast_days', 90)}-Day Revenue Forecast",
            xaxis_title="Date", yaxis_title="Revenue (SAR)", hovermode='x unified',
        )
        st.plotly_chart(fig_forecast, width='stretch')
    else:
        st.write("Not enough data for forecasting (need at least 14 days of history).")

# Segmentation
st.subheader("👥 Advanced Customer Segmentation")
if not filtered_df.empty:
    seg_agg = filtered_df.groupby('Segment Name').agg({
        'Revenue (SAR)': 'sum',
        'Unique Conversions': 'sum',
        'Unique Clicks': 'sum',
        'Sent': 'sum'
    }).reset_index()
    if len(seg_agg) > 3:
        features = seg_agg[['Revenue (SAR)', 'Unique Conversions', 'Unique Clicks', 'Sent']]
        try:
            kmeans = KMeans(n_clusters=3, random_state=42)
            seg_agg['Cluster'] = kmeans.fit_predict(features)
            fig_seg = px.scatter(seg_agg, x='Revenue (SAR)', y='Unique Conversions', color='Cluster', hover_data=['Segment Name'])
            st.plotly_chart(fig_seg)
            st.write("**Segmentation Insights:** Segments grouped by behavior. High-value clusters should be prioritized.")
        except Exception as e:
            st.write(f"Segmentation error: {e}")
    else:
        st.write("Not enough segments for clustering.")

# Optimization
st.subheader("🎯 Campaign Optimization Recommendations")
top_camp = top_campaigns(filtered_df, 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)')
if not top_camp.empty:
    best_camp = top_camp.iloc[0]['Campaign Name']
    st.success(f"🚀 **Top Performer:** {best_camp} - Allocate more budget here!")
    underperformers = top_camp.tail(3)['Campaign Name'].tolist()
    st.warning(f"⚠️ **Underperformers:** {', '.join(underperformers)} - Consider pausing or optimizing.")

# ROI Analysis
st.subheader("💰 ROI Analysis")
rev_col_roi = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
roi_df = filtered_df.groupby('Channel').agg({
    rev_col_roi: 'sum',
    'Sent': 'sum',
    'Campaign Cost': 'sum',
}).reset_index()
roi_df = roi_df.rename(columns={'Campaign Cost': 'Cost (SAR)', rev_col_roi: 'Revenue (SAR)'})
roi_df['Profit (SAR)'] = roi_df['Revenue (SAR)'] - roi_df['Cost (SAR)']
roi_df['ROAS'] = np.where(roi_df['Cost (SAR)'] > 0, roi_df['Revenue (SAR)'] / roi_df['Cost (SAR)'], 0)
roi_df['Revenue Per Send'] = np.where(roi_df['Sent'] > 0, roi_df['Revenue (SAR)'] / roi_df['Sent'], 0)

# Use column_config for proper numeric formatting
roi_cc = {
    'Revenue (SAR)': st.column_config.NumberColumn(label='Revenue (SAR)', format='%.2f'),
    'Cost (SAR)': st.column_config.NumberColumn(label='Cost (SAR)', format='%.2f'),
    'Profit (SAR)': st.column_config.NumberColumn(label='Profit (SAR)', format='%.2f'),
    'Sent': st.column_config.NumberColumn(label='Sent', format='%.0f'),
    'ROAS': st.column_config.NumberColumn(label='ROAS', format='%.2f'),
    'Revenue Per Send': st.column_config.NumberColumn(label='Revenue Per Send', format='%.4f'),
}
render_table(roi_df, key="roi_analysis", column_config=roi_cc)

# ROI chart
fig_roi = px.bar(roi_df, x='Channel', y=['Revenue (SAR)', 'Cost (SAR)'], barmode='group',
                 title="Revenue vs Cost by Channel", color_discrete_sequence=[COLORS['success'], COLORS['danger']])
st.plotly_chart(fig_roi, width='stretch')

# Dynamic Actionable Recommendations
st.subheader("📋 Actionable Recommendations")
# Generate recommendations based on actual data
_recs = []
if not roi_df.empty:
    best_roas_ch = roi_df.loc[roi_df['ROAS'].idxmax(), 'Channel'] if roi_df['ROAS'].max() > 0 else None
    best_rps_ch = roi_df.loc[roi_df['Revenue Per Send'].idxmax(), 'Channel'] if roi_df['Revenue Per Send'].max() > 0 else None
    highest_cost_ch = roi_df.loc[roi_df['Cost (SAR)'].idxmax(), 'Channel'] if roi_df['Cost (SAR)'].max() > 0 else None

    if best_roas_ch:
        _recs.append(f"- **Scale {best_roas_ch}:** Highest ROAS ({roi_df.loc[roi_df['Channel']==best_roas_ch, 'ROAS'].values[0]:.1f}x) - consider increasing budget")
    if best_rps_ch and best_rps_ch != best_roas_ch:
        _recs.append(f"- **Leverage {best_rps_ch}:** Best revenue per send - efficient at converting messages to revenue")
    if highest_cost_ch:
        cost_ch_roas = roi_df.loc[roi_df['Channel']==highest_cost_ch, 'ROAS'].values[0]
        if cost_ch_roas < 2:
            _recs.append(f"- **Optimize {highest_cost_ch}:** Highest cost channel with ROAS of only {cost_ch_roas:.1f}x - review targeting and content")

# Add data-driven segment and campaign recommendations
if 'Selected Conversions' in filtered_df.columns:
    ch_conv = filtered_df.groupby('Channel')['Selected Conversions'].sum()
    low_conv_channels = ch_conv[ch_conv > 0].nsmallest(2).index.tolist()
    if low_conv_channels:
        _recs.append(f"- **Improve conversion on {', '.join(low_conv_channels)}:** Low conversion volume - test different CTAs and offers")

_recs.append("- **A/B test creatives:** For campaigns with below-average CTR")
_recs.append("- **Monitor forecasts:** Use revenue predictions above for budget planning")

st.markdown("\n".join(_recs))
