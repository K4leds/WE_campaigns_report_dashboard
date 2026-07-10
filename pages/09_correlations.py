import streamlit as st

st.warning(
    "🔗 **Correlations has moved.** "
    "This content is now available in the **Time Series & Correlations** page "
    "under the 📈 Analysis section."
)
if st.button("Go to Time Series & Correlations"):
    st.switch_page("pages/08_time_series.py")
