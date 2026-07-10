import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric, style_total_row
from config import COLORS, COLOR_SEQUENCE
from attribution import get_attribution_display_label
from dashboard.comparisons_logic import calculate_period_metrics, calculate_metric_changes

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


st.header("📊 Period-over-Period Comparisons")
st.markdown("*Analyze performance trends across different time periods with detailed metrics*")

# Check if comparison is enabled
if comparison_result:
    st.success(f"✅ Comparison Mode Active: **{comparison_result['current_label']}** vs **{comparison_result['comparison_label']}**")

    # Calculate comprehensive metrics
    current_metrics = calculate_period_metrics(comparison_result['current_data'], comparison_result['current_days'], conversion_attribution)
    comp_metrics = calculate_period_metrics(comparison_result['comparison_data'], comparison_result['comparison_days'], conversion_attribution)
    metric_changes = calculate_metric_changes(current_metrics, comp_metrics)

    # === EXECUTIVE SUMMARY ===
    st.markdown("---")
    st.subheader("📈 Executive Summary")

    # Key highlights
    revenue_trend = metric_changes['selected_revenue']
    conv_trend = metric_changes['selected_conversions']
    ctr_trend = metric_changes['ctr']
    delivery_trend = metric_changes['delivery_rate']

    # Determine overall trend
    positive_trends = sum([
        revenue_trend['pct_change'] > 0,
        conv_trend['pct_change'] > 0,
        ctr_trend['pct_change'] > 0,
        delivery_trend['pct_change'] > 0
    ])

    if positive_trends >= 3:
        st.success("🎯 **Overall Trend: POSITIVE** - Most metrics are improving")
    elif positive_trends >= 2:
        st.info("➡️ **Overall Trend: MIXED** - Some metrics improving, others declining")
    else:
        st.warning("⚠️ **Overall Trend: NEEDS ATTENTION** - Most metrics are declining")

    # Key metrics comparison
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Revenue Change",
            f"{revenue_trend['pct_change']:+.1f}%",
            delta=format_metric(revenue_trend['absolute_change'], "SAR")
        )

    with col2:
        st.metric(
            "Conversion Change",
            f"{conv_trend['pct_change']:+.1f}%",
            delta=format_metric(conv_trend['absolute_change'])
        )

    with col3:
        st.metric(
            "CTR Change",
            f"{ctr_trend['pct_change']:+.1f}%",
            delta=f"{ctr_trend['absolute_change']:+.2%}"
        )

    with col4:
        st.metric(
            "Delivery Rate Change",
            f"{delivery_trend['pct_change']:+.1f}%",
            delta=f"{delivery_trend['absolute_change']:+.2%}"
        )

    # Business Intelligence Metrics
    st.markdown("#### 💰 Business Intelligence")
    biz_col1, biz_col2, biz_col3 = st.columns(3)

    aov_trend = metric_changes['aov']
    rpc_trend = metric_changes['revenue_per_click']
    eng_trend = metric_changes['engagement_rate']

    with biz_col1:
        st.metric(
            "AOV Change",
            f"{aov_trend['pct_change']:+.1f}%",
            delta=format_metric(aov_trend['absolute_change'], "SAR"),
            help="Average Order Value - Revenue per conversion"
        )

    with biz_col2:
        st.metric(
            "RPC Change",
            f"{rpc_trend['pct_change']:+.1f}%",
            delta=format_metric(rpc_trend['absolute_change'], "SAR"),
            help="Revenue Per Click - Measures click quality"
        )

    with biz_col3:
        st.metric(
            "Engagement Rate Change",
            f"{eng_trend['pct_change']:+.1f}%",
            delta=f"{eng_trend['absolute_change']:+.2%}",
            help="Combined engagement (clicks + opens) / impressions"
        )

    # ROI & Cost Efficiency
    st.markdown("#### 💵 ROI & Cost Efficiency")
    cost_col1, cost_col2, cost_col3, cost_col4 = st.columns(4)

    roas_trend = metric_changes['roas']
    rps_trend = metric_changes['revenue_per_send']
    cpc_trend = metric_changes['cost_per_conversion']
    profit_trend = metric_changes['profit']

    with cost_col1:
        current_roas = roas_trend['current']
        if current_roas >= 4:
            roas_status = "🟢"
        elif current_roas >= 2:
            roas_status = "🟡"
        else:
            roas_status = "🔴"

        st.metric(
            f"ROAS Change {roas_status}",
            f"{roas_trend['pct_change']:+.1f}%",
            delta=f"{roas_trend['current']:.2f}x now",
            help=f"Return on Ad Spend: {roas_trend['current']:.2f}x (was {roas_trend['comparison']:.2f}x)"
        )

    with cost_col2:
        st.metric(
            "Revenue Per Send Change",
            f"{rps_trend['pct_change']:+.1f}%",
            delta=f"{rps_trend['absolute_change']:.4f} SAR",
            help="KEY efficiency metric - answers your 'doubled sends, less revenue' question"
        )

    with cost_col3:
        st.metric(
            "Cost Per Conversion",
            f"{cpc_trend['pct_change']:+.1f}%",
            delta=format_metric(cpc_trend['absolute_change'], "SAR"),
            delta_color="inverse" if cpc_trend['pct_change'] >= 0 else "normal",
            help="Lower is better"
        )

    with cost_col4:
        st.metric(
            "Profit Change",
            f"{profit_trend['pct_change']:+.1f}%",
            delta=format_metric(profit_trend['absolute_change'], "SAR"),
            help="Revenue - Cost"
        )

    # === DETAILED METRICS TABLE ===
    st.markdown("---")
    st.subheader("📊 Detailed Metrics Comparison")

    # Create comparison dataframe
    comparison_data = []
    metric_names = {
        'selected_revenue': ('Total Revenue (SAR)', 'SAR'),
        'selected_conversions': ('Total Conversions', ''),
        'total_clicks': ('Total Clicks', ''),
        'total_impressions': ('Total Impressions', ''),
        'total_sent': ('Total Sent', ''),
        'total_delivered': ('Total Delivered', ''),
        'total_cost': ('Total Campaign Cost', 'SAR'),
        'profit': ('Profit (Revenue - Cost)', 'SAR'),
        'ctr': ('Click-Through Rate', '%'),
        'conversion_rate': ('Conversion Rate', '%'),
        'delivery_rate': ('Delivery Rate', '%'),
        'aov': ('Average Order Value (AOV)', 'SAR'),
        'revenue_per_click': ('Revenue Per Click (RPC)', 'SAR'),
        'revenue_per_send': ('Revenue Per Send (RPS)', 'SAR'),
        'engagement_rate': ('Engagement Rate', '%'),
        'roas': ('ROAS (Return on Ad Spend)', 'ratio'),
        'cost_per_conversion': ('Cost Per Conversion', 'SAR'),
        'cost_per_click': ('Cost Per Click', 'SAR'),
        'profit_margin': ('Profit Margin', '%'),
        'revenue_per_conversion': ('Revenue per Conversion', 'SAR'),
        'daily_revenue': ('Daily Avg Revenue', 'SAR'),
        'daily_conversions': ('Daily Avg Conversions', ''),
        'daily_cost': ('Daily Avg Cost', 'SAR'),
    }

    for metric_key, (metric_label, unit) in metric_names.items():
        if metric_key in metric_changes:
            change_data = metric_changes[metric_key]

            if unit == '%':
                current_val = f"{change_data['current']:.2%}"
                comp_val = f"{change_data['comparison']:.2%}"
            elif unit == 'SAR':
                current_val = format_metric(change_data['current'], 'SAR')
                comp_val = format_metric(change_data['comparison'], 'SAR')
            elif unit == 'ratio':
                current_val = f"{change_data['current']:.2f}x"
                comp_val = f"{change_data['comparison']:.2f}x"
            else:
                current_val = format_metric(change_data['current'])
                comp_val = format_metric(change_data['comparison'])

            comparison_data.append({
                'Metric': metric_label,
                'Current Period': current_val,
                'Comparison Period': comp_val,
                'Change %': f"{change_data['pct_change']:+.1f}%",
                'Trend': change_data['trend']
            })

    comparison_df = pd.DataFrame(comparison_data)
    st.dataframe(comparison_df, width='stretch')

    # === VISUALIZATION ===
    st.markdown("---")
    st.subheader("📈 Visual Comparison")

    # Select metric to visualize
    viz_metric = st.selectbox(
        "Select Metric to Visualize",
        ["Revenue (SAR)", "Conversions", "Clicks", "CTR", "Conversion Rate", "Delivery Rate"],
        key="comparison_viz_metric"
    )

    # Map selection to data keys
    viz_mapping = {
        "Revenue (SAR)": 'selected_revenue',
        "Conversions": 'selected_conversions',
        "Clicks": 'total_clicks',
        "CTR": 'ctr',
        "Conversion Rate": 'conversion_rate',
        "Delivery Rate": 'delivery_rate'
    }

    selected_key = viz_mapping[viz_metric]
    change_data = metric_changes[selected_key]

    # Create comparison bar chart
    fig_comparison = go.Figure()

    fig_comparison.add_trace(go.Bar(
        name='Comparison Period',
        x=[comparison_result['comparison_label']],
        y=[change_data['comparison']],
        marker_color=COLORS['info'],
        text=[format_metric(change_data['comparison'], 'SAR' if 'Revenue' in viz_metric else '')],
        textposition='auto'
    ))

    fig_comparison.add_trace(go.Bar(
        name='Current Period',
        x=[comparison_result['current_label']],
        y=[change_data['current']],
        marker_color=COLORS['success'] if change_data['pct_change'] > 0 else COLORS['danger'],
        text=[format_metric(change_data['current'], 'SAR' if 'Revenue' in viz_metric else '')],
        textposition='auto'
    ))

    fig_comparison.update_layout(
        title=f"{viz_metric} Comparison",
        xaxis_title="Period",
        yaxis_title=viz_metric,
        barmode='group',
        height=400
    )

    st.plotly_chart(fig_comparison, width='stretch')

    # === CHANNEL-LEVEL COMPARISON ===
    if 'Channel' in comparison_result['current_data'].columns:
        st.markdown("---")
        st.subheader("📡 Channel-Level Comparison")

        # Aggregate by channel for both periods
        current_by_channel = comparison_result['current_data'].groupby('Channel').agg({
            'Selected Revenue (SAR)': 'sum',
            'Selected Conversions': 'sum',
            'Unique Clicks': 'sum'
        }).reset_index()

        comp_by_channel = comparison_result['comparison_data'].groupby('Channel').agg({
            'Selected Revenue (SAR)': 'sum',
            'Selected Conversions': 'sum',
            'Unique Clicks': 'sum'
        }).reset_index()

        # Merge and calculate changes
        channel_comparison = current_by_channel.merge(
            comp_by_channel,
            on='Channel',
            how='outer',
            suffixes=('_current', '_comp')
        ).fillna(0)

        channel_comparison['Revenue Change %'] = ((channel_comparison['Selected Revenue (SAR)_current'] - channel_comparison['Selected Revenue (SAR)_comp']) /
                                                  channel_comparison['Selected Revenue (SAR)_comp'].replace(0, 1) * 100)

        channel_comparison['Conversion Change %'] = ((channel_comparison['Selected Conversions_current'] - channel_comparison['Selected Conversions_comp']) /
                                                     channel_comparison['Selected Conversions_comp'].replace(0, 1) * 100)

        # Display
        channel_display = channel_comparison[['Channel', 'Revenue Change %', 'Conversion Change %']].copy()
        st.dataframe(channel_display, width='stretch')

        # Channel comparison chart
        fig_channel = go.Figure()

        fig_channel.add_trace(go.Bar(
            name='Revenue Change %',
            x=channel_comparison['Channel'],
            y=channel_comparison['Revenue Change %'],
            marker_color=[COLORS['success'] if x > 0 else COLORS['danger'] for x in channel_comparison['Revenue Change %']]
        ))

        fig_channel.update_layout(
            title="Revenue Change % by Channel",
            xaxis_title="Channel",
            yaxis_title="Change %",
            height=400
        )

        st.plotly_chart(fig_channel, width='stretch')

    # === INSIGHTS & RECOMMENDATIONS ===
    st.markdown("---")
    st.subheader("💡 Insights & Recommendations")

    insights = []

    # Revenue insights
    if revenue_trend['pct_change'] > 10:
        insights.append(f"✅ **Strong Revenue Growth**: Revenue increased by {revenue_trend['pct_change']:.1f}%. Consider scaling successful campaigns.")
    elif revenue_trend['pct_change'] < -10:
        insights.append(f"⚠️ **Revenue Decline**: Revenue decreased by {abs(revenue_trend['pct_change']):.1f}%. Investigate underperforming channels and campaigns.")

    # Conversion insights
    if conv_trend['pct_change'] > 10:
        insights.append(f"✅ **Conversion Improvement**: Conversions up {conv_trend['pct_change']:.1f}%. Current strategies are working well.")
    elif conv_trend['pct_change'] < -10:
        insights.append(f"⚠️ **Conversion Drop**: Conversions down {abs(conv_trend['pct_change']):.1f}%. Review landing pages and offers.")

    # CTR insights
    if ctr_trend['pct_change'] > 10:
        insights.append(f"✅ **Engagement Increase**: CTR improved by {ctr_trend['pct_change']:.1f}%. Content resonates with audience.")
    elif ctr_trend['pct_change'] < -10:
        insights.append(f"⚠️ **Engagement Decline**: CTR down {abs(ctr_trend['pct_change']):.1f}%. Consider refreshing creative assets.")

    # Delivery insights
    if delivery_trend['pct_change'] < -5:
        insights.append(f"🚨 **Delivery Issue**: Delivery rate dropped {abs(delivery_trend['pct_change']):.1f}%. Check ESP settings and sender reputation.")

    # Display insights
    if insights:
        for insight in insights:
            st.markdown(f"- {insight}")
    else:
        st.info("Performance is relatively stable with no significant changes to highlight.")

else:
    st.info("🔍 **No Comparison Selected** - Enable comparison mode in the sidebar to analyze period-over-period trends")
    st.markdown("---")

    # Show month-over-month trend analysis as fallback
    st.subheader("📅 Monthly Trend Analysis")

    # Group by month
    monthly_df = filtered_df.copy()
    monthly_df['Month'] = monthly_df['Reporting Period Start Date'].dt.to_period('M').astype(str)

    monthly_agg = monthly_df.groupby('Month').agg({
        'Revenue (SAR)': 'sum',
        'Unique Conversions': 'sum',
        'Unique Clicks': 'sum',
        'Sent': 'sum',
        'Delivered': 'sum'
    }).reset_index()

    # Sort by month
    monthly_agg['Month'] = pd.to_datetime(monthly_agg['Month'] + '-01')
    monthly_agg = monthly_agg.sort_values('Month')
    monthly_agg['Month'] = monthly_agg['Month'].dt.strftime('%Y-%m')

    if not monthly_agg.empty and len(monthly_agg) > 1:
        st.subheader("Monthly Summary")
        # Add total row
        total_row_monthly = {'Month': 'Total'}
        for col in monthly_agg.columns:
            if col != 'Month':
                total_row_monthly[col] = monthly_agg[col].sum()
        monthly_agg_with_total = pd.concat([monthly_agg, pd.DataFrame([total_row_monthly])], ignore_index=True)
        # Format columns for display
        monthly_agg_display = monthly_agg_with_total.copy()
        monthly_agg_display['Revenue (SAR)'] = monthly_agg_display['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
        monthly_agg_display['Unique Conversions'] = monthly_agg_display['Unique Conversions'].apply(format_metric)
        monthly_agg_display['Unique Clicks'] = monthly_agg_display['Unique Clicks'].apply(format_metric)
        monthly_agg_display['Sent'] = monthly_agg_display['Sent'].apply(format_metric)
        monthly_agg_display['Delivered'] = monthly_agg_display['Delivered'].apply(format_metric)
        st.dataframe(style_total_row(monthly_agg_display), width='stretch', hide_index=True)

        # Chart
        fig_comp = px.line(monthly_agg, x='Month', y='Revenue (SAR)', title="Revenue Over Months", markers=True)
        st.plotly_chart(fig_comp, width='stretch')
    else:
        st.write("Not enough monthly data for trend analysis.")
