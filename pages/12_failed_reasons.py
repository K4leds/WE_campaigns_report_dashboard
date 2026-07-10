import streamlit as st
import pandas as pd
import plotly.express as px

from dashboard.state import get_ctx
from analysis import failed_reasons_analysis
from utils import format_metric
from config import COLORS, COLOR_SEQUENCE

ctx = get_ctx()
filtered_df = ctx.filtered_df

st.header("Failed Reasons Analysis")
failed_df = failed_reasons_analysis(filtered_df)
if not failed_df.empty:
    # Create display version for table
    failed_df_display = failed_df.copy()
    # Format counts
    failed_df_display['Count'] = failed_df_display['Count'].apply(format_metric)
    st.dataframe(failed_df_display)

    # Create chart with original numeric values
    fig_fail = px.bar(failed_df, x='Reason', y='Count', title="Failed Reasons Breakdown",
                      color_discrete_sequence=[COLORS['danger']])
    st.plotly_chart(fig_fail, width='stretch')

    # Drill-down: Failed reasons by channel
    st.subheader("Failed Reasons by Channel")
    failed_cols = [col for col in filtered_df.columns if 'Failed' in col and col != 'Failed']
    if failed_cols:
        failed_by_channel = filtered_df.groupby('Channel')[failed_cols].sum().reset_index()
        # Create display version for table
        failed_by_channel_display = failed_by_channel.copy()
        # Format failed counts
        for col in failed_cols:
            failed_by_channel_display[col] = failed_by_channel_display[col].apply(format_metric)
        st.dataframe(failed_by_channel_display)

        # Melt for plotting (use original numeric values)
        failed_melt = failed_by_channel.melt(id_vars='Channel', var_name='Reason', value_name='Count')
        fig_fail_chan = px.bar(failed_melt, x='Channel', y='Count', color='Reason',
                              title="Failed Reasons by Channel",
                              color_discrete_sequence=COLOR_SEQUENCE)
        st.plotly_chart(fig_fail_chan, width='stretch')
else:
    st.write("No failed reasons data available.")
