import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric, export_chart_image
from config import CHANNEL_COSTS, COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import get_selected_revenue_display_name, get_selected_conversion_display_name
from analysis import failed_reasons_analysis
from dashboard.comparisons_logic import (
    calculate_period_metrics, calculate_metric_changes, calculate_uplift_significance,
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

# Display-friendly rename map for attribution-selected columns (mirrors app.py prelude)
attribution_rename = {'Selected Revenue (SAR)': selected_rev_label, 'Selected Conversions': selected_conv_label}

st.header("Overview")

# Executive narrative summary
_total_rev = filtered_df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in filtered_df.columns else filtered_df['Revenue (SAR)'].sum()
_total_conv = int(filtered_df['Selected Conversions'].sum() if 'Selected Conversions' in filtered_df.columns else filtered_df['Unique Conversions'].sum())
_total_sent = int(filtered_df['Sent'].sum()) if 'Sent' in filtered_df.columns else 0
_n_campaigns = filtered_df['Campaign Name'].nunique() if 'Campaign Name' in filtered_df.columns else 0
_n_channels = filtered_df['Channel'].nunique() if 'Channel' in filtered_df.columns else 0
_date_min = filtered_df['Reporting Period Start Date'].min().strftime('%b %d, %Y') if 'Reporting Period Start Date' in filtered_df.columns else ''
_date_max = filtered_df['Reporting Period Start Date'].max().strftime('%b %d, %Y') if 'Reporting Period Start Date' in filtered_df.columns else ''

st.markdown(
    f"**{_date_min} - {_date_max}** | "
    f"**{format_metric(_total_rev, 'SAR')}** revenue from "
    f"**{_total_conv:,}** conversions across "
    f"**{_n_campaigns:,}** campaigns on **{_n_channels}** channels "
    f"({format_metric(_total_sent)} messages sent)"
)
st.markdown("---")

# Calculate metrics with comparison
if comparison_result:
    current_metrics = calculate_period_metrics(comparison_result['current_data'], comparison_result['current_days'], conversion_attribution)
    comp_metrics = calculate_period_metrics(comparison_result['comparison_data'], comparison_result['comparison_days'], conversion_attribution)
    metric_changes = calculate_metric_changes(current_metrics, comp_metrics)
    
    # Display metrics with comparisons
    col1, col2, col3 = st.columns(3)
    with col1:
        change_data = metric_changes['selected_revenue']
        st.metric(
            selected_rev_label, 
            f"{change_data['current']:,.0f} SAR",
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
        )
        change_data = metric_changes['selected_conversions']
        st.metric(
            selected_conv_label, 
            f"{change_data['current']:,.0f}",
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
        )
    with col2:
        change_data = metric_changes['total_clicks']
        st.metric(
            "Total Clicks", 
            f"{change_data['current']:,.0f}",
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
        )
        change_data = metric_changes['total_impressions']
        st.metric(
            "Total Impressions", 
            f"{change_data['current']:,.0f}",
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
        )
    with col3:
        change_data = metric_changes['ctr']
        st.metric(
            "Avg CTR", 
            f"{change_data['current']:.2%}",
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
        )
        change_data = metric_changes['conversion_rate']
        st.metric(
            "Avg Conversion Rate", 
            f"{change_data['current']:.2%}",
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
        )
        
        # Control Group Uplift
        if 'control_group_uplift' in metric_changes:
            change_data = metric_changes['control_group_uplift']
            st.metric(
                "Control Group Uplift",
                f"{change_data['current']:+.1f}%" if change_data['current'] is not None else "N/A",
                delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})" if change_data['comparison'] is not None else None,
                delta_color="normal" if change_data.get('pct_change', 0) >= 0 else "inverse",
                help="Uplift vs Control Group: (Test Conv Rate - Control Conv Rate) / Control Conv Rate"
            )
        else:
            change_data = metric_changes['delivery_rate']
            st.metric(
                "Avg Delivery Rate", 
                f"{change_data['current']:.2%}",
                delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
            )
    
    # NEW: Business Intelligence Metrics Row
    st.markdown("---")
    st.subheader("💰 Business Intelligence Metrics")
    biz_col1, biz_col2, biz_col3 = st.columns(3)
    
    with biz_col1:
        change_data = metric_changes['aov']
        st.metric(
            "Average Order Value (AOV)", 
            format_metric(change_data['current'], "SAR"),
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
            help="Revenue per conversion - shows average customer purchase value"
        )
    
    with biz_col2:
        change_data = metric_changes['revenue_per_click']
        st.metric(
            "Revenue Per Click (RPC)", 
            format_metric(change_data['current'], "SAR"),
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
            help="Revenue generated per click - measures click quality"
        )
    
    with biz_col3:
        change_data = metric_changes['engagement_rate']
        st.metric(
            "Engagement Rate", 
            f"{change_data['current']:.2%}",
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
            help="Combined engagement metric (clicks + opens) / impressions"
        )
    
    # NEW: ROI & Cost Efficiency Metrics
    st.markdown("---")
    st.subheader("💵 ROI & Cost Efficiency")
    cost_display = ", ".join(f"{ch} ({c} SAR/1k)" for ch, c in CHANNEL_COSTS.items() if c > 0)
    st.caption(f"*Based on channel costs: {cost_display}*")
    
    roi_col1, roi_col2, roi_col3, roi_col4 = st.columns(4)
    
    with roi_col1:
        change_data = metric_changes['roas']
        current_roas = change_data['current']
        # ROAS interpretation
        if current_roas >= 4:
            roas_status = "🟢 Excellent"
        elif current_roas >= 2:
            roas_status = "🟡 Good"
        elif current_roas >= 1:
            roas_status = "🟠 Break-even"
        else:
            roas_status = "🔴 Unprofitable"
        
        st.metric(
            "ROAS (Return on Ad Spend)", 
            f"{current_roas:.2f}x",
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
            help=f"Revenue / Cost ratio. {roas_status}"
        )
        st.caption(f"Status: {roas_status}")
    
    with roi_col2:
        change_data = metric_changes['revenue_per_send']
        st.metric(
            "Revenue Per Send (RPS)", 
            f"{change_data['current']:.4f} SAR",
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
            help="Revenue generated per message sent - KEY efficiency indicator"
        )
    
    with roi_col3:
        change_data = metric_changes['cost_per_conversion']
        st.metric(
            "Cost Per Conversion", 
            format_metric(change_data['current'], "SAR"),
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="inverse" if change_data['pct_change'] >= 0 else "normal",  # Lower is better
            help="How much you spend to acquire each conversion"
        )
    
    with roi_col4:
        change_data = metric_changes['profit']
        st.metric(
            "Profit (Revenue - Cost)", 
            format_metric(change_data['current'], "SAR"),
            delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
            delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
            help="Net profit after campaign costs"
        )
    
    # Comparison summary card
    st.markdown("---")
    st.subheader("📊 Period Comparison Summary")
    sum_col1, sum_col2, sum_col3 = st.columns(3)
    
    with sum_col1:
        st.markdown(f"**Current Period:** {comparison_result['current_label']}")
        st.markdown(f"- Duration: {comparison_result['current_days']} days")
        st.markdown(f"- Daily Avg Revenue: {format_metric(current_metrics['daily_revenue'], 'SAR')}")
        st.markdown(f"- Daily Avg Conversions: {format_metric(current_metrics['daily_conversions'])}")
    
    with sum_col2:
        st.markdown(f"**Comparison Period:** {comparison_result['comparison_label']}")
        st.markdown(f"- Duration: {comparison_result['comparison_days']} days")
        st.markdown(f"- Daily Avg Revenue: {format_metric(comp_metrics['daily_revenue'], 'SAR')}")
        st.markdown(f"- Daily Avg Conversions: {format_metric(comp_metrics['daily_conversions'])}")
    
    with sum_col3:
        st.markdown("**Key Changes:**")
        revenue_change = metric_changes['selected_revenue']['pct_change']
        conv_change = metric_changes['selected_conversions']['pct_change']
        ctr_change = metric_changes['ctr']['pct_change']
        
        if revenue_change > 0:
            st.success(f"✅ Revenue: {revenue_change:+.1f}%")
        else:
            st.error(f"⚠️ Revenue: {revenue_change:+.1f}%")
        
        if conv_change > 0:
            st.success(f"✅ Conversions: {conv_change:+.1f}%")
        else:
            st.error(f"⚠️ Conversions: {conv_change:+.1f}%")
        
        if ctr_change > 0:
            st.success(f"✅ CTR: {ctr_change:+.1f}%")
        else:
            st.error(f"⚠️ CTR: {ctr_change:+.1f}%")

else:
    # No comparison - show regular metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        total_revenue = filtered_df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in filtered_df.columns else filtered_df['Revenue (SAR)'].sum()
        st.metric(selected_rev_label, f"{total_revenue:,.0f} SAR")
        total_conv = filtered_df['Selected Conversions'].sum() if 'Selected Conversions' in filtered_df.columns else filtered_df['Unique Conversions'].sum()
        st.metric(selected_conv_label, f"{total_conv:,.0f}")
    with col2:
        st.metric("Total Unique Clicks", f"{filtered_df['Unique Clicks'].sum():,.0f}")
        st.metric("Total Unique Impressions", f"{filtered_df['Unique Impressions'].sum():,.0f}")
    with col3:
        st.metric("Avg CTR", f"{filtered_df['CTR'].mean():.2%}")
        # Calculate conversion rate from raw data
        total_clicks = filtered_df['Unique Clicks'].sum()
        conv_col = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'
        total_conversions = filtered_df[conv_col].sum()
        avg_conv_rate = (total_conversions / total_clicks) if total_clicks > 0 else 0
        st.metric("Avg Conversion Rate", f"{avg_conv_rate:.2%}")
        
        # Calculate Control Group Uplift (respects attribution selection)
        if 'Total in Control Group' in filtered_df.columns and 'Unique Control Group Conversions' in filtered_df.columns:
            # Filter campaigns with control groups
            control_campaigns = filtered_df[filtered_df['Total in Control Group'] > 0]
            if not control_campaigns.empty:
                # Aggregate totals
                total_control_group = control_campaigns['Total in Control Group'].sum()
                total_control_conversions = control_campaigns['Unique Control Group Conversions'].sum()
                
                # Use selected conversions based on attribution
                if 'Selected Conversions' in control_campaigns.columns:
                    test_conversions = control_campaigns['Selected Conversions'].sum()
                else:
                    test_conversions = control_campaigns['Unique Conversions'].sum()
                
                # Determine denominator based on attribution type
                if conversion_attribution == "Impression-Through":
                    test_denominator = control_campaigns['Unique Impressions'].sum()
                    denominator_label = "Impressions"
                elif conversion_attribution == "Click-Through":
                    test_denominator = control_campaigns['Unique Clicks'].sum()
                    denominator_label = "Clicks"
                else:  # Total
                    test_denominator = control_campaigns['Sent'].sum()
                    denominator_label = "Sent"
                
                # Calculate rates and significance
                if test_denominator > 0 and total_control_group > 0 and total_control_conversions > 0:
                    test_conv_rate = test_conversions / test_denominator
                    control_conv_rate = total_control_conversions / total_control_group
                    uplift_pct = ((test_conv_rate - control_conv_rate) / control_conv_rate) * 100
                    
                    # Calculate statistical significance
                    p_value, is_significant, reliability = calculate_uplift_significance(
                        test_conversions, test_denominator,
                        total_control_conversions, total_control_group
                    )
                    
                    # Build help text with significance info
                    help_text = f"Uplift vs Control Group ({conversion_attribution})\n"
                    help_text += f"Campaign Conv Rate: {test_conv_rate:.2%} ({test_conversions:,.0f}/{test_denominator:,.0f} {denominator_label})\n"
                    help_text += f"Control Group Conv Rate: {control_conv_rate:.2%} ({total_control_conversions:,.0f}/{total_control_group:,.0f})\n"
                    help_text += f"\nReliability: {reliability}\n"
                    
                    if p_value is not None:
                        # Display p-value professionally
                        if p_value < 0.0001:
                            p_display = "p < 0.0001"
                        else:
                            p_display = f"p = {p_value:.4f}"
                        help_text += f"Statistical Significance: {p_display}\n"
                        help_text += f"{'✓ Significant' if is_significant else '✗ Not significant'} at 95% confidence\n"
                    
                    help_text += f"\nFormula: (Campaign Rate - Control Rate) / Control Rate"
                    
                    # Add asterisk for statistical significance (professional standard)
                    sig_indicator = "*" if is_significant and p_value is not None else ""
                    reliability_emoji = reliability.split()[0]  # Extract emoji from reliability string
                    
                    st.metric(
                        f"Control Group Uplift {reliability_emoji}", 
                        f"{uplift_pct:+.1f}%{sig_indicator}",
                        help=help_text
                    )
                    # Add small note below metric
                    st.caption("*Based on campaigns with control groups only. Other metrics show all campaigns.")
                else:
                    st.metric("Avg Delivery Rate", f"{filtered_df['Delivery Rate'].mean():.2%}")
            else:
                st.metric("Avg Delivery Rate", f"{filtered_df['Delivery Rate'].mean():.2%}")
        else:
            st.metric("Avg Delivery Rate", f"{filtered_df['Delivery Rate'].mean():.2%}")

# Conversion Funnel - aggregate pipeline view
st.markdown("---")
st.subheader("Conversion Pipeline")
funnel_sent = filtered_df['Sent'].sum() if 'Sent' in filtered_df.columns else 0
funnel_delivered = filtered_df['Delivered'].sum() if 'Delivered' in filtered_df.columns else 0
funnel_impressions = filtered_df['Unique Impressions'].sum() if 'Unique Impressions' in filtered_df.columns else 0
funnel_clicks = filtered_df['Unique Clicks'].sum() if 'Unique Clicks' in filtered_df.columns else 0
funnel_conversions = filtered_df['Unique Conversions'].sum() if 'Unique Conversions' in filtered_df.columns else 0

funnel_stages = ['Sent', 'Delivered', 'Impressions', 'Clicks', 'Conversions']
funnel_values = [funnel_sent, funnel_delivered, funnel_impressions, funnel_clicks, funnel_conversions]
# Only show stages with data
active_stages = [(s, v) for s, v in zip(funnel_stages, funnel_values) if v > 0]

if active_stages:
    stages, values = zip(*active_stages)
    funnel_col1, funnel_col2 = st.columns([3, 2])
    with funnel_col1:
        fig_funnel = go.Figure(go.Funnel(
            y=list(stages),
            x=list(values),
            textposition="inside",
            textinfo="value+percent initial+percent previous",
            opacity=0.85,
            marker={"color": [COLORS['primary'], COLORS['info'], COLORS['warning'],
                              COLORS['secondary'], COLORS['success']][:len(stages)]},
            connector={"line": {"color": COLORS['muted'], "dash": "dot", "width": 2}}
        ))
        fig_funnel.update_layout(
            title="Aggregate Conversion Funnel",
            margin=dict(l=120, r=20, t=50, b=20),
            height=350,
        )
        st.plotly_chart(fig_funnel, use_container_width=True)
        img_funnel = export_chart_image(fig_funnel)
        if img_funnel:
            st.download_button("Download Funnel Chart", img_funnel, "conversion_funnel.png", "image/png", key='dl_funnel')

    with funnel_col2:
        st.markdown("**Stage-to-Stage Conversion Rates**")
        if funnel_sent > 0 and funnel_delivered > 0:
            st.metric("Delivery Rate", f"{funnel_delivered / funnel_sent:.2%}",
                      help="Sent → Delivered")
        if funnel_delivered > 0 and funnel_impressions > 0:
            st.metric("Impression Rate", f"{funnel_impressions / funnel_delivered:.2%}",
                      help="Delivered → Impressions (opened/viewed)")
        if funnel_impressions > 0 and funnel_clicks > 0:
            st.metric("Click-Through Rate", f"{funnel_clicks / funnel_impressions:.2%}",
                      help="Impressions → Clicks")
        if funnel_clicks > 0 and funnel_conversions > 0:
            st.metric("Conversion Rate", f"{funnel_conversions / funnel_clicks:.2%}",
                      help="Clicks → Conversions")
        if funnel_sent > 0 and funnel_conversions > 0:
            st.metric("Overall Pipeline Rate", f"{funnel_conversions / funnel_sent:.4%}",
                      help="Sent → Conversions (end-to-end)")

# Channels Overview Section
st.markdown("---")
st.subheader("📡 Channels Overview")
st.markdown("*Performance breakdown by marketing channel*")

if 'Channel' in filtered_df.columns:
    # Get channel data - determine revenue and conversion columns
    revenue_col_to_use = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
    conv_col_to_use = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'
    
    agg_dict = {
        'Sent': 'sum',
        'Delivered': 'sum',
        'Unique Impressions': 'sum',
        'Unique Clicks': 'sum',
    }
    
    # Always aggregate the conversion column being used
    agg_dict[conv_col_to_use] = 'sum'
    
    # Also aggregate Unique Conversions if it's different (needed for fallback calculations)
    if conv_col_to_use != 'Unique Conversions' and 'Unique Conversions' in filtered_df.columns:
        agg_dict['Unique Conversions'] = 'sum'
    
    # Add Click-Through Conversions if available (for accurate conversion rate)
    if 'Unique Click-Through Conversions' in filtered_df.columns:
        agg_dict['Unique Click-Through Conversions'] = 'sum'
    
    if revenue_col_to_use in filtered_df.columns:
        agg_dict[revenue_col_to_use] = 'sum'
    
    channel_data = filtered_df.groupby('Channel').agg(agg_dict).reset_index()
    
    # Calculate rates for each channel from raw counts (not pre-calculated rates)
    # Using raw metrics ensures correct calculation at channel level
    channel_data['Delivery Rate'] = np.where(
        channel_data['Sent'] > 0,
        (channel_data['Delivered'] / channel_data['Sent'] * 100),
        0
    ).round(1)
    
    channel_data['CTR'] = np.where(
        channel_data['Unique Impressions'] > 0,
        (channel_data['Unique Clicks'] / channel_data['Unique Impressions'] * 100),
        0
    ).round(2)
    
    # Conversion Rate - Use Click-Through Conversions for accurate rate
    # (Total conversions includes impression-through which didn't click)
    if 'Unique Click-Through Conversions' in channel_data.columns:
        channel_data['Conversion Rate'] = np.where(
            channel_data['Unique Clicks'] > 0,
            (channel_data['Unique Click-Through Conversions'] / channel_data['Unique Clicks'] * 100),
            0
        ).round(2)
    else:
        # Fallback to total conversions if click-through not available
        channel_data['Conversion Rate'] = np.where(
            channel_data['Unique Clicks'] > 0,
            (channel_data['Unique Conversions'] / channel_data['Unique Clicks'] * 100),
            0
        ).round(2)
    
    # Calculate business metrics for channels
    revenue_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in channel_data.columns else 'Revenue (SAR)'
    # Use the selected conversion column for calculations
    conv_col_for_calc = conv_col_to_use if conv_col_to_use in channel_data.columns else 'Unique Conversions'
    
    # AOV - Average Order Value (Revenue per Conversion) - uses selected attribution
    channel_data['AOV'] = np.where(
        channel_data[conv_col_for_calc] > 0,
        channel_data[revenue_col] / channel_data[conv_col_for_calc],
        0
    ).round(2)
    
    # RPC - Revenue Per Click
    channel_data['RPC'] = np.where(
        channel_data['Unique Clicks'] > 0,
        channel_data[revenue_col] / channel_data['Unique Clicks'],
        0
    ).round(2)
    
    # Calculate cost-based metrics for channels (uses centralized CHANNEL_COSTS)
    channel_data['Cost'] = channel_data.apply(
        lambda row: (row['Sent'] / 1000) * CHANNEL_COSTS.get(row['Channel'], 0),
        axis=1
    ).round(2)
    
    # ROAS - Return on Ad Spend
    channel_data['ROAS'] = np.where(
        channel_data['Cost'] > 0,
        channel_data[revenue_col] / channel_data['Cost'],
        0
    ).round(2)
    
    # Revenue Per Send (RPS)
    channel_data['RPS'] = np.where(
        channel_data['Sent'] > 0,
        channel_data[revenue_col] / channel_data['Sent'],
        0
    ).round(4)
    
    # Cost Per Conversion (CPC) - uses selected attribution
    channel_data['CPC'] = np.where(
        channel_data[conv_col_for_calc] > 0,
        channel_data['Cost'] / channel_data[conv_col_for_calc],
        0
    ).round(2)
    
    # Sort by revenue
    channel_data = channel_data.sort_values(revenue_col, ascending=False)
    
    # Define channel icons and status
    channel_icons = {
        'Email': '📧',
        'SMS': '💬',
        'Push': '🔔',
        'Web Push': '🌐',
        'Mobile Push': '📱',
        'App Push': '📱',
        'WhatsApp': '💚',
        'In-App': '📲',
        'On-Site': '🖥️',
        'Onsite': '🖥️',
        'On-site': '🖥️',
        'Facebook': '👤',
        'Google': '🔍'
    }
    
    # Check comparison data for channel performance
    channel_comparison = {}
    if comparison_result:
        # Determine columns for comparison
        comp_rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in comparison_result['current_data'].columns else 'Revenue (SAR)'
        comp_conv_col = 'Selected Conversions' if 'Selected Conversions' in comparison_result['current_data'].columns else 'Unique Conversions'
        
        current_channel_agg = {}
        comp_channel_agg = {}
        
        if comp_rev_col in comparison_result['current_data'].columns:
            current_channel_agg[comp_rev_col] = 'sum'
            comp_channel_agg[comp_rev_col] = 'sum'
        if comp_conv_col in comparison_result['current_data'].columns:
            current_channel_agg[comp_conv_col] = 'sum'
            comp_channel_agg[comp_conv_col] = 'sum'
        
        current_channel_data = comparison_result['current_data'].groupby('Channel').agg(current_channel_agg)
        comp_channel_data = comparison_result['comparison_data'].groupby('Channel').agg(comp_channel_agg)
        
        for channel in current_channel_data.index:
            if channel in comp_channel_data.index:
                curr_rev = current_channel_data.loc[channel, comp_rev_col]
                comp_rev = comp_channel_data.loc[channel, comp_rev_col]
                
                if comp_rev > 0:
                    rev_change = ((curr_rev - comp_rev) / comp_rev) * 100
                else:
                    rev_change = 0
                
                channel_comparison[channel] = {
                    'revenue_change': rev_change,
                    'trend': '↗' if rev_change > 1 else '↘' if rev_change < -1 else '→'
                }
    
    # Display channel cards in a grid
    num_channels = len(channel_data)
    
    if num_channels > 0:
        # Show top-level summary
        st.markdown("#### Active Channels Performance")
        
        # Create channel cards
        cols_per_row = 4
        rows_needed = (num_channels + cols_per_row - 1) // cols_per_row
        
        idx = 0
        for row in range(rows_needed):
            cols = st.columns(cols_per_row)
            
            for col_idx, col in enumerate(cols):
                if idx < num_channels:
                    channel_row = channel_data.iloc[idx]
                    channel_name = channel_row['Channel']
                    
                    # Get icon
                    icon = channel_icons.get(channel_name, '📊')
                    
                    with col:
                        # Determine if channel is active (has recent data)
                        is_active = channel_row['Sent'] > 0
                        
                        # Card styling based on activity
                        if is_active:
                            st.markdown(f"**{icon} {channel_name}**")
                            
                            # Show comparison if available
                            if channel_name in channel_comparison:
                                comp_info = channel_comparison[channel_name]
                                trend_indicator = comp_info['trend']
                                change_pct = comp_info['revenue_change']
                                
                                if change_pct > 0:
                                    st.success(f"{trend_indicator} {change_pct:+.1f}%")
                                elif change_pct < 0:
                                    st.error(f"{trend_indicator} {change_pct:+.1f}%")
                                else:
                                    st.info(f"{trend_indicator} {change_pct:+.1f}%")
                            else:
                                st.markdown("✅ **Active**")
                            
                            # Key metrics
                            revenue_val = channel_row[revenue_col]
                            # Use selected conversion column (respects attribution choice)
                            conv_val = channel_row[conv_col_to_use] if conv_col_to_use in channel_row else channel_row.get('Unique Conversions', 0)
                            delivery_rate = channel_row['Delivery Rate']
                            ctr = channel_row['CTR']
                            aov_val = channel_row['AOV']
                            rpc_val = channel_row['RPC']
                            cost_val = channel_row['Cost']
                            roas_val = channel_row['ROAS']
                            rps_val = channel_row['RPS']
                            
                            # Get raw counts for better display
                            impressions = channel_row['Unique Impressions']
                            clicks = channel_row['Unique Clicks']
                            
                            st.metric("Revenue", format_metric(revenue_val, "SAR"))
                            st.metric("Conversions", format_metric(conv_val))
                            
                            # Always show AOV if there are conversions (important business metric)
                            if conv_val > 0:
                                st.markdown(f"<small>💰 <span title='Average Order Value - Revenue per conversion' style='cursor: help;'>AOV</span>: {format_metric(aov_val, 'SAR')}</small>", unsafe_allow_html=True)
                            
                            # Show cost efficiency (highlight for paid channels)
                            if cost_val > 0:
                                st.markdown(f"<small>💵 Cost: {format_metric(cost_val, 'SAR')}</small>", unsafe_allow_html=True)
                                # ROAS color coding with tooltip
                                if roas_val >= 4:
                                    st.markdown(f"<small>📈 <span title='Return on Ad Spend - Revenue earned per SAR spent (4x = 4 SAR revenue per 1 SAR cost)' style='cursor: help;'>ROAS</span>: **{roas_val:.1f}x** 🟢</small>", unsafe_allow_html=True)
                                elif roas_val >= 2:
                                    st.markdown(f"<small>📈 <span title='Return on Ad Spend - Revenue earned per SAR spent (4x = 4 SAR revenue per 1 SAR cost)' style='cursor: help;'>ROAS</span>: **{roas_val:.1f}x** 🟡</small>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"<small>📈 <span title='Return on Ad Spend - Revenue earned per SAR spent (4x = 4 SAR revenue per 1 SAR cost)' style='cursor: help;'>ROAS</span>: **{roas_val:.1f}x** 🔴</small>", unsafe_allow_html=True)
                                st.markdown(f"<small>💰 <span title='Revenue Per Send - Revenue generated per message sent' style='cursor: help;'>RPS</span>: {rps_val:.4f} SAR</small>", unsafe_allow_html=True)
                            else:
                                # Free channels - show RPC
                                if clicks > 0:
                                    st.markdown(f"<small>🎯 <span title='Revenue Per Click - Revenue generated per click' style='cursor: help;'>RPC</span>: {format_metric(rpc_val, 'SAR')}</small>", unsafe_allow_html=True)
                            
                            # Show rates in smaller text with context and tooltips
                            st.markdown(f"<small>📨 Delivery: {delivery_rate:.1f}%</small>", unsafe_allow_html=True)
                            
                            # Show CTR with context and tooltip - some channels don't track impressions
                            if impressions > 0:
                                st.markdown(f"<small>👆 <span title='Click-Through Rate - Percentage of impressions that resulted in clicks' style='cursor: help;'>CTR</span>: {ctr:.2f}% ({format_metric(clicks)} clicks)</small>", unsafe_allow_html=True)
                            else:
                                st.markdown(f"<small>👆 <span title='Click-Through Rate - Percentage of impressions that resulted in clicks' style='cursor: help;'>CTR</span>: N/A (no impression tracking)</small>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"**{icon} {channel_name}**")
                            st.warning("❌ Inactive")
                            st.caption("No activity this period")
                    
                    idx += 1
        
        # Detailed channel comparison table
        st.markdown("---")
        st.markdown("#### Detailed Channel Metrics")
        st.caption("*Conversion Rate = Click-Through Conversions / Unique Clicks. Hover over abbreviated metrics for full names.*")
        
        # Create display dataframe
        channel_display = channel_data.copy()
        channel_display['Channel'] = channel_display['Channel'].apply(lambda x: f"{channel_icons.get(x, '📊')} {x}")
        channel_display['Sent'] = channel_display['Sent'].apply(format_metric)
        channel_display['Delivered'] = channel_display['Delivered'].apply(format_metric)
        channel_display['Unique Clicks'] = channel_display['Unique Clicks'].apply(format_metric)
        
        # Format the selected conversion column
        if conv_col_for_calc in channel_display.columns:
            channel_display[conv_col_for_calc] = channel_display[conv_col_for_calc].apply(format_metric)
        
        channel_display[revenue_col] = channel_display[revenue_col].apply(lambda x: format_metric(x, "SAR"))
        
        # Select columns to display - use selected conversion column
        display_cols = ['Channel', 'Sent', 'Delivered', 'Delivery Rate', 'Unique Clicks', 
                       'CTR', conv_col_for_calc, 'Conversion Rate', revenue_col]
        channel_display = channel_display[display_cols]
        
        # Rename columns to show actual attribution model
        channel_display = channel_display.rename(columns=attribution_rename)
        
        st.dataframe(channel_display, use_container_width=True, hide_index=True)
        
        # Channel performance charts
        col1, col2 = st.columns(2)
        
        with col1:
            # Revenue by channel - use consistent channel colors
            rev_display_name = get_selected_revenue_display_name(revenue_attribution)
            fig_channel_revenue = px.bar(
                channel_data,
                x='Channel',
                y=revenue_col,
                title=f"{rev_display_name} by Channel",
                color='Channel',
                color_discrete_map=CHANNEL_COLORS,
                labels={revenue_col: rev_display_name}
            )
            fig_channel_revenue.update_layout(showlegend=False)
            st.plotly_chart(fig_channel_revenue, use_container_width=True)

        with col2:
            # Conversions by channel - use consistent channel colors
            conv_display_name = get_selected_conversion_display_name(conversion_attribution)
            fig_channel_conv = px.bar(
                channel_data,
                x='Channel',
                y='Unique Conversions',
                title=f"{conv_display_name} by Channel",
                color='Channel',
                color_discrete_map=CHANNEL_COLORS,
                labels={'Unique Conversions': conv_display_name}
            )
            fig_channel_conv.update_layout(showlegend=False)
            st.plotly_chart(fig_channel_conv, use_container_width=True)
        
        # Channel insights
        st.markdown("#### 💡 Channel Insights")
        
        # Find best and worst performing channels
        if len(channel_data) > 0:
            best_revenue_channel = channel_data.iloc[0]
            best_conv_rate_channel = channel_data.loc[channel_data['Conversion Rate'].idxmax()]
            best_ctr_channel = channel_data.loc[channel_data['CTR'].idxmax()]
            
            insight_col1, insight_col2, insight_col3 = st.columns(3)
            
            with insight_col1:
                st.success(f"**🏆 Top Revenue Channel**")
                st.markdown(f"{channel_icons.get(best_revenue_channel['Channel'], '📊')} **{best_revenue_channel['Channel']}**")
                st.markdown(f"Revenue: {format_metric(best_revenue_channel[revenue_col], 'SAR')}")
            
            with insight_col2:
                st.success(f"**🎯 Best Conversion Rate**")
                st.markdown(f"{channel_icons.get(best_conv_rate_channel['Channel'], '📊')} **{best_conv_rate_channel['Channel']}**")
                st.markdown(f"Conv Rate: {best_conv_rate_channel['Conversion Rate']:.2f}%")
            
            with insight_col3:
                st.success(f"**👆 Best Engagement**")
                st.markdown(f"{channel_icons.get(best_ctr_channel['Channel'], '📊')} **{best_ctr_channel['Channel']}**")
                st.markdown(f"CTR: {best_ctr_channel['CTR']:.2f}%")
            
            # Additional insights
            st.markdown("**Key Observations:**")
            observations = []
            
            # Check for inactive channels
            inactive_channels = channel_data[channel_data['Sent'] == 0]['Channel'].tolist()
            if inactive_channels:
                observations.append(f"⚠️ **Inactive Channels**: {', '.join(inactive_channels)} - Consider reactivating or investigating")
            
            # Check for low delivery rates
            low_delivery = channel_data[channel_data['Delivery Rate'] < 85]
            if not low_delivery.empty:
                for _, row in low_delivery.iterrows():
                    observations.append(f"🚨 **{row['Channel']}**: Low delivery rate ({row['Delivery Rate']:.1f}%) - Check ESP settings")
            
            # Check for high CTR but low conversions
            high_ctr_low_conv = channel_data[(channel_data['CTR'] > 3) & (channel_data['Conversion Rate'] < 5)]
            if not high_ctr_low_conv.empty:
                for _, row in high_ctr_low_conv.iterrows():
                    observations.append(f"💡 **{row['Channel']}**: Good engagement ({row['CTR']:.2f}% CTR) but low conversion ({row['Conversion Rate']:.2f}%) - Optimize landing pages")
            
            # Show observations
            if observations:
                for obs in observations:
                    st.markdown(f"- {obs}")
            else:
                st.info("✅ All channels are performing well with no major issues detected")
    else:
        st.info("No channel data available for the selected period")
else:
    st.warning("⚠️ Channel information not available in the dataset")

# === REVENUE TREEMAP: Where does revenue come from? ===
st.markdown("---")
st.subheader("🗺️ Revenue Breakdown")
st.caption("*Hierarchical view: Channel → Journey/Campaign (size = revenue)*")

if 'Channel' in filtered_df.columns and 'Revenue (SAR)' in filtered_df.columns:
    rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
    # Build hierarchy: Channel > Campaign Name
    treemap_df = filtered_df.groupby(['Channel', 'Campaign Name'], dropna=False).agg({
        rev_col: 'sum', 'Unique Conversions': 'sum'
    }).reset_index()
    treemap_df = treemap_df[treemap_df[rev_col] > 0]

    if not treemap_df.empty:
        rev_display_name = get_selected_revenue_display_name(revenue_attribution)
        fig_treemap = px.treemap(
            treemap_df,
            path=['Channel', 'Campaign Name'],
            values=rev_col,
            color='Channel',
            color_discrete_map=CHANNEL_COLORS,
            title=f'{rev_display_name} by Channel & Campaign',
        )
        fig_treemap.update_traces(
            textinfo='label+value+percent parent',
            hovertemplate='<b>%{label}</b><br>' + rev_display_name + ': %{value:,.0f} SAR<br>%{percentParent:.1%} of parent<extra></extra>',
        )
        fig_treemap.update_layout(margin=dict(l=10, r=10, t=50, b=10))
        st.plotly_chart(fig_treemap, use_container_width=True)

        # Chart export button
        img_buf = export_chart_image(fig_treemap, 'revenue_treemap')
        if img_buf:
            st.download_button("📥 Download Treemap (PNG)", img_buf, file_name="revenue_treemap.png", mime="image/png")

# === CHANNEL MIX OVER TIME: Stacked area ===
st.markdown("---")
st.subheader("📊 Channel Mix Over Time")
st.caption("*How your channel revenue distribution evolves*")

if 'Channel' in filtered_df.columns and 'Reporting Period Start Date' in filtered_df.columns:
    rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
    time_channel = filtered_df.groupby(
        [pd.Grouper(key='Reporting Period Start Date', freq='W'), 'Channel']
    )[rev_col].sum().reset_index()
    time_channel.columns = ['Week', 'Channel', 'Revenue']

    if not time_channel.empty:
        rev_display_name = get_selected_revenue_display_name(revenue_attribution)
        fig_area = px.area(
            time_channel,
            x='Week', y='Revenue', color='Channel',
            color_discrete_map=CHANNEL_COLORS,
            title=f'Weekly {rev_display_name}',
            labels={'Revenue': f'{rev_display_name} (SAR)', 'Week': ''},
        )
        fig_area.update_layout(hovermode='x unified')
        st.plotly_chart(fig_area, use_container_width=True)

        img_buf = export_chart_image(fig_area, 'channel_mix')
        if img_buf:
            st.download_button("📥 Download Channel Mix (PNG)", img_buf, file_name="channel_mix.png", mime="image/png")

# Conversion Funnel
st.markdown("---")
st.subheader("Conversion Funnel")
funnel_data = {
    'Stage': ['Sent', 'Impressions', 'Clicks', 'Conversions'],
    'Count': [filtered_df['Sent'].sum(), filtered_df['Unique Impressions'].sum(), filtered_df['Unique Clicks'].sum(), filtered_df['Unique Conversions'].sum()]
}
fig_funnel = go.Figure(go.Funnel(
    y=funnel_data['Stage'],
    x=funnel_data['Count'],
    textinfo="value+percent initial",
    marker=dict(color=[COLORS['primary'], COLORS['info'], COLORS['warning'], COLORS['success']]),
))
fig_funnel.update_layout(title='Conversion Funnel')
st.plotly_chart(fig_funnel, use_container_width=True)

img_buf = export_chart_image(fig_funnel, 'conversion_funnel')
if img_buf:
    st.download_button("📥 Download Funnel (PNG)", img_buf, file_name="conversion_funnel.png", mime="image/png")

# Failed reasons
failed_df = failed_reasons_analysis(filtered_df)
if not failed_df.empty:
    st.subheader("Failed Reasons Breakdown")
    fig_fail = px.pie(failed_df, names='Reason', values='Count', color_discrete_sequence=COLOR_SEQUENCE)
    st.plotly_chart(fig_fail, use_container_width=True)

# Data Preview
with st.expander("View Filtered Data"):
    st.dataframe(filtered_df)

