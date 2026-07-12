import json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric, read_cached_json
from components.table import render_table, render_chart
from config import COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import get_attribution_display_label, get_selected_conversion_display_name
from dashboard.health import calculate_journey_health_score
from dashboard.funnels import analyze_journey_funnel
from dashboard.anomalies import detect_journey_anomalies
from dashboard.lifecycle import (
    create_revenue_attribution_waterfall, analyze_journey_lifecycle,
    analyze_stopped_journeys, estimate_revenue_loss_ml, generate_stopped_journey_recommendations,
    create_cohort_analysis,
)
from dashboard.comparisons_logic import (
    create_journey_comparison_analysis,
    calculate_period_metrics, calculate_metric_changes,
)
from dashboard.data_pipeline import cached_journey_health_scores
from dashboard.charts import render_health_dashboard
from analysis import get_top_journeys

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

# Derive unique journey names for dropdowns
unique_journeys = filtered_df['Journey Name'].dropna().unique()

# Display-friendly rename map for attribution-selected columns (mirrors app.py prelude)
attribution_rename = {'Selected Revenue (SAR)': selected_rev_label, 'Selected Conversions': selected_conv_label}


def _attribution_display(col_name):
    """Map internal 'Selected Revenue/Conversions' column names to the user-selected attribution label."""
    return get_attribution_display_label(col_name, revenue_attribution, conversion_attribution)


def analyze_individual_journey(journey_name, filtered_df):
    """
    Detailed analysis of an individual journey - returns comprehensive scoring breakdown.
    This is the same logic as the debug script but as a reusable function.
    """
    try:
        # Get the specific journey data
        journey_data = filtered_df[filtered_df['Journey Name'] == journey_name].copy()

        if journey_data.empty:
            return {'error': f"Journey '{journey_name}' not found!"}

        # Calculate the score with detailed breakdown
        score_result = calculate_journey_health_score(journey_data, filtered_df)

        # Calculate raw metrics for this journey
        raw_metrics = {}

        # Delivery metrics
        if 'Sent' in journey_data.columns and 'Delivered' in journey_data.columns:
            total_sent = journey_data['Sent'].sum()
            total_delivered = journey_data['Delivered'].sum()
            delivery_rate = (total_delivered / total_sent) if total_sent > 0 else 0
            raw_metrics['delivery'] = {
                'total_sent': total_sent,
                'total_delivered': total_delivered,
                'delivery_rate': delivery_rate
            }

        # Engagement metrics
        if 'Unique Clicks' in journey_data.columns and 'Unique Impressions' in journey_data.columns:
            total_clicks = journey_data['Unique Clicks'].sum()
            total_impressions = journey_data['Unique Impressions'].sum()
            ctr = (total_clicks / total_impressions) if total_impressions > 0 else 0
            raw_metrics['engagement'] = {
                'total_clicks': total_clicks,
                'total_impressions': total_impressions,
                'ctr': ctr
            }

        # Conversion metrics - ALWAYS CALCULATE FROM RAW FIELDS
        if 'Unique Conversions' in journey_data.columns and 'Unique Clicks' in journey_data.columns:
            total_conversions = journey_data['Unique Conversions'].sum()
            total_clicks = journey_data['Unique Clicks'].sum()
            conv_rate = (total_conversions / total_clicks) if total_clicks > 0 else 0
            raw_metrics['conversion'] = {
                'total_conversions': total_conversions,
                'total_clicks': total_clicks,
                'conversion_rate': conv_rate,
                'source': 'Calculated: Unique Conversions / Unique Clicks'
            }

        # Revenue metrics
        if 'Revenue (SAR)' in journey_data.columns and 'Unique Conversions' in journey_data.columns:
            total_revenue = journey_data['Revenue (SAR)'].sum()
            total_conversions = journey_data['Unique Conversions'].sum()
            rpc = (total_revenue / total_conversions) if total_conversions > 0 else 0
            log_rpc = np.log1p(rpc)
            raw_metrics['revenue'] = {
                'total_revenue': total_revenue,
                'total_conversions': total_conversions,
                'revenue_per_conversion': rpc,
                'log_rpc': log_rpc
            }

        # Calculate population percentiles for context
        journey_groups = filtered_df.groupby('Journey Name')
        percentiles = {}

        # Delivery percentiles
        if 'delivery' in raw_metrics:
            delivery_rates = []
            for name, group in journey_groups:
                if 'Sent' in group.columns and 'Delivered' in group.columns:
                    sent = group['Sent'].sum()
                    delivered = group['Delivered'].sum()
                    if sent > 0:
                        delivery_rates.append(delivered / sent)

            if delivery_rates:
                percentile = (np.array(delivery_rates) <= raw_metrics['delivery']['delivery_rate']).mean() * 100
                percentiles['delivery'] = percentile

        # CTR percentiles
        if 'engagement' in raw_metrics:
            ctrs = []
            for name, group in journey_groups:
                if 'Unique Clicks' in group.columns and 'Unique Impressions' in group.columns:
                    clicks = group['Unique Clicks'].sum()
                    impressions = group['Unique Impressions'].sum()
                    if impressions > 0:
                        ctrs.append(clicks / impressions)

            if ctrs:
                percentile = (np.array(ctrs) <= raw_metrics['engagement']['ctr']).mean() * 100
                percentiles['engagement'] = percentile

        # Conversion rate percentiles
        if 'conversion' in raw_metrics:
            conv_rates = []
            # Use the same method as in the scoring function for consistency
            if 'Conversion Rate' in filtered_df.columns:
                for name, group in journey_groups:
                    journey_conv_rate = group['Conversion Rate'].mean()
                    if not pd.isna(journey_conv_rate):
                        conv_rates.append(journey_conv_rate)
            else:
                for name, group in journey_groups:
                    if 'Unique Conversions' in group.columns and 'Unique Clicks' in group.columns:
                        conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
                        clicks = group['Unique Clicks'].sum()
                        if clicks > 0:
                            conv_rates.append(conversions / clicks)

            if conv_rates:
                percentile = (np.array(conv_rates) <= raw_metrics['conversion']['conversion_rate']).mean() * 100
                percentiles['conversion'] = percentile

        # Revenue per conversion percentiles
        if 'revenue' in raw_metrics:
            rpcs = []
            for name, group in journey_groups:
                if 'Revenue (SAR)' in group.columns and 'Unique Conversions' in group.columns:
                    revenue = group['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in group.columns else group['Revenue (SAR)'].sum()
                    conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
                    if conversions > 0:
                        rpcs.append(revenue / conversions)

            if rpcs:
                percentile = (np.array(rpcs) <= raw_metrics['revenue']['revenue_per_conversion']).mean() * 100
                percentiles['revenue'] = percentile

        # Component score contributions
        weights = {'delivery': 0.20, 'engagement': 0.25, 'conversion': 0.30, 'revenue': 0.25}
        component_contributions = {}
        for component, score in score_result['component_scores'].items():
            weight = weights[component]
            contribution = score * weight
            component_contributions[component] = {
                'score': score,
                'weight': weight,
                'contribution': contribution
            }

        # Summary insights
        worst_components = sorted(score_result['component_scores'].items(), key=lambda x: x[1])
        insights = []

        for component, score in worst_components[:2]:  # Show worst 2 components
            if score < 40:
                insights.append(f"🚨 {component.capitalize()} score ({score:.1f}) is critically low")
            elif score < 60:
                insights.append(f"⚠️ {component.capitalize()} score ({score:.1f}) is below average")

        return {
            'journey_name': journey_name,
            'data_rows': len(journey_data),
            'score_result': score_result,
            'raw_metrics': raw_metrics,
            'percentiles': percentiles,
            'component_contributions': component_contributions,
            'insights': insights
        }

    except Exception as e:
        return {'error': str(e)}


st.header("Journey Analysis")

# Show comparison summary if enabled
if comparison_result:
    st.info(f"📊 Period Comparison Active: {comparison_result['current_label']} vs {comparison_result['comparison_label']}")

    # Calculate journey metrics for both periods
    current_metrics = calculate_period_metrics(comparison_result['current_data'], comparison_result['current_days'], conversion_attribution)
    comp_metrics = calculate_period_metrics(comparison_result['comparison_data'], comparison_result['comparison_days'], conversion_attribution)
    metric_changes = calculate_metric_changes(current_metrics, comp_metrics)

    # Show quick comparison
    comp_col1, comp_col2, comp_col3, comp_col4 = st.columns(4)
    with comp_col1:
        change_data = metric_changes['selected_revenue']
        st.metric("Revenue", format_metric(change_data['current'], "SAR"),
                 delta=f"{change_data['pct_change']:+.1f}%")
    with comp_col2:
        change_data = metric_changes['selected_conversions']
        st.metric("Conversions", format_metric(change_data['current']),
                 delta=f"{change_data['pct_change']:+.1f}%")
    with comp_col3:
        change_data = metric_changes['ctr']
        st.metric("CTR", f"{change_data['current']:.2%}",
                 delta=f"{change_data['pct_change']:+.1f}%")
    with comp_col4:
        change_data = metric_changes['conversion_rate']
        st.metric("Conv Rate", f"{change_data['current']:.2%}",
                 delta=f"{change_data['pct_change']:+.1f}%")

    st.markdown("---")

# Revenue Type Selection - Revenue Attribution Models
st.markdown("**💰 Revenue Attribution Model Selection**")
st.markdown("*Choose the attribution model for revenue analysis:*")

available_revenue_cols = [col for col in df.columns if 'Revenue' in col]
if available_revenue_cols:
    # Create user-friendly labels for attribution models
    revenue_labels = {}
    for col in available_revenue_cols:
        if col == 'Revenue (SAR)':
            revenue_labels[col] = "📊 Total Revenue (Send-Through Attribution)"
        elif col == 'Click-Through Revenue (SAR)':
            revenue_labels[col] = "🖱️ Click-Through Revenue Attribution"
        elif col == 'Impression-Through Revenue (SAR)':
            revenue_labels[col] = "👁️ Impression-Through Revenue Attribution"
        else:
            revenue_labels[col] = col

    # Default to total revenue (send-through)
    default_revenue = 'Revenue (SAR)' if 'Revenue (SAR)' in available_revenue_cols else available_revenue_cols[0]

    selected_label = st.selectbox(
        "Select Revenue Attribution Model",
        [revenue_labels[col] for col in available_revenue_cols],
        index=[revenue_labels[col] for col in available_revenue_cols].index(revenue_labels[default_revenue]),
        key='revenue_type'
    )

    # Map back to actual column name
    selected_revenue = [col for col, label in revenue_labels.items() if label == selected_label][0]
else:
    selected_revenue = 'Revenue (SAR)'  # Fallback
    st.warning("⚠️ No revenue columns found in data")

# Journey Health Score Analysis
st.subheader("🏥 Journey Health Dashboard")

# Professional Methodology Explanation for Executives
with st.expander("📊 Scoring Methodology (Click to View)", expanded=False):
    st.markdown("""
    ### **Health Score Methodology**

    **Method**: Percentile ranking with Empirical Bayes smoothing

    #### **How Scores are Calculated:**
    - **Relative Ranking**: Each journey is scored against all other journeys in your portfolio (0-100 scale)
    - **Empirical Bayes Smoothing**: Low-volume journeys are adjusted toward the portfolio average to avoid misleading scores from small samples
    - **No Fixed Benchmarks**: Scores reflect your actual portfolio distribution, not arbitrary industry numbers

    #### **Component Weights:**
    - 🚀 **Conversion Performance**: 30% - Conversion rate (clicks to conversions)
    - 🎯 **Engagement Performance**: 25% - Click-through rate (impressions to clicks)
    - 💰 **Revenue Efficiency**: 25% - Revenue per conversion (log-scaled to reduce outlier impact)
    - 📧 **Delivery Performance**: 20% - Delivery rate (sent to delivered)

    #### **Performance Tiers:**
    - **Excellent (80-100)**: Top quartile - scale these journeys
    - **Good (60-79)**: Above average - minor optimizations needed
    - **Fair (40-59)**: Below average - moderate improvements required
    - **Poor (0-39)**: Bottom quartile - immediate action required

    #### **Data Sufficiency:**
    Journeys with fewer than 10 sends, 3 conversions, or 3 days of data are marked "Insufficient Data" to prevent unreliable scores.
    """)


# Calculate health scores for all journeys
journey_health_data = cached_journey_health_scores(filtered_df)

if journey_health_data:
    health_df = pd.DataFrame(journey_health_data)
    selected_journey_health = render_health_dashboard(health_df, 'Journey Name', 'Journey', 'journey')

    if selected_journey_health:
        journey_data_for_rec = filtered_df[filtered_df['Journey Name'] == selected_journey_health]
        health_info_for_rec = calculate_journey_health_score(journey_data_for_rec, filtered_df)

        st.subheader("💡 Recommendations")
        for rec in health_info_for_rec['recommendations']:
            st.info(rec)

        # 🔍 DETAILED INDIVIDUAL JOURNEY ANALYSIS
        st.subheader("🔍 Detailed Journey Analysis")
        st.markdown("*Get the complete story behind this journey's score - same analysis as our debug script*")

        # Call our analysis function
        individual_analysis = analyze_individual_journey(selected_journey_health, filtered_df)

        if 'error' in individual_analysis:
            st.error(f"❌ Error analyzing journey: {individual_analysis['error']}")
        else:
            # Journey Summary
            st.markdown(f"**📊 Journey:** {individual_analysis['journey_name']}")
            st.markdown(f"**📈 Data Points:** {individual_analysis['data_rows']} rows of data")
            st.markdown(f"**🎯 Final Score:** {individual_analysis['score_result']['health_score']:.1f}/100 ({individual_analysis['score_result']['tier']})")
            st.markdown(f"**🔬 Method:** {individual_analysis['score_result']['scoring_method']}")

            # Raw Metrics Breakdown
            with st.expander("📈 Raw Metrics Breakdown", expanded=True):
                if 'delivery' in individual_analysis['raw_metrics']:
                    delivery_data = individual_analysis['raw_metrics']['delivery']
                    st.markdown("**📤 Delivery Performance:**")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Sent", format_metric(delivery_data['total_sent']))
                    with col2:
                        st.metric("Delivered", format_metric(delivery_data['total_delivered']))
                    with col3:
                        st.metric("Delivery Rate", f"{delivery_data['delivery_rate']:.1%}")

                if 'engagement' in individual_analysis['raw_metrics']:
                    engagement_data = individual_analysis['raw_metrics']['engagement']
                    st.markdown("**👆 Engagement Performance:**")
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric("Impressions", format_metric(engagement_data['total_impressions']))
                    with col2:
                        st.metric("Clicks", format_metric(engagement_data['total_clicks']))
                    with col3:
                        st.metric("CTR (Click Rate)", f"{engagement_data['ctr']:.2%}",
                                 help="Impressions → Clicks: How many people who saw it clicked it")

                if 'conversion' in individual_analysis['raw_metrics']:
                    conversion_data = individual_analysis['raw_metrics']['conversion']
                    journey_data = individual_analysis.get('journey_data', filtered_df[filtered_df['Journey Name'] == selected_journey_health])

                    st.markdown("**💰 Conversion Performance:**")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric("Clicks", format_metric(conversion_data['total_clicks']))
                    with col2:
                        st.metric("Conversions", format_metric(conversion_data['total_conversions']))
                    with col3:
                        st.metric("Conversion Rate (CVR)", f"{conversion_data['conversion_rate']:.2%}",
                                 help="Clicks → Conversions: How many people who clicked actually converted")
                    with col4:
                        if 'source' in conversion_data:
                            st.caption(f"Source: {conversion_data['source']}")

                    # Additional attribution rates
                    st.markdown("**📊 Additional Attribution Metrics:**")
                    attr_col1, attr_col2, attr_col3 = st.columns(3)

                    with attr_col1:
                        # Impression-Through Rate
                        if 'Unique Impression-Through Conversions' in journey_data.columns and 'Unique Impressions' in journey_data.columns:
                            imp_conv = journey_data['Unique Impression-Through Conversions'].sum()
                            imp_total = journey_data['Unique Impressions'].sum()
                            imp_rate = (imp_conv / imp_total * 100) if imp_total > 0 else 0
                            st.metric("Impression-Through Rate", f"{imp_rate:.2%}",
                                     help="Impressions → Conversions: People who converted after seeing (no click)")

                    with attr_col2:
                        # Click-Through Rate (already shown above, but for completeness)
                        if 'Unique Click-Through Conversions' in journey_data.columns and 'Unique Clicks' in journey_data.columns:
                            click_conv = journey_data['Unique Click-Through Conversions'].sum()
                            click_total = journey_data['Unique Clicks'].sum()
                            click_rate = (click_conv / click_total * 100) if click_total > 0 else 0
                            st.metric("Click-Through Rate", f"{click_rate:.2%}",
                                     help="Clicks → Conversions: People who converted after clicking (same as CVR above)")

                    with attr_col3:
                        # Overall Rate (Sent)
                        if 'Sent' in journey_data.columns:
                            sent_total = journey_data['Sent'].sum()
                            overall_rate = (conversion_data['total_conversions'] / sent_total * 100) if sent_total > 0 else 0
                            st.metric("Overall Rate (Sent)", f"{overall_rate:.2%}",
                                     help="Sent → Conversions: End-to-end conversion rate from send to conversion")

                if 'revenue' in individual_analysis['raw_metrics']:
                    revenue_data = individual_analysis['raw_metrics']['revenue']
                    st.markdown("**💵 Revenue Performance:**")
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric(selected_rev_label, format_metric(revenue_data['total_revenue'], "SAR"))
                    with col2:
                        st.metric("Conversions", format_metric(revenue_data['total_conversions']))
                    with col3:
                        st.metric("Rev/Conversion", format_metric(revenue_data['revenue_per_conversion'], "SAR"))
                    with col4:
                        st.metric("Log(RPC)", f"{revenue_data['log_rpc']:.2f}")

            # Population Comparison & Percentiles
            with st.expander("📊 Population Comparison & Percentiles", expanded=True):
                st.markdown("**How this journey compares to all other journeys in your portfolio:**")

                percentile_cols = st.columns(2)
                with percentile_cols[0]:
                    if 'delivery' in individual_analysis['percentiles']:
                        perc = individual_analysis['percentiles']['delivery']
                        color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                        st.markdown(f"📤 **Delivery**: {color} {perc:.0f}th percentile")

                    if 'engagement' in individual_analysis['percentiles']:
                        perc = individual_analysis['percentiles']['engagement']
                        color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                        st.markdown(f"👆 **CTR**: {color} {perc:.0f}th percentile")

                with percentile_cols[1]:
                    if 'conversion' in individual_analysis['percentiles']:
                        perc = individual_analysis['percentiles']['conversion']
                        color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                        st.markdown(f"💰 **Conversion**: {color} {perc:.0f}th percentile")

                    if 'revenue' in individual_analysis['percentiles']:
                        perc = individual_analysis['percentiles']['revenue']
                        color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                        st.markdown(f"💵 **Revenue/Conv**: {color} {perc:.0f}th percentile")

            # Component Score Contributions
            with st.expander("🔢 Component Score Contributions", expanded=True):
                st.markdown("**How each component contributes to the final health score:**")

                # Create a detailed breakdown table
                contribution_data = []
                total_contribution = 0

                for component, details in individual_analysis['component_contributions'].items():
                    contribution_data.append({
                        'Component': component.capitalize(),
                        'Score': f"{details['score']:.1f}/100",
                        'Weight': f"{details['weight']:.0%}",
                        'Contribution': f"{details['contribution']:.1f} points"
                    })
                    total_contribution += details['contribution']

                # Display as a nice table
                contrib_df = pd.DataFrame(contribution_data)
                st.dataframe(contrib_df, width='stretch')

                # Show final calculation
                st.markdown(f"**🎯 Total Weighted Score: {total_contribution:.1f}/100**")

                # Show the weights explanation
                st.caption("💡 Weights: Conversion 30% (most critical for ROI) • Delivery 20% • Engagement 25% • Revenue 25%")

            # Key Insights & Problem Areas
            if individual_analysis['insights']:
                with st.expander("🎯 Key Insights & Problem Areas", expanded=True):
                    st.markdown("**Why this journey scored the way it did:**")
                    for insight in individual_analysis['insights']:
                        st.warning(insight)

            # Actionable Recommendations (already shown above but repeated here for completeness)
            st.markdown("**💡 Action Items for this Journey:**")
            for rec in individual_analysis['score_result']['recommendations']:
                st.info(rec)

# Advanced Funnel Analysis
st.subheader("🎯 Advanced Conversion Funnel Analysis")

funnel_journey = st.selectbox("Select Journey for Funnel Analysis",
                            unique_journeys,
                            key='funnel_journey')

if funnel_journey and str(funnel_journey) != 'nan':
    funnel_data = filtered_df[filtered_df['Journey Name'] == funnel_journey]
    funnel_analysis = analyze_journey_funnel(funnel_data)

    # Display funnel visualization
    if funnel_analysis['funnel_data']:
        funnel_stages = []
        funnel_values = []

        for stage, value in funnel_analysis['funnel_data'].items():
            if value > 0:
                funnel_stages.append(stage)
                funnel_values.append(value)

        if funnel_stages:
            fig_funnel = go.Figure(go.Funnel(
                y=funnel_stages,
                x=funnel_values,
                textposition="inside",
                textinfo="value+percent initial+percent previous",
                opacity=0.65,
                marker={"color": ["deepskyblue", "lightsalmon", "tan", "teal", "silver"]},
                connector={"line": {"color": "royalblue", "dash": "dot", "width": 3}}
            ))
            fig_funnel.update_layout(title=f"Conversion Funnel: {funnel_journey}")
            funnel_df = pd.DataFrame({'Stage': funnel_stages, 'Value': funnel_values})
            render_chart(fig_funnel, funnel_df, key="journey_funnel", ai_label=f"Conversion Funnel: {funnel_journey}")

    # Display conversion rates
    if funnel_analysis['conversion_rates']:
        st.subheader("📈 Conversion Rates Between Stages")
        rates_col1, rates_col2 = st.columns(2)

        rate_items = list(funnel_analysis['conversion_rates'].items())
        mid_point = len(rate_items) // 2

        with rates_col1:
            for rate_name, rate_value in rate_items[:mid_point]:
                st.metric(rate_name, f"{rate_value:.2%}")

        with rates_col2:
            for rate_name, rate_value in rate_items[mid_point:]:
                st.metric(rate_name, f"{rate_value:.2%}")

    # Display insights
    if funnel_analysis['insights']:
        st.subheader("🔍 Funnel Insights")
        for insight in funnel_analysis['insights']:
            st.warning(insight)

# Anomaly Detection
st.subheader("🚨 Journey Anomaly Detection")

col1, col2 = st.columns([2, 1])
with col2:
    lookback_days = st.slider("Analysis Period (days)", 7, 90, 30, key='anomaly_days')

with col1:
    st.write("Detecting unusual performance patterns in journeys...")

if st.button("🔍 Detect Anomalies", key='detect_anomalies'):
    with st.spinner("Analyzing journey performance patterns..."):
        anomalies = detect_journey_anomalies(filtered_df, lookback_days)

        if anomalies:
            st.subheader(f"🚨 {len(anomalies)} Anomalies Detected")

            # Group by severity
            critical_anomalies = [a for a in anomalies if '🚨 Critical' in a.get('severity', '')]
            warning_anomalies = [a for a in anomalies if '⚠️ Warning' in a.get('severity', '')]

            if critical_anomalies:
                st.error(f"🚨 {len(critical_anomalies)} Critical Issues Require Immediate Attention")
                for anomaly in critical_anomalies[:5]:  # Show top 5
                    with st.expander(f"{anomaly['journey']} - {anomaly['metric']} {anomaly.get('direction', '')}"):
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("Historical", f"{anomaly['historical_value']:.3f}")
                        with col2:
                            st.metric("Recent", f"{anomaly['recent_value']:.3f}")
                        with col3:
                            st.metric("Change", f"{anomaly['change_pct']:+.1f}%")
                        st.info(f"💡 {anomaly['recommendation']}")

            if warning_anomalies:
                st.warning(f"⚠️ {len(warning_anomalies)} Performance Changes Detected")
                with st.expander("View Warning Anomalies"):
                    for anomaly in warning_anomalies:
                        st.write(f"**{anomaly['journey']}** - {anomaly['metric']}: {anomaly['change_pct']:+.1f}% change")
                        st.write(f"   💡 {anomaly['recommendation']}")
        else:
            st.success("✅ No significant anomalies detected. All journeys are performing within normal ranges!")

# Revenue Attribution Waterfall
st.subheader("💰 Revenue Attribution Analysis")

waterfall_journey = st.selectbox("Select Journey for Revenue Attribution",
                               unique_journeys,
                               key='waterfall_journey')

if waterfall_journey and str(waterfall_journey) != 'nan':
    waterfall_data_full = filtered_df[filtered_df['Journey Name'] == waterfall_journey]
    waterfall_result = create_revenue_attribution_waterfall(waterfall_data_full)

    if waterfall_result['total_revenue'] > 0:
        # Proper waterfall chart showing attribution flow
        wf_data = waterfall_result['waterfall_data']
        wf_labels = [d['step'] for d in wf_data if d['step'] != 'Starting Point']
        wf_values = []
        wf_measures = []
        for d in wf_data:
            if d['step'] == 'Starting Point':
                continue
            if d['step'] == 'Total Revenue':
                wf_measures.append('total')
                wf_values.append(d['cumulative'])
            else:
                wf_measures.append('relative')
                wf_values.append(d['value'])

        fig_waterfall = go.Figure(go.Waterfall(
            x=wf_labels,
            y=wf_values,
            measure=wf_measures,
            text=[format_metric(v, "SAR") for v in wf_values],
            textposition='outside',
            connector=dict(line=dict(color='#E5E7EB', width=1)),
            increasing=dict(marker=dict(color=COLORS['primary'])),
            decreasing=dict(marker=dict(color=COLORS['danger'])),
            totals=dict(marker=dict(color=COLORS['success'])),
        ))
        fig_waterfall.update_layout(
            title=f"Revenue Attribution Breakdown: {waterfall_journey}",
            yaxis_title="Revenue (SAR)",
            showlegend=False,
        )
        wf_df = pd.DataFrame({'Step': wf_labels, 'Value (SAR)': wf_values, 'Measure': wf_measures})
        render_chart(fig_waterfall, wf_df, key="journey_waterfall", ai_label=f"Revenue Attribution Breakdown: {waterfall_journey}", width='stretch')

        # Attribution breakdown table
        st.subheader("📊 Attribution Breakdown")
        attr_col1, attr_col2 = st.columns(2)

        with attr_col1:
            for source, percentage in waterfall_result['attribution_breakdown'].items():
                st.metric(f"{source} Attribution", f"{percentage:.1f}%")

        with attr_col2:
            # Create pie chart for attribution
            fig_attr_pie = px.pie(
                values=list(waterfall_result['attribution_breakdown'].values()),
                names=list(waterfall_result['attribution_breakdown'].keys()),
                title="Revenue Attribution Distribution"
            )
            attr_pie_df = pd.DataFrame({
                'Source': list(waterfall_result['attribution_breakdown'].keys()),
                'Percentage': list(waterfall_result['attribution_breakdown'].values()),
            })
            render_chart(fig_attr_pie, attr_pie_df, key="journey_attr_pie", ai_label="Revenue Attribution Distribution")

        # Attribution insights
        st.subheader("🎯 Attribution Insights")
        max_source = max(waterfall_result['attribution_breakdown'], key=waterfall_result['attribution_breakdown'].get)
        max_percentage = waterfall_result['attribution_breakdown'][max_source]

        if max_percentage > 60:
            st.info(f"🎯 **{max_source}** is the dominant revenue driver ({max_percentage:.1f}%). Consider optimizing this channel further.")
        elif max_percentage < 40:
            st.info("🔄 Revenue is well-distributed across attribution sources. This indicates a healthy multi-touch journey.")
        else:
            st.info(f"⚖️ **{max_source}** leads revenue attribution. Monitor the balance between different touchpoints.")
    else:
        st.warning("No revenue data available for this journey.")

# Journey Lifecycle Analysis
st.subheader("🔄 Journey Lifecycle Analytics")

@st.cache_data
def _cached_lifecycle_analysis(filtered_df_json):
    filtered_df = read_cached_json(filtered_df_json)
    return analyze_journey_lifecycle(filtered_df)

with st.spinner("Analyzing journey maturity and performance curves..."):
    lifecycle_data = _cached_lifecycle_analysis(filtered_df.to_json())

    if lifecycle_data and not isinstance(lifecycle_data, dict) and len(lifecycle_data) > 0:
        lifecycle_df = pd.DataFrame(lifecycle_data)

        # Maturity distribution
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("📊 Journey Maturity Distribution")
            maturity_counts = lifecycle_df['maturity_stage'].value_counts()
            fig_maturity = px.pie(values=maturity_counts.values, names=maturity_counts.index,
                                title="Journeys by Maturity Stage")
            maturity_df = maturity_counts.reset_index()
            maturity_df.columns = ['Maturity Stage', 'Count']
            render_chart(fig_maturity, maturity_df, key="journey_maturity", ai_label="Journeys by Maturity Stage")

        with col2:
            st.subheader("📈 Performance vs Age")
            fig_age_perf = px.scatter(lifecycle_df,
                                    x='journey_age_days',
                                    y='efficiency_score',
                                    color='maturity_stage',
                                    size='total_revenue',
                                    hover_data=['journey', 'growth_trend'],
                                    title="Journey Performance vs Age")
            fig_age_perf.update_xaxes(title="Journey Age (Days)")
            fig_age_perf.update_yaxes(title="Efficiency Score")
            render_chart(fig_age_perf, lifecycle_df, key="journey_age_perf", ai_label="Journey Performance vs Age")

        # Lifecycle insights table
        st.subheader("🔍 Journey Lifecycle Insights")

        # Sort by efficiency score for display
        lifecycle_display = lifecycle_df.sort_values('efficiency_score', ascending=False)

        # Format the table for better readability
        display_cols = ['journey', 'maturity_stage', 'journey_age_days', 'activity_frequency',
                      'consistency_score', 'growth_trend', 'efficiency_score', 'recommendation']

        for idx, row in lifecycle_display.head(10).iterrows():
            with st.expander(f"{row['journey']} - {row['maturity_stage']} ({row['efficiency_score']:.1f} efficiency)"):
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Age", f"{row['journey_age_days']} days")
                    st.metric("Activity", f"{row['activity_frequency']:.1f}%")
                with col2:
                    st.metric("Consistency", f"{row['consistency_score']:.1f}/100")
                    st.metric("Trend", row['growth_trend'])
                with col3:
                    st.metric("Efficiency", f"{row['efficiency_score']:.1f}/100")
                    st.metric("Revenue", format_metric(row['total_revenue'], "SAR"))
                with col4:
                    st.metric("Conversions", format_metric(row['total_conversions']))
                    st.metric("Active Days", f"{row['active_days']}")

                st.info(f"💡 **Recommendation:** {row['recommendation']}")
    else:
        st.info("No journey lifecycle data available. Journeys need at least 2 data points over time for lifecycle analysis.")

# Journey Comparison Tool
st.subheader("🔄 Advanced Journey Comparison")

comparison_col1, comparison_col2 = st.columns(2)

with comparison_col1:
    journey_comp_1 = st.selectbox("Select First Journey", unique_journeys, key='compare_journey_1')
with comparison_col2:
    journey_comp_2 = st.selectbox("Select Second Journey",
                                [j for j in unique_journeys if j != journey_comp_1],
                                key='compare_journey_2')

if journey_comp_1 and journey_comp_2 and str(journey_comp_1) != 'nan' and str(journey_comp_2) != 'nan':
    if st.button("🔍 Compare Journeys", key='compare_button'):
        with st.spinner("Performing statistical comparison..."):
            comparison_result = create_journey_comparison_analysis(filtered_df, journey_comp_1, journey_comp_2)

            if 'error' not in comparison_result:
                st.subheader(f"📊 Comparison: {journey_comp_1} vs {journey_comp_2}")

                # Overall winner
                if comparison_result['overall_winner'] != "Tie":
                    st.success(f"🏆 **Overall Winner:** {comparison_result['overall_winner']} (Confidence: {comparison_result['confidence']})")
                else:
                    st.info("🤝 **Result:** Performance is very similar between both journeys")

                # Detailed metrics comparison
                st.subheader("📈 Detailed Metrics Comparison")

                for metric_name, metric_data in comparison_result['metrics'].items():
                    with st.expander(f"{metric_name} Comparison"):
                        comp_col1, comp_col2, comp_col3 = st.columns(3)

                        with comp_col1:
                            st.metric(f"{journey_comp_1} (Avg)",
                                    format_metric(metric_data['journey1_avg'], "SAR" if "Revenue" in metric_name else ""))
                            st.write(f"Total: {format_metric(metric_data['journey1_total'], 'SAR' if 'Revenue' in metric_name else '')}")

                        with comp_col2:
                            st.metric(f"{journey_comp_2} (Avg)",
                                    format_metric(metric_data['journey2_avg'], "SAR" if "Revenue" in metric_name else ""))
                            st.write(f"Total: {format_metric(metric_data['journey2_total'], 'SAR' if 'Revenue' in metric_name else '')}")

                        with comp_col3:
                            diff_color = "normal" if abs(metric_data['pct_difference']) < 10 else "inverse" if metric_data['pct_difference'] < 0 else "normal"
                            st.metric("Difference",
                                    f"{metric_data['pct_difference']:+.1f}%",
                                    delta=f"Winner: {metric_data['winner']}")

                            if metric_data['significance'] != "N/A":
                                significance_color = "🟢" if metric_data['significance'] == "Significant" else "🟡"
                                st.write(f"{significance_color} Statistical Significance: {metric_data['significance']}")
                                if metric_data['p_value']:
                                    st.write(f"p-value: {metric_data['p_value']:.4f}")

                # Recommendations based on comparison
                st.subheader("💡 Comparison Insights & Recommendations")

                winner = comparison_result['overall_winner']
                if winner != "Tie":
                    st.info(f"🎯 **Primary Recommendation:** Scale up **{winner}** and apply its successful elements to **{journey_comp_1 if winner == journey_comp_2 else journey_comp_2}**")

                    # Specific metric recommendations
                    strong_metrics = [name for name, data in comparison_result['metrics'].items() if data['winner'] == winner and abs(data['pct_difference']) > 20]
                    if strong_metrics:
                        st.success(f"🔥 **{winner}** excels in: {', '.join(strong_metrics)}")

                else:
                    st.info("🤝 Both journeys perform similarly. Consider A/B testing specific elements to find optimization opportunities.")

            else:
                st.error(f"Comparison failed: {comparison_result['error']}")


st.markdown("---")
st.info("📅 For period-over-period comparison analysis, see the **Comparisons** page under 🤖 AI & Forecasting.")

# Cohort Analysis Section
st.markdown("---")
st.subheader("👥 Cohort Performance Analysis")

cohort_period = st.selectbox("Select Cohort Period", ['week', 'month'], key='cohort_period')

if st.button("📊 Generate Cohort Analysis", key='run_cohort'):
    with st.spinner("Analyzing cohort performance..."):
        cohort_result = create_cohort_analysis(filtered_df, cohort_period)
        
        if isinstance(cohort_result, pd.DataFrame) and not cohort_result.empty:
            st.subheader(f"📈 {cohort_period.title()}ly Cohort Performance")
            
            # Display cohort data
            cohort_cc = {
                'Revenue (SAR)': st.column_config.NumberColumn(label='Revenue (SAR)', format='%.2f'),
                'Unique Conversions': st.column_config.NumberColumn(label='Unique Conversions', format='%.0f'),
            }
            render_table(cohort_result.head(20), key="cohort_analysis", column_config=cohort_cc)
            
            # Growth rate visualization
            if 'Revenue (SAR)_growth' in cohort_result.columns:
                fig_growth = px.line(cohort_result, 
                                   x='cohort_str', 
                                   y='Revenue (SAR)_growth', 
                                   color='Journey Name',
                                   title=f"Revenue Growth Rate by {cohort_period.title()}")
                fig_growth.update_xaxes(title=f"{cohort_period.title()} Period")
                fig_growth.update_yaxes(title="Growth Rate (%)")
                render_chart(fig_growth, cohort_result, key="cohort_growth", ai_label=f"Revenue Growth Rate by {cohort_period.title()}", width='stretch')
        
        else:
            st.warning("Insufficient data for cohort analysis")

# Top Journeys
st.subheader("Top Journeys")
jour_metric_options = ['Delivered Rate', 'Unique Clicks', 'Unique Conversions', 'Selected Revenue (SAR)', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
if 'Selected Revenue (SAR)' not in filtered_df.columns:
    jour_metric_options = [m for m in jour_metric_options if m != 'Selected Revenue (SAR)']
# Add conversion attribution options if they exist
if 'Unique Click-Through Conversions' in filtered_df.columns:
    jour_metric_options.insert(3, 'Unique Click-Through Conversions')
if 'Unique Impression-Through Conversions' in filtered_df.columns:
    jour_metric_options.insert(3, 'Unique Impression-Through Conversions')
jour_metric = st.selectbox("Metric", jour_metric_options, key='jour_metric', format_func=_attribution_display)

@st.cache_data
def _cached_top_journeys(filtered_df_json, jour_metric):
    filtered_df = read_cached_json(filtered_df_json)
    return get_top_journeys(filtered_df, jour_metric)

top_jour = _cached_top_journeys(filtered_df.to_json(), jour_metric)

# Build column config based on metric type for clean numeric display
if 'Rate' in jour_metric:
    # Convert rate to percentage
    top_jour[jour_metric] = top_jour[jour_metric] * 100

metric_fmt = '%.1f' if 'Rate' in jour_metric else ('%.2f' if 'Revenue' in jour_metric else '%.0f')
top_jour_cc = {
    attribution_rename.get(jour_metric, jour_metric): st.column_config.NumberColumn(
        label=_attribution_display(jour_metric),
        format=metric_fmt
    ),
}
render_table(top_jour.rename(columns=attribution_rename), key="top_journeys", column_config=top_jour_cc)

# Create chart with original numeric values
fig2 = px.bar(top_jour, x='Journey Name', y=jour_metric, title=f"Top Journeys by {_attribution_display(jour_metric)}",
              color_discrete_sequence=COLOR_SEQUENCE)
render_chart(fig2, top_jour, key="top_journeys_chart", ai_label=f"Top Journeys by {_attribution_display(jour_metric)}", width='stretch')

# Journey Drill-Down
st.subheader("Journey Drill-Down")
selected_journeys = st.multiselect("Select Journeys for Details", filtered_df['Journey Name'].unique(), key='drill_jour')
if selected_journeys:
    jour_details = filtered_df[filtered_df['Journey Name'].isin(selected_journeys)]
    
    # Summary KPIs
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Total Sent", format_metric(jour_details['Sent'].sum()))
    with col2:
        st.metric("Total Delivered", format_metric(jour_details['Delivered'].sum()))
    with col3:
        st.metric(selected_conv_label, format_metric(jour_details['Unique Conversions'].sum()))
    with col4:
        st.metric("Send-Through Revenue", format_metric(jour_details['Revenue (SAR)'].sum(), "SAR"))
    with col5:
        st.metric("Impression-Through Revenue", format_metric(jour_details['Impression-Through Revenue (SAR)'].sum(), "SAR"))
    with col6:
        st.metric("Click-Through Revenue", format_metric(jour_details['Click-Through Revenue (SAR)'].sum(), "SAR"))
    
    # Performance by Channel
    st.subheader("Performance by Channel")
    chan_perf_jour = jour_details.groupby('Channel').agg({
        'Sent': 'sum',
        'Delivered': 'sum',
        'Unique Conversions': 'sum',
        'Revenue (SAR)': 'sum',
        'Impression-Through Revenue (SAR)': 'sum',
        'Click-Through Revenue (SAR)': 'sum'
    }).reset_index()
    # Display table with column_config for clean numeric display
    chan_perf_cc = {
        'Sent': st.column_config.NumberColumn(label='Sent', format='compact'),
        'Delivered': st.column_config.NumberColumn(label='Delivered', format='compact'),
        'Unique Conversions': st.column_config.NumberColumn(label='Unique Conversions', format='compact'),
        'Revenue (SAR)': st.column_config.NumberColumn(label='Revenue (SAR)', format='compact'),
        'Impression-Through Revenue (SAR)': st.column_config.NumberColumn(label='Impression-Through Revenue (SAR)', format='compact'),
        'Click-Through Revenue (SAR)': st.column_config.NumberColumn(label='Click-Through Revenue (SAR)', format='compact'),
    }
    # Compute the "Total" pinned row from raw (unrounded) values.
    total_row_jour = {'Channel': 'Total'}
    for col in chan_perf_jour.columns:
        if col != 'Channel':
            total_row_jour[col] = chan_perf_jour[col].sum()
    render_table(chan_perf_jour, key="jour_channel_perf", column_config=chan_perf_cc, total_row=total_row_jour)
    
    # Chart data - chan_perf_jour is already numeric, no parsing needed
    conv_display_name = get_selected_conversion_display_name(conversion_attribution)
    fig_chan_jour = px.bar(chan_perf_jour, x='Channel', y='Unique Conversions',
                           title=f"{conv_display_name} by Channel for Selected Journeys",
                           color='Channel', color_discrete_map=CHANNEL_COLORS,
                           labels={'Unique Conversions': conv_display_name})
    fig_chan_jour.update_layout(showlegend=False)
    render_chart(fig_chan_jour, chan_perf_jour, key="jour_drilldown_channel", ai_label="Channel Performance for Selected Journeys", width='stretch')
    
    # Time Series for Selected Journeys
    st.subheader("Time Series Performance")
    # For rates, use mean; for counts/revenue, use sum
    if 'Rate' in jour_metric:
        ts_jour = jour_details.groupby(['Reporting Period Start Date', 'Journey Name'])[jour_metric].mean().reset_index()
    else:
        ts_jour = jour_details.groupby(['Reporting Period Start Date', 'Journey Name'])[jour_metric].sum().reset_index()
    if not ts_jour.empty:
        # Format y-axis for rates
        if 'Rate' in jour_metric:
            ts_jour[jour_metric] = ts_jour[jour_metric] * 100  # Convert to percentage for display
            fig_ts_jour = px.line(ts_jour, x='Reporting Period Start Date', y=jour_metric, color='Journey Name',
                                   title=f"{jour_metric} Over Time for Selected Journeys",
                                   color_discrete_sequence=COLOR_SEQUENCE)
            fig_ts_jour.update_yaxes(tickformat=".1f", title=f"{jour_metric} (%)")
        else:
            fig_ts_jour = px.line(ts_jour, x='Reporting Period Start Date', y=jour_metric, color='Journey Name',
                                   title=f"{jour_metric} Over Time for Selected Journeys",
                                   color_discrete_sequence=COLOR_SEQUENCE)
        fig_ts_jour.update_traces(line_width=2.5)
        render_chart(fig_ts_jour, ts_jour, key="jour_drilldown_ts", ai_label=f"{jour_metric} Over Time for Selected Journeys", width='stretch')
        
        # Journey Performance Insights
        st.subheader("📊 Journey Performance Insights")
        
        # Calculate gaps and stopped periods
        for journey in selected_journeys:
            journey_data = ts_jour[ts_jour['Journey Name'] == journey].copy()
            journey_data = journey_data.sort_values('Reporting Period Start Date')
            
            if len(journey_data) > 1:
                # Calculate gaps between dates
                journey_data['Date'] = pd.to_datetime(journey_data['Reporting Period Start Date'])
                journey_data['Days_Gap'] = journey_data['Date'].diff().dt.days
                
                # Find periods where journey was stopped (gaps > 7 days)
                stopped_periods = journey_data[journey_data['Days_Gap'] > 7]
                
                # Count total stopped days and periods
                total_stopped_days = stopped_periods['Days_Gap'].sum() if not stopped_periods.empty else 0
                total_stopped_periods = len(stopped_periods)
                
                if not stopped_periods.empty:
                    st.write(f"**{journey} - Campaign Interruptions:**")
                    st.write(f"• **Total Stopped Periods:** {total_stopped_periods}")
                    st.write(f"• **Total Days Stopped:** {int(total_stopped_days)} days")
                    
                    for _, row in stopped_periods.iterrows():
                        prev_date = journey_data[journey_data['Date'] < row['Date']].iloc[-1]['Date'] if len(journey_data[journey_data['Date'] < row['Date']]) > 0 else None
                        if prev_date is not None:
                            gap_days = int(row['Days_Gap'])
                            st.write(f"  - Stopped for {gap_days} days: {prev_date.strftime('%Y-%m-%d')} → {row['Date'].strftime('%Y-%m-%d')}")
                
                # Performance metrics - handle rates differently
                is_rate_metric = 'Rate' in jour_metric
                
                if is_rate_metric:
                    # For rates, show as percentages and calculate meaningful stats
                    avg_metric = journey_data[jour_metric].mean() * 100  # Convert to percentage
                    max_metric = journey_data[jour_metric].max() * 100
                    min_metric = journey_data[jour_metric].min() * 100
                    consistency = journey_data[jour_metric].std() * 100 if not journey_data[jour_metric].empty else 0
                    
                    # Weighted average by volume (if we have sent data)
                    journey_full_data = jour_details[jour_details['Journey Name'] == journey]
                    if not journey_full_data.empty and 'Sent' in journey_full_data.columns:
                        weighted_avg = (journey_full_data[jour_metric] * journey_full_data['Sent']).sum() / journey_full_data['Sent'].sum() * 100
                    else:
                        weighted_avg = avg_metric
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric(f"Average {jour_metric}", f"{avg_metric:.1f}%")
                    with col2:
                        st.metric(f"Volume-Weighted {jour_metric}", f"{weighted_avg:.1f}%")
                    with col3:
                        st.metric(f"Peak {jour_metric}", f"{max_metric:.1f}%")
                    with col4:
                        st.metric("Rate Variability", f"±{consistency:.1f}pp")
                    
                    st.info(f"💡 **Rate Explanation:** {jour_metric} shows delivery/conversion efficiency. Higher % = better performance. Volume-weighted average accounts for campaign size.")
                
                else:
                    # For count/revenue metrics, use original calculations
                    total_metric = journey_data[jour_metric].sum()
                    avg_metric = journey_data[jour_metric].mean()
                    max_metric = journey_data[jour_metric].max()
                    min_metric = journey_data[jour_metric].min()
                    consistency = journey_data[jour_metric].std() / journey_data[jour_metric].mean() if journey_data[jour_metric].mean() > 0 else 0
                    
                    col1, col2, col3, col4 = st.columns(4)
                    with col1:
                        st.metric(f"Total {jour_metric.replace(' (SAR)', '')}", format_metric(total_metric, "SAR" if "Revenue" in jour_metric else ""))
                    with col2:
                        st.metric(f"Average {jour_metric.replace(' (SAR)', '')}", format_metric(avg_metric, "SAR" if "Revenue" in jour_metric else ""))
                    with col3:
                        st.metric(f"Peak {jour_metric.replace(' (SAR)', '')}", format_metric(max_metric, "SAR" if "Revenue" in jour_metric else ""))
                    with col4:
                        st.metric("Consistency", f"{consistency:.2f}")
                    
                    st.info(f"💡 **{jour_metric.replace(' (SAR)', '')} Explanation:** {jour_metric} represents total volume. Consistency shows performance stability (lower = more consistent).")
                
                # Trend analysis
                if len(journey_data) >= 3:
                    if is_rate_metric:
                        recent_avg = journey_data[jour_metric].tail(3).mean() * 100
                        earlier_avg = journey_data[jour_metric].head(len(journey_data)-3).mean() * 100 if len(journey_data) > 3 else journey_data[jour_metric].mean() * 100
                    else:
                        recent_avg = journey_data[jour_metric].tail(3).mean()
                        earlier_avg = journey_data[jour_metric].head(len(journey_data)-3).mean() if len(journey_data) > 3 else journey_data[jour_metric].mean()
                    
                    if earlier_avg > 0:
                        trend_pct = ((recent_avg - earlier_avg) / earlier_avg) * 100
                        trend_direction = "📈 Improving" if trend_pct > 5 else "📉 Declining" if trend_pct < -5 else "➡️ Stable"
                        st.write(f"**Trend:** {trend_direction} ({trend_pct:+.1f}% change in recent performance)")
                
                # Best and worst performing periods
                if is_rate_metric:
                    best_period = journey_data.loc[journey_data[jour_metric].idxmax()]
                    worst_period = journey_data.loc[journey_data[jour_metric].idxmin()]
                    best_value = best_period[jour_metric] * 100
                    worst_value = worst_period[jour_metric] * 100
                    unit = "%"
                else:
                    best_period = journey_data.loc[journey_data[jour_metric].idxmax()]
                    worst_period = journey_data.loc[journey_data[jour_metric].idxmin()]
                    best_value = best_period[jour_metric]
                    worst_value = worst_period[jour_metric]
                    unit = "SAR" if "Revenue" in jour_metric else ""
                
                st.write(f"**Best Period:** {best_period['Reporting Period Start Date'].strftime('%Y-%m-%d')} with {format_metric(best_value, unit)}")
                st.write(f"**Worst Period:** {worst_period['Reporting Period Start Date'].strftime('%Y-%m-%d')} with {format_metric(worst_value, unit)}")
                
                # Activity frequency
                total_days = (journey_data['Date'].max() - journey_data['Date'].min()).days + 1  # +1 to include both start and end
                active_days = len(journey_data)
                frequency = active_days / max(total_days, 1) * 100
                st.write(f"**Activity Frequency:** {frequency:.1f}% of days had activity ({active_days}/{max(total_days, 1)} days)")
                
                # Lost Revenue Estimation for Stopped Periods
                if total_stopped_days > 0 and not is_rate_metric and 'Revenue' in jour_metric:
                    st.subheader("💰 Lost Revenue Estimation")
                    
                    # Calculate average daily revenue during active periods
                    active_revenue = journey_data[jour_metric].sum()
                    active_days_calc = len(journey_data)
                    avg_daily_revenue = active_revenue / active_days_calc if active_days_calc > 0 else 0
                    
                    estimated_lost_revenue = avg_daily_revenue * total_stopped_days
                    
                    st.warning(f"⚠️ **Estimated Lost Revenue:** {format_metric(estimated_lost_revenue, 'SAR')} over {int(total_stopped_days)} stopped days")
                    st.write(f"   - Based on average daily revenue of {format_metric(avg_daily_revenue, 'SAR')} from {selected_revenue}")
                    st.write(f"   - This represents {estimated_lost_revenue/active_revenue*100:.1f}% of total journey revenue if stopped periods had performed at average levels")
                    
                    # Prophet-based estimation if enough data
                    if len(journey_data) >= 7:  # Need minimum data for Prophet
                        try:
                            st.write("**AI-Powered Revenue Projection:**")
                            # Prepare data for Prophet
                            prophet_data = journey_data[['Date', jour_metric]].rename(columns={'Date': 'ds', jour_metric: 'y'})
                            
                            model = Prophet(daily_seasonality=True)
                            model.fit(prophet_data)
                            
                            # Create future dates including the stopped periods
                            last_date = prophet_data['ds'].max()
                            future_dates = pd.date_range(start=journey_data['Date'].min(), end=last_date, freq='D')
                            future_df = pd.DataFrame({'ds': future_dates})
                            
                            forecast = model.predict(future_df)
                            
                            # Calculate what revenue would have been during stopped periods
                            stopped_dates = []
                            for _, row in stopped_periods.iterrows():
                                prev_date = journey_data[journey_data['Date'] < row['Date']].iloc[-1]['Date'] if len(journey_data[journey_data['Date'] < row['Date']]) > 0 else None
                                if prev_date is not None:
                                    gap_dates = pd.date_range(start=prev_date + pd.Timedelta(days=1), end=row['Date'] - pd.Timedelta(days=1), freq='D')
                                    stopped_dates.extend(gap_dates)
                            
                            if stopped_dates:
                                stopped_forecast = forecast[forecast['ds'].isin(stopped_dates)]
                                ai_estimated_lost = stopped_forecast['yhat'].sum()
                                st.info(f"🤖 **AI Estimated Lost Revenue:** {format_metric(ai_estimated_lost, 'SAR')} (using Prophet forecasting)")
                                st.write("   - This accounts for seasonal patterns and trends in the data")
                            
                        except Exception as e:
                            st.write(f"AI forecasting not available: {str(e)}")
                
            else:
                st.write(f"**{journey}:** Insufficient data for detailed analysis (only {len(journey_data)} data point)")
    else:
        st.write("No time series data available for selected journeys.")
    
    # Conversion Attribution
    st.subheader("Conversion Attribution")
    attr_jour = {
        'Impression-Through': jour_details['Unique Impression-Through Conversions'].sum(),
        'Click-Through': jour_details['Unique Click-Through Conversions'].sum(),
        'Direct/Open-Through': jour_details['Unique Conversions'].sum() - jour_details['Unique Impression-Through Conversions'].sum() - jour_details['Unique Click-Through Conversions'].sum()
    }
    attr_df_jour = pd.DataFrame(list(attr_jour.items()), columns=['Source', 'Conversions'])
    fig_attr_jour = px.pie(attr_df_jour, names='Source', values='Conversions', title="Attribution for Selected Journeys",
                            color_discrete_sequence=COLOR_SEQUENCE)
    render_chart(fig_attr_jour, attr_df_jour, key="jour_drilldown_attr", ai_label="Attribution for Selected Journeys", width='stretch')

    # Failed Reasons for Selected Journeys
    st.subheader("Failed Reasons")
    failed_cols = [col for col in jour_details.columns if 'Failed' in col and col != 'Failed']
    if failed_cols:
        failed_jour = jour_details[failed_cols].sum().reset_index().rename(columns={'index': 'Reason', 0: 'Count'})
        fig_fail_jour = px.bar(failed_jour, x='Reason', y='Count', title="Failed Reasons for Selected Journeys",
                               color_discrete_sequence=[COLORS['danger']])
        render_chart(fig_fail_jour, failed_jour, key="jour_drilldown_failed", ai_label="Failed Reasons for Selected Journeys", width='stretch')

# 🚨 Stopped Journey Analysis with Revenue Loss Estimation
st.markdown("---")
st.header("🚨 Stopped Journey Analysis & Revenue Loss Estimation")

st.markdown("""
**🎯 Advanced Analytics for Journey Performance Issues**

This analysis identifies journeys with zero delivery periods and estimates revenue loss using:
- **📊 Statistical Forecasting**: Time-series analysis with confidence intervals
- **🎪 Multiple Attribution Models**: Send-through, impression-through, and click-through revenue
- **📈 Machine Learning**: Prophet model for revenue prediction during stopped periods
- **💰 Loss Quantification**: Daily revenue loss estimation with confidence ranges
""")

# Analysis parameters
stopped_col1, stopped_col2, stopped_col3 = st.columns(3)

with stopped_col1:
    stopped_threshold_days = st.slider("🚫 Stopped Threshold (days)", 1, 14, 3,
                                     help="Minimum consecutive days with zero delivery to consider journey 'stopped'")
    st.write(f"**Threshold:** {stopped_threshold_days} consecutive zero-delivery days")

with stopped_col2:
    lookback_period = st.slider("📅 Analysis Period (days)", 30, 180, 90,
                              help="How far back to analyze journey performance")
    st.write(f"**Analysis Window:** {lookback_period} days")

with stopped_col3:
    confidence_level = st.selectbox("🎯 Confidence Level", [0.80, 0.90, 0.95, 0.99], index=2,
                                  help="Statistical confidence level for revenue loss estimates")
    st.write(f"**Confidence:** {int(confidence_level*100)}%")

if st.button("🔍 Analyze Stopped Journeys", key='analyze_stopped'):
    with st.spinner("🔄 Analyzing journey delivery patterns and estimating revenue loss..."):

        # Create stopped journey analysis
        stopped_analysis = analyze_stopped_journeys(
            filtered_df,
            stopped_threshold_days=stopped_threshold_days,
            lookback_period=lookback_period,
            confidence_level=confidence_level
        )

        if stopped_analysis and 'stopped_journeys' in stopped_analysis:

            stopped_journeys = stopped_analysis['stopped_journeys']

            if stopped_journeys:
                st.error(f"🚨 **{len(stopped_journeys)} Journeys Identified with Stopped Delivery**")
                
                # Check for journeys that were never active
                never_active_count = 0
                for journey in stopped_journeys:
                    for period in journey['stopped_periods']['periods']:
                        if not period.get('was_active_before', True):
                            never_active_count += 1
                            break  # Count journey only once
                
                if never_active_count > 0:
                    st.warning(f"⚠️ **Note:** {never_active_count} journey(s) had zero delivery periods but were never active before. These might be journeys that haven't launched yet rather than journeys that stopped.")

                # Summary metrics
                total_revenue_loss = sum(journey['estimated_revenue_loss']['total_loss'] for journey in stopped_journeys)
                total_stopped_days = sum(journey['stopped_periods']['total_stopped_days'] for journey in stopped_journeys)

                summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)

                with summary_col1:
                    st.metric("🚫 Stopped Journeys", len(stopped_journeys))
                with summary_col2:
                    st.metric("📅 Total Stopped Days", format_metric(total_stopped_days))
                with summary_col3:
                    st.metric("💰 Total Revenue Loss", format_metric(total_revenue_loss, "SAR"))
                with summary_col4:
                    avg_daily_loss = total_revenue_loss / total_stopped_days if total_stopped_days > 0 else 0
                    st.metric("📊 Avg Daily Loss", format_metric(avg_daily_loss, "SAR"))

                # Detailed analysis for each stopped journey
                st.subheader("🔍 Detailed Stopped Journey Analysis")

                for journey in stopped_journeys:
                    journey_name = journey['journey_name']

                    with st.expander(f"🚨 {journey_name} - Revenue Loss: {format_metric(journey['estimated_revenue_loss']['total_loss'], 'SAR')}", expanded=True):

                        # Journey overview
                        overview_col1, overview_col2, overview_col3 = st.columns(3)

                        with overview_col1:
                            st.metric("📅 Stopped Days", journey['stopped_periods']['total_stopped_days'])
                            st.metric("📊 Stopped Periods", len(journey['stopped_periods']['periods']))

                        with overview_col2:
                            loss_data = journey['estimated_revenue_loss']
                            st.metric("💰 Total Loss", format_metric(loss_data['total_loss'], "SAR"))
                            st.metric("📈 Daily Loss", format_metric(loss_data['avg_daily_loss'], "SAR"))

                        with overview_col3:
                            confidence_range = loss_data['confidence_interval']
                            st.metric("🎯 Confidence Range",
                                    f"{format_metric(confidence_range[0], 'SAR')} - {format_metric(confidence_range[1], 'SAR')}")
                            
                            # Show model quality indicator
                            model_quality = loss_data.get('model_quality', 'medium')
                            if model_quality == 'high':
                                quality_icon = "✅"
                                quality_label = "High Reliability"
                                quality_color = "green"
                            elif model_quality == 'medium':
                                quality_icon = "⚠️"
                                quality_label = "Moderate Reliability"
                                quality_color = "orange"
                            else:
                                quality_icon = "ℹ️"
                                quality_label = "Directional Estimate"
                                quality_color = "gray"
                            
                            st.markdown(f"<div style='padding: 10px; border-left: 4px solid {quality_color};'>"
                                      f"{quality_icon} <b>{quality_label}</b></div>", 
                                      unsafe_allow_html=True)

                        # Revenue attribution breakdown
                        st.subheader("💰 Revenue Loss by Attribution Model")

                        attr_loss_col1, attr_loss_col2, attr_loss_col3 = st.columns(3)

                        loss_breakdown = loss_data['attribution_breakdown']

                        with attr_loss_col1:
                            send_loss = loss_breakdown.get('Revenue (SAR)', 0)
                            st.metric("📊 Send-Through Loss", format_metric(send_loss, "SAR"))

                        with attr_loss_col2:
                            impression_loss = loss_breakdown.get('Impression-Through Revenue (SAR)', 0)
                            st.metric("👁️ Impression-Through Loss", format_metric(impression_loss, "SAR"))

                        with attr_loss_col3:
                            click_loss = loss_breakdown.get('Click-Through Revenue (SAR)', 0)
                            st.metric("🖱️ Click-Through Loss", format_metric(click_loss, "SAR"))

                        # Stopped periods timeline
                        st.subheader("📅 Stopped Periods Timeline")

                        periods_data = journey['stopped_periods']['periods']
                        if periods_data:
                            periods_df = pd.DataFrame(periods_data)

                            # Create timeline visualization
                            fig_timeline = go.Figure()

                            for _, period in periods_df.iterrows():
                                fig_timeline.add_trace(go.Scatter(
                                    x=[period['start_date'], period['end_date']],
                                    y=[journey_name, journey_name],
                                    mode='lines+markers',
                                    name=f"Stopped Period ({period['days_stopped']} days)",
                                    line=dict(color=COLORS['danger'], width=4),
                                    marker=dict(size=8, color=COLORS['danger']),
                                    showlegend=False
                                ))

                            fig_timeline.update_layout(
                                title=f"Stopped Delivery Periods: {journey_name}",
                                xaxis_title="Date",
                                yaxis_title="Journey",
                                showlegend=False,
                                height=200
                            )

                            render_chart(fig_timeline, periods_df, key=f"stopped_timeline_{journey_name}", ai_label=f"Stopped Delivery Periods: {journey_name}")

                            # Detailed periods table
                            st.subheader("📋 Stopped Period Details")
                            periods_display = periods_df.copy()
                            
                            # Calculate expected days from dates for verification
                            periods_display['calculated_days'] = (
                                (periods_display['end_date'] - periods_display['start_date']).dt.days + 1
                            )
                            
                            # Format dates
                            periods_display['start_date'] = periods_display['start_date'].dt.strftime('%Y-%m-%d')
                            periods_display['end_date'] = periods_display['end_date'].dt.strftime('%Y-%m-%d')
                            
                            # Add verification indicator
                            periods_display['days_match'] = periods_display.apply(
                                lambda row: '✓' if row['days_stopped'] == row['calculated_days'] else f'⚠️ Mismatch!',
                                axis=1
                            )
                            
                            # Store raw numeric values - no format_metric on DataFrame columns
                            # Add activity information (string column, keep as-is)
                            if 'was_active_before' in periods_display.columns:
                                periods_display['Status'] = periods_display.apply(
                                    lambda row: f"✅ Was Active ({format_metric(row['active_days_before_stop'])} days, avg: {format_metric(row['avg_delivery_before_stop'])} delivered)"
                                    if row.get('was_active_before', False)
                                    else "⚠️ Never Active",
                                    axis=1
                                )
                                display_cols = ['start_date', 'end_date', 'days_stopped', 'calculated_days', 'days_match', 'Status']
                            else:
                                display_cols = ['start_date', 'end_date', 'days_stopped', 'calculated_days', 'days_match']

                            # Add estimated_daily_loss if available; use NaN for missing
                            if 'estimated_daily_loss' not in periods_display.columns:
                                periods_display['estimated_daily_loss'] = np.nan
                            display_cols.append('estimated_daily_loss')

                            # Use column_config for clean numeric display
                            periods_cc = {
                                'days_stopped': st.column_config.NumberColumn(label='Days Stopped', format='%.0f'),
                                'calculated_days': st.column_config.NumberColumn(label='Calculated Days', format='%.0f'),
                                'estimated_daily_loss': st.column_config.NumberColumn(label='Est. Daily Loss (SAR)', format='%.2f'),
                            }
                            render_table(periods_display[display_cols], key="stopped_periods", column_config=periods_cc)

                        # Recommendations
                        st.subheader("💡 Recommendations & Actions")

                        recommendations = journey.get('recommendations', [])

                        if recommendations:
                            for rec in recommendations:
                                st.info(f"🎯 {rec}")
                        else:
                            st.info("🔍 **Analysis Complete:** Review journey configuration and delivery settings to prevent future stoppages.")

            else:
                st.success("✅ **No Stopped Journeys Detected!** All journeys are actively delivering.")

        else:
            st.error("❌ Analysis failed. Please check your data and try again.")
