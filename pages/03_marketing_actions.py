import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric, style_total_row
from config import COLORS, CHANNEL_COLORS

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

st.header("📈 Marketing Actions Dashboard")
st.markdown("*Actionable insights for the marketing & business team — what to scale, pause, and optimize.*")
st.markdown("---")

# =====================================================================
# SECTION 1: Channel Efficiency (Revenue Per Send, CVR by Channel)
# =====================================================================
st.subheader("1. Channel Efficiency Comparison")
st.caption("Which channels deliver the most revenue per message sent? (No cost data needed)")

if 'Channel' in filtered_df.columns and not filtered_df.empty:
    chan_eff = filtered_df.groupby('Channel').agg(
        Total_Sent=('Sent', 'sum'),
        Total_Delivered=('Delivered', 'sum'),
        Total_Clicks=('Unique Clicks', 'sum'),
        Total_Impressions=('Unique Impressions', 'sum'),
        Total_Conversions=('Selected Conversions', 'sum') if 'Selected Conversions' in filtered_df.columns else ('Unique Conversions', 'sum'),
        Total_Revenue=('Selected Revenue (SAR)', 'sum') if 'Selected Revenue (SAR)' in filtered_df.columns else ('Revenue (SAR)', 'sum'),
    ).reset_index()

    # Compute efficiency metrics
    chan_eff['Revenue Per Send'] = np.where(chan_eff['Total_Sent'] > 0, chan_eff['Total_Revenue'] / chan_eff['Total_Sent'], 0)
    chan_eff['Revenue Per Click'] = np.where(chan_eff['Total_Clicks'] > 0, chan_eff['Total_Revenue'] / chan_eff['Total_Clicks'], 0)
    chan_eff['CVR (%)'] = np.where(chan_eff['Total_Clicks'] > 0, (chan_eff['Total_Conversions'] / chan_eff['Total_Clicks']) * 100, 0)
    chan_eff['CTR (%)'] = np.where(chan_eff['Total_Impressions'] > 0, (chan_eff['Total_Clicks'] / chan_eff['Total_Impressions']) * 100, 0)
    chan_eff['AOV (SAR)'] = np.where(chan_eff['Total_Conversions'] > 0, chan_eff['Total_Revenue'] / chan_eff['Total_Conversions'], 0)

    # Sort by Revenue Per Send
    chan_eff = chan_eff.sort_values('Revenue Per Send', ascending=False)

    # Display KPI cards per channel
    eff_cols = st.columns(min(len(chan_eff), 4))
    for i, (_, row) in enumerate(chan_eff.head(4).iterrows()):
        with eff_cols[i]:
            st.metric(row['Channel'], f"{row['Revenue Per Send']:.2f} SAR/send", delta=f"CVR: {row['CVR (%)']:.1f}%")

    # Bar chart: Revenue Per Send by Channel
    fig_rps = px.bar(
        chan_eff, x='Channel', y='Revenue Per Send',
        color='Channel', color_discrete_map=CHANNEL_COLORS,
        title="Revenue Per Send by Channel (SAR)",
        text=chan_eff['Revenue Per Send'].apply(lambda v: f"{v:.2f}")
    )
    fig_rps.update_traces(textposition='outside')
    fig_rps.update_layout(showlegend=False)
    st.plotly_chart(fig_rps, use_container_width=True)

    # Detailed table
    chan_eff_display = chan_eff[['Channel', 'Total_Sent', 'Total_Conversions', 'Total_Revenue', 'Revenue Per Send', 'Revenue Per Click', 'CTR (%)', 'CVR (%)', 'AOV (SAR)']].copy()
    chan_eff_display.columns = ['Channel', 'Sends', 'Conversions', f'{selected_rev_label}', 'Rev/Send', 'Rev/Click', 'CTR %', 'CVR %', 'AOV (SAR)']
    # Add total row
    total_row = pd.DataFrame([{
        'Channel': 'TOTAL',
        'Sends': chan_eff_display['Sends'].sum(),
        'Conversions': chan_eff_display['Conversions'].sum(),
        selected_rev_label: chan_eff_display[selected_rev_label].sum(),
        'Rev/Send': chan_eff_display[selected_rev_label].sum() / chan_eff_display['Sends'].sum() if chan_eff_display['Sends'].sum() > 0 else 0,
        'Rev/Click': 0,
        'CTR %': 0,
        'CVR %': 0,
        'AOV (SAR)': chan_eff_display[selected_rev_label].sum() / chan_eff_display['Conversions'].sum() if chan_eff_display['Conversions'].sum() > 0 else 0,
    }])
    chan_eff_display = pd.concat([chan_eff_display, total_row], ignore_index=True)
    st.dataframe(style_total_row(chan_eff_display), use_container_width=True, hide_index=True)
else:
    st.info("No channel data available with current filters.")

st.markdown("---")

# =====================================================================
# SECTION 2: Journey vs One-Time Comparison
# =====================================================================
st.subheader("2. Journey vs One-Time Campaign Effectiveness")
st.caption("Are automated journeys outperforming one-time blasts?")

if 'Type of Campaign' in filtered_df.columns and not filtered_df.empty:
    type_comparison = filtered_df.groupby('Type of Campaign').agg(
        Campaigns=('Campaign Name', 'nunique'),
        Total_Sent=('Sent', 'sum'),
        Total_Delivered=('Delivered', 'sum'),
        Total_Clicks=('Unique Clicks', 'sum'),
        Total_Conversions=('Selected Conversions', 'sum') if 'Selected Conversions' in filtered_df.columns else ('Unique Conversions', 'sum'),
        Total_Revenue=('Selected Revenue (SAR)', 'sum') if 'Selected Revenue (SAR)' in filtered_df.columns else ('Revenue (SAR)', 'sum'),
    ).reset_index()

    type_comparison['Rev/Send'] = np.where(type_comparison['Total_Sent'] > 0, type_comparison['Total_Revenue'] / type_comparison['Total_Sent'], 0)
    type_comparison['CVR (%)'] = np.where(type_comparison['Total_Clicks'] > 0, (type_comparison['Total_Conversions'] / type_comparison['Total_Clicks']) * 100, 0)
    type_comparison['CTR (%)'] = np.where(type_comparison['Total_Sent'] > 0, (type_comparison['Total_Clicks'] / type_comparison['Total_Sent']) * 100, 0)

    # Side-by-side metrics
    type_cols = st.columns(len(type_comparison))
    for i, (_, row) in enumerate(type_comparison.iterrows()):
        with type_cols[i]:
            st.markdown(f"**{row['Type of Campaign']}**")
            st.metric("Revenue", f"{row['Total_Revenue']:,.0f} SAR")
            st.metric("Conversions", f"{int(row['Total_Conversions']):,}")
            st.metric("Rev/Send", f"{row['Rev/Send']:.3f} SAR")
            st.metric("CVR", f"{row['CVR (%)']:.1f}%")
            st.metric("Campaigns", f"{int(row['Campaigns'])}")

    # Comparative bar charts
    fig_type = px.bar(
        type_comparison, x='Type of Campaign', y=['Total_Revenue', 'Total_Conversions'],
        barmode='group', title="Revenue & Conversions: Journey vs One-Time",
        color_discrete_sequence=[COLORS['primary'], COLORS['success']]
    )
    st.plotly_chart(fig_type, use_container_width=True)

    # Insight callout
    if len(type_comparison) >= 2:
        journey_row = type_comparison[type_comparison['Type of Campaign'] == 'Journey']
        onetime_row = type_comparison[type_comparison['Type of Campaign'] == 'One-time']
        if not journey_row.empty and not onetime_row.empty:
                # Robust ratio calculation: parse totals (handles any formatted strings)
                from utils import parse_short_number
                # Extract totals and sends for each type
                j_total = parse_short_number(journey_row['Total_Revenue'].values[0])
                j_sends = parse_short_number(journey_row['Total_Sent'].values[0])
                o_total = parse_short_number(onetime_row['Total_Revenue'].values[0])
                o_sends = parse_short_number(onetime_row['Total_Sent'].values[0])

                # Compute revenue-per-send with safe guards
                j_rps = (j_total / j_sends) if j_sends > 0 else 0
                o_rps = (o_total / o_sends) if o_sends > 0 else 0

                # If both RPS present, compute ratio. Otherwise fall back to total revenue ratio
                ratio = None
                if o_rps > 0:
                    ratio = j_rps / o_rps
                elif o_total > 0 and o_sends == 0 and j_sends > 0:
                    # fallback: compare totals per send using only the other side's sends to avoid div0
                    ratio = (j_total / max(j_sends, 1)) / max(o_total / max(o_sends, 1), 1e-9)

                # Safety: if ratio is None or not finite, avoid showing misleading large numbers
                try:
                    if ratio is None or not (ratio > 0 and ratio < 1e6):
                        # fallback to simple total revenue ratio (bounded)
                        ratio = (j_total / max(o_total, 1)) if o_total > 0 else 0
                except Exception:
                    ratio = 0

                # Show a more informative insight with totals and Rev/Send to explain large ratios
                from utils import format_metric
                j_total_fmt = format_metric(j_total, 'SAR')
                o_total_fmt = format_metric(o_total, 'SAR')
                j_sends_fmt = f"{int(j_sends):,}"
                o_sends_fmt = f"{int(o_sends):,}"
                j_rps_fmt = f"{j_rps:.3f} SAR/send"
                o_rps_fmt = f"{o_rps:.3f} SAR/send"

                # Headline: compare total revenue (this addresses your requested phrasing)
                total_ratio = (j_total / o_total) if o_total > 0 else None
                if total_ratio and total_ratio > 0:
                    st.success(f"Insight: Automated journeys produced about {total_ratio:.1f}× the total revenue of one-time campaigns.")
                    # Provide the detailed breakdown for context
                    st.caption(
                        f"(Journeys: {j_total_fmt} over {j_sends_fmt} sends → {j_rps_fmt}; "
                        f"One-time: {o_total_fmt} over {o_sends_fmt} sends → {o_rps_fmt})"
                    )
                else:
                    # Fallback to Rev/Send comparison when totals aren't available
                    if ratio > 1:
                        st.success(
                            f"**Insight:** Journeys generate **{ratio:.1f}x** more revenue per send than one-time campaigns. "
                            f"(Journeys: {j_total_fmt} over {j_sends_fmt} sends → {j_rps_fmt}; "
                            f"One-time: {o_total_fmt} over {o_sends_fmt} sends → {o_rps_fmt}). "
                        )
                    elif 0 < ratio <= 1:
                        st.warning(
                            f"**Insight:** One-time campaigns generate **{1/ratio:.1f}x** more revenue per send. "
                            f"(Journeys: {j_total_fmt} over {j_sends_fmt} sends → {j_rps_fmt}; "
                            f"One-time: {o_total_fmt} over {o_sends_fmt} sends → {o_rps_fmt}). "
                        )
                    else:
                        st.info(
                            "**Insight:** Unable to compute a reliable comparison with current data. "
                            f"(Journeys: {j_total_fmt} / {j_sends_fmt} sends; One-time: {o_total_fmt} / {o_sends_fmt} sends)"
                        )
else:
    st.info("No campaign type data available with current filters.")

st.markdown("---")

# =====================================================================
# SECTION 3: Day-of-Week Performance Heatmap
# =====================================================================
st.subheader("3. Best Sending Days (Day-of-Week Analysis)")
st.caption("Which days deliver the highest engagement and conversions?")

date_col = 'Reporting Period Start Date' if 'Reporting Period Start Date' in filtered_df.columns else 'Day'
if date_col in filtered_df.columns and not filtered_df.empty:
    df_dow = filtered_df.copy()
    df_dow['DayOfWeek'] = pd.to_datetime(df_dow[date_col]).dt.day_name()
    df_dow['DayNum'] = pd.to_datetime(df_dow[date_col]).dt.dayofweek  # Mon=0, Sun=6

    dow_agg = df_dow.groupby(['DayOfWeek', 'DayNum']).agg(
        Sends=('Sent', 'sum'),
        Clicks=('Unique Clicks', 'sum'),
        Conversions=('Selected Conversions', 'sum') if 'Selected Conversions' in df_dow.columns else ('Unique Conversions', 'sum'),
        Revenue=('Selected Revenue (SAR)', 'sum') if 'Selected Revenue (SAR)' in df_dow.columns else ('Revenue (SAR)', 'sum'),
        Days_Count=(date_col, 'nunique'),
    ).reset_index().sort_values('DayNum')

    # Normalize to per-day averages
    dow_agg['Avg Revenue/Day'] = dow_agg['Revenue'] / dow_agg['Days_Count']
    dow_agg['Avg Conversions/Day'] = dow_agg['Conversions'] / dow_agg['Days_Count']
    dow_agg['CVR (%)'] = np.where(dow_agg['Clicks'] > 0, (dow_agg['Conversions'] / dow_agg['Clicks']) * 100, 0)

    # Heatmap-style bar chart
    fig_dow = go.Figure()
    fig_dow.add_trace(go.Bar(
        x=dow_agg['DayOfWeek'], y=dow_agg['Avg Revenue/Day'],
        name='Avg Revenue/Day', marker_color=COLORS['primary'],
        text=dow_agg['Avg Revenue/Day'].apply(lambda v: f"{v:,.0f}"),
        textposition='outside'
    ))
    fig_dow.add_trace(go.Scatter(
        x=dow_agg['DayOfWeek'], y=dow_agg['CVR (%)'],
        name='CVR %', yaxis='y2', mode='lines+markers',
        line=dict(color=COLORS['success'], width=3),
        marker=dict(size=8)
    ))
    fig_dow.update_layout(
        title="Average Daily Revenue & Conversion Rate by Day of Week",
        yaxis=dict(title="Revenue (SAR)"),
        yaxis2=dict(title="CVR %", overlaying='y', side='right', rangemode='tozero'),
        barmode='group'
    )
    st.plotly_chart(fig_dow, use_container_width=True)

    # Highlight best/worst days
    best_day = dow_agg.loc[dow_agg['Avg Revenue/Day'].idxmax()]
    worst_day = dow_agg.loc[dow_agg['Avg Revenue/Day'].idxmin()]
    col_best, col_worst = st.columns(2)
    with col_best:
        st.success(f"**Best Day:** {best_day['DayOfWeek']} — Avg {best_day['Avg Revenue/Day']:,.0f} SAR/day, {best_day['CVR (%)']:.1f}% CVR")
    with col_worst:
        st.warning(f"**Weakest Day:** {worst_day['DayOfWeek']} — Avg {worst_day['Avg Revenue/Day']:,.0f} SAR/day, {worst_day['CVR (%)']:.1f}% CVR")

    # Show table
    with st.expander("View Day-of-Week Details"):
        dow_display = dow_agg[['DayOfWeek', 'Sends', 'Clicks', 'Conversions', 'Revenue', 'Avg Revenue/Day', 'Avg Conversions/Day', 'CVR (%)']].copy()
        dow_display.columns = ['Day', 'Total Sends', 'Total Clicks', 'Total Conversions', 'Total Revenue', 'Avg Rev/Day', 'Avg Conv/Day', 'CVR %']
        st.dataframe(dow_display, use_container_width=True, hide_index=True)
else:
    st.info("No date data available for day-of-week analysis.")

st.markdown("---")

# =====================================================================
# SECTION 4: Campaign Tags Performance
# =====================================================================
st.subheader("4. Campaign Tags Performance")
st.caption("How do different campaign strategies (by tag) perform?")

if 'Campaign Tags' in filtered_df.columns and not filtered_df.empty:
    df_tags = filtered_df.copy()
    # Parse tags - they come as string like "[cart abandonment, coupon, cosmetics]"
    df_tags['Campaign Tags'] = df_tags['Campaign Tags'].astype(str)
    # Explode tags into individual rows
    df_tags['Tag_List'] = df_tags['Campaign Tags'].apply(
        lambda x: [t.strip() for t in x.strip('[]').split(',') if t.strip() and t.strip() != 'nan']
    )
    df_tags_exploded = df_tags.explode('Tag_List')
    df_tags_exploded = df_tags_exploded[df_tags_exploded['Tag_List'].notna() & (df_tags_exploded['Tag_List'] != '')]

    if not df_tags_exploded.empty:
        rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in df_tags_exploded.columns else 'Revenue (SAR)'
        conv_col = 'Selected Conversions' if 'Selected Conversions' in df_tags_exploded.columns else 'Unique Conversions'

        tag_perf = df_tags_exploded.groupby('Tag_List').agg(
            Campaigns=('Campaign Name', 'nunique'),
            Sends=('Sent', 'sum'),
            Clicks=('Unique Clicks', 'sum'),
            Conversions=(conv_col, 'sum'),
            Revenue=(rev_col, 'sum'),
        ).reset_index()
        tag_perf.rename(columns={'Tag_List': 'Tag'}, inplace=True)
        tag_perf['CVR (%)'] = np.where(tag_perf['Clicks'] > 0, (tag_perf['Conversions'] / tag_perf['Clicks']) * 100, 0)
        tag_perf['Rev/Send'] = np.where(tag_perf['Sends'] > 0, tag_perf['Revenue'] / tag_perf['Sends'], 0)
        tag_perf = tag_perf.sort_values('Revenue', ascending=False)

        # Show top tags
        fig_tags = px.bar(
            tag_perf.head(15), x='Tag', y='Revenue',
            color='CVR (%)', color_continuous_scale='Greens',
            title="Top 15 Tags by Revenue (color = CVR %)",
            text=tag_perf.head(15)['Revenue'].apply(lambda v: f"{v:,.0f}")
        )
        fig_tags.update_traces(textposition='outside')
        st.plotly_chart(fig_tags, use_container_width=True)

        # Table
        st.dataframe(tag_perf.head(20), use_container_width=True, hide_index=True)
    else:
        st.info("No campaign tags found in the data. Tags are optional in WebEngage campaigns.")
else:
    st.info("No Campaign Tags column in this dataset.")

st.markdown("---")

# =====================================================================
# SECTION 5: Bottom Performers — Campaigns to Pause
# =====================================================================
st.subheader("5. Underperforming Campaigns (Candidates to Pause)")
st.caption("Campaigns with significant sends but zero or near-zero conversions/revenue — immediate action candidates.")

if not filtered_df.empty:
    rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
    conv_col = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'

    camp_agg_dict = {
        'Channel': ('Channel', 'first'),
        'Sends': ('Sent', 'sum'),
        'Delivered': ('Delivered', 'sum'),
        'Clicks': ('Unique Clicks', 'sum'),
        'Conversions': (conv_col, 'sum'),
        'Revenue': (rev_col, 'sum'),
    }
    if 'Type of Campaign' in filtered_df.columns:
        camp_agg_dict['Type'] = ('Type of Campaign', 'first')
    if 'Status' in filtered_df.columns:
        camp_agg_dict['Status'] = ('Status', 'first')
    camp_perf = filtered_df.groupby('Campaign Name').agg(**camp_agg_dict).reset_index()

    # Filter to campaigns with meaningful send volume but poor results
    min_sends_threshold = st.slider("Minimum sends to consider", 10, 1000, 100, step=50, key="bottom_perf_min_sends")
    underperformers = camp_perf[
        (camp_perf['Sends'] >= min_sends_threshold) &
        (camp_perf['Revenue'] == 0) &
        (camp_perf['Conversions'] == 0)
    ].sort_values('Sends', ascending=False)

    if not underperformers.empty:
        st.error(f"**{len(underperformers)} campaigns** sent {int(underperformers['Sends'].sum()):,} messages with ZERO conversions and ZERO revenue.")
        display_cols = ['Campaign Name', 'Channel'] + ([c for c in ['Type', 'Status'] if c in underperformers.columns]) + ['Sends', 'Delivered', 'Clicks', 'Conversions', 'Revenue']
        st.dataframe(
            underperformers[display_cols].head(20),
            use_container_width=True, hide_index=True
        )

        # Also show low-revenue campaigns (have conversions but very low ROI)
        low_roi = camp_perf[
            (camp_perf['Sends'] >= min_sends_threshold) &
            (camp_perf['Conversions'] > 0) &
            (camp_perf['Revenue'] > 0)
        ].copy()
        if not low_roi.empty:
            low_roi['Rev/Send'] = low_roi['Revenue'] / low_roi['Sends']
            low_roi = low_roi.nsmallest(10, 'Rev/Send')
            st.markdown("**Low-efficiency campaigns** (have conversions but very low revenue per send):")
            st.dataframe(
                low_roi[['Campaign Name', 'Channel', 'Sends', 'Conversions', 'Revenue', 'Rev/Send']].head(10),
                use_container_width=True, hide_index=True
            )
    else:
        st.success("No zero-performance campaigns found at this send threshold. All active campaigns are generating some conversions.")

st.markdown("---")

# =====================================================================
# SECTION 6: Segment Performance
# =====================================================================
st.subheader("6. Segment Performance Ranking")
st.caption("Which audience segments drive the most value?")

if 'Segment Name' in filtered_df.columns and not filtered_df.empty:
    rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
    conv_col = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'

    df_seg = filtered_df[filtered_df['Segment Name'].notna() & (filtered_df['Segment Name'] != 'nan') & (filtered_df['Segment Name'] != '')]
    if not df_seg.empty:
        seg_perf = df_seg.groupby('Segment Name').agg(
            Campaigns=('Campaign Name', 'nunique'),
            Sends=('Sent', 'sum'),
            Clicks=('Unique Clicks', 'sum'),
            Conversions=(conv_col, 'sum'),
            Revenue=(rev_col, 'sum'),
        ).reset_index()
        seg_perf['CVR (%)'] = np.where(seg_perf['Clicks'] > 0, (seg_perf['Conversions'] / seg_perf['Clicks']) * 100, 0)
        seg_perf['Rev/Send'] = np.where(seg_perf['Sends'] > 0, seg_perf['Revenue'] / seg_perf['Sends'], 0)
        seg_perf = seg_perf.sort_values('Revenue', ascending=False)

        # Top segments chart
        fig_seg = px.bar(
            seg_perf.head(15), x='Segment Name', y='Revenue',
            color='CVR (%)', color_continuous_scale='Blues',
            title="Top 15 Segments by Revenue (color = CVR %)",
            text=seg_perf.head(15)['Revenue'].apply(lambda v: f"{v:,.0f}")
        )
        fig_seg.update_traces(textposition='outside')
        fig_seg.update_layout(xaxis_tickangle=-45)
        st.plotly_chart(fig_seg, use_container_width=True)

        # Summary insight
        if len(seg_perf) >= 2:
            top_seg = seg_perf.iloc[0]
            top_share = (top_seg['Revenue'] / seg_perf['Revenue'].sum() * 100) if seg_perf['Revenue'].sum() > 0 else 0
            st.info(f"**Top segment '{top_seg['Segment Name']}'** drives {top_share:.0f}% of total revenue with {top_seg['CVR (%)']:.1f}% CVR.")

        # Full table
        with st.expander("View All Segments"):
            st.dataframe(seg_perf, use_container_width=True, hide_index=True)
    else:
        st.info("No segment data available after filtering.")
else:
    st.info("No Segment Name column in this dataset.")

st.markdown("---")

# =====================================================================
# SECTION 7: Monthly Performance Trends
# =====================================================================
st.subheader("7. Monthly Performance Trends")
st.caption("Month-over-month revenue, conversions, and efficiency — spot growth or decline at a glance.")

date_col_m = 'Reporting Period Start Date' if 'Reporting Period Start Date' in filtered_df.columns else 'Day'
if date_col_m in filtered_df.columns and not filtered_df.empty:
    rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
    conv_col = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'

    df_monthly = filtered_df.copy()
    df_monthly['Month'] = pd.to_datetime(df_monthly[date_col_m]).dt.to_period('M')

    monthly_agg = df_monthly.groupby('Month').agg(
        Revenue=(rev_col, 'sum'),
        Conversions=(conv_col, 'sum'),
        Sends=('Sent', 'sum'),
        Delivered=('Delivered', 'sum'),
        Clicks=('Unique Clicks', 'sum'),
        Impressions=('Unique Impressions', 'sum'),
        Campaigns=('Campaign Name', 'nunique'),
    ).reset_index()

    monthly_agg['Month_str'] = monthly_agg['Month'].astype(str)
    monthly_agg['Rev/Send'] = np.where(monthly_agg['Sends'] > 0, monthly_agg['Revenue'] / monthly_agg['Sends'], 0)
    monthly_agg['CVR (%)'] = np.where(monthly_agg['Clicks'] > 0, (monthly_agg['Conversions'] / monthly_agg['Clicks']) * 100, 0)
    monthly_agg['CTR (%)'] = np.where(monthly_agg['Impressions'] > 0, (monthly_agg['Clicks'] / monthly_agg['Impressions']) * 100, 0)
    monthly_agg['AOV (SAR)'] = np.where(monthly_agg['Conversions'] > 0, monthly_agg['Revenue'] / monthly_agg['Conversions'], 0)

    # MoM change columns
    monthly_agg['Rev_MoM (%)'] = monthly_agg['Revenue'].pct_change() * 100
    monthly_agg['Conv_MoM (%)'] = monthly_agg['Conversions'].pct_change() * 100
    monthly_agg['Sends_MoM (%)'] = monthly_agg['Sends'].pct_change() * 100

    # --- KPI summary for latest vs previous month ---
    if len(monthly_agg) >= 2:
        latest = monthly_agg.iloc[-1]
        prev = monthly_agg.iloc[-2]
        kpi_cols = st.columns(4)
        with kpi_cols[0]:
            rev_change = latest['Rev_MoM (%)'] if not pd.isna(latest['Rev_MoM (%)']) else 0
            st.metric(f"Revenue ({latest['Month_str']})", f"{latest['Revenue']:,.0f} SAR",
                      delta=f"{rev_change:+.1f}% vs {prev['Month_str']}")
        with kpi_cols[1]:
            conv_change = latest['Conv_MoM (%)'] if not pd.isna(latest['Conv_MoM (%)']) else 0
            st.metric(f"Conversions ({latest['Month_str']})", f"{int(latest['Conversions']):,}",
                      delta=f"{conv_change:+.1f}% vs {prev['Month_str']}")
        with kpi_cols[2]:
            st.metric(f"Rev/Send ({latest['Month_str']})", f"{latest['Rev/Send']:.3f} SAR",
                      delta=f"{((latest['Rev/Send'] - prev['Rev/Send']) / prev['Rev/Send'] * 100) if prev['Rev/Send'] > 0 else 0:+.1f}%")
        with kpi_cols[3]:
            st.metric(f"CVR ({latest['Month_str']})", f"{latest['CVR (%)']:.1f}%",
                      delta=f"{latest['CVR (%)'] - prev['CVR (%)']:+.1f}pp")

    # --- Revenue & Conversions trend chart ---
    fig_monthly = go.Figure()
    fig_monthly.add_trace(go.Bar(
        x=monthly_agg['Month_str'], y=monthly_agg['Revenue'],
        name='Revenue (SAR)', marker_color=COLORS['primary'],
        text=monthly_agg['Revenue'].apply(lambda v: f"{v:,.0f}"),
        textposition='outside'
    ))
    fig_monthly.add_trace(go.Scatter(
        x=monthly_agg['Month_str'], y=monthly_agg['Conversions'],
        name='Conversions', yaxis='y2', mode='lines+markers',
        line=dict(color=COLORS['success'], width=3),
        marker=dict(size=8)
    ))
    fig_monthly.update_layout(
        title="Monthly Revenue & Conversions",
        yaxis=dict(title="Revenue (SAR)"),
        yaxis2=dict(title="Conversions", overlaying='y', side='right', rangemode='tozero'),
        barmode='group'
    )
    st.plotly_chart(fig_monthly, use_container_width=True)

    # --- Efficiency metrics trend ---
    fig_eff = go.Figure()
    fig_eff.add_trace(go.Scatter(
        x=monthly_agg['Month_str'], y=monthly_agg['Rev/Send'],
        name='Rev/Send (SAR)', mode='lines+markers',
        line=dict(color=COLORS['primary'], width=2), marker=dict(size=7)
    ))
    fig_eff.add_trace(go.Scatter(
        x=monthly_agg['Month_str'], y=monthly_agg['CVR (%)'],
        name='CVR %', yaxis='y2', mode='lines+markers',
        line=dict(color=COLORS['success'], width=2), marker=dict(size=7)
    ))
    fig_eff.add_trace(go.Scatter(
        x=monthly_agg['Month_str'], y=monthly_agg['CTR (%)'],
        name='CTR %', yaxis='y2', mode='lines+markers',
        line=dict(color=COLORS['warning'], width=2, dash='dot'), marker=dict(size=6)
    ))
    fig_eff.update_layout(
        title="Monthly Efficiency Metrics",
        yaxis=dict(title="Rev/Send (SAR)"),
        yaxis2=dict(title="Rate (%)", overlaying='y', side='right', rangemode='tozero'),
    )
    st.plotly_chart(fig_eff, use_container_width=True)

    # --- Channel breakdown by month ---
    if 'Channel' in df_monthly.columns:
        st.markdown("**Monthly Revenue by Channel**")
        monthly_chan = df_monthly.groupby(['Month', 'Channel']).agg(
            Revenue=(rev_col, 'sum'),
        ).reset_index()
        monthly_chan['Month_str'] = monthly_chan['Month'].astype(str)

        fig_chan_monthly = px.bar(
            monthly_chan, x='Month_str', y='Revenue', color='Channel',
            color_discrete_map=CHANNEL_COLORS,
            title="Revenue by Channel per Month",
            barmode='stack'
        )
        fig_chan_monthly.update_layout(xaxis_title="Month", yaxis_title="Revenue (SAR)")
        st.plotly_chart(fig_chan_monthly, use_container_width=True)

    # --- MoM growth table ---
    with st.expander("View Monthly Details Table"):
        monthly_display = monthly_agg[['Month_str', 'Revenue', 'Conversions', 'Sends', 'Clicks',
                                       'Rev/Send', 'CVR (%)', 'CTR (%)', 'AOV (SAR)',
                                       'Rev_MoM (%)', 'Conv_MoM (%)', 'Campaigns']].copy()
        monthly_display.columns = ['Month', 'Revenue (SAR)', 'Conversions', 'Sends', 'Clicks',
                                   'Rev/Send', 'CVR %', 'CTR %', 'AOV (SAR)',
                                   'Rev MoM %', 'Conv MoM %', 'Active Campaigns']
        # Format MoM columns
        monthly_display['Rev MoM %'] = monthly_display['Rev MoM %'].apply(lambda v: f"{v:+.1f}%" if not pd.isna(v) else "—")
        monthly_display['Conv MoM %'] = monthly_display['Conv MoM %'].apply(lambda v: f"{v:+.1f}%" if not pd.isna(v) else "—")
        st.dataframe(monthly_display, use_container_width=True, hide_index=True)

    # --- Growth insight ---
    if len(monthly_agg) >= 3:
        recent_3 = monthly_agg.tail(3)
        avg_rev_growth = recent_3['Rev_MoM (%)'].dropna().mean()
        if avg_rev_growth > 10:
            st.success(f"**Trend:** Revenue is growing at **{avg_rev_growth:.0f}% MoM** average over the last 3 months.")
        elif avg_rev_growth < -10:
            st.error(f"**Trend:** Revenue is declining at **{avg_rev_growth:.0f}% MoM** average over the last 3 months. Investigate channel performance and campaign strategy.")
        else:
            st.info(f"**Trend:** Revenue is relatively stable ({avg_rev_growth:+.0f}% MoM average).")
else:
    st.info("No date data available for monthly analysis.")
