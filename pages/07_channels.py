import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric
from components.table import render_table
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

# Display-friendly rename map for attribution-selected columns (mirrors app.py prelude)
attribution_rename = {'Selected Revenue (SAR)': selected_rev_label, 'Selected Conversions': selected_conv_label}


def _attribution_display(col_name):
    """Map internal 'Selected Revenue/Conversions' column names to the user-selected attribution label."""
    return get_attribution_display_label(col_name, revenue_attribution, conversion_attribution)


st.header("Channels & Delivery Analysis")

tab1, tab2 = st.tabs(["📡 Channels", "❌ Failed Reasons"])

with tab1:
    chan_df = channel_analysis(filtered_df)

    # Channel conversion rate based on selected conversion attribution
    conv_rate_source_col = 'Selected Conversions' if 'Selected Conversions' in chan_df.columns else 'Unique Conversions'
    if conv_rate_source_col in chan_df.columns and 'Unique Clicks' in chan_df.columns:
        chan_df['Conversion Rate'] = np.where(
            chan_df['Unique Clicks'] > 0,
            (chan_df[conv_rate_source_col] / chan_df['Unique Clicks']) * 100,
            0
        )

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
        total_conv_for_rate = chan_df[conv_rate_source_col].sum() if conv_rate_source_col in chan_df.columns else 0
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
        chan_df_comparison = channel_analysis(comparison_result['comparison_data'])
        if conv_rate_source_col in chan_df_comparison.columns and 'Unique Clicks' in chan_df_comparison.columns:
            chan_df_comparison['Conversion Rate'] = np.where(
                chan_df_comparison['Unique Clicks'] > 0,
                (chan_df_comparison[conv_rate_source_col] / chan_df_comparison['Unique Clicks']) * 100,
                0
            )
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
            comp_conv_for_rate = chan_df_comparison[conv_rate_source_col].sum() if conv_rate_source_col in chan_df_comparison.columns else 0
            total_row_chan['Conversion Rate__total_comp'] = (comp_conv_for_rate / comp_clicks) * 100 if comp_clicks > 0 else 0

    render_table(
        chan_df_display,
        key="channel_analysis",
        column_config=chan_cc,
        comparison_df=chan_df_comparison_display,
        compare_on="Channel",
        total_row=total_row_chan,
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
        st.plotly_chart(fig_donut, width='stretch')

    # Revenue + Conversions by Channel (using selected attribution)
    st.subheader("Revenue & Conversions Comparison")
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
            st.plotly_chart(fig_rev_chan, width='stretch')
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
        st.plotly_chart(fig_conv_chan, width='stretch')

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
        st.plotly_chart(fig_dr, width='stretch')
    with ch_col2:
        fig_ctr = px.bar(
            chan_rates, x='Channel', y='CTR',
            title="Click-Through Rate by Channel (%)",
            color='Channel', color_discrete_map=CHANNEL_COLORS,
        )
        fig_ctr.update_layout(showlegend=False, yaxis_title="CTR (%)")
        st.plotly_chart(fig_ctr, width='stretch')
    with ch_col3:
        fig_cvr = px.bar(
            chan_rates, x='Channel', y='Conversion Rate',
            title="Conversion Rate by Channel (%)",
            color='Channel', color_discrete_map=CHANNEL_COLORS,
        )
        fig_cvr.update_layout(showlegend=False, yaxis_title="Conversion Rate (%)")
        st.plotly_chart(fig_cvr, width='stretch')

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
    st.plotly_chart(fig_vol, width='stretch')

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
        st.plotly_chart(fig_rev_compare, width='stretch')

    # Campaign Type Performance by Channel (One-Time vs Journey)
    if 'Type of Campaign' in filtered_df.columns and 'Channel' in filtered_df.columns:
        type_vals = filtered_df['Type of Campaign'].dropna().unique()
        if len(type_vals) > 0:
            st.subheader("One-Time vs Journey Performance by Channel")
            rev_col_type = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
            conv_col_type = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'

            # Aggregate all available revenue and conversion columns
            type_chan_agg = {'Sent': 'sum', 'Delivered': 'sum'}
            # Always include selected attribution columns
            if conv_col_type in filtered_df.columns:
                type_chan_agg[conv_col_type] = 'sum'
            if rev_col_type in filtered_df.columns:
                type_chan_agg[rev_col_type] = 'sum'
            # Also aggregate all other revenue/conversion columns for detail view
            extra_rev_cols = [c for c in ['Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Impression-Through Revenue (SAR)'] if c in filtered_df.columns and c != rev_col_type]
            extra_conv_cols = [c for c in ['Unique Conversions', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions'] if c in filtered_df.columns and c != conv_col_type]
            for c in extra_rev_cols + extra_conv_cols:
                type_chan_agg[c] = 'sum'
            type_chan_df = filtered_df.groupby(['Channel', 'Type of Campaign']).agg(type_chan_agg).reset_index()

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
                    st.plotly_chart(fig_type_chan_rev, width='stretch')
            with type_chan_col2:
                conv_display_name = get_selected_conversion_display_name(conversion_attribution)
                fig_type_chan_conv = px.bar(
                    type_chan_df, x='Channel', y=conv_col_type, color='Type of Campaign',
                    barmode='stack', title=f"{conv_display_name} by Channel & Campaign Type",
                    color_discrete_sequence=COLOR_SEQUENCE,
                    labels={conv_col_type: conv_display_name}
                )
                fig_type_chan_conv.update_layout(legend=dict(orientation='h', y=-0.2))
                st.plotly_chart(fig_type_chan_conv, width='stretch')

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
                st.plotly_chart(fig_share, width='stretch')

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

        esp_col1, esp_col2 = st.columns(2)
        with esp_col1:
            fig_esp = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Delivered',
                             title="Delivered by ESP", color_discrete_sequence=COLOR_SEQUENCE)
            st.plotly_chart(fig_esp, width='stretch')
        with esp_col2:
            if 'Revenue (SAR)' in esp_df.columns:
                fig_esp_rev = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Revenue (SAR)',
                                     title="Send-Through Revenue by ESP", color_discrete_sequence=COLOR_SEQUENCE,
                                     labels={'Revenue (SAR)': 'Send-Through Revenue (SAR)'})
                st.plotly_chart(fig_esp_rev, width='stretch')

with tab2:
    failed_df = failed_reasons_analysis(filtered_df)
    if not failed_df.empty:
        # Create display version for table
        col_config = {"Count": st.column_config.NumberColumn(label="Count", format="%.0f")}
        render_table(failed_df, key="failed_reasons", column_config=col_config)

        # Create chart with original numeric values
        fig_fail = px.bar(failed_df, x='Reason', y='Count', title="Failed Reasons Breakdown",
                          color_discrete_sequence=[COLORS['danger']])
        st.plotly_chart(fig_fail, width='stretch')

        # Drill-down: Failed reasons by channel
        st.subheader("Failed Reasons by Channel")
        failed_cols = [col for col in filtered_df.columns if 'Failed' in col and col != 'Failed']
        if failed_cols:
            failed_by_channel = filtered_df.groupby('Channel')[failed_cols].sum().reset_index()
            # Build column config for failed count columns (all are integer counts)
            channel_cc = {col: st.column_config.NumberColumn(label=col, format="%.0f") for col in failed_cols}
            render_table(failed_by_channel, key="failed_by_channel", column_config=channel_cc)

            # Melt for plotting (use original numeric values)
            failed_melt = failed_by_channel.melt(id_vars='Channel', var_name='Reason', value_name='Count')
            fig_fail_chan = px.bar(failed_melt, x='Channel', y='Count', color='Reason',
                                  title="Failed Reasons by Channel",
                                  color_discrete_sequence=COLOR_SEQUENCE)
            st.plotly_chart(fig_fail_chan, width='stretch')
    else:
        st.write("No failed reasons data available.")
