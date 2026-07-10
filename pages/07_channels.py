import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric, style_total_row
from config import COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import get_attribution_display_label, get_selected_revenue_display_name, get_selected_conversion_display_name, resolve_source_column
from analysis import channel_analysis, esp_analysis

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


st.header("Channel Analysis")
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

# If comparison mode is active, calculate comparison metrics and add percentage changes
if comparison_result:
    # Calculate channel metrics for comparison period
    chan_df_comparison = channel_analysis(comparison_result['comparison_data'])
    
    # Create a new display dataframe with values and percentage changes
    chan_df_with_changes = chan_df_display.copy()

    # Compare metric values for each channel
    display_metric_cols = [c for c in chan_df_display.columns if c != 'Channel']

    for display_col in display_metric_cols:
        source_col = resolve_source_column(display_col, revenue_attribution, conversion_attribution)

        if source_col not in chan_df.columns:
            continue

        new_col_data = []
        for channel in chan_df_display['Channel']:
            if source_col == 'AOV (SAR)':
                curr_rev = chan_df.loc[chan_df['Channel'] == channel, 'Selected Revenue (SAR)'] if 'Selected Revenue (SAR)' in chan_df.columns else chan_df.loc[chan_df['Channel'] == channel, 'Revenue (SAR)']
                curr_conv = chan_df.loc[chan_df['Channel'] == channel, 'Selected Conversions'] if 'Selected Conversions' in chan_df.columns else chan_df.loc[chan_df['Channel'] == channel, 'Unique Conversions']
                current_val = curr_rev.sum() / curr_conv.sum() if curr_conv.sum() > 0 else 0

                comp_val = 0
                if 'Selected Revenue (SAR)' in chan_df_comparison.columns and 'Selected Conversions' in chan_df_comparison.columns:
                    comp_rev = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, 'Selected Revenue (SAR)']
                    comp_conv = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, 'Selected Conversions']
                    comp_val = comp_rev.sum() / comp_conv.sum() if comp_conv.sum() > 0 else 0
            elif source_col == 'Conversion Rate':
                curr_clicks = chan_df.loc[chan_df['Channel'] == channel, 'Unique Clicks'].sum()
                curr_conv = chan_df.loc[chan_df['Channel'] == channel, conv_rate_source_col].sum() if conv_rate_source_col in chan_df.columns else 0
                current_val = (curr_conv / curr_clicks) * 100 if curr_clicks > 0 else 0

                comp_val = 0
                if conv_rate_source_col in chan_df_comparison.columns and 'Unique Clicks' in chan_df_comparison.columns:
                    comp_clicks = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, 'Unique Clicks'].sum()
                    comp_conv = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, conv_rate_source_col].sum()
                    comp_val = (comp_conv / comp_clicks) * 100 if comp_clicks > 0 else 0
            else:
                current_val = chan_df.loc[chan_df['Channel'] == channel, source_col].values
                current_val = current_val[0] if len(current_val) > 0 else 0

                comp_val = 0
                if source_col in chan_df_comparison.columns:
                    comp_val = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, source_col].values
                    comp_val = comp_val[0] if len(comp_val) > 0 else 0

            if comp_val > 0:
                pct_change = ((current_val - comp_val) / comp_val) * 100
                if pct_change > 0:
                    pct_str = f" <span style='color: #28a745; font-weight: 600; white-space: nowrap; display: inline-block;'>▲&nbsp;{pct_change:.1f}%</span>"
                elif pct_change < 0:
                    pct_str = f" <span style='color: #dc3545; font-weight: 600; white-space: nowrap; display: inline-block;'>▼&nbsp;{abs(pct_change):.1f}%</span>"
                else:
                    pct_str = " <span style='color: #6c757d; white-space: nowrap; display: inline-block;'>→&nbsp;0%</span>"
            elif current_val > 0 and comp_val == 0:
                pct_str = " <span style='color: #17a2b8; font-weight: 600; white-space: nowrap; display: inline-block;'>🆕</span>"
            else:
                pct_str = ""

            if source_col == 'Conversion Rate':
                formatted_val = f"{current_val:.2f}%"
            elif 'Revenue' in source_col or 'AOV' in source_col:
                formatted_val = format_metric(current_val, "SAR", abbreviate=True)
            else:
                formatted_val = format_metric(current_val, "", abbreviate=True)

            new_col_data.append(formatted_val + pct_str)

        chan_df_with_changes[display_col] = new_col_data

    # Add total row with comparisons
    total_row_chan = {'Channel': 'Total'}
    for display_col in display_metric_cols:
        source_col = resolve_source_column(display_col, revenue_attribution, conversion_attribution)

        if source_col not in chan_df.columns:
            continue

        current_total = chan_df[source_col].sum()
        comp_total = chan_df_comparison[source_col].sum() if source_col in chan_df_comparison.columns else 0

        if source_col == 'AOV (SAR)':
            total_rev = chan_df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in chan_df.columns else chan_df['Revenue (SAR)'].sum()
            total_conv = chan_df['Selected Conversions'].sum() if 'Selected Conversions' in chan_df.columns else chan_df['Unique Conversions'].sum()
            current_total = total_rev / total_conv if total_conv > 0 else 0
            comp_total = 0
            if 'Selected Revenue (SAR)' in chan_df_comparison.columns and 'Selected Conversions' in chan_df_comparison.columns:
                comp_rev = chan_df_comparison['Selected Revenue (SAR)'].sum()
                comp_conv = chan_df_comparison['Selected Conversions'].sum()
                comp_total = comp_rev / comp_conv if comp_conv > 0 else 0
        elif source_col == 'Conversion Rate':
            current_clicks = chan_df['Unique Clicks'].sum() if 'Unique Clicks' in chan_df.columns else 0
            current_conv = chan_df[conv_rate_source_col].sum() if conv_rate_source_col in chan_df.columns else 0
            current_total = (current_conv / current_clicks) * 100 if current_clicks > 0 else 0

            comp_clicks = chan_df_comparison['Unique Clicks'].sum() if 'Unique Clicks' in chan_df_comparison.columns else 0
            comp_conv = chan_df_comparison[conv_rate_source_col].sum() if conv_rate_source_col in chan_df_comparison.columns else 0
            comp_total = (comp_conv / comp_clicks) * 100 if comp_clicks > 0 else 0
        else:
            current_total = chan_df[source_col].sum()
            comp_total = chan_df_comparison[source_col].sum() if source_col in chan_df_comparison.columns else 0

        if comp_total > 0:
            pct_change = ((current_total - comp_total) / comp_total) * 100
            if pct_change > 0:
                pct_str = f" <span style='color: #28a745; font-weight: 600; white-space: nowrap; display: inline-block;'>▲&nbsp;{pct_change:.1f}%</span>"
            elif pct_change < 0:
                pct_str = f" <span style='color: #dc3545; font-weight: 600; white-space: nowrap; display: inline-block;'>▼&nbsp;{abs(pct_change):.1f}%</span>"
            else:
                pct_str = " <span style='color: #6c757d; white-space: nowrap; display: inline-block;'>→&nbsp;0%</span>"
        elif current_total > 0:
            pct_str = " <span style='color: #17a2b8; font-weight: 600; white-space: nowrap; display: inline-block;'>🆕</span>"
        else:
            pct_str = ""

        if source_col == 'Conversion Rate':
            formatted_total = f"{current_total:.2f}%"
        elif 'Revenue' in source_col or 'AOV' in source_col:
            formatted_total = format_metric(current_total, "SAR", abbreviate=True)
        else:
            formatted_total = format_metric(current_total, "", abbreviate=True)

        total_row_chan[display_col] = formatted_total + pct_str

    chan_df_with_changes = pd.concat([chan_df_with_changes, pd.DataFrame([total_row_chan])], ignore_index=True)
    chan_df_display = chan_df_with_changes
else:
    # No comparison - use regular formatting
    # Add total row
    total_row_chan = {'Channel': 'Total'}
    for col in chan_df_display.columns:
        if col == 'Channel':
            continue
        if 'AOV' in col:
            continue
        total_row_chan[col] = chan_df_display[col].sum()

    # Compute total AOV from total revenue/total conversions
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
    for col in [c for c in chan_df_display.columns if 'AOV' in c]:
        total_row_chan[col] = total_aov

    # Compute total conversion rate from totals (not sum of row percentages)
    if 'Conversion Rate' in chan_df_display.columns:
        total_clicks = chan_df['Unique Clicks'].sum() if 'Unique Clicks' in chan_df.columns else 0
        total_conv_for_rate = chan_df[conv_rate_source_col].sum() if conv_rate_source_col in chan_df.columns else 0
        total_row_chan['Conversion Rate'] = (total_conv_for_rate / total_clicks) * 100 if total_clicks > 0 else 0

    chan_df_display = pd.concat([chan_df_display, pd.DataFrame([total_row_chan])], ignore_index=True)
    # Format columns
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

    for col in numeric_cols:
        if col in chan_df_display.columns:
            chan_df_display[col] = chan_df_display[col].apply(format_metric)
    revenue_cols = [col for col in chan_df_display.columns if 'Revenue' in col]
    for col in revenue_cols:
        chan_df_display[col] = chan_df_display[col].apply(lambda x: format_metric(x, "SAR"))
    # Format AOV columns
    aov_cols = [col for col in chan_df_display.columns if 'AOV' in col]
    for col in aov_cols:
        chan_df_display[col] = chan_df_display[col].apply(lambda x: format_metric(x, "SAR"))
    if 'Conversion Rate' in chan_df_display.columns:
        chan_df_display['Conversion Rate'] = chan_df_display['Conversion Rate'].apply(lambda x: f"{x:.2f}%")

# Display table with HTML rendering if comparison is active
if comparison_result:
    table_html = chan_df_display.to_html(escape=False, index=False)
    components.html(
        """
        <style>
        @media (prefers-color-scheme: dark) {
            .channel-compare-table {
                color: rgba(250, 250, 250, 0.95);
            }
            .channel-compare-table table {
                background: #0e1117;
                border: 1px solid rgba(250, 250, 250, 0.2);
            }
            .channel-compare-table th {
                background: rgba(38, 39, 48, 0.8);
                border-bottom: 1px solid rgba(250, 250, 250, 0.2);
            }
            .channel-compare-table td {
                border-bottom: 1px solid rgba(250, 250, 250, 0.1);
            }
            .channel-compare-table tr:nth-child(even) td {
                background: rgba(250, 250, 250, 0.03);
            }
            .channel-compare-table tr:hover td {
                background: rgba(250, 250, 250, 0.08);
            }
            .channel-compare-table tbody tr:last-child td {
                background: rgba(100, 150, 255, 0.15);
                border-top: 2px solid rgba(100, 150, 255, 0.5);
            }
        }
        @media (prefers-color-scheme: light) {
            .channel-compare-table {
                color: #262730;
            }
            .channel-compare-table table {
                background: #ffffff;
                border: 1px solid #e6e6e6;
            }
            .channel-compare-table th {
                background: #f6f7f9;
                border-bottom: 1px solid #e6e6e6;
            }
            .channel-compare-table td {
                border-bottom: 1px solid #f0f0f0;
            }
            .channel-compare-table tr:nth-child(even) td {
                background: #fafafa;
            }
            .channel-compare-table tr:hover td {
                background: #f0f7ff;
            }
            .channel-compare-table tbody tr:last-child td {
                background: #e8f4ff;
                border-top: 2px solid #4a90e2;
            }
        }
        .channel-compare-table {
            font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            font-size: 14px;
        }
        .channel-compare-table table {
            width: 100%;
            border-collapse: collapse;
        }
        .channel-compare-table th,
        .channel-compare-table td {
            white-space: nowrap;
            padding: 8px 10px;
            text-align: left;
            vertical-align: middle;
        }
        .channel-compare-table th {
            font-weight: 600;
            position: sticky;
            top: 0;
            z-index: 1;
        }
        .channel-compare-table tbody tr:last-child td {
            font-weight: 700;
        }
        </style>
        """ + f"<div class='channel-compare-table'>{table_html}</div>",
        height=360,
        scrolling=True
    )
else:
    st.dataframe(style_total_row(chan_df_display), width='stretch', hide_index=True)

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
        # Format numeric columns
        for col in ['Sent', 'Delivered'] + extra_conv_cols + ([conv_col_type] if conv_col_type in type_chan_display.columns else []):
            if col in type_chan_display.columns:
                type_chan_display[col] = type_chan_display[col].apply(format_metric)
        for col in [rev_col_type] + extra_rev_cols:
            if col in type_chan_display.columns:
                type_chan_display[col] = type_chan_display[col].apply(lambda x: format_metric(x, "SAR"))
        # Rename Selected columns to show actual attribution model
        type_chan_display = type_chan_display.rename(columns=attribution_rename)
        st.dataframe(type_chan_display, width='stretch', hide_index=True)

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
    numeric_cols = ['Sent', 'Delivered', 'Unique Conversions']
    for col in numeric_cols:
        if col in esp_df_display.columns:
            esp_df_display[col] = esp_df_display[col].apply(format_metric)
    revenue_cols = [col for col in esp_df_display.columns if 'Revenue' in col]
    for col in revenue_cols:
        esp_df_display[col] = esp_df_display[col].apply(lambda x: format_metric(x, "SAR"))
    st.dataframe(esp_df_display)

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
