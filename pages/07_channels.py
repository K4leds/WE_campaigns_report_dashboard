import streamlit as st
import pandas as pd
import numpy as np
import json
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric, read_cached_json, render_kpi_card
from components.table import render_table, render_chart, render_ai_explain_bar
from components.channel_cards import render_channel_card, render_insight_chips, icon, channel_icon
from config import COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import get_attribution_display_label, get_selected_revenue_display_name, get_selected_conversion_display_name
from analysis import channel_analysis, esp_analysis, failed_reasons_analysis

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
channel_costs = ctx.channel_costs

# Display-friendly rename map for attribution-selected columns (mirrors app.py prelude)
attribution_rename = {'Selected Revenue (SAR)': selected_rev_label, 'Selected Conversions': selected_conv_label}


def _attribution_display(col_name):
    """Map internal 'Selected Revenue/Conversions' column names to the user-selected attribution label."""
    return get_attribution_display_label(col_name, revenue_attribution, conversion_attribution)


@st.cache_data
def _cached_channel_analysis(filtered_df_json):
    """Cache wrapper for channel_analysis() to avoid dark-screen rerenders."""
    _df = read_cached_json(filtered_df_json)
    return channel_analysis(_df)


@st.cache_data
def _cached_channel_type_breakdown(filtered_df_json):
    """Cache the Channel + Campaign Type groupby aggregation."""
    _df = read_cached_json(filtered_df_json)
    rev_col_type = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in _df.columns else 'Revenue (SAR)'
    conv_col_type = 'Selected Conversions' if 'Selected Conversions' in _df.columns else 'Unique Conversions'
    type_chan_agg = {'Sent': 'sum', 'Delivered': 'sum'}
    if conv_col_type in _df.columns:
        type_chan_agg[conv_col_type] = 'sum'
    if rev_col_type in _df.columns:
        type_chan_agg[rev_col_type] = 'sum'
    extra_rev_cols = [c for c in ['Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Impression-Through Revenue (SAR)']
                      if c in _df.columns and c != rev_col_type]
    extra_conv_cols = [c for c in ['Unique Conversions', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions']
                       if c in _df.columns and c != conv_col_type]
    for c in extra_rev_cols + extra_conv_cols:
        type_chan_agg[c] = 'sum'
    type_chan_df = _df.groupby(['Channel', 'Type of Campaign']).agg(type_chan_agg).reset_index()
    # Safety: fill NaN with 0 for attribution-aware columns (same reasoning as channel_analysis)
    if 'Selected Conversions' in type_chan_df.columns:
        type_chan_df['Selected Conversions'] = type_chan_df['Selected Conversions'].fillna(0)
    if 'Selected Revenue (SAR)' in type_chan_df.columns:
        type_chan_df['Selected Revenue (SAR)'] = type_chan_df['Selected Revenue (SAR)'].fillna(0)
    return type_chan_df, rev_col_type, conv_col_type, extra_rev_cols, extra_conv_cols


@st.cache_data
def _cached_channel_weekly(filtered_df_json):
    """Cache weekly Revenue + Conversions per channel, used by the card sparklines
    and the Channel Spotlight trend chart."""
    _df = read_cached_json(filtered_df_json)
    rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in _df.columns else 'Revenue (SAR)'
    conv_col = 'Selected Conversions' if 'Selected Conversions' in _df.columns else 'Unique Conversions'
    weekly = _df.groupby([pd.Grouper(key='Reporting Period Start Date', freq='W'), 'Channel']).agg(
        {rev_col: 'sum', conv_col: 'sum'}
    ).reset_index()
    weekly.columns = ['Week', 'Channel', 'Revenue', 'Conversions']
    return weekly


@st.cache_data
def _cached_failed_by_channel(filtered_df_json):
    """Cache the groupby Channel for failed delivery reasons."""
    _df = read_cached_json(filtered_df_json)
    failed_cols = [col for col in _df.columns if 'Failed' in col and col != 'Failed']
    if failed_cols:
        return _df.groupby('Channel')[failed_cols].sum().reset_index()
    return pd.DataFrame()


st.header("Channels & Delivery Analysis")

tab1, tab2 = st.tabs([":material/cell_tower: Channels", ":material/error: Failed Reasons"])

with tab1:
    chan_df = _cached_channel_analysis(filtered_df.to_json())

    # Channel conversion rate: always use click-through conversions as numerator so the rate
    # never exceeds 100% (Selected Conversions includes impression-through which can outnumber clicks).
    conv_rate_source_col = 'Selected Conversions' if 'Selected Conversions' in chan_df.columns else 'Unique Conversions'
    conv_rate_numerator_col = (
        'Unique Click-Through Conversions' if 'Unique Click-Through Conversions' in chan_df.columns
        else conv_rate_source_col
    )
    if conv_rate_numerator_col in chan_df.columns and 'Unique Clicks' in chan_df.columns:
        chan_df['Conversion Rate'] = np.where(
            chan_df['Unique Clicks'] > 0,
            np.minimum((chan_df[conv_rate_numerator_col] / chan_df['Unique Clicks']) * 100, 100.0),
            0
        )

    # =====================================================================
    # TOP DASHBOARD: everything about channel performance at a glance, no
    # sidebar filtering required. The existing table/charts below remain
    # untouched as the "scroll down for analysis" deep-dive layer.
    # =====================================================================
    rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in chan_df.columns else 'Revenue (SAR)'
    conv_col = 'Selected Conversions' if 'Selected Conversions' in chan_df.columns else 'Unique Conversions'
    rev_display_name_top = get_selected_revenue_display_name(revenue_attribution)
    conv_display_name_top = get_selected_conversion_display_name(conversion_attribution)

    chan_cards_df = chan_df.copy()
    chan_cards_df['Delivery Rate'] = np.where(
        chan_cards_df['Sent'] > 0, chan_cards_df['Delivered'] / chan_cards_df['Sent'] * 100, 0
    )
    chan_cards_df['CTR'] = np.where(
        chan_cards_df['Unique Impressions'] > 0,
        chan_cards_df['Unique Clicks'] / chan_cards_df['Unique Impressions'] * 100, 0
    )
    chan_cards_df = chan_cards_df.sort_values(rev_col, ascending=False)

    chan_comp_df = None
    if comparison_result:
        chan_comp_df = _cached_channel_analysis(comparison_result['comparison_data'].to_json())

    weekly_df = _cached_channel_weekly(filtered_df.to_json())

    # --- Headline strip ---
    total_revenue_top = chan_cards_df[rev_col].sum()
    total_conv_top = chan_cards_df[conv_col].sum()
    total_sent_top = chan_cards_df['Sent'].sum()
    total_delivered_top = chan_cards_df['Delivered'].sum()
    total_impr_top = chan_cards_df['Unique Impressions'].sum()
    total_clicks_top = chan_cards_df['Unique Clicks'].sum()
    active_channels_top = int((chan_cards_df['Sent'] > 0).sum())
    delivery_rate_top = (total_delivered_top / total_sent_top * 100) if total_sent_top > 0 else 0
    ctr_top = (total_clicks_top / total_impr_top * 100) if total_impr_top > 0 else 0

    comp_deltas = {}
    if chan_comp_df is not None:
        comp_rev_col = rev_col if rev_col in chan_comp_df.columns else 'Revenue (SAR)'
        comp_conv_col = conv_col if conv_col in chan_comp_df.columns else 'Unique Conversions'
        comp_sent = chan_comp_df['Sent'].sum()
        comp_delivered = chan_comp_df['Delivered'].sum()
        comp_impr = chan_comp_df['Unique Impressions'].sum()
        comp_clicks = chan_comp_df['Unique Clicks'].sum()
        comp_rev = chan_comp_df[comp_rev_col].sum() if comp_rev_col in chan_comp_df.columns else 0
        comp_conv = chan_comp_df[comp_conv_col].sum() if comp_conv_col in chan_comp_df.columns else 0
        comp_delivery_rate = (comp_delivered / comp_sent * 100) if comp_sent > 0 else 0
        comp_ctr = (comp_clicks / comp_impr * 100) if comp_impr > 0 else 0

        def _pct(cur, comp):
            return f"{'+' if cur >= comp else ''}{((cur - comp) / comp * 100):.1f}%" if comp else None

        comp_deltas = {
            'revenue': _pct(total_revenue_top, comp_rev),
            'conv': _pct(total_conv_top, comp_conv),
            'delivery': _pct(delivery_rate_top, comp_delivery_rate),
            'ctr': _pct(ctr_top, comp_ctr),
        }

    st.markdown(f"#### {icon('rocket', size=18)} Channels at a Glance", unsafe_allow_html=True)
    h1, h2, h3, h4, h5 = st.columns(5)
    with h1:
        render_kpi_card(rev_display_name_top, format_metric(total_revenue_top, "SAR"),
                         delta=comp_deltas.get('revenue'), icon=icon('cash_coin', size=22))
    with h2:
        render_kpi_card(conv_display_name_top, format_metric(total_conv_top),
                         delta=comp_deltas.get('conv'), icon=icon('bullseye', size=22))
    with h3:
        render_kpi_card("Active Channels", f"{active_channels_top}/{len(chan_cards_df)}", icon=icon('broadcast', size=22))
    with h4:
        render_kpi_card("Delivery Rate", f"{delivery_rate_top:.1f}%",
                         delta=comp_deltas.get('delivery'), icon=icon('inbox', size=22))
    with h5:
        render_kpi_card("CTR", f"{ctr_top:.1f}%", delta=comp_deltas.get('ctr'), icon=icon('cursor', size=22))

    # --- Channel cards grid ---
    st.markdown(f"#### {icon('broadcast', size=18)} Channel Performance", unsafe_allow_html=True)
    cols_per_row_cards = 4
    channels_list = chan_cards_df['Channel'].tolist()
    for row_start in range(0, len(channels_list), cols_per_row_cards):
        row_channels = channels_list[row_start:row_start + cols_per_row_cards]
        cols = st.columns(cols_per_row_cards)
        for col, channel_name in zip(cols, row_channels):
            with col:
                row = chan_cards_df[chan_cards_df['Channel'] == channel_name].iloc[0]
                comp_row = None
                if chan_comp_df is not None and channel_name in chan_comp_df['Channel'].values:
                    comp_row = chan_comp_df[chan_comp_df['Channel'] == channel_name].iloc[0]
                sparkline = weekly_df[weekly_df['Channel'] == channel_name]['Revenue']
                render_channel_card(
                    row, channel_costs=channel_costs, revenue_col=rev_col, conv_col=conv_col,
                    revenue_label=rev_display_name_top, conv_label=conv_display_name_top,
                    comparison_row=comp_row, sparkline_weekly=sparkline, key=f"chandash_{channel_name}",
                )

    # --- Insight strip ---
    insights = []
    active_only = chan_cards_df[chan_cards_df['Sent'] > 0]
    if not active_only.empty:
        top_rev_channel = active_only.iloc[0]
        insights.append({'icon': channel_icon(top_rev_channel['Channel'], color=COLORS['success']),
                          'text': f"Top Revenue: {top_rev_channel['Channel']} ({format_metric(top_rev_channel[rev_col], 'SAR')})",
                          'level': 'good'})
        best_cvr = active_only.loc[active_only['Conversion Rate'].idxmax()]
        insights.append({'icon': 'bullseye', 'text': f"Best Conversion Rate: {best_cvr['Channel']} ({best_cvr['Conversion Rate']:.1f}%)",
                          'level': 'good'})
        engagement_candidates = active_only[active_only['Unique Impressions'] > 0]
        if not engagement_candidates.empty:
            best_ctr_ch = engagement_candidates.loc[engagement_candidates['CTR'].idxmax()]
            insights.append({'icon': 'thumbs_up', 'text': f"Best Engagement: {best_ctr_ch['Channel']} ({best_ctr_ch['CTR']:.1f}% CTR)",
                              'level': 'good'})
    inactive_names = chan_cards_df[chan_cards_df['Sent'] == 0]['Channel'].tolist()
    if inactive_names:
        insights.append({'icon': 'slash_circle', 'text': f"Inactive: {', '.join(inactive_names)}", 'level': 'warning'})
    low_delivery = active_only[active_only['Delivery Rate'] < 85]
    for _, r in low_delivery.iterrows():
        insights.append({'icon': 'warning', 'text': f"{r['Channel']}: Low delivery rate ({r['Delivery Rate']:.1f}%)", 'level': 'critical'})
    render_insight_chips(insights)

    # --- Channel Spotlight: local drill-down, no sidebar filtering needed ---
    st.markdown(f"#### {icon('search', size=18)} Channel Spotlight", unsafe_allow_html=True)
    spotlight_channel = st.selectbox(
        "Drill into a channel", ["All Channels"] + channels_list, key="channel_spotlight_select"
    )
    if spotlight_channel != "All Channels":
        spot_row = chan_cards_df[chan_cards_df['Channel'] == spotlight_channel].iloc[0]
        spot_comp_row = None
        if chan_comp_df is not None and spotlight_channel in chan_comp_df['Channel'].values:
            spot_comp_row = chan_comp_df[chan_comp_df['Channel'] == spotlight_channel].iloc[0]

        sp1, sp2, sp3 = st.columns(3)
        with sp1:
            render_kpi_card(rev_display_name_top, format_metric(spot_row[rev_col], "SAR"),
                             delta=(_pct(spot_row[rev_col], spot_comp_row[rev_col]) if spot_comp_row is not None else None),
                             icon=channel_icon(spotlight_channel, size=22))
        with sp2:
            render_kpi_card(conv_display_name_top, format_metric(spot_row[conv_col]),
                             delta=(_pct(spot_row[conv_col], spot_comp_row[conv_col]) if spot_comp_row is not None else None),
                             icon=icon('bullseye', size=22))
        with sp3:
            render_kpi_card("Conversion Rate", f"{spot_row['Conversion Rate']:.1f}%", icon=icon('check_circle', size=22))

        spot_slice = filtered_df[filtered_df['Channel'] == spotlight_channel]
        top_journey_html = "*No journeys this period*"
        top_onetime_html = "*No one-time campaigns this period*"
        if 'Type of Campaign' in spot_slice.columns and 'Campaign Name' in spot_slice.columns:
            by_campaign = spot_slice.groupby(['Campaign Name', 'Type of Campaign'], dropna=False).agg(
                {rev_col: 'sum', conv_col: 'sum'}
            ).reset_index()
            journeys = by_campaign[by_campaign['Type of Campaign'].astype(str).str.contains('journey', case=False, na=False)]
            onetime = by_campaign[by_campaign['Type of Campaign'].astype(str).str.contains('one-time', case=False, na=False)]
            if not journeys.empty:
                top_j = journeys.sort_values(rev_col, ascending=False).iloc[0]
                top_journey_html = f"**{top_j['Campaign Name']}**<br>{format_metric(top_j[rev_col], 'SAR')} · {format_metric(top_j[conv_col])} conversions"
            if not onetime.empty:
                top_o = onetime.sort_values(rev_col, ascending=False).iloc[0]
                top_onetime_html = f"**{top_o['Campaign Name']}**<br>{format_metric(top_o[rev_col], 'SAR')} · {format_metric(top_o[conv_col])} conversions"

        spot_j_col, spot_o_col = st.columns(2)
        with spot_j_col:
            st.markdown(
                f'<div style="border:1px solid {COLORS["muted"]}44;border-radius:8px;padding:14px;">'
                f'<div style="font-size:13px;color:{COLORS["muted"]};">{icon("compass")} Top Journey</div>'
                f'<div style="margin-top:6px;">{top_journey_html}</div></div>',
                unsafe_allow_html=True,
            )
        with spot_o_col:
            st.markdown(
                f'<div style="border:1px solid {COLORS["muted"]}44;border-radius:8px;padding:14px;">'
                f'<div style="font-size:13px;color:{COLORS["muted"]};">{icon("send")} Top One-Time Campaign</div>'
                f'<div style="margin-top:6px;">{top_onetime_html}</div></div>',
                unsafe_allow_html=True,
            )

        spot_weekly = weekly_df[weekly_df['Channel'] == spotlight_channel]
        if not spot_weekly.empty:
            trend_col1, trend_col2 = st.columns(2)
            with trend_col1:
                fig_spot_rev = px.area(spot_weekly, x='Week', y='Revenue',
                                        title=f"{spotlight_channel} — Weekly {rev_display_name_top}",
                                        color_discrete_sequence=[CHANNEL_COLORS.get(spotlight_channel, COLORS['primary'])])
                render_chart(fig_spot_rev, spot_weekly, key="spotlight_revenue_trend", ai_label=f"{spotlight_channel} Weekly Revenue")
            with trend_col2:
                fig_spot_conv = px.bar(spot_weekly, x='Week', y='Conversions',
                                        title=f"{spotlight_channel} — Weekly {conv_display_name_top}",
                                        color_discrete_sequence=[CHANNEL_COLORS.get(spotlight_channel, COLORS['primary'])])
                render_chart(fig_spot_conv, spot_weekly, key="spotlight_conv_trend", ai_label=f"{spotlight_channel} Weekly Conversions")

        spot_failed_cols = [c for c in spot_slice.columns if 'Failed' in c and c != 'Failed']
        if spot_failed_cols:
            spot_failed = spot_slice[spot_failed_cols].sum()
            spot_failed = spot_failed[spot_failed > 0].sort_values()
            if not spot_failed.empty:
                spot_failed_df = spot_failed.reset_index()
                spot_failed_df.columns = ['Reason', 'Count']
                fig_spot_failed = px.bar(spot_failed_df, x='Count', y='Reason', orientation='h',
                                          title=f"{spotlight_channel} — Failed Reasons",
                                          color_discrete_sequence=[COLORS['danger']])
                render_chart(fig_spot_failed, spot_failed_df, key="spotlight_failed_reasons", ai_label=f"{spotlight_channel} Failed Reasons")

    st.markdown("---")
    st.subheader(":material/bar_chart: Detailed Analysis")
    st.caption("Full breakdown, tables, and charts across all channels — scroll for the deep dive.")

    # Create display version for table - keep selected attribution columns visible
    chan_df_display = chan_df.copy()
    # For Total attribution, Selected Revenue (SAR) == Revenue (SAR) and will be renamed to it,
    # so drop the raw Revenue (SAR) first to avoid a duplicate after the rename.
    # For CT/IT attribution, keep Revenue (SAR) so total revenue stays visible in the table.
    if (selected_rev_label == 'Revenue (SAR)'
            and 'Selected Revenue (SAR)' in chan_df_display.columns
            and 'Revenue (SAR)' in chan_df_display.columns):
        chan_df_display = chan_df_display.drop(columns=['Revenue (SAR)'])
    if 'Selected Conversions' in chan_df_display.columns and 'Unique Conversions' in chan_df_display.columns:
        chan_df_display = chan_df_display.drop(columns=['Unique Conversions'])

    # If selected labels match existing raw attribution columns, drop the raw duplicate first.
    # Example: selecting Click-Through makes 'Selected Revenue (SAR)' rename to
    # 'Click-Through Revenue (SAR)', which may already exist in chan_df_display.
    selected_rev_display = attribution_rename.get('Selected Revenue (SAR)')
    if selected_rev_display and selected_rev_display != 'Selected Revenue (SAR)' and selected_rev_display in chan_df_display.columns:
        chan_df_display = chan_df_display.drop(columns=[selected_rev_display])

    selected_conv_display = attribution_rename.get('Selected Conversions')
    if selected_conv_display and selected_conv_display != 'Selected Conversions' and selected_conv_display in chan_df_display.columns:
        chan_df_display = chan_df_display.drop(columns=[selected_conv_display])

    # 'Unique Click-Through Conversions' is aggregated only as the numerator for the
    # Conversion Rate calc above (on chan_df) -- it is NOT a display column. Drop it so
    # it doesn't render as a second, near-duplicate conversions column next to the
    # attribution-selected one (which broke the table's rendering for CT/IT attribution).
    if 'Unique Click-Through Conversions' in chan_df_display.columns:
        chan_df_display = chan_df_display.drop(columns=['Unique Click-Through Conversions'])

    # Rename selected attribution columns in display table only
    chan_df_display = chan_df_display.rename(columns=attribution_rename)

    # Safety guard: ensure concat/reindex operations always see unique columns.
    if not chan_df_display.columns.is_unique:
        chan_df_display = chan_df_display.loc[:, ~chan_df_display.columns.duplicated(keep='first')]

    # Identify numeric column groups for display config
    conversion_col = None
    for col in [selected_conv_label, 'Selected Conversions', 'Unique Conversions', 'Total Conversions']:
        if col in chan_df_display.columns:
            conversion_col = col
            break

    numeric_cols = ['Sent', 'Delivered', 'Unique Impressions', 'Unique Clicks']
    if conversion_col:
        numeric_cols.append(conversion_col)
    if 'Total Conversions' in chan_df_display.columns and 'Total Conversions' not in numeric_cols:
        numeric_cols.append('Total Conversions')
    revenue_cols = [col for col in chan_df_display.columns if 'Revenue' in col]
    aov_cols = [col for col in chan_df_display.columns if 'AOV' in col]

    # Compute the "Total" pinned row from raw (unrounded) current-period values.
    total_row_chan = {'Channel': 'Total'}
    for col in chan_df_display.columns:
        if col == 'Channel' or 'AOV' in col:
            continue
        total_row_chan[col] = chan_df_display[col].sum()

    if 'Selected Revenue (SAR)' in chan_df.columns and 'Selected Conversions' in chan_df.columns:
        total_conv = chan_df['Selected Conversions'].sum()
        total_rev = chan_df['Selected Revenue (SAR)'].sum()
    elif 'Revenue (SAR)' in chan_df.columns and 'Unique Conversions' in chan_df.columns:
        total_conv = chan_df['Unique Conversions'].sum()
        total_rev = chan_df['Revenue (SAR)'].sum()
    else:
        total_conv = 0
        total_rev = 0
    total_aov = (total_rev / total_conv) if total_conv > 0 else 0
    for col in aov_cols:
        total_row_chan[col] = total_aov

    if 'Conversion Rate' in chan_df_display.columns:
        total_clicks = chan_df['Unique Clicks'].sum() if 'Unique Clicks' in chan_df.columns else 0
        total_conv_for_rate = chan_df[conv_rate_numerator_col].sum() if conv_rate_numerator_col in chan_df.columns else 0
        total_row_chan['Conversion Rate'] = (total_conv_for_rate / total_clicks) * 100 if total_clicks > 0 else 0

    chan_cc = {}
    for col in numeric_cols + revenue_cols + aov_cols:
        if col in chan_df_display.columns:
            chan_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
    if 'Conversion Rate' in chan_df_display.columns:
        chan_cc['Conversion Rate'] = st.column_config.NumberColumn(label='Conversion Rate', format='%.2f%%')

    # Build the comparison-period display frame (same columns as chan_df_display) so
    # render_table can compute deltas itself, rather than pre-formatting HTML strings.
    chan_df_comparison_display = None
    if comparison_result:
        chan_df_comparison = _cached_channel_analysis(comparison_result['comparison_data'].to_json())
        comp_rate_numerator_col = (
            'Unique Click-Through Conversions' if 'Unique Click-Through Conversions' in chan_df_comparison.columns
            else conv_rate_source_col
        )
        if comp_rate_numerator_col in chan_df_comparison.columns and 'Unique Clicks' in chan_df_comparison.columns:
            chan_df_comparison['Conversion Rate'] = np.where(
                chan_df_comparison['Unique Clicks'] > 0,
                np.minimum((chan_df_comparison[comp_rate_numerator_col] / chan_df_comparison['Unique Clicks']) * 100, 100.0),
                0
            )
        # Same helper-column drop as the main frame (see note above) so the comparison
        # frame's columns line up with chan_df_display for delta matching.
        if 'Unique Click-Through Conversions' in chan_df_comparison.columns:
            chan_df_comparison = chan_df_comparison.drop(columns=['Unique Click-Through Conversions'])
        chan_df_comparison_display = chan_df_comparison.rename(columns=attribution_rename)
        if not chan_df_comparison_display.columns.is_unique:
            chan_df_comparison_display = chan_df_comparison_display.loc[:, ~chan_df_comparison_display.columns.duplicated(keep='first')]

        comp_total_conv = chan_df_comparison['Selected Conversions'].sum() if 'Selected Conversions' in chan_df_comparison.columns else chan_df_comparison.get('Unique Conversions', pd.Series(dtype=float)).sum()
        comp_total_rev = chan_df_comparison['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in chan_df_comparison.columns else chan_df_comparison.get('Revenue (SAR)', pd.Series(dtype=float)).sum()
        for col in aov_cols:
            total_row_chan[f"{col}__total_comp"] = (comp_total_rev / comp_total_conv) if comp_total_conv > 0 else 0
        for col in numeric_cols + revenue_cols:
            if col in chan_df_comparison_display.columns:
                total_row_chan[f"{col}__total_comp"] = chan_df_comparison_display[col].sum()
        if 'Conversion Rate' in chan_df_comparison_display.columns:
            comp_clicks = chan_df_comparison['Unique Clicks'].sum() if 'Unique Clicks' in chan_df_comparison.columns else 0
            comp_conv_for_rate = chan_df_comparison[comp_rate_numerator_col].sum() if comp_rate_numerator_col in chan_df_comparison.columns else 0
            total_row_chan['Conversion Rate__total_comp'] = (comp_conv_for_rate / comp_clicks) * 100 if comp_clicks > 0 else 0

    render_table(
        chan_df_display,
        key="channel_analysis",
        column_config=chan_cc,
        comparison_df=chan_df_comparison_display,
        compare_on="Channel",
        total_row=total_row_chan,
    )
    st.caption(
        "Conversion Rate = Click-Through Conversions ÷ Unique Clicks (of those who clicked, "
        "the share who converted). It is always click-based, so it doesn't change with the "
        "revenue/conversion attribution selected in the sidebar."
    )

    # Revenue Distribution (Donut Chart)
    rev_display_name = get_selected_revenue_display_name(revenue_attribution)
    st.subheader(f"Revenue Distribution Across Channels - {rev_display_name}")
    if 'Selected Revenue (SAR)' in chan_df.columns:
        # Calculate total revenue for center annotation
        total_revenue = chan_df['Selected Revenue (SAR)'].sum()

        # Create donut chart for revenue share
        fig_donut = px.pie(
            chan_df,
            values='Selected Revenue (SAR)',
            names='Channel',
            title=f"Channel Revenue Share<br><sub>Using: {rev_display_name}</sub>",
            color='Channel',
            color_discrete_map=CHANNEL_COLORS,
            hole=0.4  # Makes it a donut chart
        )
        fig_donut.update_traces(
            textposition='inside',
            textinfo='percent+label',
            hovertemplate='<b>%{label}</b><br>' +
                          'Revenue: %{value:,.0f} SAR<br>' +
                          'Share: %{percent}<br>' +
                          '<extra></extra>'
        )
        fig_donut.update_layout(
            showlegend=True,
            legend=dict(orientation='h', yanchor='bottom', y=-0.2, xanchor='center', x=0.5),
            annotations=[dict(
                text=f'<b>Total</b><br>{format_metric(total_revenue, "SAR", abbreviate=True)}',
                x=0.5, y=0.5,
                font_size=16,
                showarrow=False
            )]
        )
        render_chart(fig_donut, chan_df, key="channel_revenue_donut", ai_label="Channel Revenue Share")

    # Revenue + Conversions by Channel (using selected attribution)
    st.subheader("Revenue & Conversions Comparison")
    render_ai_explain_bar(chan_df, key="channel_rev_conv_charts", ai_label="Revenue & Conversions Comparison",
                           help_text="Explain these charts with AI")
    rev_conv_col1, rev_conv_col2 = st.columns(2)
    with rev_conv_col1:
        if 'Selected Revenue (SAR)' in chan_df.columns:
            rev_display_name = get_selected_revenue_display_name(revenue_attribution)
            fig_rev_chan = px.bar(
                chan_df, x='Channel', y='Selected Revenue (SAR)',
                title=f"{rev_display_name} by Channel",
                color='Channel', color_discrete_map=CHANNEL_COLORS,
                labels={'Selected Revenue (SAR)': rev_display_name}
            )
            fig_rev_chan.update_layout(showlegend=False)
            st.plotly_chart(fig_rev_chan)
    with rev_conv_col2:
        conv_col = 'Selected Conversions' if 'Selected Conversions' in chan_df.columns else 'Unique Conversions'
        conv_display_name = get_selected_conversion_display_name(conversion_attribution) if conv_col == 'Selected Conversions' else 'Unique Conversions'
        fig_conv_chan = px.bar(
            chan_df, x='Channel', y=conv_col,
            title=f"{conv_display_name} by Channel",
            color='Channel', color_discrete_map=CHANNEL_COLORS,
            labels={conv_col: conv_display_name}
        )
        fig_conv_chan.update_layout(showlegend=False)
        st.plotly_chart(fig_conv_chan)

    # Compute derived rates for deeper channel analysis
    chan_rates = chan_df.copy()
    chan_rates['Delivery Rate'] = np.where(
        chan_rates['Sent'] > 0,
        (chan_rates['Delivered'] / chan_rates['Sent']) * 100, 0
    )
    chan_rates['CTR'] = np.where(
        chan_rates['Unique Impressions'] > 0,
        (chan_rates['Unique Clicks'] / chan_rates['Unique Impressions']) * 100, 0
    )
    chan_rates['Conversion Rate'] = np.where(
        chan_rates['Unique Clicks'] > 0,
        (chan_rates[conv_rate_source_col] / chan_rates['Unique Clicks']) * 100,
        0
    )

    # Charts: Delivery Rate + CTR + Conversion Rate
    st.subheader("Engagement & Delivery Rates")
    render_ai_explain_bar(chan_rates, key="channel_rates_charts", ai_label="Engagement & Delivery Rates",
                           help_text="Explain these charts with AI")
    ch_col1, ch_col2, ch_col3 = st.columns(3)
    with ch_col1:
        fig_dr = px.bar(
            chan_rates, x='Channel', y='Delivery Rate',
            title="Delivery Rate by Channel (%)",
            color='Channel', color_discrete_map=CHANNEL_COLORS,
        )
        fig_dr.update_layout(showlegend=False, yaxis_title="Delivery Rate (%)")
        fig_dr.add_hline(y=95, line_dash="dash", line_color=COLORS['muted'],
                         annotation_text="95% target", annotation_position="top right")
        st.plotly_chart(fig_dr)
    with ch_col2:
        fig_ctr = px.bar(
            chan_rates, x='Channel', y='CTR',
            title="Click-Through Rate by Channel (%)",
            color='Channel', color_discrete_map=CHANNEL_COLORS,
        )
        fig_ctr.update_layout(showlegend=False, yaxis_title="CTR (%)")
        st.plotly_chart(fig_ctr)
    with ch_col3:
        fig_cvr = px.bar(
            chan_rates, x='Channel', y='Conversion Rate',
            title="Conversion Rate by Channel (%)",
            color='Channel', color_discrete_map=CHANNEL_COLORS,
        )
        fig_cvr.update_layout(showlegend=False, yaxis_title="Conversion Rate (%)")
        st.plotly_chart(fig_cvr)

    # Volume comparison (Sent vs Delivered side-by-side)
    st.subheader("Send Volume & Delivery")
    volume_melt = chan_df[['Channel', 'Sent', 'Delivered']].melt(
        id_vars='Channel', var_name='Metric', value_name='Count'
    )
    fig_vol = px.bar(
        volume_melt, x='Channel', y='Count', color='Metric',
        barmode='group', title="Sent vs Delivered by Channel",
        color_discrete_map={'Sent': COLORS['primary'], 'Delivered': COLORS['success']},
    )
    render_chart(fig_vol, volume_melt, key="channel_volume", ai_label="Sent vs Delivered by Channel")

    # Revenue Attribution Comparison (all three side-by-side)
    rev_compare_cols = [c for c in ['Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Impression-Through Revenue (SAR)'] if c in chan_df.columns]
    if len(rev_compare_cols) > 1:
        st.subheader("Revenue Attribution Comparison")
        rev_melt = chan_df[['Channel'] + rev_compare_cols].melt(
            id_vars='Channel', var_name='Attribution Model', value_name='Revenue'
        )
        # Shorten labels for readability
        rev_melt['Attribution Model'] = rev_melt['Attribution Model'].str.replace(' (SAR)', '', regex=False).str.replace('Revenue', '').str.strip()
        fig_rev_compare = px.bar(
            rev_melt, x='Channel', y='Revenue', color='Attribution Model',
            barmode='group', title="Revenue by Channel & Attribution Model",
            color_discrete_sequence=COLOR_SEQUENCE,
        )
        render_chart(fig_rev_compare, rev_melt, key="channel_rev_compare", ai_label="Revenue by Channel & Attribution Model")

    # Campaign Type Performance by Channel (One-Time vs Journey)
    if 'Type of Campaign' in filtered_df.columns and 'Channel' in filtered_df.columns:
        type_vals = filtered_df['Type of Campaign'].dropna().unique()
        if len(type_vals) > 0:
            st.subheader("One-Time vs Journey Performance by Channel")
            type_chan_df, rev_col_type, conv_col_type, extra_rev_cols, extra_conv_cols = _cached_channel_type_breakdown(filtered_df.to_json())

            # Toggle for showing all revenue/conversion types
            show_all_attrs = st.checkbox("Show all revenue & conversion types", value=False, key='chan_type_show_all')

            # Build display columns
            default_cols = ['Channel', 'Type of Campaign', 'Sent', 'Delivered', conv_col_type, rev_col_type]
            default_cols = [c for c in default_cols if c in type_chan_df.columns]
            if show_all_attrs:
                display_cols = default_cols + [c for c in extra_rev_cols + extra_conv_cols if c not in default_cols]
            else:
                display_cols = default_cols

            type_chan_display = type_chan_df[display_cols].copy()
            # Rename Selected columns to show actual attribution model
            type_chan_display = type_chan_display.rename(columns=attribution_rename)
            # Build column_config for proper numeric display
            type_chan_cc = {}
            num_type_cols = ['Sent', 'Delivered'] + extra_conv_cols + ([conv_col_type] if conv_col_type in type_chan_display.columns else [])
            for col in num_type_cols:
                renamed_col = attribution_rename.get(col, col)
                if renamed_col in type_chan_display.columns:
                    type_chan_cc[renamed_col] = st.column_config.NumberColumn(label=renamed_col, format='compact')
            rev_type_cols = [rev_col_type] + extra_rev_cols
            for col in rev_type_cols:
                renamed_col = attribution_rename.get(col, col)
                if renamed_col in type_chan_display.columns:
                    type_chan_cc[renamed_col] = st.column_config.NumberColumn(label=renamed_col, format='compact')
            render_table(type_chan_display, key="chan_type", column_config=type_chan_cc)

            # Stacked bar: Revenue by Channel, stacked by Campaign Type
            render_ai_explain_bar(type_chan_df, key="channel_type_charts", ai_label="Revenue & Conversions by Channel & Campaign Type",
                                   help_text="Explain these charts with AI")
            type_chan_col1, type_chan_col2 = st.columns(2)
            with type_chan_col1:
                if rev_col_type in type_chan_df.columns:
                    rev_display_name = get_selected_revenue_display_name(revenue_attribution)
                    fig_type_chan_rev = px.bar(
                        type_chan_df, x='Channel', y=rev_col_type, color='Type of Campaign',
                        barmode='stack', title=f"{rev_display_name} by Channel & Campaign Type",
                        color_discrete_sequence=COLOR_SEQUENCE,
                        labels={rev_col_type: rev_display_name}
                    )
                    fig_type_chan_rev.update_layout(legend=dict(orientation='h', y=-0.2))
                    st.plotly_chart(fig_type_chan_rev)
            with type_chan_col2:
                conv_display_name = get_selected_conversion_display_name(conversion_attribution)
                fig_type_chan_conv = px.bar(
                    type_chan_df, x='Channel', y=conv_col_type, color='Type of Campaign',
                    barmode='stack', title=f"{conv_display_name} by Channel & Campaign Type",
                    color_discrete_sequence=COLOR_SEQUENCE,
                    labels={conv_col_type: conv_display_name}
                )
                fig_type_chan_conv.update_layout(legend=dict(orientation='h', y=-0.2))
                st.plotly_chart(fig_type_chan_conv)

            # Share breakdown: what % of each channel's revenue comes from journeys vs one-time
            if rev_col_type in type_chan_df.columns:
                channel_totals = type_chan_df.groupby('Channel')[rev_col_type].sum().reset_index()
                channel_totals.columns = ['Channel', 'Total']
                type_share = type_chan_df.merge(channel_totals, on='Channel')
                type_share['Revenue Share'] = np.where(
                    type_share['Total'] > 0,
                    type_share[rev_col_type] / type_share['Total'] * 100, 0
                )
                fig_share = px.bar(
                    type_share, x='Channel', y='Revenue Share', color='Type of Campaign',
                    barmode='stack', title="Revenue Share by Campaign Type per Channel (%)",
                    color_discrete_sequence=COLOR_SEQUENCE,
                    custom_data=['Type of Campaign']
                )
                fig_share.update_traces(
                    hovertemplate='<b>%{x}</b><br>' +
                                  'Campaign Type: %{customdata[0]}<br>' +
                                  'Revenue Share: %{y:.1f}%<br>' +
                                  '<extra></extra>'
                )
                fig_share.update_layout(
                    yaxis_title="Revenue Share (%)", yaxis_range=[0, 100],
                    legend=dict(orientation='h', y=-0.2)
                )
                render_chart(fig_share, type_share, key="channel_type_share", ai_label="Revenue Share by Campaign Type per Channel")

    # ESP Analysis
    esp_df = esp_analysis(filtered_df)
    if not esp_df.empty:
        st.subheader("ESP/SSP Analysis")
        esp_df_display = esp_df.copy()
        # Build column_config for proper numeric display
        esp_cc = {}
        for col in ['Sent', 'Delivered', 'Unique Conversions']:
            if col in esp_df_display.columns:
                esp_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
        for col in [c for c in esp_df_display.columns if 'Revenue' in c]:
            if col in esp_df_display.columns:
                esp_cc[col] = st.column_config.NumberColumn(label=col, format='compact')
        render_table(esp_df_display, key="esp", column_config=esp_cc)

        render_ai_explain_bar(esp_df, key="esp_charts", ai_label="ESP/SSP Analysis", help_text="Explain these charts with AI")
        esp_col1, esp_col2 = st.columns(2)
        with esp_col1:
            fig_esp = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Delivered',
                             title="Delivered by ESP", color_discrete_sequence=COLOR_SEQUENCE)
            st.plotly_chart(fig_esp)
        with esp_col2:
            if 'Revenue (SAR)' in esp_df.columns:
                fig_esp_rev = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Revenue (SAR)',
                                     title="Send-Through Revenue by ESP", color_discrete_sequence=COLOR_SEQUENCE,
                                     labels={'Revenue (SAR)': 'Send-Through Revenue (SAR)'})
                st.plotly_chart(fig_esp_rev)

with tab2:
    failed_df = failed_reasons_analysis(filtered_df)
    if not failed_df.empty:
        # Create display version for table
        col_config = {"Count": st.column_config.NumberColumn(label="Count", format="%.0f")}
        render_table(failed_df, key="failed_reasons", column_config=col_config)

        # Horizontal ranked bars (largest on top): long reason labels stay readable.
        fig_fail = px.bar(failed_df.sort_values('Count'), x='Count', y='Reason', orientation='h',
                          title="Failed Reasons Breakdown",
                          color_discrete_sequence=[COLORS['danger']])
        render_chart(fig_fail, failed_df, key="channels_failed_reasons", ai_label="Failed Reasons Breakdown")

        # Drill-down: Failed reasons by channel
        st.subheader("Failed Reasons by Channel")
        failed_cols = [col for col in filtered_df.columns if 'Failed' in col and col != 'Failed']
        if failed_cols:
            failed_by_channel = _cached_failed_by_channel(filtered_df.to_json())
            # Build column config for failed count columns (all are integer counts)
            channel_cc = {col: st.column_config.NumberColumn(label=col, format="%.0f") for col in failed_cols}
            render_table(failed_by_channel, key="failed_by_channel", column_config=channel_cc)

            # Melt for plotting (use original numeric values)
            failed_melt = failed_by_channel.melt(id_vars='Channel', var_name='Reason', value_name='Count')
            fig_fail_chan = px.bar(failed_melt, x='Channel', y='Count', color='Reason',
                                  title="Failed Reasons by Channel",
                                  color_discrete_sequence=COLOR_SEQUENCE)
            render_chart(fig_fail_chan, failed_melt, key="channels_failed_by_channel", ai_label="Failed Reasons by Channel")
    else:
        st.write("No failed reasons data available.")
