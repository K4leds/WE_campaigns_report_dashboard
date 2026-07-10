import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from dashboard.charts import attribution_display
from utils import format_metric, style_total_row, export_chart_image
from config import CHANNEL_COSTS, REQUIRED_COLUMNS, COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import (
    apply_attribution, apply_dimension_filters, get_attribution_display_label,
    get_selected_revenue_display_name, get_selected_conversion_display_name, resolve_source_column,
)
from dashboard.data_pipeline import cached_executive_summary
from insights_engine import (
    generate_narrative_insights,
    predict_revenue_forecast,
    generate_top_actions,
)

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
    return attribution_display(ctx, col_name)

st.header("🎯 Automated Insights & Recommendations")
st.markdown("*AI-powered narrative insights, predictions, and prioritized actions - like having a super team of analysts*")

# Generate executive summary
with st.spinner("🧠 Analyzing data and generating insights..."):
    exec_summary = cached_executive_summary(filtered_df)

# === EXECUTIVE SUMMARY CARD ===
st.markdown("---")
st.subheader("📊 Executive Summary")

col1, col2 = st.columns([2, 1])

with col1:
    if exec_summary.get('period'):
        st.info(f"📅 **Analysis Period:** {exec_summary['period']}")

    # Display headline metrics in a clean grid
    metrics = exec_summary.get('headline_metrics', {})
    met_col1, met_col2, met_col3 = st.columns(3)

    with met_col1:
        st.metric(f"💰 {selected_rev_label}", format_metric(metrics.get('total_revenue', 0), "SAR"))
        st.metric(f"🔄 {selected_conv_label}", format_metric(metrics.get('total_conversions', 0)))

    with met_col2:
        st.metric("📧 Total Sent", format_metric(metrics.get('total_sent', 0)))
        st.metric("📨 Avg Delivery Rate", f"{metrics.get('avg_delivery_rate', 0):.1%}")

    with met_col3:
        st.metric("👆 Avg CTR", f"{metrics.get('avg_ctr', 0):.2%}")
        st.metric("💵 Avg Conv Rate", f"{metrics.get('avg_conversion_rate', 0):.2%}")

with col2:
    # Alerts count
    alerts_count = exec_summary.get('alerts_count', 0)
    if alerts_count > 0:
        st.error(f"🚨 **{alerts_count} Critical Alerts**\nRequire Immediate Attention")
    else:
        st.success("✅ **No Critical Alerts**\nAll Systems Performing Well")

    st.metric("📈 Generated At", exec_summary.get('timestamp', 'N/A'))

# === HEADLINE NARRATIVE INSIGHTS (Like the example images) ===
st.markdown("---")
st.subheader("📰 What's Happening: Narrative Insights")
st.markdown("*Automated explanations of your performance - no manual analysis needed*")

insights = exec_summary.get('narrative_insights', {})

# Headline Insights
headline_insights = insights.get('headline_insights', [])
if headline_insights:
    for insight in headline_insights:
        emoji = insight.get('emoji', 'ℹ️')
        title = insight.get('title', '')
        message = insight.get('message', '')
        severity = insight.get('severity', 'info')

        if severity == 'positive':
            st.success(f"{emoji} **{title}**\n\n{message}")
        elif severity == 'critical':
            st.error(f"{emoji} **{title}**\n\n{message}")
        elif severity == 'warning':
            st.warning(f"{emoji} **{title}**\n\n{message}")
        else:
            st.info(f"{emoji} **{title}**\n\n{message}")

# Trend Analysis (Like: "Gradual Recovery")
trend_analysis = insights.get('trend_analysis', [])
if trend_analysis:
    st.markdown("### 📈 Trend Analysis")
    for trend in trend_analysis:
        emoji = trend.get('emoji', '📊')
        title = trend.get('title', '')
        message = trend.get('message', '')
        detail = trend.get('detail', '')
        severity = trend.get('severity', 'info')

        with st.expander(f"{emoji} {title}", expanded=True):
            st.markdown(f"**{message}**")
            if detail:
                st.caption(detail)

# Performance Alerts
performance_alerts = insights.get('performance_alerts', [])
if performance_alerts:
    st.markdown("### 🚨 Performance Alerts")
    for alert in performance_alerts:
        emoji = alert.get('emoji', '⚠️')
        title = alert.get('title', '')
        message = alert.get('message', '')
        action = alert.get('action', '')
        severity = alert.get('severity', 'warning')

        if severity == 'critical':
            st.error(f"{emoji} **{title}**\n\n{message}")
        else:
            st.warning(f"{emoji} **{title}**\n\n{message}")

        if action:
            st.caption(f"💡 **Action:** {action}")

# Optimization Opportunities
opportunities = insights.get('opportunities', [])
if opportunities:
    st.markdown("### 🎯 Optimization Opportunities")
    for opp in opportunities:
        emoji = opp.get('emoji', '💡')
        title = opp.get('title', '')
        message = opp.get('message', '')
        action = opp.get('action', '')
        expected_impact = opp.get('expected_impact', '')

        with st.expander(f"{emoji} {title}"):
            st.markdown(f"**Observation:** {message}")
            if action:
                st.info(f"**Recommended Action:** {action}")
            if expected_impact:
                st.success(f"**Expected Impact:** {expected_impact}")

# Business Context Notes
context_notes = insights.get('context_notes', [])
if context_notes:
    st.markdown("### 🌍 Business Context")
    for note in context_notes:
        emoji = note.get('emoji', 'ℹ️')
        title = note.get('title', '')
        message = note.get('message', '')
        st.info(f"{emoji} **{title}**\n\n{message}")

# === REVENUE FORECAST ===
st.markdown("---")
st.subheader("📈 Revenue Forecast")
st.markdown("*Predictive analytics for proactive planning*")

forecast_col1, forecast_col2 = st.columns([1, 3])

with forecast_col1:
    forecast_days = st.selectbox("Forecast Horizon", [7, 14, 30], index=1, key='forecast_horizon')

    if st.button("🔮 Generate Forecast", key='run_forecast'):
        with st.spinner("Running Prophet forecast model..."):
            forecast_result = predict_revenue_forecast(filtered_df, forecast_days=forecast_days)

            if forecast_result:
                st.session_state['forecast_result'] = forecast_result
            else:
                st.error("❌ Unable to generate forecast. Need at least 14 days of historical data.")

with forecast_col2:
    if 'forecast_result' in st.session_state and st.session_state['forecast_result']:
        forecast = st.session_state['forecast_result']

        # Display forecast insight
        insight = forecast.get('insight', {})
        emoji = insight.get('emoji', '📊')
        message = insight.get('message', '')
        severity = insight.get('severity', 'info')

        if severity == 'positive':
            st.success(f"{emoji} {message}")
        elif severity == 'warning':
            st.warning(f"{emoji} {message}")
        else:
            st.info(f"{emoji} {message}")

        # Display forecast metrics
        fcol1, fcol2, fcol3 = st.columns(3)

        with fcol1:
            st.metric("Total Predicted", format_metric(forecast.get('total_predicted', 0), "SAR"))

        with fcol2:
            st.metric("Daily Average", format_metric(forecast.get('daily_average', 0), "SAR"))

        with fcol3:
            trend_pct = forecast.get('trend_pct', 0)
            st.metric("Trend", f"{trend_pct:+.1f}%")

        # Plot forecast
        forecast_df = forecast.get('forecast_df')
        if forecast_df is not None and not forecast_df.empty:
            fig_forecast = go.Figure()

            # Add predicted revenue line
            fig_forecast.add_trace(go.Scatter(
                x=forecast_df['ds'],
                y=forecast_df['yhat'],
                mode='lines',
                name='Predicted Revenue',
                line=dict(color=COLORS['primary'], width=2)
            ))

            # Add confidence interval
            fig_forecast.add_trace(go.Scatter(
                x=forecast_df['ds'],
                y=forecast_df['yhat_upper'],
                mode='lines',
                name='Upper Bound (95%)',
                line=dict(color=COLORS['info'], width=1, dash='dash'),
                showlegend=False
            ))

            fig_forecast.add_trace(go.Scatter(
                x=forecast_df['ds'],
                y=forecast_df['yhat_lower'],
                mode='lines',
                name='Lower Bound (95%)',
                line=dict(color=COLORS['info'], width=1, dash='dash'),
                fill='tonexty',
                fillcolor='rgba(8, 145, 178, 0.15)',
                showlegend=False
            ))

            fig_forecast.update_layout(
                title=f"{forecast.get('forecast_days', 0)}-Day Revenue Forecast",
                xaxis_title="Date",
                yaxis_title="Revenue (SAR)",
                hovermode='x unified'
            )

            st.plotly_chart(fig_forecast, use_container_width=True)
            forecast_img = export_chart_image(fig_forecast, 'revenue_forecast')
            if forecast_img:
                st.download_button("Download Forecast Chart", forecast_img, "revenue_forecast.png", "image/png", key='dl_forecast')

            # Show confidence interval info
            st.caption(f"📊 95% Confidence Interval: {format_metric(forecast.get('confidence_lower', 0), 'SAR')} - {format_metric(forecast.get('confidence_upper', 0), 'SAR')}")

# === TOP ACTIONS (Like the example: "Add reminder blocks") ===
st.markdown("---")
st.subheader("🎯 Top 5 Prioritized Actions")
st.markdown("*Specific, actionable recommendations with expected ROI*")

top_actions = exec_summary.get('top_actions', [])

if top_actions:
    for idx, action in enumerate(top_actions, 1):
        priority = action.get('priority', 'MEDIUM')
        title = action.get('title', '')
        action_text = action.get('action', '')
        expected_impact = action.get('expected_impact', '')
        confidence = action.get('confidence', '')
        impl_time = action.get('implementation_time', '')

        # Color code by priority
        if priority == 'HIGH':
            priority_color = '🔴'
            container_type = st.error
        elif priority == 'MEDIUM':
            priority_color = '🟡'
            container_type = st.warning
        else:
            priority_color = '🟢'
            container_type = st.info

        with st.expander(f"{idx}. {priority_color} [{priority}] {title}", expanded=(idx <= 2)):
            st.markdown(f"**Action:** {action_text}")

            act_col1, act_col2, act_col3 = st.columns(3)

            with act_col1:
                st.metric("Expected Impact", expected_impact)

            with act_col2:
                st.metric("Confidence", confidence)

            with act_col3:
                st.metric("Implementation Time", impl_time)
else:
    st.info("✅ No critical actions needed at this time. Continue monitoring performance.")

# === JOURNEY-SPECIFIC INSIGHTS ===
st.markdown("---")
st.subheader("🔍 Journey-Specific Deep Dive")
st.markdown("*Analyze individual journeys with automated insights*")

if 'Journey Name' in filtered_df.columns:
    unique_journeys = filtered_df['Journey Name'].dropna().unique()

    selected_journey_insights = st.selectbox(
        "Select Journey for Detailed Insights",
        [''] + list(unique_journeys),
        key='journey_insights_selector'
    )

    if selected_journey_insights:
        with st.spinner(f"Generating insights for {selected_journey_insights}..."):
            journey_insights = generate_narrative_insights(
                filtered_df,
                journey_name=selected_journey_insights,
                lookback_days=30
            )

            # Display journey-specific insights
            for category, items in journey_insights.items():
                if items and category != 'context_notes':
                    st.markdown(f"**{category.replace('_', ' ').title()}:**")
                    for item in items:
                        if isinstance(item, dict):
                            emoji = item.get('emoji', '')
                            title = item.get('title', '')
                            message = item.get('message', '')
                            st.info(f"{emoji} **{title}**: {message}")

            # Generate journey-specific forecast
            st.markdown("### 📈 Journey Revenue Forecast")
            journey_forecast = predict_revenue_forecast(
                filtered_df,
                journey_name=selected_journey_insights,
                forecast_days=14
            )

            if journey_forecast:
                insight = journey_forecast.get('insight', {})
                st.info(f"{insight.get('emoji', '')} {insight.get('message', '')}")

                jf_col1, jf_col2 = st.columns(2)
                with jf_col1:
                    st.metric("14-Day Predicted Total",
                            format_metric(journey_forecast.get('total_predicted', 0), "SAR"))
                with jf_col2:
                    st.metric("Trend", f"{journey_forecast.get('trend_pct', 0):+.1f}%")

            # Generate journey-specific actions
            st.markdown("### 🎯 Recommended Actions for This Journey")
            journey_actions = generate_top_actions(
                filtered_df,
                journey_name=selected_journey_insights,
                max_actions=3
            )

            if journey_actions:
                for action in journey_actions:
                    st.success(f"**{action.get('title', '')}**\n\n{action.get('action', '')}\n\n*Expected Impact: {action.get('expected_impact', '')}*")
            else:
                st.info("✅ Journey is performing well. Continue current strategy.")

# === DOWNLOAD INSIGHTS REPORT ===
st.markdown("---")
st.subheader("📄 Export Insights Report")

if st.button("📥 Download Full Insights Report (PDF-Ready)", key='download_insights'):
    st.info("💡 **Export Feature**: Copy the insights above or use browser print (Ctrl+P) to save as PDF")
