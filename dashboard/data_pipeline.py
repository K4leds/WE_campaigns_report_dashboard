"""Cached data-loading, filtering, and attribution pipeline for the dashboard."""
import streamlit as st
import pandas as pd

from data_processing import clean_data
from attribution import apply_attribution, apply_dimension_filters
from insights_engine import generate_executive_summary
from dashboard.health import calculate_journey_health_score
from dashboard.lifecycle import analyze_journey_lifecycle
from dashboard.comparisons_logic import calculate_comparison_periods


@st.cache_data
def load_and_clean_data(uploaded_file, channel_costs=None):
    df = pd.read_csv(uploaded_file)
    df = clean_data(df, channel_costs=channel_costs)
    return df


@st.cache_data
def apply_filters_and_attribution(df, revenue_attribution, conversion_attribution, date_range, channels, campaign_types, campaigns, segments, journeys, conversion_events=None):
    # copy() because apply_attribution writes columns in place; df is the shared cached object
    df = apply_attribution(df.copy(), revenue_attribution, conversion_attribution)
    filtered_df = df
    if date_range and len(date_range) == 2:
        start_dt = pd.to_datetime(date_range[0])
        end_dt = pd.to_datetime(date_range[1])
        # Filter by the Day column (reporting date) to include all attribution window days
        if 'Day' in filtered_df.columns:
            filtered_df = filtered_df[(filtered_df['Day'] >= start_dt) & (filtered_df['Day'] <= end_dt)]
        elif 'Reporting Period Start Date' in filtered_df.columns:
            filtered_df = filtered_df[(filtered_df['Reporting Period Start Date'] >= start_dt) &
                                      (filtered_df['Reporting Period End Date'] <= end_dt)]
    filtered_df = apply_dimension_filters(filtered_df, channels, campaign_types, campaigns, segments, journeys, conversion_events)
    return filtered_df


@st.cache_data
def cached_executive_summary(filtered_df):
    return generate_executive_summary(filtered_df)


@st.cache_data
def cached_journey_health_scores(filtered_df):
    journey_health_data = []
    unique_journeys = filtered_df['Journey Name'].dropna().unique()
    for journey in unique_journeys:
        if str(journey) != 'nan' and journey:
            journey_data = filtered_df[filtered_df['Journey Name'] == journey]
            health_info = calculate_journey_health_score(journey_data, filtered_df)
            journey_health_data.append({
                'Journey Name': journey,
                'Status': journey_data['Status'].iloc[-1] if 'Status' in journey_data.columns else None,
                'Health Score': health_info['health_score'],
                'Tier': health_info['tier'],
                'Revenue (SAR)': journey_data['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in journey_data.columns else journey_data['Revenue (SAR)'].sum(),
                'Impression-Through Revenue (SAR)': journey_data['Impression-Through Revenue (SAR)'].sum() if 'Impression-Through Revenue (SAR)' in journey_data.columns else 0,
                'Click-Through Revenue (SAR)': journey_data['Click-Through Revenue (SAR)'].sum() if 'Click-Through Revenue (SAR)' in journey_data.columns else 0,
                'Total Conversions': journey_data['Selected Conversions'].sum() if 'Selected Conversions' in journey_data.columns else journey_data['Unique Conversions'].sum(),
                'Delivery Score': health_info['component_scores'].get('delivery', 0),
                'Engagement Score': health_info['component_scores'].get('engagement', 0),
                'Conversion Score': health_info['component_scores'].get('conversion', 0),
                'Revenue Score': health_info['component_scores'].get('revenue', 0)
            })
    return journey_health_data


@st.cache_data
def cached_journey_lifecycle(filtered_df):
    return analyze_journey_lifecycle(filtered_df)


@st.cache_data
def cached_comparison(df, revenue_attribution, conversion_attribution, channels, campaign_types, campaigns, segments, journeys, conversion_events, date_range, comparison_mode, comparison_date_range):
    # copy() because apply_attribution writes columns in place; df is the shared cached object
    base = apply_attribution(df.copy(), revenue_attribution, conversion_attribution)
    base = apply_dimension_filters(base, list(channels), list(campaign_types), list(campaigns), list(segments), list(journeys), list(conversion_events))
    return calculate_comparison_periods(base, date_range, comparison_mode, comparison_date_range)
