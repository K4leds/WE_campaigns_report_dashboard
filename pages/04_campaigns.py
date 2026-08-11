import json

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric, read_cached_json, render_kpi_card
from components.table import render_table, render_chart, render_ai_explain_bar
from config import COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import get_attribution_display_label, get_selected_revenue_display_name, get_selected_conversion_display_name
from analysis import top_campaigns, attribution_analysis
from dashboard.health import calculate_campaign_health_score
from dashboard.funnels import analyze_campaign_funnel
from dashboard.anomalies import detect_campaign_anomalies
from dashboard.comparisons_logic import calculate_period_metrics, calculate_metric_changes
from dashboard.charts import render_health_dashboard


# ---------------------------------------------------------------------------
# Cached data-computation helpers (heavy Pandas ops only; no Plotly figures)
# ---------------------------------------------------------------------------

@st.cache_data
def _cached_top_campaigns(filtered_df_json, camp_metric):
    """Cached top_campaigns() call + Conversion Rate scaling."""
    filtered_df = read_cached_json(filtered_df_json)
    top_camp = top_campaigns(filtered_df, camp_metric)
    if camp_metric == 'Conversion Rate' and camp_metric in top_camp.columns:
        top_camp = top_camp.copy()
        top_camp[camp_metric] = top_camp[camp_metric] * 100
    return top_camp


@st.cache_data
def _cached_campaign_type_breakdown(filtered_df_json):
    """Cached campaign-type groupby aggregation with calculated columns."""
    filtered_df = read_cached_json(filtered_df_json)
    if 'Type of Campaign' not in filtered_df.columns:
        return None

    type_agg_cols = {'Sent': 'sum', 'Delivered': 'sum', 'Unique Clicks': 'sum', 'Unique Conversions': 'sum'}
    for col in ['Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Selected Revenue (SAR)']:
        if col in filtered_df.columns:
            type_agg_cols[col] = 'sum'

    type_breakdown = filtered_df.groupby('Type of Campaign').agg(type_agg_cols).reset_index()
    type_breakdown['Conversion Rate'] = np.where(
        type_breakdown['Unique Clicks'] > 0,
        type_breakdown['Unique Conversions'] / type_breakdown['Unique Clicks'], 0
    )

    # AOV for each revenue type
    conv_mask = type_breakdown['Unique Conversions'] > 0
    if 'Revenue (SAR)' in type_breakdown.columns:
        type_breakdown['AOV (SAR)'] = np.where(conv_mask, type_breakdown['Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0)
    if 'Click-Through Revenue (SAR)' in type_breakdown.columns:
        type_breakdown['AOV Click-Through (SAR)'] = np.where(conv_mask, type_breakdown['Click-Through Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0)
    if 'Impression-Through Revenue (SAR)' in type_breakdown.columns:
        type_breakdown['AOV Impression-Through (SAR)'] = np.where(conv_mask, type_breakdown['Impression-Through Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0)
    if 'Selected Revenue (SAR)' in type_breakdown.columns:
        type_breakdown['AOV Selected (SAR)'] = np.where(conv_mask, type_breakdown['Selected Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0)

    return type_breakdown


@st.cache_data
def _cached_one_time_campaigns(filtered_df_json, min_sent_threshold):
    """Cached one-time campaign aggregation: groupby + calculated columns + sort."""
    filtered_df = read_cached_json(filtered_df_json)
    if 'Type of Campaign' not in filtered_df.columns:
        return None
    onetime_df = filtered_df[filtered_df['Type of Campaign'].str.lower().str.contains('one-time', na=False)].copy()
    if onetime_df.empty:
        return None

    # Build aggregation dict dynamically based on available columns
    agg_dict = {
        'Sent': 'sum',
        'Delivered': 'sum',
        'Failed': 'sum',
        'Unique Clicks': 'sum',
        'Unique Conversions': 'sum',
        'Day': 'min'
    }
    for col in ['Selected Revenue (SAR)', 'Revenue (SAR)', 'Selected Conversions',
                'Unique Click-Through Conversions', 'Unique Impressions',
                'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']:
        if col in onetime_df.columns:
            agg_dict[col] = 'sum'

    groupby_cols = ['Campaign Name', 'Channel'] if 'Channel' in onetime_df.columns else ['Campaign Name']
    onetime_summary = onetime_df.groupby(groupby_cols).agg(agg_dict).reset_index()
    onetime_summary = onetime_summary[onetime_summary['Sent'] >= min_sent_threshold]

    # Calculated columns
    onetime_summary['Delivery Rate'] = onetime_summary['Delivered'] / onetime_summary['Sent']
    onetime_summary['CTR'] = np.where(onetime_summary['Delivered'] > 0,
                                      onetime_summary['Unique Clicks'] / onetime_summary['Delivered'], 0)

    # Conversion rate with correct numerator/denominator pairing
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
    onetime_summary = onetime_summary.sort_values('Sent', ascending=False)
    return onetime_summary


@st.cache_data
def _cached_monthly_one_time(filtered_df_json, min_sent_threshold):
    """Cached monthly aggregation of one-time campaigns, by the calendar month the
    activity/revenue actually happened (earned month).

    WebEngage emits one row per campaign per day through the report end date, so a
    campaign sent once keeps producing trailing all-zero rows in later months.
    Summing metrics by each row's calendar month is what we want — revenue lands in
    the month it was earned, and a campaign's send + later conversions naturally
    split across the months they occurred. Those trailing all-zero rows add nothing
    to the sums, but they WOULD inflate the campaign count, so Unique Campaigns only
    counts campaigns with real activity (a send, delivery, conversion, or revenue)
    that month.
    """
    filtered_df = read_cached_json(filtered_df_json)
    if 'Type of Campaign' not in filtered_df.columns:
        return None
    onetime_df = filtered_df[filtered_df['Type of Campaign'].str.lower().str.contains('one-time', na=False)].copy()
    if onetime_df.empty:
        return None

    # Calendar month the row's activity occurred (read_cached_json already restores
    # Day/Reporting Period Start Date to real datetimes).
    if 'Day' in onetime_df.columns:
        date_col = 'Day'
    elif 'Reporting Period Start Date' in onetime_df.columns:
        date_col = 'Reporting Period Start Date'
    else:
        return None

    onetime_df['Month'] = onetime_df[date_col].dt.to_period('M').dt.strftime('%Y-%m')

    # Revenue columns shown side by side (independent of the sidebar attribution
    # toggle, so this table never looks "frozen" when only one model has revenue).
    revenue_cols = [c for c in ['Revenue (SAR)', 'Impression-Through Revenue (SAR)',
                                'Click-Through Revenue (SAR)'] if c in onetime_df.columns]
    sum_cols = [c for c in ['Sent', 'Delivered', 'Unique Conversions'] if c in onetime_df.columns] + revenue_cols

    # Metrics summed over every row (trailing all-zero rows contribute nothing).
    monthly_campaigns = onetime_df.groupby('Month')[sum_cols].sum().reset_index()

    # Count only campaigns that had real activity that month, so trailing
    # all-zero rows don't inflate the Unique Campaigns figure.
    active_rows = onetime_df[onetime_df[sum_cols].gt(0).any(axis=1)]
    active_counts = (active_rows.groupby('Month')['Campaign Name'].nunique()
                     .rename('Unique Campaigns'))
    monthly_campaigns = monthly_campaigns.merge(active_counts, on='Month', how='left')
    monthly_campaigns['Unique Campaigns'] = monthly_campaigns['Unique Campaigns'].fillna(0).astype(int)

    ordered = ['Month', 'Unique Campaigns'] + sum_cols
    monthly_campaigns = monthly_campaigns[[c for c in ordered if c in monthly_campaigns.columns]]
    monthly_campaigns = monthly_campaigns.sort_values('Month', ascending=False)
    return monthly_campaigns, revenue_cols


@st.cache_data
def _cached_campaign_drilldown_kpis(filtered_df_json, selected_campaigns):
    """Cached KPI column-sums for the selected campaigns."""
    filtered_df = read_cached_json(filtered_df_json)
    camp_details = filtered_df[filtered_df['Campaign Name'].isin(selected_campaigns)]

    total_sent = camp_details['Sent'].sum()
    total_delivered = camp_details['Delivered'].sum()
    total_clicks = camp_details['Unique Clicks'].sum()
    conv_total = camp_details['Selected Conversions'].sum() if 'Selected Conversions' in camp_details.columns else camp_details['Unique Conversions'].sum()
    rev_total = camp_details['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in camp_details.columns else camp_details['Revenue (SAR)'].sum()
    ct_rev = camp_details['Click-Through Revenue (SAR)'].sum()
    total_revenue = rev_total
    total_conversions = conv_total

    return {
        'total_sent': total_sent,
        'total_delivered': total_delivered,
        'total_clicks': total_clicks,
        'conv_total': conv_total,
        'rev_total': rev_total,
        'ct_rev': ct_rev,
        'total_revenue': total_revenue,
        'total_conversions': total_conversions,
    }


@st.cache_data
def _cached_channel_perf_for_campaigns(filtered_df_json, selected_campaigns):
    """Cached Channel groupby for the selected campaigns."""
    filtered_df = read_cached_json(filtered_df_json)
    camp_details = filtered_df[filtered_df['Campaign Name'].isin(selected_campaigns)]
    agg_cols = {c: 'sum' for c in ['Sent', 'Delivered', 'Unique Conversions', 'Revenue (SAR)',
                                   'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
                if c in camp_details.columns}
    return camp_details.groupby('Channel').agg(agg_cols).reset_index()


@st.cache_data
def _cached_campaign_health_scores(filtered_df_json):
    """Cached campaign health scores loop — heaviest computation on the page."""
    filtered_df = read_cached_json(filtered_df_json)
    campaign_health_data = []
    unique_campaigns = filtered_df['Campaign Name'].dropna().unique()

    for campaign in unique_campaigns:
        if str(campaign) != 'nan' and campaign:
            campaign_data = filtered_df[filtered_df['Campaign Name'] == campaign]
            health_info = calculate_campaign_health_score(campaign_data, filtered_df)
            campaign_health_data.append({
                'Campaign Name': campaign,
                'Status': campaign_data['Status'].iloc[-1] if 'Status' in campaign_data.columns else None,
                'Health Score': health_info['health_score'],
                'Tier': health_info['tier'],
                'Revenue (SAR)': campaign_data['Revenue (SAR)'].sum(),
                'Impression-Through Revenue (SAR)': campaign_data['Impression-Through Revenue (SAR)'].sum(),
                'Click-Through Revenue (SAR)': campaign_data['Click-Through Revenue (SAR)'].sum(),
                'Total Conversions': campaign_data['Unique Conversions'].sum(),
                'Sent': campaign_data['Sent'].sum() if 'Sent' in campaign_data.columns else 0,
                'Days': campaign_data['Reporting Period Start Date'].nunique() if 'Reporting Period Start Date' in campaign_data.columns else len(campaign_data),
                'Delivery Score': health_info['component_scores'].get('delivery', 0),
                'Engagement Score': health_info['component_scores'].get('engagement', 0),
                'Conversion Score': health_info['component_scores'].get('conversion', 0),
                'Revenue Score': health_info['component_scores'].get('revenue', 0)
            })
    return campaign_health_data


ctx = get_ctx()
df = ctx.df
filtered_df = ctx.filtered_df
unique_campaigns = filtered_df['Campaign Name'].dropna().unique()
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

# --- Glance row: the overall picture before ranking by any one metric ---
rev_col_glance = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
conv_col_glance = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'
n_campaigns_glance = filtered_df['Campaign Name'].dropna().nunique()
total_rev_glance = filtered_df[rev_col_glance].sum() if rev_col_glance in filtered_df.columns else 0
total_conv_glance = filtered_df[conv_col_glance].sum() if conv_col_glance in filtered_df.columns else 0
g1, g2, g3 = st.columns(3)
with g1:
    render_kpi_card("Campaigns", format_metric(n_campaigns_glance), icon="🚀")
with g2:
    render_kpi_card(selected_rev_label, format_metric(total_rev_glance, "SAR"), icon="💰")
with g3:
    render_kpi_card(selected_conv_label, format_metric(total_conv_glance), icon="🎯")

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
top_camp = _cached_top_campaigns(filtered_df.to_json(), camp_metric)

# Build column_config for proper numeric formatting
top_camp_cc = {}
if 'Revenue' in camp_metric:
    top_camp_cc[camp_metric] = st.column_config.NumberColumn(label=camp_metric, format='compact')
elif camp_metric in ['Unique Conversions', 'Unique Clicks', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions']:
    top_camp_cc[camp_metric] = st.column_config.NumberColumn(label=camp_metric, format='compact')
elif camp_metric == 'Conversion Rate':
    top_camp_cc[camp_metric] = st.column_config.NumberColumn(label=camp_metric, format='%.2f%%')

# Handle attribution rename for column_config keys
renamed_display = top_camp.rename(columns=attribution_rename)
if camp_metric in attribution_rename:
    renamed_metric = attribution_rename[camp_metric]
    top_camp_cc[renamed_metric] = top_camp_cc.pop(camp_metric)

render_table(renamed_display, key="top_camp", column_config=top_camp_cc if top_camp_cc else None)

# Horizontal ranked bars (largest on top): long campaign names stay readable
# on the y-axis instead of colliding as rotated x-ticks.
fig = px.bar(top_camp.iloc[::-1], x=camp_metric, y='Campaign Name', orientation='h',
             title=f"Top Campaigns by {_attribution_display(camp_metric)}",
             color_discrete_sequence=COLOR_SEQUENCE)
fig.update_layout(yaxis_title=None, height=max(400, 36 * len(top_camp)))
render_chart(fig, top_camp, key="top_campaigns_chart", ai_label=f"Top Campaigns by {_attribution_display(camp_metric)}")

# Campaign Type Breakdown (Journey vs One-Time)
if 'Type of Campaign' in filtered_df.columns:
    st.subheader("Performance by Campaign Type")
    type_breakdown = _cached_campaign_type_breakdown(filtered_df.to_json())

    # Display table - drop Selected Revenue/Conversions since all attribution types are shown
    type_display = type_breakdown.copy()
    for drop_col in ['Selected Revenue (SAR)', 'Selected Conversions']:
        if drop_col in type_display.columns:
            type_display = type_display.drop(columns=[drop_col])

    # Conversion Rate is stored as a 0-1 fraction; render_table's percent formatter
    # expects rate columns pre-scaled to 0-100 (matching 07_channels' convention).
    if 'Conversion Rate' in type_display.columns:
        type_display['Conversion Rate'] = type_display['Conversion Rate'] * 100

    # Build column_config for type breakdown
    type_cc = {}
    for col in ['Sent', 'Delivered', 'Unique Clicks', 'Unique Conversions']:
        if col in type_display.columns:
            type_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
    for col in [c for c in type_display.columns if 'Revenue' in c]:
        type_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
    for col in [c for c in type_display.columns if 'AOV' in c]:
        type_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
    if 'Conversion Rate' in type_display.columns:
        type_cc['Conversion Rate'] = st.column_config.NumberColumn(label='Conversion Rate', format='%.2f%%')

    # Compute the "Total" pinned row from raw (unrounded) values, matching type_display's columns.
    total_row = {'Type of Campaign': 'Total'}
    total_conversions = type_breakdown['Unique Conversions'].sum()
    for col in type_display.columns:
        if col == 'Type of Campaign':
            continue
        elif col == 'Conversion Rate':
            clicks_total = type_breakdown['Unique Clicks'].sum()
            total_row[col] = (type_breakdown['Unique Conversions'].sum() / clicks_total * 100) if clicks_total > 0 else 0
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
            total_row[col] = type_display[col].sum()

    render_table(type_display, key="type_breakdown", column_config=type_cc, total_row=total_row)

    # Side-by-side charts
    type_chart_data = type_breakdown
    render_ai_explain_bar(type_chart_data, key="campaign_type_charts", ai_label="Performance by Campaign Type",
                           help_text="Explain these campaign type charts with AI")
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
            st.plotly_chart(fig_type_rev)
    with type_col2:
        conv_display_name = get_selected_conversion_display_name(conversion_attribution)
        fig_type_conv = px.bar(type_chart_data, x='Type of Campaign', y='Unique Conversions',
                               title=f"{conv_display_name} by Campaign Type", color='Type of Campaign',
                               color_discrete_sequence=COLOR_SEQUENCE,
                               labels={'Unique Conversions': conv_display_name})
        fig_type_conv.update_layout(showlegend=False)
        st.plotly_chart(fig_type_conv)

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
        onetime_summary = _cached_one_time_campaigns(filtered_df.to_json(), min_sent_threshold)

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
                st.dataframe(sample_data)

                st.write("**After aggregation:**")
                sample_agg = onetime_summary[onetime_summary['Campaign Name'] == sample_campaign]
                st.dataframe(sample_agg)

                st.write(f"**Number of days in raw data:** {len(sample_data)}")
                st.write(f"**Total campaigns in dataset:** {onetime_df['Campaign Name'].nunique()}")
                st.write(f"**Total rows before aggregation:** {len(onetime_df)}")
                st.write(f"**Total rows after aggregation:** {len(onetime_summary)}")


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

        # Delivery Rate / CTR / Conversion Rate are stored as 0-1 fractions; render_table's
        # percent formatter expects rate columns pre-scaled to 0-100 (matches 07_channels'
        # convention) — otherwise a 5% rate renders as "0.05%".
        for col in ['Delivery Rate', 'CTR', 'Conversion Rate']:
            if col in onetime_display.columns:
                onetime_display[col] = onetime_display[col] * 100

        # Build column_config for one-time campaigns
        onetime_cc = {}
        for col in ['Sent', 'Delivered', 'Unique Clicks', conv_col_display]:
            if col in onetime_display.columns:
                onetime_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
        for col in [revenue_col]:
            if col in onetime_display.columns:
                onetime_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
        for col in ['Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']:
            if col in onetime_display.columns:
                onetime_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
        for col in ['Delivery Rate', 'CTR', 'Conversion Rate']:
            if col in onetime_display.columns:
                onetime_cc[col] = st.column_config.NumberColumn(label=col, format='%.2f%%')

        # Rename columns to show actual attribution model
        onetime_display = onetime_display.rename(columns=attribution_rename)

        # Map column_config keys to post-rename names
        onetime_cc_renamed = {}
        for col, cfg in onetime_cc.items():
            renamed = attribution_rename.get(col, col)
            onetime_cc_renamed[renamed] = cfg

        render_table(onetime_display, key="onetime_campaigns", column_config=onetime_cc_renamed)

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

            # Delivery Rate is stored as a 0-1 fraction; render_table's percent formatter
            # expects rate columns pre-scaled to 0-100 (matches 07_channels' convention).
            if 'Delivery Rate' in channel_breakdown.columns:
                channel_breakdown['Delivery Rate'] = channel_breakdown['Delivery Rate'] * 100

            # Build column_config for channel breakdown
            channel_cc = {}
            for col in ['Sent', 'Delivered', 'Conversions']:
                if col in channel_breakdown.columns:
                    channel_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
            if rev_col_channel in channel_breakdown.columns:
                channel_cc[rev_col_channel] = st.column_config.NumberColumn(label=rev_col_channel, format='compact')
            if 'Delivery Rate' in channel_breakdown.columns:
                channel_cc['Delivery Rate'] = st.column_config.NumberColumn(label='Delivery Rate', format='%.2f%%')

            # Rename columns to show actual attribution model
            channel_display = channel_breakdown.copy()
            channel_display = channel_display.rename(columns=attribution_rename)
            display_rev_col = selected_rev_label if rev_col_channel == 'Selected Revenue (SAR)' else rev_col_channel

            # Map column_config keys to post-rename names
            channel_cc_renamed = {}
            for col, cfg in channel_cc.items():
                renamed = attribution_rename.get(col, col)
                channel_cc_renamed[renamed] = cfg

            display_cols = ['Channel', 'Sent', 'Delivered', 'Delivery Rate', 'Conversions', display_rev_col]
            display_cols = [c for c in display_cols if c in channel_display.columns]
            render_table(channel_display[display_cols], key="channel_breakdown", column_config=channel_cc_renamed)
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
            # Roll each one-time campaign up to its SEND month (full lifetime
            # totals credited to the month it was sent), and show all three
            # revenue models side by side so this table is independent of the
            # sidebar attribution toggle.
            monthly_campaigns, revenue_cols = _cached_monthly_one_time(filtered_df.to_json(), min_sent_threshold)

            # Build column_config for monthly display
            monthly_cc = {}
            for col in ['Sent', 'Delivered', 'Unique Conversions', 'Unique Campaigns']:
                if col in monthly_campaigns.columns:
                    monthly_cc[col] = st.column_config.NumberColumn(label=col, format='%.0f')
            for col in revenue_cols:
                if col in monthly_campaigns.columns:
                    monthly_cc[col] = st.column_config.NumberColumn(label=col, format='%.2f')

            # Chart first (the "what happened" signal); table is the opt-in
            # drill-down to verify exact numbers, not the default view.
            chart_data = monthly_campaigns.sort_values('Month')
            fig_monthly = px.bar(chart_data, x='Month', y='Unique Campaigns',
                               title="Unique One-Time Campaigns per Month",
                               color_discrete_sequence=[COLORS['primary']])
            fig_monthly.update_layout(
                xaxis_title="Month",
                yaxis_title="Number of Campaigns",
                xaxis=dict(type='category')
            )
            render_chart(fig_monthly, chart_data, key="onetime_monthly_trend", ai_label="One-Time Campaigns per Month")

            with st.expander("View Monthly Details Table", expanded=False):
                render_table(monthly_campaigns, key="monthly_onetime", column_config=monthly_cc)

# Campaign Drill-Down
st.subheader("Campaign Drill-Down")
selected_campaigns = st.multiselect("Select Campaigns for Details", filtered_df['Campaign Name'].unique(), key='drill_camp')
if selected_campaigns:
    camp_details = filtered_df[filtered_df['Campaign Name'].isin(selected_campaigns)]
    kpis = _cached_campaign_drilldown_kpis(filtered_df.to_json(), tuple(selected_campaigns))

    # Summary KPIs - Row 1: Volume Metrics
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    with col1:
        st.metric('Total Sent', format_metric(kpis['total_sent']))
    with col2:
        st.metric('Total Delivered', format_metric(kpis['total_delivered']))
    with col3:
        st.metric('Total Clicks', format_metric(kpis['total_clicks']))
    with col4:
        st.metric(selected_conv_label, format_metric(kpis['conv_total']))
    with col5:
        st.metric(selected_rev_label, format_metric(kpis['rev_total'], 'SAR'))
    with col6:
        st.metric('Click-Through Revenue', format_metric(kpis['ct_rev'], 'SAR'))

    # Row 2: Business Metrics
    st.markdown("#### 💰 Business Intelligence")
    biz_col1, biz_col2, biz_col3, biz_col4 = st.columns(4)

    total_revenue = kpis['total_revenue']
    total_conversions = kpis['total_conversions']
    total_clicks = kpis['total_clicks']

    with biz_col1:
        aov = (total_revenue / total_conversions) if total_conversions > 0 else 0
        st.metric('Average Order Value', format_metric(aov, 'SAR'), help='Revenue per conversion')
    with biz_col2:
        rpc = (total_revenue / total_clicks) if total_clicks > 0 else 0
        st.metric('Revenue Per Click', format_metric(rpc, 'SAR'), help='Revenue generated per click')
    with biz_col3:
        avg_ctr = camp_details['CTR'].mean()
        st.metric('Avg CTR', f'{avg_ctr:.2%}', help='Average click-through rate')
    with biz_col4:
        total_clicks_metric = kpis['total_clicks']
        total_conversions_metric = kpis['conv_total']
        avg_conv_rate = (total_conversions_metric / total_clicks_metric) if total_clicks_metric > 0 else 0
        st.metric('Avg Conversion Rate', f'{avg_conv_rate:.2%}', help='Average conversion rate')

    # Performance by Channel
    st.subheader("Performance by Channel")
    chan_perf = _cached_channel_perf_for_campaigns(filtered_df.to_json(), tuple(selected_campaigns))
    # Build column_config for channel performance
    chan_perf_cc = {}
    for col in ['Sent', 'Delivered', 'Unique Conversions']:
        if col in chan_perf.columns:
            chan_perf_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
    for col in ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']:
        if col in chan_perf.columns:
            chan_perf_cc[col] = st.column_config.NumberColumn(label=col, format='compact')

    # Compute the "Total" pinned row from raw (unrounded) values.
    total_row = {'Channel': 'Total'}
    for col in chan_perf.columns:
        if col != 'Channel':
            total_row[col] = chan_perf[col].sum()

    render_table(chan_perf, key="camp_channel_perf", column_config=chan_perf_cc, total_row=total_row)
    conv_display_name = get_selected_conversion_display_name(conversion_attribution)
    fig_chan = px.bar(chan_perf, x='Channel', y='Unique Conversions',
                      title=f"{conv_display_name} by Channel for Selected Campaigns",
                      color='Channel', color_discrete_map=CHANNEL_COLORS,
                      labels={'Unique Conversions': conv_display_name})
    fig_chan.update_layout(showlegend=False)
    render_chart(fig_chan, chan_perf, key="camp_drilldown_channel", ai_label="Channel Performance for Selected Campaigns")

    # Time Series for Selected Campaigns
    st.subheader("Time Series Performance")
    ts_camp = camp_details.groupby(['Reporting Period Start Date', 'Campaign Name'])[camp_metric].sum().reset_index()
    if not ts_camp.empty:
        fig_ts_camp = px.line(ts_camp, x='Reporting Period Start Date', y=camp_metric, color='Campaign Name',
                              title=f"{camp_metric} Over Time for Selected Campaigns",
                              color_discrete_sequence=COLOR_SEQUENCE)
        fig_ts_camp.update_traces(line_width=2.5)
        render_chart(fig_ts_camp, ts_camp, key="camp_drilldown_ts", ai_label=f"{camp_metric} Over Time for Selected Campaigns")

    # Conversion Attribution
    st.subheader("Conversion Attribution")
    attr_df_camp = attribution_analysis(camp_details)
    fig_attr_camp = px.pie(attr_df_camp, names='Source', values='Conversions', title="Attribution for Selected Campaigns",
                            color_discrete_sequence=COLOR_SEQUENCE)
    render_chart(fig_attr_camp, attr_df_camp, key="camp_drilldown_attr", ai_label="Attribution for Selected Campaigns")

    # Failed Reasons for Selected Campaigns
    st.subheader("Failed Reasons")
    failed_cols = [col for col in camp_details.columns if 'Failed' in col and col != 'Failed']
    if failed_cols:
        failed_camp = camp_details[failed_cols].sum().reset_index().rename(columns={'index': 'Reason', 0: 'Count'})
        fig_fail_camp = px.bar(failed_camp.sort_values('Count'), x='Count', y='Reason', orientation='h',
                               title="Failed Reasons for Selected Campaigns",
                               color_discrete_sequence=[COLORS['danger']])
        render_chart(fig_fail_camp, failed_camp, key="camp_drilldown_failed", ai_label="Failed Reasons for Selected Campaigns")

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
    - 💰 **Revenue Impact**: 35% - log-scaled total revenue, so big earners rank above tiny-but-efficient campaigns
    - 🚀 **Conversion Performance**: 25% - click-through conversions ÷ unique clicks (Empirical Bayes smoothed)
    - 🎯 **Engagement Performance**: 20% - click-through rate, impressions → clicks (Empirical Bayes smoothed)
    - 📧 **Delivery Performance**: 20% - delivery rate, sent → delivered

    #### **Performance Tiers (relative to this portfolio):**
    - **Excellent (80-100)**: Top of this portfolio - scale and replicate
    - **Good (60-79)**: Above portfolio average - minor optimizations
    - **Fair (40-59)**: Below portfolio average - review and improve
    - **Poor (0-39)**: Bottom of this portfolio - immediate action needed

    #### **Data Sufficiency:**
    Campaigns with fewer than 100 sends, 5 conversions, or 3 days of data are marked "Insufficient Data" instead of being ranked.
    """)


# Calculate health scores for all campaigns
campaign_health_data = _cached_campaign_health_scores(filtered_df.to_json())

if campaign_health_data:
    health_df = pd.DataFrame(campaign_health_data)
    selected_campaign_health = render_health_dashboard(health_df, 'Campaign Name', 'Campaign', 'campaign')

    if selected_campaign_health:
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
        st.dataframe(contrib_df)

        # Show final calculation
        st.markdown(f"**🎯 Total Weighted Score: {total_contribution:.1f}/100**")

        # Show the weights explanation
        st.caption("💡 Weights: Revenue Impact 35% (business outcome first) • Conversion 25% • Engagement 20% • Delivery 20%")

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

    # Build column_config — Metric column is text, rest are numeric with per-column format
    perf_cc = {
        'Metric': st.column_config.TextColumn(label='Metric'),
        'Campaign': st.column_config.NumberColumn(label='Campaign', format='%.2f'),
        'Portfolio Average': st.column_config.NumberColumn(label='Portfolio Average', format='%.2f'),
        'Difference': st.column_config.NumberColumn(label='Difference', format='%+.2f'),
    }

    render_table(comparison_df, key="campaign_vs_portfolio", column_config=perf_cc)

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
            funnel_df = pd.DataFrame({'Stage': funnel_stages, 'Value': funnel_values})
            render_chart(fig_funnel, funnel_df, key="campaign_funnel", ai_label=f"Conversion Funnel: {funnel_campaign}")

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
