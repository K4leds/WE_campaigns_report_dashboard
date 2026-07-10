import streamlit as st
import pandas as pd
from io import BytesIO

from dashboard.state import get_ctx
from analysis import top_campaigns, get_top_journeys, top_segments, channel_analysis, esp_analysis, time_series_analysis, failed_reasons_analysis
from utils import format_metric

ctx = get_ctx()
filtered_df = ctx.filtered_df

st.header("Export")

# Compute aggregates for export
camp_metric = 'Unique Conversions'
top_camp = top_campaigns(filtered_df, camp_metric)
jour_metric = 'Unique Conversions'
top_jour = get_top_journeys(filtered_df, jour_metric)
seg_metric = 'Unique Conversions'
top_seg = top_segments(filtered_df, seg_metric)
chan_df = channel_analysis(filtered_df)
esp_df = esp_analysis(filtered_df)
ts_metric = 'Unique Conversions'
ts_df = time_series_analysis(filtered_df, ts_metric)
failed_df = failed_reasons_analysis(filtered_df)

if st.button("Download Cleaned Data as CSV"):
    csv = filtered_df.to_csv(index=False)
    st.download_button("Download CSV", csv, "cleaned_data.csv", "text/csv", key='csv_dl')

if st.button("Download Aggregated Report as Excel"):
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        top_camp.to_excel(writer, sheet_name='Top Campaigns', index=False)
        top_jour.to_excel(writer, sheet_name='Top Journeys', index=False)
        top_seg.to_excel(writer, sheet_name='Top Segments', index=False)
        chan_df.to_excel(writer, sheet_name='Channel Analysis', index=False)
        esp_df.to_excel(writer, sheet_name='ESP Analysis', index=False)
        ts_df.to_excel(writer, sheet_name='Time Series', index=False)
        failed_df.to_excel(writer, sheet_name='Failed Reasons', index=False)
    buffer.seek(0)
    st.download_button("Download Excel", buffer, "aggregated_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key='excel_dl')
