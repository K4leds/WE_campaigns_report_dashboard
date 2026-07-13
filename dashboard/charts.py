"""Shared presentation helpers for dashboard pages."""
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

from utils import format_metric, style_total_row, export_chart_image  # noqa: F401
from attribution import get_attribution_display_label
from components.table import render_table, render_chart
from config import COLORS


def attribution_display(ctx, col_name):
    """Map 'Selected Revenue/Conversions' column names to the user-selected label."""
    return get_attribution_display_label(
        col_name, ctx.revenue_attribution, ctx.conversion_attribution
    )


def render_health_dashboard(health_df: pd.DataFrame, entity_col: str, entity_label: str, key_prefix: str) -> str | None:
    """Render the Top Performers / Needs Attention / Distribution / Full Report / Radar
    breakdown for a health-scored DataFrame.

    Shared by the Campaigns and Journeys pages, which apply the same health-score
    lens (delivery/engagement/conversion/revenue, Empirical Bayes smoothed) to
    different entities.

    Args:
        health_df: one row per entity, with columns [entity_col, 'Health Score', 'Tier',
            'Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)',
            'Total Conversions', 'Delivery Score', 'Engagement Score', 'Conversion Score',
            'Revenue Score'], and optionally 'Status'.
        entity_col: column name identifying the entity ('Campaign Name' or 'Journey Name').
        entity_label: human label for text ('Campaign' or 'Journey').
        key_prefix: unique prefix for widget keys ('campaign' or 'journey').

    Returns:
        The entity name selected in the radar-chart dropdown, so the caller can
        render a Recommendations section using its own health-score function
        (calculate_campaign_health_score / calculate_journey_health_score take
        different positional data, so that step stays in the page).
    """
    health_df = health_df.sort_values('Health Score', ascending=False)
    scored = health_df[health_df['Tier'] != 'Insufficient Data']
    insufficient_n = len(health_df) - len(scored)

    _COMPONENT_COLS = {'Delivery Score': 'Delivery', 'Engagement Score': 'Engagement',
                       'Conversion Score': 'Conversion', 'Revenue Score': 'Revenue impact'}
    _TIER_ICON = {'Excellent': '🟢', 'Good': '🟡', 'Fair': '🟠', 'Poor': '🔴'}

    def _weakest_component(row):
        present = {label: row[col] for col, label in _COMPONENT_COLS.items() if col in row.index}
        if not present:
            return None
        label = min(present, key=present.get)
        return label, present[label]

    # --- Portfolio summary strip: the "general idea" at a glance ---
    strip = st.columns(6)
    strip[0].metric(f"Median Health", f"{scored['Health Score'].median():.0f}/100" if not scored.empty else "—",
                    help="Median of scored entities. Scores are percentiles relative to this view, not industry benchmarks.")
    strip[1].metric("🟢 Excellent", int((scored['Tier'] == 'Excellent').sum()))
    strip[2].metric("🟡 Good", int((scored['Tier'] == 'Good').sum()))
    strip[3].metric("🟠 Fair", int((scored['Tier'] == 'Fair').sum()))
    strip[4].metric("🔴 Poor", int((scored['Tier'] == 'Poor').sum()))
    strip[5].metric("⚪ Not scored", insufficient_n,
                    help="Too little data to rank reliably — visible in the full report table below.")
    st.caption(f"Scores are percentile ranks **within the current view**: 80 = healthier than 80% "
               f"of the {entity_label.lower()}s shown, weighted Revenue impact 35% · Conversion 25% · "
               f"Engagement 20% · Delivery 20%.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader(f"🔥 Top Performing {entity_label}s")
        for _, row in scored.head(5).iterrows():
            icon = _TIER_ICON.get(row['Tier'], '⚪')
            revenue_txt = f" · {format_metric(row['Revenue (SAR)'], 'SAR')} revenue" if 'Revenue (SAR)' in row.index else ""
            st.markdown(f"**{row[entity_col]}**  \n"
                        f"{icon} **{row['Health Score']:.0f}/100** · {row['Tier']}{revenue_txt}")
            st.markdown("---")

    with col2:
        st.subheader(f"🚨 {entity_label}s Needing Attention")
        st.caption(f"Worst first. Only currently *Running* {entity_label.lower()}s are shown — there's nothing to act on for an Ended or Paused {entity_label.lower()}.")
        needs_attention_pool = scored[scored['Status'] == 'Running'] if 'Status' in scored.columns else scored
        # ascending: the sickest entities lead the list, not the borderline ones
        bottom = needs_attention_pool[needs_attention_pool['Health Score'] < 60].sort_values('Health Score').head(5)
        if not bottom.empty:
            for _, row in bottom.iterrows():
                icon = _TIER_ICON.get(row['Tier'], '⚪')
                weak = _weakest_component(row)
                weak_txt = f" · fix first: **{weak[0]}** ({weak[1]:.0f}/100)" if weak else ""
                st.markdown(f"**{row[entity_col]}**  \n"
                            f"{icon} **{row['Health Score']:.0f}/100** · {row['Tier']}{weak_txt}")
                st.markdown("---")
        else:
            st.success(f"🎉 All {entity_label.lower()}s are performing well!")

    # Health Score Distribution (scored entities only — the zero-pile of
    # unscored entities used to drag the average line into fiction)
    st.subheader("📊 Health Score Distribution")
    if not scored.empty:
        fig_health_dist = px.histogram(scored, x='Health Score', nbins=20,
                                        title=f"Distribution of {entity_label} Health Scores",
                                        color_discrete_sequence=[COLORS['primary']])
        fig_health_dist.add_vline(x=scored['Health Score'].mean(),
                                   line_dash="dash", line_color=COLORS['danger'],
                                   annotation_text=f"Average: {scored['Health Score'].mean():.1f}")
        render_chart(fig_health_dist, scored[[entity_col, 'Health Score', 'Tier']],
                     key=f"{key_prefix}_health_dist", ai_label=f"{entity_label} Health Score Distribution")
        if insufficient_n:
            st.caption(f"{insufficient_n} {entity_label.lower()}s with insufficient data are excluded from this chart.")
    else:
        st.info(f"No {entity_label.lower()}s have enough data to score yet.")

    # Complete Health Dashboard Table
    st.subheader(f"📋 Complete {entity_label} Health Report")

    search_col, filter_col = st.columns([2, 1])
    with search_col:
        search_term = st.text_input(f"🔍 Search {entity_label} Names", placeholder=f"Type to filter {entity_label.lower()}s...", key=f'{key_prefix}_search')
    with filter_col:
        tier_filter = st.selectbox("Filter by Tier", ['All'] + list(health_df['Tier'].unique()), key=f'{key_prefix}_tier_filter')

    display_health_df = health_df.copy()
    if search_term:
        display_health_df = display_health_df[
            display_health_df[entity_col].str.contains(search_term, case=False, na=False)
        ]
    if tier_filter != 'All':
        display_health_df = display_health_df[display_health_df['Tier'] == tier_filter]

    numeric_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Total Conversions',
                     'Health Score', 'Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']
    for col in numeric_cols:
        if col in display_health_df.columns:
            display_health_df[col] = pd.to_numeric(display_health_df[col], errors='coerce')

    tier_emoji_map = {'Excellent': '🟢 Excellent', 'Good': '🟡 Good', 'Fair': '🟠 Fair', 'Poor': '🔴 Poor'}
    display_health_df['Tier Display'] = display_health_df['Tier'].apply(lambda x: tier_emoji_map.get(x, f'⚪ {x}'))

    st.info(f"📊 Showing {len(display_health_df)} {entity_label.lower()}s (filtered from {len(health_df)} total)")

    columns_order = [entity_col, 'Health Score', 'Tier Display', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)',
                      'Click-Through Revenue (SAR)', 'Total Conversions', 'Sent', 'Days', 'Delivery Score',
                      'Engagement Score', 'Conversion Score', 'Revenue Score']
    columns_order = [c for c in columns_order if c in display_health_df.columns]

    report_cc = {'Health Score': st.column_config.NumberColumn(label='Health Score', format='%.1f')}
    if 'Sent' in columns_order:
        report_cc['Sent'] = st.column_config.NumberColumn(label='Sent', format='compact')
    if 'Days' in columns_order:
        report_cc['Days'] = st.column_config.NumberColumn(label='Days', format='%.0f')
    for rev_col in ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']:
        if rev_col in columns_order:
            report_cc[rev_col] = st.column_config.NumberColumn(label=rev_col, format='compact')
    if 'Total Conversions' in columns_order:
        report_cc['Total Conversions'] = st.column_config.NumberColumn(label='Total Conversions', format='compact')
    for score_col in ['Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']:
        if score_col in columns_order:
            report_cc[score_col] = st.column_config.NumberColumn(label=score_col, format='%.1f')

    render_table(display_health_df[columns_order], key=f"{key_prefix}_health_report", column_config=report_cc)

    # Component Scores Radar Chart for Selected Entity
    st.subheader(f"🎯 {entity_label} Performance Breakdown")
    selected_name = st.selectbox(f"Select {entity_label} for Detailed Analysis",
                                  health_df[entity_col].tolist(),
                                  key=f'{key_prefix}_health_select')

    if selected_name:
        selected_row = health_df[health_df[entity_col] == selected_name].iloc[0]
        categories = ['Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']
        values = [selected_row[cat] for cat in categories]

        st.write("**📊 Component Score Values:**")
        score_cols = st.columns(4)
        for i, (cat, val) in enumerate(zip(categories, values)):
            with score_cols[i]:
                st.metric(cat.replace(' Score', ''), f"{val:.1f}/100")

        fig_radar = go.Figure()
        fig_radar.add_trace(go.Scatterpolar(
            r=values, theta=categories, fill='toself', name=selected_name,
            line=dict(color=COLORS['primary'], width=3),
            fillcolor='rgba(14, 165, 233, 0.3)',
            marker=dict(size=8, color=COLORS['primary']),
        ))
        fig_radar.add_trace(go.Scatterpolar(
            r=[80] * len(categories), theta=categories, mode='lines', name='Excellent (80+)',
            line=dict(color=COLORS['success'], width=2, dash='dash'), showlegend=True,
        ))
        fig_radar.add_trace(go.Scatterpolar(
            r=[60] * len(categories), theta=categories, mode='lines', name='Good (60+)',
            line=dict(color=COLORS['warning'], width=2, dash='dot'), showlegend=True,
        ))
        # Translucent slate grid reads as a hairline on both light and dark surfaces.
        _polar_grid = 'rgba(148, 163, 184, 0.35)'
        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], tickmode='linear', tick0=0, dtick=20,
                                 gridcolor=_polar_grid, gridwidth=1),
                angularaxis=dict(gridcolor=_polar_grid, gridwidth=1),
            ),
            showlegend=True,
            title=dict(text=f"Performance Breakdown: {selected_name}", x=0.5, font=dict(size=16)),
            width=600, height=500,
            margin=dict(l=80, r=80, t=80, b=80),
        )
        st.plotly_chart(fig_radar)

    return selected_name
