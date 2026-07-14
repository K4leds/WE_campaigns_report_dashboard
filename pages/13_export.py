import streamlit as st
import pandas as pd
from io import BytesIO

from dashboard.state import get_ctx
from analysis import top_campaigns, get_top_journeys, top_segments, channel_analysis, esp_analysis, time_series_analysis, failed_reasons_analysis
from utils import format_metric
import slides_deck_content

ctx = get_ctx()
filtered_df = ctx.filtered_df

st.header("Export")

st.subheader("Client Review Deck (PowerPoint)")
client_name = st.text_input("Client / brand name", value="", key="deck_client")


def _deck_signature(df, name, comparison_result):
    # Cheap fingerprint of the inputs so a previously-generated deck isn't offered
    # for download after the user changes filters, the client name, or the
    # comparison-mode selection (any of which would otherwise silently serve a
    # deck built from stale data).
    if df is None or df.empty:
        return None
    comp_sig = None
    if comparison_result:
        comp_sig = (comparison_result.get("comparison_label"), comparison_result.get("current_label"))
    return (df.shape, float(df.select_dtypes("number").fillna(0).to_numpy().sum()), name, comp_sig)


cur_sig = _deck_signature(filtered_df, client_name, ctx.comparison_result)
if st.button("Generate Client Review Deck"):
    if filtered_df is None or filtered_df.empty:
        st.warning("No data for the current filters — adjust filters and try again.")
    else:
        with st.spinner("Building deck (rendering charts)…"):
            try:
                st.session_state["deck_bytes"] = slides_deck_content.build_deck(
                    filtered_df, client_name=client_name,
                    comparison_result=ctx.comparison_result,
                    conversion_attribution=ctx.conversion_attribution,
                )
                st.session_state["deck_sig"] = cur_sig
            except Exception as e:
                st.error(f"Could not build the deck: {e}")
if st.session_state.get("deck_bytes") and st.session_state.get("deck_sig") == cur_sig:
    safe = (client_name or "WebEngage").replace(" ", "_")
    st.download_button(
        "Download Deck (.pptx)", st.session_state["deck_bytes"],
        file_name=f"WebEngage_Review_{safe}.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        key="deck_dl")

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
