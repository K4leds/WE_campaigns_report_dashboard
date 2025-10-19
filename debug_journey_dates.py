"""
Debug script to check if journey data has gaps
"""
import pandas as pd
import streamlit as st

# Add this to your app temporarily to debug
def debug_journey_dates(journey_data, journey_name):
    """Check for date gaps in journey data"""
    
    st.write(f"### Debug Info for: {journey_name}")
    
    journey_data_sorted = journey_data.sort_values('date').reset_index(drop=True)
    
    st.write(f"**Total rows in data:** {len(journey_data_sorted)}")
    st.write(f"**Date range:** {journey_data_sorted['date'].min().date()} to {journey_data_sorted['date'].max().date()}")
    
    # Calculate expected days vs actual rows
    expected_days = (journey_data_sorted['date'].max() - journey_data_sorted['date'].min()).days + 1
    actual_rows = len(journey_data_sorted)
    
    st.write(f"**Expected calendar days:** {expected_days}")
    st.write(f"**Actual data rows:** {actual_rows}")
    st.write(f"**Missing days:** {expected_days - actual_rows}")
    
    if expected_days != actual_rows:
        st.warning(f"⚠️ Data has gaps! {expected_days - actual_rows} days are missing from the data.")
        st.write("This means the journey doesn't have daily reporting - some dates are missing.")
    
    # Show date differences
    journey_data_sorted['date_diff'] = journey_data_sorted['date'].diff().dt.days
    gaps = journey_data_sorted[journey_data_sorted['date_diff'] > 1]
    
    if len(gaps) > 0:
        st.write(f"\n**Found {len(gaps)} date gaps:**")
        st.dataframe(gaps[['date', 'date_diff', 'Delivered']].head(20))
    
    # Show delivery pattern
    st.write("\n**Delivery Pattern (last 20 rows):**")
    st.dataframe(journey_data_sorted[['date', 'Delivered']].tail(20))

# Usage: Add this in your stopped journey analysis
# debug_journey_dates(journey_data, journey)
