import streamlit as st

st.warning(
    "🤖 **AI Insights has moved.** "
    "This content is now available in the **AI Insights & Recommendations** page "
    "under the 🤖 AI & Forecasting section."
)
if st.button("Go to AI Insights & Recommendations"):
    st.switch_page("pages/01_automated_insights.py")
