import streamlit as st

st.warning(
    "❌ **Failed Reasons has moved.** "
    "This content is now available in the **Channels** page "
    "under the 📈 Analysis section."
)
if st.button("Go to Channels"):
    st.switch_page("pages/07_channels.py")
