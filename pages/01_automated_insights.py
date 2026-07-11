import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from sklearn.cluster import KMeans

from dashboard.state import get_ctx
from dashboard.charts import attribution_display
from utils import format_metric
from config import REQUIRED_COLUMNS, COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import (
    apply_attribution, apply_dimension_filters, get_attribution_display_label,
    get_selected_revenue_display_name, get_selected_conversion_display_name, resolve_source_column,
)
from components.table import render_table
from analysis import top_campaigns
from dashboard.data_pipeline import cached_executive_summary
from insights_engine import (
    generate_narrative_insights,
    predict_revenue_forecast,
    generate_top_actions,
)
from llm_narrative import generate_ai_summary

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

st.header("🤖 AI Insights & Recommendations")
st.markdown("*AI-powered narrative insights, predictions, and prioritized actions - like having a super team of analysts*")

# Generate executive summary (feeds every tab below)
with st.spinner("🧠 Analyzing data and generating insights..."):
    exec_summary = cached_executive_summary(filtered_df)

tab_narrative, tab_forecast, tab_segmentation, tab_roi = st.tabs(
    ["📰 Narrative & Actions", "📈 Forecast", "👥 Segmentation", "💰 ROI Analysis"]
)

with tab_narrative:
    # === AI SUMMARY (DeepSeek, optional) ===
    # Only the numbers insights_engine already computed above are given to the
    # model to write up -- it never invents a figure. Renders nothing if no
    # DEEPSEEK_API_KEY is configured or the call fails; see llm_narrative.py.
    ai_summary = generate_ai_summary(exec_summary)
    if ai_summary:
        st.subheader("🤖 AI Summary")
        st.info(ai_summary)

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

    # === HEADLINE NARRATIVE INSIGHTS ===
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

            with st.expander(f"{emoji} {title}", expanded=True):
                st.markdown(f"**{message}**")
                if detail:
                    st.caption(detail)

    # Performance Alerts (now includes per-channel alerts from insights_engine)
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

    # Optimization Opportunities (now includes per-channel opportunities)
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

    # === TOP ACTIONS (now includes channel budget-reallocation) ===
    st.markdown("---")
    st.subheader("🎯 Top Prioritized Actions")
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
            elif priority == 'MEDIUM':
                priority_color = '🟡'
            else:
                priority_color = '🟢'

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

with tab_forecast:
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

                st.plotly_chart(fig_forecast, width='stretch')

                # Show confidence interval info
                st.caption(f"📊 95% Confidence Interval: {format_metric(forecast.get('confidence_lower', 0), 'SAR')} - {format_metric(forecast.get('confidence_upper', 0), 'SAR')}")

with tab_segmentation:
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

with tab_roi:
    st.subheader("🎯 Campaign Optimization Recommendations")
    top_camp = top_campaigns(filtered_df, 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)')
    if not top_camp.empty:
        best_camp = top_camp.iloc[0]['Campaign Name']
        st.success(f"🚀 **Top Performer:** {best_camp} - Allocate more budget here!")
        underperformers = top_camp.tail(3)['Campaign Name'].tolist()
        st.warning(f"⚠️ **Underperformers:** {', '.join(underperformers)} - Consider pausing or optimizing.")

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
