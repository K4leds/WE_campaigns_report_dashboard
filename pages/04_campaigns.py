import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric, style_total_row, export_chart_image
from config import COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import get_attribution_display_label, get_selected_revenue_display_name, get_selected_conversion_display_name
from analysis import top_campaigns
from dashboard.health import calculate_campaign_health_score
from dashboard.funnels import analyze_campaign_funnel
from dashboard.anomalies import detect_campaign_anomalies
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

# Display-friendly rename map for attribution-selected columns (mirrors app.py prelude)
attribution_rename = {'Selected Revenue (SAR)': selected_rev_label, 'Selected Conversions': selected_conv_label}


def _attribution_display(col_name):
    """Map internal 'Selected Revenue/Conversions' column names to the user-selected attribution label."""
    return get_attribution_display_label(col_name, revenue_attribution, conversion_attribution)


st.header("Campaign Analysis")

# Show comparison summary if enabled
if comparison_result:
    st.info(f"📊 Period Comparison Active: {comparison_result['current_label']} vs {comparison_result['comparison_label']}")

    # Calculate campaign metrics for both periods
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

# Top Campaigns
st.subheader("Top Campaigns")
camp_metric_options = [
    'Unique Conversions',
    'Selected Revenue (SAR)',
    'Revenue (SAR)',
    'Unique Clicks',
    'Click-Through Revenue (SAR)',
    'Impression-Through Revenue (SAR)',
    'CTR',
    'Conversion Rate',
    'AOV',
    'Revenue Per Click',
    'Engagement Rate'
]
# Only show Selected Revenue if it exists in data
if 'Selected Revenue (SAR)' not in filtered_df.columns:
    camp_metric_options = [m for m in camp_metric_options if m != 'Selected Revenue (SAR)']
# Add conversion attribution options if they exist
if 'Unique Click-Through Conversions' in filtered_df.columns:
    camp_metric_options.insert(1, 'Unique Click-Through Conversions')
if 'Unique Impression-Through Conversions' in filtered_df.columns:
    camp_metric_options.insert(1, 'Unique Impression-Through Conversions')
camp_metric = st.selectbox("Metric", camp_metric_options, key='camp_metric', format_func=_attribution_display)
top_camp = top_campaigns(filtered_df, camp_metric)

# Create display version for table
top_camp_display = top_camp.copy()

# Store original numeric values for sorting
original_values = top_camp_display[camp_metric].copy()

# Format the metric column for display
if 'Revenue' in camp_metric:
    top_camp_display[camp_metric] = top_camp_display[camp_metric].apply(lambda x: format_metric(x, "SAR"))
elif camp_metric in ['Unique Conversions', 'Unique Clicks', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions']:
    top_camp_display[camp_metric] = top_camp_display[camp_metric].apply(format_metric)
elif camp_metric == 'Conversion Rate':
    top_camp_display[camp_metric] = top_camp_display[camp_metric].apply(lambda x: f"{x:.2%}")
# For other rates, keep as is

# Display table with proper sorting
st.dataframe(top_camp_display.rename(columns=attribution_rename))

# Create chart with original numeric values
fig = px.bar(top_camp, x='Campaign Name', y=camp_metric, title=f"Top Campaigns by {_attribution_display(camp_metric)}",
             color_discrete_sequence=COLOR_SEQUENCE)
st.plotly_chart(fig, use_container_width=True)

# Campaign Type Breakdown (Journey vs One-Time)
if 'Type of Campaign' in filtered_df.columns:
    st.subheader("Performance by Campaign Type")
    type_agg_cols = {'Sent': 'sum', 'Delivered': 'sum', 'Unique Clicks': 'sum', 'Unique Conversions': 'sum'}
    if 'Revenue (SAR)' in filtered_df.columns:
        type_agg_cols['Revenue (SAR)'] = 'sum'
    if 'Click-Through Revenue (SAR)' in filtered_df.columns:
        type_agg_cols['Click-Through Revenue (SAR)'] = 'sum'
    if 'Impression-Through Revenue (SAR)' in filtered_df.columns:
        type_agg_cols['Impression-Through Revenue (SAR)'] = 'sum'
    if 'Selected Revenue (SAR)' in filtered_df.columns:
        type_agg_cols['Selected Revenue (SAR)'] = 'sum'
    type_breakdown = filtered_df.groupby('Type of Campaign').agg(type_agg_cols).reset_index()
    type_breakdown['Conversion Rate'] = np.where(
        type_breakdown['Unique Clicks'] > 0,
        type_breakdown['Unique Conversions'] / type_breakdown['Unique Clicks'], 0
    )

    # Calculate AOV for each revenue type
    if 'Revenue (SAR)' in type_breakdown.columns:
        type_breakdown['AOV (SAR)'] = np.where(
            type_breakdown['Unique Conversions'] > 0,
            type_breakdown['Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0
        )
    if 'Click-Through Revenue (SAR)' in type_breakdown.columns:
        type_breakdown['AOV Click-Through (SAR)'] = np.where(
            type_breakdown['Unique Conversions'] > 0,
            type_breakdown['Click-Through Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0
        )
    if 'Impression-Through Revenue (SAR)' in type_breakdown.columns:
        type_breakdown['AOV Impression-Through (SAR)'] = np.where(
            type_breakdown['Unique Conversions'] > 0,
            type_breakdown['Impression-Through Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0
        )
    if 'Selected Revenue (SAR)' in type_breakdown.columns:
        type_breakdown['AOV Selected (SAR)'] = np.where(
            type_breakdown['Unique Conversions'] > 0,
            type_breakdown['Selected Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0
        )

    # Add total row
    total_row = {'Type of Campaign': 'Total'}
    total_conversions = type_breakdown['Unique Conversions'].sum()
    for col in type_breakdown.columns:
        if col == 'Type of Campaign':
            continue
        elif col == 'Conversion Rate':
            clicks_total = type_breakdown['Unique Clicks'].sum()
            total_row[col] = type_breakdown['Unique Conversions'].sum() / clicks_total if clicks_total > 0 else 0
        elif 'AOV' in col:
            # Calculate total AOV from total revenue / total conversions
            if 'Click-Through' in col and 'Click-Through Revenue (SAR)' in type_breakdown.columns:
                total_rev = type_breakdown['Click-Through Revenue (SAR)'].sum()
            elif 'Impression-Through' in col and 'Impression-Through Revenue (SAR)' in type_breakdown.columns:
                total_rev = type_breakdown['Impression-Through Revenue (SAR)'].sum()
            elif 'Selected' in col and 'Selected Revenue (SAR)' in type_breakdown.columns:
                total_rev = type_breakdown['Selected Revenue (SAR)'].sum()
            elif 'Revenue (SAR)' in type_breakdown.columns:
                total_rev = type_breakdown['Revenue (SAR)'].sum()
            else:
                total_rev = 0
            total_row[col] = total_rev / total_conversions if total_conversions > 0 else 0
        else:
            total_row[col] = type_breakdown[col].sum()
    type_breakdown = pd.concat([type_breakdown, pd.DataFrame([total_row])], ignore_index=True)

    # Display table - drop Selected Revenue/Conversions since all attribution types are shown
    type_display = type_breakdown.copy()
    for drop_col in ['Selected Revenue (SAR)', 'Selected Conversions']:
        if drop_col in type_display.columns:
            type_display = type_display.drop(columns=[drop_col])
    for col in ['Sent', 'Delivered', 'Unique Clicks', 'Unique Conversions']:
        if col in type_display.columns:
            type_display[col] = type_display[col].apply(format_metric)
    for col in [c for c in type_display.columns if 'Revenue' in c]:
        type_display[col] = type_display[col].apply(lambda x: format_metric(x, "SAR"))
    for col in [c for c in type_display.columns if 'AOV' in c]:
        type_display[col] = type_display[col].apply(lambda x: format_metric(x, "SAR"))
    type_display['Conversion Rate'] = type_display['Conversion Rate'].apply(lambda x: f"{x:.2%}")
    st.dataframe(style_total_row(type_display), use_container_width=True, hide_index=True)

    # Side-by-side charts (exclude Total row)
    type_chart_data = type_breakdown[type_breakdown['Type of Campaign'] != 'Total']
    type_col1, type_col2 = st.columns(2)
    rev_col_for_type = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in type_chart_data.columns else 'Revenue (SAR)'
    with type_col1:
        if rev_col_for_type in type_chart_data.columns:
            rev_display_name = get_selected_revenue_display_name(revenue_attribution)
            fig_type_rev = px.bar(type_chart_data, x='Type of Campaign', y=rev_col_for_type,
                                  title=f"{rev_display_name} by Campaign Type", color='Type of Campaign',
                                  color_discrete_sequence=COLOR_SEQUENCE,
                                  labels={rev_col_for_type: rev_display_name})
            fig_type_rev.update_layout(showlegend=False)
            st.plotly_chart(fig_type_rev, use_container_width=True)
    with type_col2:
        conv_display_name = get_selected_conversion_display_name(conversion_attribution)
        fig_type_conv = px.bar(type_chart_data, x='Type of Campaign', y='Unique Conversions',
                               title=f"{conv_display_name} by Campaign Type", color='Type of Campaign',
                               color_discrete_sequence=COLOR_SEQUENCE,
                               labels={'Unique Conversions': conv_display_name})
        fig_type_conv.update_layout(showlegend=False)
        st.plotly_chart(fig_type_conv, use_container_width=True)

# One-Time Campaigns Overview
if 'Type of Campaign' in filtered_df.columns:
    onetime_df = filtered_df[filtered_df['Type of Campaign'].str.lower().str.contains('one-time', na=False)].copy()

    # Filter out likely test campaigns (low volume) - applied AFTER aggregation
    # to avoid excluding attribution-window rows where Sent=0
    min_sent_threshold = st.slider("Minimum Sent Threshold (exclude tests)", 0, 1000, 100,
                                 help="Campaigns with fewer sends than this threshold will be excluded as potential tests")

    if not onetime_df.empty:
        st.subheader("🚀 One-Time Campaigns Overview")

        # Campaign details table
        st.markdown("#### Campaign Details")
        # Respect selected attribution if present
        agg_dict = {
            'Sent': 'sum',
            'Delivered': 'sum',
            'Failed': 'sum',
            'Unique Clicks': 'sum',
            'Unique Conversions': 'sum',
            'Day': 'min'  # Launch date
        }
        if 'Selected Revenue (SAR)' in onetime_df.columns:
            agg_dict['Selected Revenue (SAR)'] = 'sum'
        elif 'Revenue (SAR)' in onetime_df.columns:
            agg_dict['Revenue (SAR)'] = 'sum'

        # Add selected conversions if available
        if 'Selected Conversions' in onetime_df.columns:
            agg_dict['Selected Conversions'] = 'sum'
        # Add click-through conversion counts if available; these should drive the campaign-level conversion rate
        if 'Unique Click-Through Conversions' in onetime_df.columns:
            agg_dict['Unique Click-Through Conversions'] = 'sum'
        # Add impression counts if available, so we can fall back to impression-based rate when clicks-only metrics are unavailable
        if 'Unique Impressions' in onetime_df.columns:
            agg_dict['Unique Impressions'] = 'sum'

        # Add all revenue attribution types (summed totals across all dates)
        if 'Impression-Through Revenue (SAR)' in onetime_df.columns:
            agg_dict['Impression-Through Revenue (SAR)'] = 'sum'
        if 'Click-Through Revenue (SAR)' in onetime_df.columns:
            agg_dict['Click-Through Revenue (SAR)'] = 'sum'

        groupby_cols = ['Campaign Name', 'Channel'] if 'Channel' in onetime_df.columns else ['Campaign Name']
        onetime_summary = onetime_df.groupby(groupby_cols).agg(agg_dict).reset_index()

        # Apply sent threshold AFTER aggregation so attribution-window rows (Sent=0) aren't lost
        onetime_summary = onetime_summary[onetime_summary['Sent'] >= min_sent_threshold]

        # Summary metrics (computed after aggregation so they reflect true totals)
        total_onetime_campaigns = onetime_summary['Campaign Name'].nunique()
        total_onetime_sent = onetime_summary['Sent'].sum()
        total_onetime_delivered = onetime_summary['Delivered'].sum()

        sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
        with sum_col1:
            st.metric("One-Time Campaigns", format_metric(total_onetime_campaigns),
                     help=f"Total unique one-time campaigns launched (sent ≥ {min_sent_threshold})")
        with sum_col2:
            st.metric("Total Sent", format_metric(total_onetime_sent))
        with sum_col3:
            st.metric("Total Delivered", format_metric(total_onetime_delivered))
        with sum_col4:
            delivery_rate = total_onetime_delivered / total_onetime_sent if total_onetime_sent > 0 else 0
            st.metric("Avg Delivery Rate", f"{delivery_rate:.1%}")

        # Debug: Show aggregation details
        with st.expander("🔍 Debug: Revenue Aggregation Details", expanded=False):
            st.write("**Data before aggregation:**")
            sample_campaign = onetime_df['Campaign Name'].iloc[0] if not onetime_df.empty else None
            if sample_campaign:
                sample_data = onetime_df[onetime_df['Campaign Name'] == sample_campaign][['Campaign Name', 'Day', 'Sent', 'Delivered', 'Revenue (SAR)'] +
                                                                                           ([col for col in ['Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Selected Revenue (SAR)'] if col in onetime_df.columns])]
                st.write(f"Sample campaign: **{sample_campaign}**")
                st.dataframe(sample_data, use_container_width=True)

                st.write("**After aggregation:**")
                sample_agg = onetime_summary[onetime_summary['Campaign Name'] == sample_campaign]
                st.dataframe(sample_agg, use_container_width=True)

                st.write(f"**Number of days in raw data:** {len(sample_data)}")
                st.write(f"**Total campaigns in dataset:** {onetime_df['Campaign Name'].nunique()}")
                st.write(f"**Total rows before aggregation:** {len(onetime_df)}")
                st.write(f"**Total rows after aggregation:** {len(onetime_summary)}")

        # Add calculated columns
        onetime_summary['Delivery Rate'] = onetime_summary['Delivered'] / onetime_summary['Sent']
        onetime_summary['CTR'] = np.where(onetime_summary['Delivered'] > 0,
                                        onetime_summary['Unique Clicks'] / onetime_summary['Delivered'], 0)

        # Compute campaign conversion rate using the correct numerator/denominator pairing
        if 'Unique Click-Through Conversions' in onetime_summary.columns and 'Unique Clicks' in onetime_summary.columns:
            conv_numer = onetime_summary['Unique Click-Through Conversions']
            conv_denom = onetime_summary['Unique Clicks']
        elif 'Unique Impressions' in onetime_summary.columns and 'Unique Conversions' in onetime_summary.columns:
            conv_numer = onetime_summary['Unique Conversions']
            conv_denom = onetime_summary['Unique Impressions']
        else:
            conv_col_for_rate = 'Selected Conversions' if 'Selected Conversions' in onetime_summary.columns else 'Unique Conversions'
            conv_numer = onetime_summary[conv_col_for_rate]
            conv_denom = onetime_summary['Unique Clicks'] if 'Unique Clicks' in onetime_summary.columns else 1

        onetime_summary['Conversion Rate'] = np.where(conv_denom > 0,
                                                    conv_numer / conv_denom, 0)

        # Sort by sent volume descending
        onetime_summary = onetime_summary.sort_values('Sent', ascending=False)

        # Format for display
        # Use selected revenue column if available
        revenue_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in onetime_summary.columns else 'Revenue (SAR)'
        conv_col_display = 'Selected Conversions' if 'Selected Conversions' in onetime_summary.columns else 'Unique Conversions'

        # Build display columns dynamically to include all revenue types (but avoid duplicates)
        base_cols = ['Campaign Name'] + (['Channel'] if 'Channel' in onetime_summary.columns else [])
        display_cols = base_cols + ['Sent', 'Delivered', 'Delivery Rate',
                      'Unique Clicks', 'CTR', conv_col_display, 'Conversion Rate', revenue_col]

        # Add attribution revenue columns ONLY if they won't conflict after rename
        # revenue_col is 'Selected Revenue (SAR)' which will be renamed to selected_rev_label
        # So we need to check if selected_rev_label != the column we're trying to add
        if 'Impression-Through Revenue (SAR)' in onetime_summary.columns and selected_rev_label != 'Impression-Through Revenue (SAR)':
            display_cols.append('Impression-Through Revenue (SAR)')
        if 'Click-Through Revenue (SAR)' in onetime_summary.columns and selected_rev_label != 'Click-Through Revenue (SAR)':
            display_cols.append('Click-Through Revenue (SAR)')

        # Remove any duplicates while preserving order
        display_cols = list(dict.fromkeys(display_cols))
        onetime_display = onetime_summary[display_cols].copy()

        # Format columns (convert to strings for display with K/M abbreviations)
        onetime_display['Sent'] = onetime_display['Sent'].apply(format_metric)
        onetime_display['Delivered'] = onetime_display['Delivered'].apply(format_metric)
        onetime_display['Unique Clicks'] = onetime_display['Unique Clicks'].apply(format_metric)
        onetime_display[conv_col_display] = onetime_display[conv_col_display].apply(format_metric)
        onetime_display[revenue_col] = onetime_display[revenue_col].apply(lambda x: format_metric(x, "SAR"))

        # Format attribution revenue columns if they exist
        if 'Impression-Through Revenue (SAR)' in onetime_display.columns:
            onetime_display['Impression-Through Revenue (SAR)'] = onetime_display['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
        if 'Click-Through Revenue (SAR)' in onetime_display.columns:
            onetime_display['Click-Through Revenue (SAR)'] = onetime_display['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))

        onetime_display['Delivery Rate'] = onetime_display['Delivery Rate'].apply(lambda x: f"{x:.1%}")
        onetime_display['CTR'] = onetime_display['CTR'].apply(lambda x: f"{x:.2%}")
        onetime_display['Conversion Rate'] = onetime_display['Conversion Rate'].apply(lambda x: f"{x:.2%}")

        # Rename columns to show actual attribution model
        onetime_display = onetime_display.rename(columns=attribution_rename)
        st.dataframe(onetime_display, use_container_width=True, hide_index=True)

        # Optional: Channel breakdown for one-time campaigns
        if st.checkbox("Show Channel Breakdown for One-Time Campaigns", key='onetime_channel_breakdown'):
            st.markdown("#### Channel Performance")
            # Respect selected revenue attribution
            agg_cols = {
                'Sent': 'sum',
                'Delivered': 'sum',
                'Unique Conversions': 'sum'
            }
            if 'Selected Revenue (SAR)' in onetime_df.columns:
                agg_cols['Selected Revenue (SAR)'] = 'sum'
                rev_col_channel = 'Selected Revenue (SAR)'
            else:
                agg_cols['Revenue (SAR)'] = 'sum'
                rev_col_channel = 'Revenue (SAR)'

            channel_breakdown = onetime_df.groupby('Channel').agg(agg_cols).reset_index()

            channel_breakdown['Delivery Rate'] = channel_breakdown['Delivered'] / channel_breakdown['Sent']
            channel_breakdown['Conversions'] = channel_breakdown['Unique Conversions']

            # Format
            channel_display = channel_breakdown.copy()
            channel_display['Sent'] = channel_display['Sent'].apply(format_metric)
            channel_display['Delivered'] = channel_display['Delivered'].apply(format_metric)
            channel_display['Conversions'] = channel_display['Conversions'].apply(format_metric)
            channel_display[rev_col_channel] = channel_display[rev_col_channel].apply(lambda x: format_metric(x, "SAR"))
            channel_display['Delivery Rate'] = channel_display['Delivery Rate'].apply(lambda x: f"{x:.1%}")

            # Rename columns to show actual attribution model
            channel_display = channel_display.rename(columns=attribution_rename)
            display_rev_col = selected_rev_label if rev_col_channel == 'Selected Revenue (SAR)' else rev_col_channel
            st.dataframe(channel_display[['Channel', 'Sent', 'Delivered', 'Delivery Rate', 'Conversions', display_rev_col]],
                       use_container_width=True, hide_index=True)
    else:
        st.info("No one-time campaigns found matching the criteria.")

    # Monthly breakdown of unique one-time campaigns
    if not onetime_df.empty:
        st.markdown("#### 📅 Monthly One-Time Campaign Activity")

        # Extract month from date column
        if 'Day' in onetime_df.columns:
            onetime_df['Month'] = onetime_df['Day'].dt.to_period('M').dt.strftime('%Y-%m')
        elif 'Reporting Period Start Date' in onetime_df.columns:
            onetime_df['Month'] = onetime_df['Reporting Period Start Date'].dt.to_period('M').dt.strftime('%Y-%m')
        else:
            st.info("No date column available for monthly breakdown.")

        if 'Month' in onetime_df.columns:
            # Group by month and count unique campaigns
            # Use selected revenue if present
            monthly_agg = {
                'Campaign Name': 'nunique',  # Count unique campaigns
                'Sent': 'sum',
                'Delivered': 'sum',
                'Unique Conversions': 'sum'
            }
            if 'Selected Revenue (SAR)' in onetime_df.columns:
                monthly_agg['Selected Revenue (SAR)'] = 'sum'
                rev_col_month = 'Selected Revenue (SAR)'
            else:
                monthly_agg['Revenue (SAR)'] = 'sum'
                rev_col_month = 'Revenue (SAR)'

            monthly_campaigns = onetime_df.groupby('Month').agg(monthly_agg).reset_index()

            monthly_campaigns = monthly_campaigns.rename(columns={'Campaign Name': 'Unique Campaigns'})
            monthly_campaigns = monthly_campaigns.sort_values('Month', ascending=False)

            # Format for display
            monthly_display = monthly_campaigns.copy()
            monthly_display['Sent'] = monthly_display['Sent'].apply(format_metric)
            monthly_display['Delivered'] = monthly_display['Delivered'].apply(format_metric)
            monthly_display['Unique Conversions'] = monthly_display['Unique Conversions'].apply(format_metric)
            monthly_display[rev_col_month] = monthly_display[rev_col_month].apply(lambda x: format_metric(x, "SAR"))

            # Rename columns to show actual attribution model
            monthly_display = monthly_display.rename(columns=attribution_rename)
            st.dataframe(monthly_display, use_container_width=True, hide_index=True)

            # Optional chart
            if st.checkbox("Show Monthly Trend Chart", key='monthly_onetime_chart'):
                chart_data = monthly_campaigns.sort_values('Month')
                fig_monthly = px.bar(chart_data, x='Month', y='Unique Campaigns',
                                   title="Unique One-Time Campaigns per Month",
                                   color_discrete_sequence=[COLORS['primary']])
                fig_monthly.update_layout(
                    xaxis_title="Month",
                    yaxis_title="Number of Campaigns",
                    xaxis=dict(type='category')
                )
                st.plotly_chart(fig_monthly, use_container_width=True)

# Campaign Drill-Down
st.subheader("Campaign Drill-Down")
selected_campaigns = st.multiselect("Select Campaigns for Details", filtered_df['Campaign Name'].unique(), key='drill_camp')
if selected_campaigns:
    camp_details = filtered_df[filtered_df['Campaign Name'].isin(selected_campaigns)]

    # Summary KPIs - Row 1: Volume Metrics
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric("Total Sent", format_metric(camp_details['Sent'].sum()))
    with col2:
        st.metric("Total Delivered", format_metric(camp_details['Delivered'].sum()))
    with col3:
        st.metric("Total Clicks", format_metric(camp_details['Unique Clicks'].sum()))
    with col4:
        conv_total = camp_details['Selected Conversions'].sum() if 'Selected Conversions' in camp_details.columns else camp_details['Unique Conversions'].sum()
        st.metric(selected_conv_label, format_metric(conv_total))
    with col5:
        rev_total = camp_details['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in camp_details.columns else camp_details['Revenue (SAR)'].sum()
        st.metric(selected_rev_label, format_metric(rev_total, "SAR"))
    with col6:
        st.metric("Click-Through Revenue", format_metric(camp_details['Click-Through Revenue (SAR)'].sum(), "SAR"))

    # Row 2: Business Metrics
    st.markdown("#### 💰 Business Intelligence")
    biz_col1, biz_col2, biz_col3, biz_col4 = st.columns(4)

    total_revenue = camp_details['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in camp_details.columns else camp_details['Revenue (SAR)'].sum()
    total_conversions = camp_details['Selected Conversions'].sum() if 'Selected Conversions' in camp_details.columns else camp_details['Unique Conversions'].sum()
    total_clicks = camp_details['Unique Clicks'].sum()

    with biz_col1:
        aov = (total_revenue / total_conversions) if total_conversions > 0 else 0
        st.metric("Average Order Value", format_metric(aov, "SAR"), help="Revenue per conversion")
    with biz_col2:
        rpc = (total_revenue / total_clicks) if total_clicks > 0 else 0
        st.metric("Revenue Per Click", format_metric(rpc, "SAR"), help="Revenue generated per click")
    with biz_col3:
        avg_ctr = camp_details['CTR'].mean()
        st.metric("Avg CTR", f"{avg_ctr:.2%}", help="Average click-through rate")
    with biz_col4:
        # Calculate conversion rate from raw data
        total_clicks_metric = camp_details['Unique Clicks'].sum()
        conv_col_metric = 'Selected Conversions' if 'Selected Conversions' in camp_details.columns else 'Unique Conversions'
        total_conversions_metric = camp_details[conv_col_metric].sum()
        avg_conv_rate = (total_conversions_metric / total_clicks_metric) if total_clicks_metric > 0 else 0
        st.metric("Avg Conversion Rate", f"{avg_conv_rate:.2%}", help="Average conversion rate")

    # Performance by Channel
    st.subheader("Performance by Channel")
    chan_perf = camp_details.groupby('Channel').agg({
        'Sent': 'sum',
        'Delivered': 'sum',
        'Unique Conversions': 'sum',
        'Revenue (SAR)': 'sum',
        'Impression-Through Revenue (SAR)': 'sum',
        'Click-Through Revenue (SAR)': 'sum'
    }).reset_index()
    # Add total row
    total_row = {'Channel': 'Total'}
    for col in chan_perf.columns:
        if col != 'Channel':
            total_row[col] = chan_perf[col].sum()
    chan_perf_with_total = pd.concat([chan_perf, pd.DataFrame([total_row])], ignore_index=True)
    # Format columns for display
    chan_perf_display = chan_perf_with_total.copy()
    chan_perf_display['Sent'] = chan_perf_display['Sent'].apply(format_metric)
    chan_perf_display['Delivered'] = chan_perf_display['Delivered'].apply(format_metric)
    chan_perf_display['Unique Conversions'] = chan_perf_display['Unique Conversions'].apply(format_metric)
    chan_perf_display['Revenue (SAR)'] = chan_perf_display['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
    chan_perf_display['Impression-Through Revenue (SAR)'] = chan_perf_display['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
    chan_perf_display['Click-Through Revenue (SAR)'] = chan_perf_display['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
    st.dataframe(style_total_row(chan_perf_display), use_container_width=True, hide_index=True)
    conv_display_name = get_selected_conversion_display_name(conversion_attribution)
    fig_chan = px.bar(chan_perf, x='Channel', y='Unique Conversions',
                      title=f"{conv_display_name} by Channel for Selected Campaigns",
                      color='Channel', color_discrete_map=CHANNEL_COLORS,
                      labels={'Unique Conversions': conv_display_name})
    fig_chan.update_layout(showlegend=False)
    st.plotly_chart(fig_chan, use_container_width=True)

    # Time Series for Selected Campaigns
    st.subheader("Time Series Performance")
    ts_camp = camp_details.groupby(['Reporting Period Start Date', 'Campaign Name'])[camp_metric].sum().reset_index()
    if not ts_camp.empty:
        fig_ts_camp = px.line(ts_camp, x='Reporting Period Start Date', y=camp_metric, color='Campaign Name',
                              title=f"{camp_metric} Over Time for Selected Campaigns",
                              color_discrete_sequence=COLOR_SEQUENCE)
        fig_ts_camp.update_traces(line_width=2.5)
        st.plotly_chart(fig_ts_camp, use_container_width=True)

    # Conversion Attribution
    st.subheader("Conversion Attribution")
    attr_camp = {
        'Impression-Through': camp_details['Unique Impression-Through Conversions'].sum(),
        'Click-Through': camp_details['Unique Click-Through Conversions'].sum(),
        'Direct/Open-Through': camp_details['Unique Conversions'].sum() - camp_details['Unique Impression-Through Conversions'].sum() - camp_details['Unique Click-Through Conversions'].sum()
    }
    attr_df_camp = pd.DataFrame(list(attr_camp.items()), columns=['Source', 'Conversions'])
    attr_df_camp['Conversions'] = attr_df_camp['Conversions'].apply(format_metric)
    fig_attr_camp = px.pie(attr_df_camp, names='Source', values='Conversions', title="Attribution for Selected Campaigns",
                            color_discrete_sequence=COLOR_SEQUENCE)
    st.plotly_chart(fig_attr_camp, use_container_width=True)

    # Failed Reasons for Selected Campaigns
    st.subheader("Failed Reasons")
    failed_cols = [col for col in camp_details.columns if 'Failed' in col and col != 'Failed']
    if failed_cols:
        failed_camp = camp_details[failed_cols].sum().reset_index().rename(columns={'index': 'Reason', 0: 'Count'})
        failed_camp['Count'] = failed_camp['Count'].apply(format_metric)
        fig_fail_camp = px.bar(failed_camp, x='Reason', y='Count', title="Failed Reasons for Selected Campaigns",
                               color_discrete_sequence=[COLORS['danger']])
        st.plotly_chart(fig_fail_camp, use_container_width=True)

# Campaign Health Score Analysis
st.subheader("🏥 Campaign Health Dashboard")

# Professional Methodology Explanation for Executives
with st.expander("📊 Scoring Methodology (Click to View)", expanded=False):
    st.markdown("""
    ### **Health Score Methodology**

    **Method**: Percentile ranking with Empirical Bayes smoothing

    #### **How Scores are Calculated:**
    - **Relative Ranking**: Each campaign is scored against all other campaigns in your portfolio (0-100 scale)
    - **Empirical Bayes Smoothing**: Low-volume campaigns are adjusted toward the portfolio average to avoid misleading scores from small samples
    - **No Fixed Benchmarks**: Scores reflect your actual portfolio distribution, not arbitrary industry numbers

    #### **Component Weights:**
    - 🚀 **Conversion Performance**: 30% - Conversion rate (clicks to conversions)
    - 🎯 **Engagement Performance**: 25% - Click-through rate (impressions to clicks)
    - 💰 **Revenue Efficiency**: 25% - Revenue per conversion (log-scaled to reduce outlier impact)
    - 📧 **Delivery Performance**: 20% - Delivery rate (sent to delivered)

    #### **Performance Tiers:**
    - **Excellent (80-100)**: Top quartile - scale and replicate
    - **Good (60-79)**: Above average - minor optimizations
    - **Fair (40-59)**: Below average - review and improve
    - **Poor (0-39)**: Bottom quartile - immediate action needed

    #### **Data Sufficiency:**
    Campaigns with fewer than 10 sends, 3 conversions, or 3 days of data are marked "Insufficient Data" to avoid misleading scores.
    """)


# Calculate health scores for all campaigns
campaign_health_data = []
unique_campaigns = filtered_df['Campaign Name'].dropna().unique()

for campaign in unique_campaigns:
    if str(campaign) != 'nan' and campaign:
        campaign_data = filtered_df[filtered_df['Campaign Name'] == campaign]
        health_info = calculate_campaign_health_score(campaign_data, filtered_df)
        campaign_health_data.append({
            'Campaign Name': campaign,
            'Health Score': health_info['health_score'],
            'Tier': health_info['tier'],
            'Revenue (SAR)': campaign_data['Revenue (SAR)'].sum(),
            'Impression-Through Revenue (SAR)': campaign_data['Impression-Through Revenue (SAR)'].sum(),
            'Click-Through Revenue (SAR)': campaign_data['Click-Through Revenue (SAR)'].sum(),
            'Total Conversions': campaign_data['Unique Conversions'].sum(),
            'Delivery Score': health_info['component_scores'].get('delivery', 0),
            'Engagement Score': health_info['component_scores'].get('engagement', 0),
            'Conversion Score': health_info['component_scores'].get('conversion', 0),
            'Revenue Score': health_info['component_scores'].get('revenue', 0)
        })

if campaign_health_data:
    health_df = pd.DataFrame(campaign_health_data)
    health_df = health_df.sort_values('Health Score', ascending=False)

    # Display top performers and those needing attention
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("🔥 Top Performing Campaigns")
        top_performing_campaigns = health_df.head(5)
        for _, row in top_performing_campaigns.iterrows():
            # Use expandable containers for full campaign names
            with st.container():
                st.markdown(f"**{row['Campaign Name']}**")
                score_col, tier_col = st.columns([2, 1])
                with score_col:
                    st.markdown(f"🏥 **{row['Health Score']:.1f}/100**")
                with tier_col:
                    tier_color = "🟢" if row['Tier'] == "Excellent" else "🟡" if row['Tier'] == "Good" else "🟠"
                    st.markdown(f"{tier_color} {row['Tier']}")
                st.markdown("---")

    with col2:
        st.subheader("🚨 Campaigns Needing Attention")
        bottom_campaigns = health_df[health_df['Health Score'] < 60].head(5)
        if not bottom_campaigns.empty:
            for _, row in bottom_campaigns.iterrows():
                # Use expandable containers for full campaign names
                with st.container():
                    st.markdown(f"**{row['Campaign Name']}**")
                    score_col, tier_col = st.columns([2, 1])
                    with score_col:
                        st.markdown(f"🏥 **{row['Health Score']:.1f}/100**")
                    with tier_col:
                        tier_color = "🔴" if row['Tier'] == "Poor" else "🟠" if row['Tier'] == "Fair" else "🟡"
                        st.markdown(f"{tier_color} {row['Tier']}")
                    st.markdown("---")
        else:
            st.success("🎉 All campaigns are performing well!")

    # Health Score Distribution
    st.subheader("📊 Health Score Distribution")
    fig_health_dist = px.histogram(health_df, x='Health Score', nbins=20,
                                 title="Distribution of Campaign Health Scores",
                                 color_discrete_sequence=[COLORS['primary']])
    fig_health_dist.add_vline(x=health_df['Health Score'].mean(),
                            line_dash="dash", line_color=COLORS['danger'],
                            annotation_text=f"Average: {health_df['Health Score'].mean():.1f}")
    st.plotly_chart(fig_health_dist, use_container_width=True)

    # Complete Health Dashboard Table
    st.subheader("📋 Complete Campaign Health Report")

    # Add search and filter options
    search_col, filter_col = st.columns([2, 1])

    with search_col:
        search_term = st.text_input("🔍 Search Campaign Names", placeholder="Type to filter campaigns...", key='campaign_search')

    with filter_col:
        tier_filter = st.selectbox("Filter by Tier", ['All'] + list(health_df['Tier'].unique()), key='campaign_tier_filter')

    # Apply filters
    display_health_df = health_df.copy()

    if search_term:
        display_health_df = display_health_df[
            display_health_df['Campaign Name'].str.contains(search_term, case=False, na=False)
        ]

    if tier_filter != 'All':
        display_health_df = display_health_df[display_health_df['Tier'] == tier_filter]

    # Prepare numeric dataframe for display while keeping numeric types so Streamlit sorts correctly
    numeric_display_df = display_health_df.copy()

    # Ensure numeric columns are numeric (coerce if necessary)
    numeric_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Total Conversions',
                    'Health Score', 'Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']
    for col in numeric_cols:
        if col in numeric_display_df.columns:
            numeric_display_df[col] = pd.to_numeric(numeric_display_df[col], errors='coerce')

    # Add tier emojis to a separate display column (keep original Tier for filtering logic)
    tier_emojis = {
        'Excellent': '🟢',
        'Good': '🟡',
        'Fair': '🟠',
        'Poor': '🔴'
    }
    # Create a human-friendly Tier display column
    numeric_display_df['Tier Display'] = numeric_display_df['Tier'].apply(lambda x: f"{tier_emojis.get(x, '⚪')} {x}")

    # Show filtered results count
    st.info(f"📊 Showing {len(numeric_display_df)} campaigns (filtered from {len(health_df)} total)")

    # Define columns order for display
    columns_order = ['Campaign Name', 'Health Score', 'Tier Display', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)',
                     'Click-Through Revenue (SAR)', 'Total Conversions', 'Delivery Score', 'Engagement Score',
                     'Conversion Score', 'Revenue Score']

    # Create formatters for Styler so values look nice but remain numeric underneath (preserves numeric sorting)
    formatters = {}
    if 'Health Score' in numeric_display_df.columns:
        formatters['Health Score'] = lambda x: f"{x:.1f}/100"
    if 'Revenue (SAR)' in numeric_display_df.columns:
        formatters['Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
        formatters['Impression-Through Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
        formatters['Click-Through Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
    if 'Total Conversions' in numeric_display_df.columns:
        formatters['Total Conversions'] = lambda x: format_metric(x)
    for score in ['Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']:
        if score in numeric_display_df.columns:
            formatters[score] = lambda x: f"{x:.1f}"

    # Use pandas Styler to format display without changing underlying dtypes
    try:
        styled = numeric_display_df[columns_order].style.format(formatters)
        st.dataframe(styled, width='stretch', height=400)
    except Exception:
        # Fallback: if Styler isn't supported in this environment, fall back to pre-formatted strings
        fallback = numeric_display_df[columns_order].copy()
        if 'Health Score' in fallback.columns:
            fallback['Health Score'] = fallback['Health Score'].apply(lambda x: f"{x:.1f}/100")
        if 'Revenue (SAR)' in fallback.columns:
            fallback['Revenue (SAR)'] = fallback['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            fallback['Impression-Through Revenue (SAR)'] = fallback['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            fallback['Click-Through Revenue (SAR)'] = fallback['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
        if 'Total Conversions' in fallback.columns:
            fallback['Total Conversions'] = fallback['Total Conversions'].apply(format_metric)
        if 'Tier Display' in fallback.columns:
            fallback = fallback.rename(columns={'Tier Display': 'Tier'})

        st.dataframe(fallback, width='stretch', height=400)

    # Component Scores Radar Chart for Selected Campaign
    st.subheader("🎯 Campaign Performance Breakdown")
    selected_campaign_health = st.selectbox("Select Campaign for Detailed Analysis",
                                          health_df['Campaign Name'].tolist(),
                                          key='health_campaign')

    if selected_campaign_health:
        selected_health_data = health_df[health_df['Campaign Name'] == selected_campaign_health].iloc[0]

        # Create radar chart for component scores with better visualization
        categories = ['Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']
        values = [selected_health_data[cat] for cat in categories]

        # Debug information to understand the values
        st.write("**📊 Component Score Values:**")
        score_cols = st.columns(4)
        for i, (cat, val) in enumerate(zip(categories, values)):
            with score_cols[i]:
                st.metric(cat.replace(' Score', ''), f"{val:.1f}/100")

        # Create enhanced radar chart
        fig_radar = go.Figure()

        # Add the main data trace
        fig_radar.add_trace(go.Scatterpolar(
            r=values,
            theta=categories,
            fill='toself',
            name=selected_campaign_health,
            line=dict(color='rgb(0, 123, 255)', width=3),
            fillcolor='rgba(0, 123, 255, 0.3)',
            marker=dict(size=8, color='rgb(0, 123, 255)')
        ))

        # Add reference lines for performance levels
        excellent_line = [80] * len(categories)
        good_line = [60] * len(categories)

        fig_radar.add_trace(go.Scatterpolar(
            r=excellent_line,
            theta=categories,
            mode='lines',
            name='Excellent (80+)',
            line=dict(color=COLORS['success'], width=2, dash='dash'),
            showlegend=True
        ))

        fig_radar.add_trace(go.Scatterpolar(
            r=good_line,
            theta=categories,
            mode='lines',
            name='Good (60+)',
            line=dict(color=COLORS['warning'], width=2, dash='dot'),
            showlegend=True
        ))

        # Update layout with better styling
        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(
                    visible=True,
                    range=[0, 100],
                    tickmode='linear',
                    tick0=0,
                    dtick=20,
                    gridcolor='lightgray',
                    gridwidth=1
                ),
                angularaxis=dict(
                    gridcolor='lightgray',
                    gridwidth=1
                )
            ),
            showlegend=True,
            title=dict(
                text=f"Performance Breakdown: {selected_campaign_health}",
                x=0.5,
                font=dict(size=16)
            ),
            width=600,
            height=500,
            margin=dict(l=80, r=80, t=80, b=80)
        )
        st.plotly_chart(fig_radar, use_container_width=True)
        radar_img = export_chart_image(fig_radar, 'campaign_radar')
        if radar_img:
            st.download_button("Download Radar Chart", radar_img, "campaign_radar.png", "image/png", key='dl_camp_radar')

        # Show recommendations
        campaign_data_for_rec = filtered_df[filtered_df['Campaign Name'] == selected_campaign_health]
        health_info_for_rec = calculate_campaign_health_score(campaign_data_for_rec, filtered_df)

        st.subheader("💡 Recommendations")
        for rec in health_info_for_rec['recommendations']:
            st.info(rec)

# Campaign Performance Breakdown Analysis
st.subheader("📊 Campaign Performance Breakdown")

# Select campaign for detailed breakdown
breakdown_campaign = st.selectbox("Select Campaign for Performance Breakdown",
                                unique_campaigns,
                                key='breakdown_campaign')

if breakdown_campaign and str(breakdown_campaign) != 'nan':
    breakdown_data = filtered_df[filtered_df['Campaign Name'] == breakdown_campaign]

    # Calculate component scores and contributions
    breakdown_health = calculate_campaign_health_score(breakdown_data, filtered_df)

    # Component Contribution Analysis
    st.subheader("🔢 Component Contribution Analysis")

    # Create a detailed breakdown table
    contribution_data = []
    total_contribution = 0

    for component, details in breakdown_health.get('component_contributions', {}).items():
        contribution_data.append({
            'Component': component.capitalize(),
            'Score': f"{details['score']:.1f}/100",
            'Weight': f"{details['weight']:.0%}",
            'Contribution': f"{details['contribution']:.1f} points"
        })
        total_contribution += details['contribution']

    # Display as a nice table
    if contribution_data:
        contrib_df = pd.DataFrame(contribution_data)
        st.dataframe(contrib_df, use_container_width=True)

        # Show final calculation
        st.markdown(f"**🎯 Total Weighted Score: {total_contribution:.1f}/100**")

        # Show the weights explanation
        st.caption("💡 Weights: Conversion 30% (most critical for ROI) • Delivery 25% • Engagement 25% • Revenue 20%")

    # Performance Insights
    st.subheader("🎯 Performance Insights")

    # Key metrics breakdown
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        total_sent = breakdown_data['Sent'].sum()
        st.metric("📤 Total Sent", format_metric(total_sent))

        total_delivered = breakdown_data['Delivered'].sum()
        delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0
        st.metric("📧 Delivery Rate", f"{delivery_rate:.1f}%")

    with col2:
        total_impressions = breakdown_data['Unique Impressions'].sum() if 'Unique Impressions' in breakdown_data.columns else 0
        st.metric("👁️ Total Impressions", format_metric(total_impressions))

        total_clicks = breakdown_data['Unique Clicks'].sum()
        ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        st.metric("🖱️ CTR", f"{ctr:.2f}%")

    with col3:
        total_conversions = breakdown_data['Selected Conversions'].sum() if 'Selected Conversions' in breakdown_data.columns else breakdown_data['Unique Conversions'].sum()
        st.metric(selected_conv_label, format_metric(total_conversions))

        conversion_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
        st.metric("📈 Conversion Rate", f"{conversion_rate:.2f}%")

    with col4:
        total_revenue = breakdown_data['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in breakdown_data.columns else breakdown_data['Revenue (SAR)'].sum()
        st.metric(selected_rev_label, format_metric(total_revenue, "SAR"))

        rpc = (total_revenue / total_conversions) if total_conversions > 0 else 0
        st.metric("💰 Revenue/Conversion", format_metric(rpc, "SAR"))

    # Performance vs Portfolio Analysis
    st.subheader("📊 Performance vs Portfolio")

    # Calculate portfolio averages
    portfolio_delivery_rate = (filtered_df['Delivered'].sum() / filtered_df['Sent'].sum() * 100) if filtered_df['Sent'].sum() > 0 else 0
    portfolio_ctr = (filtered_df['Unique Clicks'].sum() / filtered_df['Unique Impressions'].sum() * 100) if filtered_df['Unique Impressions'].sum() > 0 else 0
    portfolio_conversion_rate = (filtered_df['Selected Conversions'].sum() / filtered_df['Unique Clicks'].sum() * 100) if filtered_df['Unique Clicks'].sum() > 0 else 0
    portfolio_rpc = (filtered_df['Selected Revenue (SAR)'].sum() / filtered_df['Selected Conversions'].sum()) if filtered_df['Selected Conversions'].sum() > 0 else 0

    # Compare campaign vs portfolio
    comparison_data = {
        'Metric': ['Delivery Rate', 'CTR', 'Conversion Rate', 'Revenue/Conversion'],
        'Campaign': [delivery_rate, ctr, conversion_rate, rpc],
        'Portfolio Average': [portfolio_delivery_rate, portfolio_ctr, portfolio_conversion_rate, portfolio_rpc],
        'Difference': [
            delivery_rate - portfolio_delivery_rate,
            ctr - portfolio_ctr,
            conversion_rate - portfolio_conversion_rate,
            rpc - portfolio_rpc
        ]
    }

    comparison_df = pd.DataFrame(comparison_data)

    # Format for display
    display_comparison = comparison_df.copy()
    display_comparison['Campaign'] = display_comparison.apply(
        lambda row: f"{row['Campaign']:.1f}%" if 'Rate' in row['Metric'] else format_metric(row['Campaign'], "SAR" if "Revenue" in row['Metric'] else ""),
        axis=1
    )
    display_comparison['Portfolio Average'] = display_comparison.apply(
        lambda row: f"{row['Portfolio Average']:.1f}%" if 'Rate' in row['Metric'] else format_metric(row['Portfolio Average'], "SAR" if "Revenue" in row['Metric'] else ""),
        axis=1
    )
    display_comparison['Difference'] = display_comparison.apply(
        lambda row: f"{row['Difference']:+.1f}%" if 'Rate' in row['Metric'] else f"{format_metric(row['Difference'], 'SAR' if 'Revenue' in row['Metric'] else '')}",
        axis=1
    )

    st.dataframe(display_comparison, use_container_width=True)

    # Performance Summary
    st.subheader("📋 Performance Summary")

    # Calculate performance level for each metric
    summary_points = []

    if delivery_rate > portfolio_delivery_rate * 1.1:
        summary_points.append("🚀 **Delivery Excellence**: Significantly above portfolio average")
    elif delivery_rate < portfolio_delivery_rate * 0.9:
        summary_points.append("⚠️ **Delivery Challenge**: Below portfolio average - investigate deliverability")

    if ctr > portfolio_ctr * 1.1:
        summary_points.append("🎯 **Engagement Strength**: Strong click-through performance")
    elif ctr < portfolio_ctr * 0.9:
        summary_points.append("📉 **Engagement Opportunity**: CTR below average - consider creative optimization")

    if conversion_rate > portfolio_conversion_rate * 1.1:
        summary_points.append("💰 **Conversion Champion**: Exceptional conversion performance")
    elif conversion_rate < portfolio_conversion_rate * 0.9:
        summary_points.append("🔄 **Conversion Focus**: Conversion rate needs improvement")

    if rpc > portfolio_rpc * 1.1:
        summary_points.append("💎 **Revenue Efficiency**: High-value conversions")
    elif rpc < portfolio_rpc * 0.9:
        summary_points.append("💸 **Revenue Optimization**: Revenue per conversion below average")

    if summary_points:
        for point in summary_points:
            st.info(point)
    else:
        st.info("📊 Campaign performance is generally aligned with portfolio averages")

    # Actionable Recommendations
    st.subheader("🎯 Actionable Recommendations")

    recommendations = []

    # Delivery recommendations
    if delivery_rate < portfolio_delivery_rate * 0.95:
        recommendations.append("📧 **Improve Deliverability**: Review sender reputation, authentication, and content filters")
        recommendations.append("🔍 **List Quality**: Clean email lists and remove inactive subscribers")

    # Engagement recommendations
    if ctr < portfolio_ctr * 0.95:
        recommendations.append("🎨 **Creative Optimization**: Test subject lines, preheaders, and visual elements")
        recommendations.append("⏰ **Timing Strategy**: Experiment with send times and frequencies")

    # Conversion recommendations
    if conversion_rate < portfolio_conversion_rate * 0.95:
        recommendations.append("🎯 **Landing Page Optimization**: Improve page load speed and mobile experience")
        recommendations.append("🛒 **Call-to-Action**: Test button text, placement, and design")

    # Revenue recommendations
    if rpc < portfolio_rpc * 0.95:
        recommendations.append("💰 **Value Proposition**: Enhance product messaging and benefits")
        recommendations.append("🎯 **Audience Targeting**: Focus on higher-value customer segments")

    # Success recommendations
    if delivery_rate > portfolio_delivery_rate * 1.05 and ctr > portfolio_ctr * 1.05 and conversion_rate > portfolio_conversion_rate * 1.05:
        recommendations.append("📈 **Scale Up**: This campaign shows strong performance - consider increasing budget")
        recommendations.append("🔄 **Replicate Success**: Apply successful elements to other campaigns")

    if recommendations:
        for rec in recommendations:
            st.success(rec)
    else:
        st.info("✅ Campaign is performing well across all metrics - continue monitoring and optimizing")

# Campaign Funnel Analysis
st.subheader("🎯 Campaign Conversion Funnel Analysis")

funnel_campaign = st.selectbox("Select Campaign for Funnel Analysis",
                            unique_campaigns,
                            key='funnel_campaign')

if funnel_campaign and str(funnel_campaign) != 'nan':
    funnel_data = filtered_df[filtered_df['Campaign Name'] == funnel_campaign]
    funnel_analysis = analyze_campaign_funnel(funnel_data)

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
            fig_funnel.update_layout(title=f"Conversion Funnel: {funnel_campaign}")
            st.plotly_chart(fig_funnel)

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

# Campaign Anomaly Detection
st.subheader("🚨 Campaign Anomaly Detection")

col1, col2 = st.columns([2, 1])
with col2:
    lookback_days = st.slider("Analysis Period (days)", 7, 90, 30, key='campaign_anomaly_days')

with col1:
    st.write("Detecting unusual performance patterns in campaigns...")

if st.button("🔍 Detect Anomalies", key='detect_campaign_anomalies'):
    with st.spinner("Analyzing campaign performance patterns..."):
        anomalies = detect_campaign_anomalies(filtered_df, lookback_days)

        if anomalies:
            st.subheader(f"🚨 {len(anomalies)} Anomalies Detected")

            # Group by severity
            critical_anomalies = [a for a in anomalies if '🚨 Critical' in a.get('severity', '')]
            warning_anomalies = [a for a in anomalies if '⚠️ Warning' in a.get('severity', '')]

            if critical_anomalies:
                st.error(f"🚨 {len(critical_anomalies)} Critical Issues Require Immediate Attention")
                for anomaly in critical_anomalies[:5]:  # Show top 5
                    with st.expander(f"{anomaly['campaign']} - {anomaly['metric']} {anomaly.get('direction', '')}"):
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
                        st.write(f"**{anomaly['campaign']}** - {anomaly['metric']}: {anomaly['change_pct']:+.1f}% change")
                        st.write(f"   💡 {anomaly['recommendation']}")
        else:
            st.success("✅ No significant anomalies detected. All campaigns are performing within normal ranges!")
