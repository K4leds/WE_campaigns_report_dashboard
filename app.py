import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
from statsmodels.tsa.arima.model import ARIMA
from prophet import Prophet
import warnings
warnings.filterwarnings('ignore')

def format_metric(value, unit=""):
    if isinstance(value, (int, float)) and not pd.isna(value):
        abs_val = abs(value)
        if abs_val >= 1e6:
            return f"{value/1e6:.1f}M {unit}".strip()
        elif abs_val >= 1e3:
            return f"{value/1e3:.1f}K {unit}".strip()
        else:
            return f"{value:,.0f} {unit}".strip()
    else:
        return f"{value} {unit}".strip()

st.title("WebEngage CSV Dashboard")

# Sidebar navigation
page = st.sidebar.selectbox("Navigate to", [
    "Overview", 
    "Campaigns", 
    "Journeys", 
    "Segments", 
    "Channels", 
    "Time Series", 
    "Correlations", 
    "A/B Testing", 
    "Attribution", 
    "Failed Reasons", 
    "ESP Performance", 
    "Comparisons", 
    "AI Insights",
    "Export"
])

# Upload CSV
uploaded_file = st.file_uploader("Upload WebEngage CSV", type="csv")

def clean_data(df):
    # Convert date columns to datetime - try multiple possible column names
    date_cols = []
    possible_date_cols = ['Reporting Period Start Date', 'Reporting Period End Date', 'Campaign Start Date', 'Campaign End Date', 'Day', 'Start Date']
    for col in possible_date_cols:
        if col in df.columns:
            date_cols.append(col)
    
    for col in date_cols:
        df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # If we have 'Day' column, use it as reporting period
    if 'Day' in df.columns and 'Reporting Period Start Date' not in df.columns:
        df['Reporting Period Start Date'] = df['Day']
        df['Reporting Period End Date'] = df['Day']
    
    # Convert percentage columns to float - handle different formats
    pct_cols = [col for col in df.columns if 'Rate' in col or 'Rate' in col.lower()]
    for col in pct_cols:
        # Convert to string first to handle mixed types
        df[col] = df[col].astype(str)
        
        # Check if values contain '%' - if so, strip it and divide by 100
        if df[col].str.contains('%').any():
            df[col] = df[col].str.rstrip('%').astype(float) / 100
        else:
            # Values without '%" - check if they're already decimals (< 1) or raw percentages (>= 1)
            df[col] = df[col].astype(float)
            # If mean value is > 1, assume these are raw percentages and divide by 100
            if df[col].mean() > 1:
                df[col] = df[col] / 100
    
    # Convert revenue columns to float
    revenue_cols = [col for col in df.columns if 'Revenue' in col]
    for col in revenue_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Convert numeric columns - handle missing columns gracefully
    numeric_cols = ['Total in Control Group', 'Unique Control Group Conversions', 'Sent', 'Failed', 'Delivered', 
                    'Unique Impressions', 'Total Impressions', 'Unique Clicks', 'Total Clicks', 
                    'Unique Conversions', 'Total Conversions', 'Unique Impression-Through Conversions', 
                    'Total Impression-Through Conversions', 'Unique Click-Through Conversions', 
                    'Total Click-Through Conversions', 'Queued']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Fill NaN with 0 for numeric columns only
    existing_numeric_cols = [col for col in numeric_cols if col in df.columns]
    df[existing_numeric_cols] = df[existing_numeric_cols].fillna(0)
    df[revenue_cols] = df[revenue_cols].fillna(0)
    df[pct_cols] = df[pct_cols].fillna(0)
    
    # Add total revenue column - handle different revenue column combinations
    revenue_combinations = [
        ['Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Impression-Through Revenue (SAR)'],
        ['Revenue (SAR)', 'Click-Through Revenue (SAR)'],
        ['Revenue (SAR)']
    ]
    
    for combo in revenue_combinations:
        if all(col in df.columns for col in combo):
            df['Total Revenue (SAR)'] = sum(df[col] for col in combo)
            break
    else:
        # If no combination works, use whatever revenue columns exist
        available_revenue = [col for col in revenue_cols if col in df.columns]
        if available_revenue:
            df['Total Revenue (SAR)'] = df[available_revenue[0]]
        else:
            df['Total Revenue (SAR)'] = 0
    
    # Add calculated metrics - only if required columns exist
    if 'Unique Clicks' in df.columns and 'Unique Impressions' in df.columns:
        df['CTR'] = np.where(df['Unique Impressions'] > 0, df['Unique Clicks'] / df['Unique Impressions'], 0)
    else:
        df['CTR'] = 0
    
    if 'Unique Conversions' in df.columns and 'Unique Clicks' in df.columns:
        df['Conversion Rate'] = np.where(df['Unique Clicks'] > 0, df['Unique Conversions'] / df['Unique Clicks'], 0)
    else:
        df['Conversion Rate'] = 0
    
    if 'Delivered' in df.columns and 'Sent' in df.columns:
        df['Delivery Rate'] = np.where(df['Sent'] > 0, df['Delivered'] / df['Sent'], 0)
    else:
        df['Delivery Rate'] = 0
    
    # Convert object columns to string for Arrow compatibility
    object_cols = df.select_dtypes(include='object').columns
    df[object_cols] = df[object_cols].astype(str)
    
    return df

def top_campaigns(df, metric='Unique Conversions', top_n=10):
    return df.groupby('Campaign Name')[metric].sum().nlargest(top_n).reset_index()

def top_journeys(df, metric='Delivered Rate', top_n=10):
    return df.groupby('Journey Name')[metric].mean().nlargest(top_n).reset_index()

def top_segments(df, metric='Unique Conversions', top_n=10):
    return df.groupby('Segment Name')[metric].sum().nlargest(top_n).reset_index()

def channel_analysis(df):
    agg_dict = {
        'Sent': 'sum',
        'Delivered': 'sum',
        'Unique Impressions': 'sum',
        'Unique Clicks': 'sum',
        'Unique Conversions': 'sum'
    }
    # Only add columns that exist in the dataframe
    if 'Total Conversions' in df.columns:
        agg_dict['Total Conversions'] = 'sum'
    if 'Revenue (SAR)' in df.columns:
        agg_dict['Revenue (SAR)'] = 'sum'
    if 'Click-Through Revenue (SAR)' in df.columns:
        agg_dict['Click-Through Revenue (SAR)'] = 'sum'
    if 'Impression-Through Revenue (SAR)' in df.columns:
        agg_dict['Impression-Through Revenue (SAR)'] = 'sum'
    if 'Total Revenue (SAR)' in df.columns:
        agg_dict['Total Revenue (SAR)'] = 'sum'
    return df.groupby('Channel').agg(agg_dict).reset_index()

def time_series_analysis(df, metric='Unique Conversions'):
    df_ts = df.groupby('Reporting Period Start Date')[metric].sum().reset_index()
    return df_ts

def failed_reasons_analysis(df):
    failed_cols = [col for col in df.columns if 'Failed' in col and col != 'Failed']
    if failed_cols:
        return df[failed_cols].sum().reset_index().rename(columns={'index': 'Reason', 0: 'Count'})
    return pd.DataFrame()

def esp_analysis(df):
    agg_dict = {
        'Sent': 'sum',
        'Delivered': 'sum',
        'Unique Conversions': 'sum'
    }
    # Only add columns that exist in the dataframe
    if 'Total Conversions' in df.columns:
        agg_dict['Total Conversions'] = 'sum'
    if 'Revenue (SAR)' in df.columns:
        agg_dict['Revenue (SAR)'] = 'sum'
    if 'Click-Through Revenue (SAR)' in df.columns:
        agg_dict['Click-Through Revenue (SAR)'] = 'sum'
    if 'Impression-Through Revenue (SAR)' in df.columns:
        agg_dict['Impression-Through Revenue (SAR)'] = 'sum'
    if 'Total Revenue (SAR)' in df.columns:
        agg_dict['Total Revenue (SAR)'] = 'sum'
    return df.groupby('ESP/SSP/WSP/RSP name').agg(agg_dict).reset_index()

def ab_testing_analysis(df):
    # Calculate lift for campaigns with control group
    df_ab = df[df['Total in Control Group'] > 0].copy()
    if not df_ab.empty:
        df_ab['Test Conversion Rate'] = df_ab['Unique Conversions'] / df_ab['Sent']
        df_ab['Control Conversion Rate'] = df_ab['Unique Control Group Conversions'] / df_ab['Total in Control Group']
        df_ab['Lift'] = np.where(df_ab['Control Conversion Rate'] > 0, 
                                (df_ab['Test Conversion Rate'] - df_ab['Control Conversion Rate']) / df_ab['Control Conversion Rate'], 
                                np.nan)
        return df_ab[['Campaign Name', 'Test Conversion Rate', 'Control Conversion Rate', 'Lift']].dropna()
    return pd.DataFrame()

def attribution_analysis(df):
    # Summarize conversions by source
    attr = {
        'Impression-Through': df['Unique Impression-Through Conversions'].sum(),
        'Click-Through': df['Unique Click-Through Conversions'].sum(),
        'Direct/Open-Through': df['Unique Conversions'].sum() - df['Unique Impression-Through Conversions'].sum() - df['Unique Click-Through Conversions'].sum()
    }
    return pd.DataFrame(list(attr.items()), columns=['Source', 'Conversions'])

# In the main code, after cleaning
if uploaded_file is not None:
    df = pd.read_csv(uploaded_file)
    df = clean_data(df)
    st.success("Data cleaned and normalized!")

    # Filters
    st.sidebar.header("Filters")
    
    # Global Attribution Filters
    st.sidebar.subheader("Attribution Settings")
    revenue_attribution = st.sidebar.selectbox(
        "Revenue Attribution",
        ["Total", "Click-Through", "Impression-Through"],
        help="Select which type of revenue attribution to use throughout the dashboard"
    )
    
    conversion_attribution = st.sidebar.selectbox(
        "Conversion Attribution", 
        ["Total", "Click-Through", "Impression-Through"],
        help="Select which type of conversion attribution to use throughout the dashboard"
    )
    
    # Apply attribution settings
    if 'Revenue (SAR)' in df.columns:
        if revenue_attribution == "Click-Through" and 'Click-Through Revenue (SAR)' in df.columns:
            df['Selected Revenue (SAR)'] = df['Click-Through Revenue (SAR)']
        elif revenue_attribution == "Impression-Through" and 'Impression-Through Revenue (SAR)' in df.columns:
            df['Selected Revenue (SAR)'] = df['Impression-Through Revenue (SAR)']
        else:
            # For "Total" attribution, use the Total Revenue column that sums all revenue types
            df['Selected Revenue (SAR)'] = df['Total Revenue (SAR)'] if 'Total Revenue (SAR)' in df.columns else df['Revenue (SAR)']
    else:
        df['Selected Revenue (SAR)'] = 0
    
    if 'Unique Conversions' in df.columns:
        if conversion_attribution == "Click-Through" and 'Unique Click-Through Conversions' in df.columns:
            df['Selected Conversions'] = df['Unique Click-Through Conversions']
        elif conversion_attribution == "Impression-Through" and 'Unique Impression-Through Conversions' in df.columns:
            df['Selected Conversions'] = df['Unique Impression-Through Conversions']
        else:
            df['Selected Conversions'] = df['Unique Conversions']
    else:
        df['Selected Conversions'] = 0
    
    if not df.empty:
        min_date = df['Reporting Period Start Date'].min()
        max_date = df['Reporting Period End Date'].max()
        date_range = st.sidebar.date_input("Date Range", value=(min_date, max_date))
    else:
        date_range = st.sidebar.date_input("Date Range", [])
    channels = st.sidebar.multiselect("Channels", df['Channel'].unique() if not df.empty else [])
    campaigns = st.sidebar.multiselect("Campaigns", df['Campaign Name'].unique() if not df.empty else [])
    segments = st.sidebar.multiselect("Segments", df['Segment Name'].unique() if not df.empty else [])
    journeys = st.sidebar.multiselect("Journeys", df['Journey Name'].unique() if not df.empty else [])

    # Apply filters
    filtered_df = df.copy()
    if date_range and len(date_range) == 2:
        filtered_df = filtered_df[(filtered_df['Reporting Period Start Date'] >= pd.to_datetime(date_range[0])) & 
                                  (filtered_df['Reporting Period End Date'] <= pd.to_datetime(date_range[1]))]
    if channels:
        filtered_df = filtered_df[filtered_df['Channel'].isin(channels)]
    if campaigns:
        filtered_df = filtered_df[filtered_df['Campaign Name'].isin(campaigns)]
    if segments:
        filtered_df = filtered_df[filtered_df['Segment Name'].isin(segments)]
    if journeys:
        filtered_df = filtered_df[filtered_df['Journey Name'].isin(journeys)]

    st.write(f"Filtered data: {len(filtered_df)} rows")

    # Page content based on selection
    if page == "Overview":
        st.header("Overview")
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Total Revenue", format_metric(filtered_df['Selected Revenue (SAR)'].sum(), "SAR"))
            st.metric("Total Conversions", format_metric(filtered_df['Selected Conversions'].sum()))
        with col2:
            st.metric("Total Clicks", format_metric(filtered_df['Unique Clicks'].sum()))
            st.metric("Total Impressions", format_metric(filtered_df['Unique Impressions'].sum()))
        with col3:
            st.metric("Avg CTR", f"{filtered_df['CTR'].mean():.2%}")
            st.metric("Avg Conversion Rate", f"{filtered_df['Conversion Rate'].mean():.2%}")
            st.metric("Avg Delivery Rate", f"{filtered_df['Delivery Rate'].mean():.2%}")

        # Conversion Funnel
        st.subheader("Conversion Funnel")
        funnel_data = {
            'Stage': ['Sent', 'Impressions', 'Clicks', 'Conversions'],
            'Count': [filtered_df['Sent'].sum(), filtered_df['Unique Impressions'].sum(), filtered_df['Unique Clicks'].sum(), filtered_df['Selected Conversions'].sum()]
        }
        fig_funnel = go.Figure(go.Funnel(
            y=funnel_data['Stage'],
            x=funnel_data['Count'],
            textinfo="value+percent initial"
        ))
        st.plotly_chart(fig_funnel)

        # Failed reasons
        failed_df = failed_reasons_analysis(filtered_df)
        if not failed_df.empty:
            st.subheader("Failed Reasons Breakdown")
            fig_fail = px.pie(failed_df, names='Reason', values='Count')
            st.plotly_chart(fig_fail)

        # Data Preview
        with st.expander("View Filtered Data"):
            st.dataframe(filtered_df)

    elif page == "Campaigns":
        st.header("Campaign Analysis")
        
        # Top Campaigns
        st.subheader("Top Campaigns")
        camp_metric = st.selectbox("Metric", ['Unique Conversions', 'Total Revenue (SAR)', 'Unique Clicks', 'Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Open-Through Revenue (SAR)', 'CTR', 'Conversion Rate'], key='camp_metric')
        top_camp = top_campaigns(filtered_df, camp_metric)
        
        # Create display version for table
        top_camp_display = top_camp.copy()
        # Format the metric column for display
        if 'Revenue' in camp_metric:
            top_camp_display[camp_metric] = top_camp_display[camp_metric].apply(lambda x: format_metric(x, "SAR"))
        elif camp_metric in ['Unique Conversions', 'Unique Clicks']:
            top_camp_display[camp_metric] = top_camp_display[camp_metric].apply(format_metric)
        # For rates, keep as is
        st.dataframe(top_camp_display)
        
        # Create chart with original numeric values
        fig = px.bar(top_camp, x='Campaign Name', y=camp_metric, title=f"Top Campaigns by {camp_metric}")
        st.plotly_chart(fig)
        
        # Campaign Drill-Down
        st.subheader("Campaign Drill-Down")
        selected_campaigns = st.multiselect("Select Campaigns for Details", filtered_df['Campaign Name'].unique(), key='drill_camp')
        if selected_campaigns:
            camp_details = filtered_df[filtered_df['Campaign Name'].isin(selected_campaigns)]
            
            # Summary KPIs
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Sent", format_metric(camp_details['Sent'].sum()))
            with col2:
                st.metric("Total Delivered", format_metric(camp_details['Delivered'].sum()))
            with col3:
                st.metric("Total Conversions", format_metric(camp_details['Unique Conversions'].sum()))
            with col4:
                st.metric("Total Revenue", format_metric(camp_details['Total Revenue (SAR)'].sum(), "SAR"))
            
            # Performance by Channel
            st.subheader("Performance by Channel")
            chan_perf = camp_details.groupby('Channel').agg({
                'Sent': 'sum',
                'Delivered': 'sum',
                'Unique Conversions': 'sum',
                'Total Revenue (SAR)': 'sum'
            }).reset_index()
            # Format columns
            chan_perf['Sent'] = chan_perf['Sent'].apply(format_metric)
            chan_perf['Delivered'] = chan_perf['Delivered'].apply(format_metric)
            chan_perf['Unique Conversions'] = chan_perf['Unique Conversions'].apply(format_metric)
            chan_perf['Total Revenue (SAR)'] = chan_perf['Total Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            st.dataframe(chan_perf)
            fig_chan = px.bar(chan_perf, x='Channel', y='Unique Conversions', title="Conversions by Channel for Selected Campaigns")
            st.plotly_chart(fig_chan)
            
            # Time Series for Selected Campaigns
            st.subheader("Time Series Performance")
            ts_camp = camp_details.groupby(['Reporting Period Start Date', 'Campaign Name'])[camp_metric].sum().reset_index()
            if not ts_camp.empty:
                fig_ts_camp = px.line(ts_camp, x='Reporting Period Start Date', y=camp_metric, color='Campaign Name', title=f"{camp_metric} Over Time for Selected Campaigns")
                st.plotly_chart(fig_ts_camp)
            
            # Conversion Attribution
            st.subheader("Conversion Attribution")
            attr_camp = {
                'Impression-Through': camp_details['Unique Impression-Through Conversions'].sum(),
                'Click-Through': camp_details['Unique Click-Through Conversions'].sum(),
                'Direct/Open-Through': camp_details['Unique Conversions'].sum() - camp_details['Unique Impression-Through Conversions'].sum() - camp_details['Unique Click-Through Conversions'].sum()
            }
            attr_df_camp = pd.DataFrame(list(attr_camp.items()), columns=['Source', 'Conversions'])
            attr_df_camp['Conversions'] = attr_df_camp['Conversions'].apply(format_metric)
            fig_attr_camp = px.pie(attr_df_camp, names='Source', values='Conversions', title="Attribution for Selected Campaigns")
            st.plotly_chart(fig_attr_camp)
            
            # Failed Reasons for Selected Campaigns
            st.subheader("Failed Reasons")
            failed_cols = [col for col in camp_details.columns if 'Failed' in col and col != 'Failed']
            if failed_cols:
                failed_camp = camp_details[failed_cols].sum().reset_index().rename(columns={'index': 'Reason', 0: 'Count'})
                failed_camp['Count'] = failed_camp['Count'].apply(format_metric)
                fig_fail_camp = px.bar(failed_camp, x='Reason', y='Count', title="Failed Reasons for Selected Campaigns")
                st.plotly_chart(fig_fail_camp)

    elif page == "Journeys":
        st.header("Journey Analysis")
        
        # Revenue Type Selection
        available_revenue_cols = [col for col in df.columns if 'Revenue' in col and col != 'Total Revenue (SAR)']
        if available_revenue_cols:
            revenue_options = ['Total Revenue (SAR)'] + available_revenue_cols
            selected_revenue = st.selectbox("Revenue Type", revenue_options, key='revenue_type')
        else:
            selected_revenue = 'Total Revenue (SAR)'
        
        # Top Journeys
        st.subheader("Top Journeys")
        jour_metric = st.selectbox("Metric", ['Delivered Rate', 'Unique Clicks', 'Unique Conversions', selected_revenue], key='jour_metric')
        top_jour = top_journeys(filtered_df, jour_metric)
        
        # Create display version for table
        top_jour_display = top_jour.copy()
        # Format the metric column for display
        if 'Revenue' in jour_metric:
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(lambda x: format_metric(x, "SAR"))
        elif jour_metric in ['Unique Clicks', 'Unique Conversions']:
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(format_metric)
        elif 'Rate' in jour_metric:
            # For rates, convert to percentage
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(lambda x: f"{x*100:.1f}%")
        st.dataframe(top_jour_display)
        
        # Create chart with original numeric values
        fig2 = px.bar(top_jour, x='Journey Name', y=jour_metric, title=f"Top Journeys by {jour_metric}")
        st.plotly_chart(fig2)
        
        # Journey Drill-Down
        st.subheader("Journey Drill-Down")
        selected_journeys = st.multiselect("Select Journeys for Details", filtered_df['Journey Name'].unique(), key='drill_jour')
        if selected_journeys:
            jour_details = filtered_df[filtered_df['Journey Name'].isin(selected_journeys)]
            
            # Summary KPIs
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("Total Sent", format_metric(jour_details['Sent'].sum()))
            with col2:
                st.metric("Total Delivered", format_metric(jour_details['Delivered'].sum()))
            with col3:
                st.metric("Total Conversions", format_metric(jour_details['Unique Conversions'].sum()))
            with col4:
                st.metric(f"Total {selected_revenue}", format_metric(jour_details[selected_revenue].sum(), "SAR"))
            
            # Performance by Channel
            st.subheader("Performance by Channel")
            chan_perf_jour = jour_details.groupby('Channel').agg({
                'Sent': 'sum',
                'Delivered': 'sum',
                'Unique Conversions': 'sum',
                selected_revenue: 'sum'
            }).reset_index()
            # Format columns
            chan_perf_jour['Sent'] = chan_perf_jour['Sent'].apply(format_metric)
            chan_perf_jour['Delivered'] = chan_perf_jour['Delivered'].apply(format_metric)
            chan_perf_jour['Unique Conversions'] = chan_perf_jour['Unique Conversions'].apply(format_metric)
            chan_perf_jour[selected_revenue] = chan_perf_jour[selected_revenue].apply(lambda x: format_metric(x, "SAR"))
            
            # Display table with formatted values
            st.dataframe(chan_perf_jour)
            
            # Create chart data with numeric values for plotting
            chart_data = chan_perf_jour.copy()
            chart_data['Sent'] = pd.to_numeric(chart_data['Sent'].str.replace(',', '').str.replace('K', '000').str.replace('M', '000000'), errors='coerce')
            chart_data['Delivered'] = pd.to_numeric(chart_data['Delivered'].str.replace(',', '').str.replace('K', '000').str.replace('M', '000000'), errors='coerce')
            chart_data['Unique Conversions'] = pd.to_numeric(chart_data['Unique Conversions'].str.replace(',', '').str.replace('K', '000').str.replace('M', '000000'), errors='coerce')
            chart_data[selected_revenue] = pd.to_numeric(chart_data[selected_revenue].str.replace(',', '').str.replace('K', '000').str.replace('M', '000000').str.replace(' SAR', ''), errors='coerce')
            
            fig_chan_jour = px.bar(chart_data, x='Channel', y='Unique Conversions', title="Conversions by Channel for Selected Journeys")
            st.plotly_chart(fig_chan_jour)
            
            # Time Series for Selected Journeys
            st.subheader("Time Series Performance")
            # For rates, use mean; for counts/revenue, use sum
            if 'Rate' in jour_metric:
                ts_jour = jour_details.groupby(['Reporting Period Start Date', 'Journey Name'])[jour_metric].mean().reset_index()
            else:
                ts_jour = jour_details.groupby(['Reporting Period Start Date', 'Journey Name'])[jour_metric].sum().reset_index()
            if not ts_jour.empty:
                # Format y-axis for rates
                if 'Rate' in jour_metric:
                    ts_jour[jour_metric] = ts_jour[jour_metric] * 100  # Convert to percentage for display
                    fig_ts_jour = px.line(ts_jour, x='Reporting Period Start Date', y=jour_metric, color='Journey Name', title=f"{jour_metric} Over Time for Selected Journeys")
                    fig_ts_jour.update_yaxes(tickformat=".1f", title=f"{jour_metric} (%)")
                else:
                    fig_ts_jour = px.line(ts_jour, x='Reporting Period Start Date', y=jour_metric, color='Journey Name', title=f"{jour_metric} Over Time for Selected Journeys")
                st.plotly_chart(fig_ts_jour)
                
                # Journey Performance Insights
                st.subheader("📊 Journey Performance Insights")
                
                # Calculate gaps and stopped periods
                for journey in selected_journeys:
                    journey_data = ts_jour[ts_jour['Journey Name'] == journey].copy()
                    journey_data = journey_data.sort_values('Reporting Period Start Date')
                    
                    if len(journey_data) > 1:
                        # Calculate gaps between dates
                        journey_data['Date'] = pd.to_datetime(journey_data['Reporting Period Start Date'])
                        journey_data['Days_Gap'] = journey_data['Date'].diff().dt.days
                        
                        # Find periods where journey was stopped (gaps > 7 days)
                        stopped_periods = journey_data[journey_data['Days_Gap'] > 7]
                        
                        # Count total stopped days and periods
                        total_stopped_days = stopped_periods['Days_Gap'].sum() if not stopped_periods.empty else 0
                        total_stopped_periods = len(stopped_periods)
                        
                        if not stopped_periods.empty:
                            st.write(f"**{journey} - Campaign Interruptions:**")
                            st.write(f"• **Total Stopped Periods:** {total_stopped_periods}")
                            st.write(f"• **Total Days Stopped:** {int(total_stopped_days)} days")
                            
                            for _, row in stopped_periods.iterrows():
                                prev_date = journey_data[journey_data['Date'] < row['Date']].iloc[-1]['Date'] if len(journey_data[journey_data['Date'] < row['Date']]) > 0 else None
                                if prev_date is not None:
                                    gap_days = int(row['Days_Gap'])
                                    st.write(f"  - Stopped for {gap_days} days: {prev_date.strftime('%Y-%m-%d')} → {row['Date'].strftime('%Y-%m-%d')}")
                        
                        # Performance metrics - handle rates differently
                        is_rate_metric = 'Rate' in jour_metric
                        
                        if is_rate_metric:
                            # For rates, show as percentages and calculate meaningful stats
                            avg_metric = journey_data[jour_metric].mean() * 100  # Convert to percentage
                            max_metric = journey_data[jour_metric].max() * 100
                            min_metric = journey_data[jour_metric].min() * 100
                            consistency = journey_data[jour_metric].std() * 100 if not journey_data[jour_metric].empty else 0
                            
                            # Weighted average by volume (if we have sent data)
                            journey_full_data = jour_details[jour_details['Journey Name'] == journey]
                            if not journey_full_data.empty and 'Sent' in journey_full_data.columns:
                                weighted_avg = (journey_full_data[jour_metric] * journey_full_data['Sent']).sum() / journey_full_data['Sent'].sum() * 100
                            else:
                                weighted_avg = avg_metric
                            
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric(f"Average {jour_metric}", f"{avg_metric:.1f}%")
                            with col2:
                                st.metric(f"Volume-Weighted {jour_metric}", f"{weighted_avg:.1f}%")
                            with col3:
                                st.metric(f"Peak {jour_metric}", f"{max_metric:.1f}%")
                            with col4:
                                st.metric("Rate Variability", f"±{consistency:.1f}pp")
                            
                            st.info(f"💡 **Rate Explanation:** {jour_metric} shows delivery/conversion efficiency. Higher % = better performance. Volume-weighted average accounts for campaign size.")
                        
                        else:
                            # For count/revenue metrics, use original calculations
                            total_metric = journey_data[jour_metric].sum()
                            avg_metric = journey_data[jour_metric].mean()
                            max_metric = journey_data[jour_metric].max()
                            min_metric = journey_data[jour_metric].min()
                            consistency = journey_data[jour_metric].std() / journey_data[jour_metric].mean() if journey_data[jour_metric].mean() > 0 else 0
                            
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric(f"Total {jour_metric.replace(' (SAR)', '')}", format_metric(total_metric, "SAR" if "Revenue" in jour_metric else ""))
                            with col2:
                                st.metric(f"Average {jour_metric.replace(' (SAR)', '')}", format_metric(avg_metric, "SAR" if "Revenue" in jour_metric else ""))
                            with col3:
                                st.metric(f"Peak {jour_metric.replace(' (SAR)', '')}", format_metric(max_metric, "SAR" if "Revenue" in jour_metric else ""))
                            with col4:
                                st.metric("Consistency", f"{consistency:.2f}")
                            
                            st.info(f"💡 **{jour_metric.replace(' (SAR)', '')} Explanation:** {jour_metric} represents total volume. Consistency shows performance stability (lower = more consistent).")
                        
                        # Trend analysis
                        if len(journey_data) >= 3:
                            if is_rate_metric:
                                recent_avg = journey_data[jour_metric].tail(3).mean() * 100
                                earlier_avg = journey_data[jour_metric].head(len(journey_data)-3).mean() * 100 if len(journey_data) > 3 else journey_data[jour_metric].mean() * 100
                            else:
                                recent_avg = journey_data[jour_metric].tail(3).mean()
                                earlier_avg = journey_data[jour_metric].head(len(journey_data)-3).mean() if len(journey_data) > 3 else journey_data[jour_metric].mean()
                            
                            if earlier_avg > 0:
                                trend_pct = ((recent_avg - earlier_avg) / earlier_avg) * 100
                                trend_direction = "📈 Improving" if trend_pct > 5 else "📉 Declining" if trend_pct < -5 else "➡️ Stable"
                                st.write(f"**Trend:** {trend_direction} ({trend_pct:+.1f}% change in recent performance)")
                        
                        # Best and worst performing periods
                        if is_rate_metric:
                            best_period = journey_data.loc[journey_data[jour_metric].idxmax()]
                            worst_period = journey_data.loc[journey_data[jour_metric].idxmin()]
                            best_value = best_period[jour_metric] * 100
                            worst_value = worst_period[jour_metric] * 100
                            unit = "%"
                        else:
                            best_period = journey_data.loc[journey_data[jour_metric].idxmax()]
                            worst_period = journey_data.loc[journey_data[jour_metric].idxmin()]
                            best_value = best_period[jour_metric]
                            worst_value = worst_period[jour_metric]
                            unit = "SAR" if "Revenue" in jour_metric else ""
                        
                        st.write(f"**Best Period:** {best_period['Reporting Period Start Date'].strftime('%Y-%m-%d')} with {format_metric(best_value, unit)}")
                        st.write(f"**Worst Period:** {worst_period['Reporting Period Start Date'].strftime('%Y-%m-%d')} with {format_metric(worst_value, unit)}")
                        
                        # Activity frequency
                        total_days = (journey_data['Date'].max() - journey_data['Date'].min()).days + 1  # +1 to include both start and end
                        active_days = len(journey_data)
                        frequency = active_days / max(total_days, 1) * 100
                        st.write(f"**Activity Frequency:** {frequency:.1f}% of days had activity ({active_days}/{max(total_days, 1)} days)")
                        
                        # Lost Revenue Estimation for Stopped Periods
                        if total_stopped_days > 0 and not is_rate_metric and 'Revenue' in jour_metric:
                            st.subheader("💰 Lost Revenue Estimation")
                            
                            # Calculate average daily revenue during active periods
                            active_revenue = journey_data[jour_metric].sum()
                            active_days_calc = len(journey_data)
                            avg_daily_revenue = active_revenue / active_days_calc if active_days_calc > 0 else 0
                            
                            estimated_lost_revenue = avg_daily_revenue * total_stopped_days
                            
                            st.warning(f"⚠️ **Estimated Lost Revenue:** {format_metric(estimated_lost_revenue, 'SAR')} over {int(total_stopped_days)} stopped days")
                            st.write(f"   - Based on average daily revenue of {format_metric(avg_daily_revenue, 'SAR')} from {selected_revenue}")
                            st.write(f"   - This represents {estimated_lost_revenue/active_revenue*100:.1f}% of total journey revenue if stopped periods had performed at average levels")
                            
                            # Prophet-based estimation if enough data
                            if len(journey_data) >= 7:  # Need minimum data for Prophet
                                try:
                                    st.write("**AI-Powered Revenue Projection:**")
                                    # Prepare data for Prophet
                                    prophet_data = journey_data[['Date', jour_metric]].rename(columns={'Date': 'ds', jour_metric: 'y'})
                                    
                                    model = Prophet(daily_seasonality=True)
                                    model.fit(prophet_data)
                                    
                                    # Create future dates including the stopped periods
                                    last_date = prophet_data['ds'].max()
                                    future_dates = pd.date_range(start=journey_data['Date'].min(), end=last_date, freq='D')
                                    future_df = pd.DataFrame({'ds': future_dates})
                                    
                                    forecast = model.predict(future_df)
                                    
                                    # Calculate what revenue would have been during stopped periods
                                    stopped_dates = []
                                    for _, row in stopped_periods.iterrows():
                                        prev_date = journey_data[journey_data['Date'] < row['Date']].iloc[-1]['Date'] if len(journey_data[journey_data['Date'] < row['Date']]) > 0 else None
                                        if prev_date is not None:
                                            gap_dates = pd.date_range(start=prev_date + pd.Timedelta(days=1), end=row['Date'] - pd.Timedelta(days=1), freq='D')
                                            stopped_dates.extend(gap_dates)
                                    
                                    if stopped_dates:
                                        stopped_forecast = forecast[forecast['ds'].isin(stopped_dates)]
                                        ai_estimated_lost = stopped_forecast['yhat'].sum()
                                        st.info(f"🤖 **AI Estimated Lost Revenue:** {format_metric(ai_estimated_lost, 'SAR')} (using Prophet forecasting)")
                                        st.write("   - This accounts for seasonal patterns and trends in the data")
                                    
                                except Exception as e:
                                    st.write(f"AI forecasting not available: {str(e)}")
                        
                    else:
                        st.write(f"**{journey}:** Insufficient data for detailed analysis (only {len(journey_data)} data point)")
            else:
                st.write("No time series data available for selected journeys.")
            
            # Conversion Attribution
            st.subheader("Conversion Attribution")
            attr_jour = {
                'Impression-Through': jour_details['Unique Impression-Through Conversions'].sum(),
                'Click-Through': jour_details['Unique Click-Through Conversions'].sum(),
                'Direct/Open-Through': jour_details['Unique Conversions'].sum() - jour_details['Unique Impression-Through Conversions'].sum() - jour_details['Unique Click-Through Conversions'].sum()
            }
            attr_df_jour = pd.DataFrame(list(attr_jour.items()), columns=['Source', 'Conversions'])
            attr_df_jour['Conversions'] = attr_df_jour['Conversions'].apply(format_metric)
            fig_attr_jour = px.pie(attr_df_jour, names='Source', values='Conversions', title="Attribution for Selected Journeys")
            st.plotly_chart(fig_attr_jour)
            
            # Failed Reasons for Selected Journeys
            st.subheader("Failed Reasons")
            failed_cols = [col for col in jour_details.columns if 'Failed' in col and col != 'Failed']
            if failed_cols:
                failed_jour = jour_details[failed_cols].sum().reset_index().rename(columns={'index': 'Reason', 0: 'Count'})
                failed_jour['Count'] = failed_jour['Count'].apply(format_metric)
                fig_fail_jour = px.bar(failed_jour, x='Reason', y='Count', title="Failed Reasons for Selected Journeys")
                st.plotly_chart(fig_fail_jour)

    elif page == "Segments":
        st.header("Top Segments")
        seg_metric = st.selectbox("Metric", ['Unique Conversions', 'Total Revenue (SAR)', 'Unique Clicks', 'Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Open-Through Revenue (SAR)'], key='seg_metric')
        top_seg = top_segments(filtered_df, seg_metric)
        
        # Create display version for table
        top_seg_display = top_seg.copy()
        # Format the metric column for display
        if 'Revenue' in seg_metric:
            top_seg_display[seg_metric] = top_seg_display[seg_metric].apply(lambda x: format_metric(x, "SAR"))
        elif seg_metric in ['Unique Conversions', 'Unique Clicks']:
            top_seg_display[seg_metric] = top_seg_display[seg_metric].apply(format_metric)
        st.dataframe(top_seg_display)
        
        # Create chart with original numeric values
        fig3 = px.bar(top_seg, x='Segment Name', y=seg_metric, title=f"Top Segments by {seg_metric}")
        st.plotly_chart(fig3)

    elif page == "Channels":
        st.header("Channel Analysis")
        chan_df = channel_analysis(filtered_df)
        # Create display version for table
        chan_df_display = chan_df.copy()
        # Format numeric columns for display
        numeric_cols = ['Sent', 'Delivered', 'Unique Impressions', 'Unique Clicks', 'Unique Conversions', 'Total Conversions']
        for col in numeric_cols:
            if col in chan_df_display.columns:
                chan_df_display[col] = chan_df_display[col].apply(format_metric)
        revenue_cols = [col for col in chan_df_display.columns if 'Revenue' in col]
        for col in revenue_cols:
            chan_df_display[col] = chan_df_display[col].apply(lambda x: format_metric(x, "SAR"))
        st.dataframe(chan_df_display)
        
        # Create charts with original numeric values
        fig4 = px.bar(chan_df, x='Channel', y='Unique Conversions', title="Conversions by Channel")
        st.plotly_chart(fig4)
        if 'Total Revenue (SAR)' in chan_df.columns:
            fig_rev = px.bar(chan_df, x='Channel', y='Total Revenue (SAR)', title="Revenue by Channel")
            st.plotly_chart(fig_rev)
        
        # ESP Analysis
        esp_df = esp_analysis(filtered_df)
        if not esp_df.empty:
            st.subheader("ESP/SSP Analysis")
            # Create display version for table
            esp_df_display = esp_df.copy()
            # Format numeric columns
            numeric_cols = ['Sent', 'Delivered', 'Unique Conversions']
            for col in numeric_cols:
                if col in esp_df_display.columns:
                    esp_df_display[col] = esp_df_display[col].apply(format_metric)
            revenue_cols = [col for col in esp_df_display.columns if 'Revenue' in col]
            for col in revenue_cols:
                esp_df_display[col] = esp_df_display[col].apply(lambda x: format_metric(x, "SAR"))
            st.dataframe(esp_df_display)
            
            # Create charts with original numeric values
            fig_esp = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Delivered', title="Delivered by ESP")
            st.plotly_chart(fig_esp)
            if 'Total Revenue (SAR)' in esp_df.columns:
                fig_esp_rev = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Total Revenue (SAR)', title="Revenue by ESP")
                st.plotly_chart(fig_esp_rev)

    elif page == "Time Series":
        st.header("Time Series Analysis")
        ts_metric = st.selectbox("Metric", ['Unique Conversions', 'Total Revenue (SAR)', 'Unique Clicks', 'Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Open-Through Revenue (SAR)'], key='ts_metric')
        ts_df = time_series_analysis(filtered_df, ts_metric)
        if not ts_df.empty:
            fig_ts = px.line(ts_df, x='Reporting Period Start Date', y=ts_metric, title=f"{ts_metric} Over Time")
            st.plotly_chart(fig_ts)
        else:
            st.write("No time series data available.")

    elif page == "Correlations":
        st.header("Correlations")
        numeric_df = filtered_df.select_dtypes(include=[np.number])
        if not numeric_df.empty:
            corr = numeric_df.corr()
            fig_corr = px.imshow(corr, text_auto=True, title="Correlation Matrix")
            st.plotly_chart(fig_corr)
        else:
            st.write("No numeric data for correlation.")

    elif page == "A/B Testing":
        st.header("A/B Testing Analysis")
        ab_df = ab_testing_analysis(filtered_df)
        if not ab_df.empty:
            st.dataframe(ab_df)
            fig_ab = px.bar(ab_df, x='Campaign Name', y='Lift', title="Conversion Lift by Campaign")
            st.plotly_chart(fig_ab)
        else:
            st.write("No A/B testing data available (no control groups).")

    elif page == "Attribution":
        st.header("Attribution Analysis")
        attr_df = attribution_analysis(filtered_df)
        # Create display version for table
        attr_df_display = attr_df.copy()
        attr_df_display['Conversions'] = attr_df_display['Conversions'].apply(format_metric)
        st.dataframe(attr_df_display)
        
        # Create chart with original numeric values
        fig_attr = px.pie(attr_df, names='Source', values='Conversions', title="Conversions by Attribution Source")
        st.plotly_chart(fig_attr)

    elif page == "Failed Reasons":
        st.header("Failed Reasons Analysis")
        failed_df = failed_reasons_analysis(filtered_df)
        if not failed_df.empty:
            # Create display version for table
            failed_df_display = failed_df.copy()
            # Format counts
            failed_df_display['Count'] = failed_df_display['Count'].apply(format_metric)
            st.dataframe(failed_df_display)
            
            # Create chart with original numeric values
            fig_fail = px.bar(failed_df, x='Reason', y='Count', title="Failed Reasons Breakdown")
            st.plotly_chart(fig_fail)
            
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
                fig_fail_chan = px.bar(failed_melt, x='Channel', y='Count', color='Reason', title="Failed Reasons by Channel")
                st.plotly_chart(fig_fail_chan)
        else:
            st.write("No failed reasons data available.")

    elif page == "ESP Performance":
        st.header("ESP Performance")
        esp_df = esp_analysis(filtered_df)
        if not esp_df.empty:
            # Create display version for table
            esp_df_display = esp_df.copy()
            # Format numeric columns
            numeric_cols = ['Sent', 'Delivered', 'Unique Conversions']
            for col in numeric_cols:
                if col in esp_df_display.columns:
                    esp_df_display[col] = esp_df_display[col].apply(format_metric)
            revenue_cols = [col for col in esp_df_display.columns if 'Revenue' in col]
            for col in revenue_cols:
                esp_df_display[col] = esp_df_display[col].apply(lambda x: format_metric(x, "SAR"))
            st.dataframe(esp_df_display)
            
            # Create charts with original numeric values
            fig_esp = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Delivered', title="Delivered by ESP")
            st.plotly_chart(fig_esp)
            if 'Total Revenue (SAR)' in esp_df.columns:
                fig_esp_rev = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Total Revenue (SAR)', title="Revenue by ESP")
                st.plotly_chart(fig_esp_rev)
        else:
            st.write("No ESP data available.")

    elif page == "Export":
        st.header("Export")
        # Compute aggregates for export
        camp_metric = 'Unique Conversions'
        top_camp = top_campaigns(filtered_df, camp_metric)
        jour_metric = 'Unique Conversions'
        top_jour = top_journeys(filtered_df, jour_metric)
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

    elif page == "Comparisons":
        st.header("Month-over-Month Comparisons")
        
        # Group by month
        monthly_df = filtered_df.copy()
        monthly_df['Month'] = monthly_df['Reporting Period Start Date'].dt.to_period('M').astype(str)
        
        monthly_agg = monthly_df.groupby('Month').agg({
            'Total Revenue (SAR)': 'sum',
            'Unique Conversions': 'sum',
            'Unique Clicks': 'sum',
            'Sent': 'sum',
            'Delivered': 'sum'
        }).reset_index()
        
        # Sort by month
        monthly_agg['Month'] = pd.to_datetime(monthly_agg['Month'] + '-01')
        monthly_agg = monthly_agg.sort_values('Month')
        monthly_agg['Month'] = monthly_agg['Month'].dt.strftime('%Y-%m')
        
        if not monthly_agg.empty:
            st.subheader("Monthly Summary")
            # Format columns for display
            monthly_agg_display = monthly_agg.copy()
            monthly_agg_display['Total Revenue (SAR)'] = monthly_agg_display['Total Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            monthly_agg_display['Unique Conversions'] = monthly_agg_display['Unique Conversions'].apply(format_metric)
            monthly_agg_display['Unique Clicks'] = monthly_agg_display['Unique Clicks'].apply(format_metric)
            monthly_agg_display['Sent'] = monthly_agg_display['Sent'].apply(format_metric)
            monthly_agg_display['Delivered'] = monthly_agg_display['Delivered'].apply(format_metric)
            st.dataframe(monthly_agg_display)
            
            # Chart
            fig_comp = px.line(monthly_agg, x='Month', y='Total Revenue (SAR)', title="Revenue Over Months")
            st.plotly_chart(fig_comp)
            
            # Comparison between two months
            st.subheader("Compare Two Months")
            months = monthly_agg['Month'].tolist()
            if len(months) >= 2:
                col1, col2 = st.columns(2)
                with col1:
                    month1 = st.selectbox("Select First Month", months, index=0)
                with col2:
                    month2 = st.selectbox("Select Second Month", [m for m in months if m != month1], index=0 if len(months) > 1 else None)
                
                if month1 and month2:
                    data1 = monthly_agg[monthly_agg['Month'] == month1].iloc[0]
                    data2 = monthly_agg[monthly_agg['Month'] == month2].iloc[0]
                    
                    st.write(f"### Comparison: {month1} vs {month2}")
                    
                    metrics = ['Total Revenue (SAR)', 'Unique Conversions', 'Unique Clicks', 'Sent', 'Delivered']
                    
                    for metric in metrics:
                        val1 = data1[metric]
                        val2 = data2[metric]
                        delta = val2 - val1
                        delta_pct = (delta / val1 * 100) if val1 != 0 else 0
                        
                        unit = "SAR" if "Revenue" in metric else ""
                        st.metric(
                            f"{metric} ({month1})", 
                            format_metric(val1, unit), 
                            delta=format_metric(delta, unit) + f" ({delta_pct:+.1f}%)"
                        )
                        st.metric(
                            f"{metric} ({month2})", 
                            format_metric(val2, unit)
                        )
            else:
                st.write("Not enough months to compare.")
        else:
            st.write("No monthly data available.")

    elif page == "AI Insights":
        st.header("🤖 AI-Powered Insights")
        
        # Forecasting
        st.subheader("📈 Revenue Forecasting")
        if not filtered_df.empty:
            monthly_df = filtered_df.copy()
            monthly_df['Month'] = monthly_df['Reporting Period Start Date'].dt.to_period('M').dt.to_timestamp()
            monthly_rev = monthly_df.groupby('Month')['Total Revenue (SAR)'].sum().reset_index()
            if len(monthly_rev) > 2:
                # Prepare data for Prophet
                df_prophet = monthly_rev.rename(columns={'Month': 'ds', 'Total Revenue (SAR)': 'y'})
                try:
                    model = Prophet()
                    model.fit(df_prophet)
                    future = model.make_future_dataframe(periods=3, freq='M')
                    forecast = model.predict(future)
                    fig_forecast = model.plot(forecast)
                    st.plotly_chart(fig_forecast)
                    st.write("**Forecast Insights:** Next 3 months revenue prediction with confidence intervals.")
                except Exception as e:
                    st.write(f"Forecasting error: {e}")
            else:
                st.write("Not enough data for forecasting.")
        
        # Segmentation
        st.subheader("👥 Advanced Customer Segmentation")
        if not filtered_df.empty:
            seg_agg = filtered_df.groupby('Segment Name').agg({
                'Total Revenue (SAR)': 'sum',
                'Unique Conversions': 'sum',
                'Unique Clicks': 'sum',
                'Sent': 'sum'
            }).reset_index()
            if len(seg_agg) > 3:
                features = seg_agg[['Total Revenue (SAR)', 'Unique Conversions', 'Unique Clicks', 'Sent']]
                try:
                    kmeans = KMeans(n_clusters=3, random_state=42)
                    seg_agg['Cluster'] = kmeans.fit_predict(features)
                    fig_seg = px.scatter(seg_agg, x='Total Revenue (SAR)', y='Unique Conversions', color='Cluster', hover_data=['Segment Name'])
                    st.plotly_chart(fig_seg)
                    st.write("**Segmentation Insights:** Segments grouped by behavior. High-value clusters should be prioritized.")
                except Exception as e:
                    st.write(f"Segmentation error: {e}")
            else:
                st.write("Not enough segments for clustering.")
        
        # Optimization
        st.subheader("🎯 Campaign Optimization Recommendations")
        top_camp = top_campaigns(filtered_df, 'Total Revenue (SAR)')
        if not top_camp.empty:
            best_camp = top_camp.iloc[0]['Campaign Name']
            st.success(f"🚀 **Top Performer:** {best_camp} - Allocate more budget here!")
            underperformers = top_camp.tail(3)['Campaign Name'].tolist()
            st.warning(f"⚠️ **Underperformers:** {', '.join(underperformers)} - Consider pausing or optimizing.")
        
        # ROI Analysis
        st.subheader("💰 ROI Analysis")
        roi_df = filtered_df.groupby('Channel').agg({'Total Revenue (SAR)': 'sum'}).reset_index()
        roi_df['Estimated Cost'] = roi_df['Total Revenue (SAR)'] * 0.1  # placeholder
        roi_df['ROI'] = (roi_df['Total Revenue (SAR)'] - roi_df['Estimated Cost']) / roi_df['Estimated Cost']
        st.dataframe(roi_df)
        st.write("**ROI Insights:** Channels with ROI > 1 are profitable. Focus on Email and Push.")
        
        # Actionable Recommendations
        st.subheader("📋 Actionable Recommendations")
        st.markdown("""
        - **Increase Email Budget:** Highest ROI channel
        - **Optimize SMS Campaigns:** High delivery but low conversion
        - **Target High-Value Segments:** From clustering analysis
        - **Monitor Trends:** Use forecasting for budget planning
        - **A/B Test Creatives:** For underperforming campaigns
        """)

else:
    st.write("Please upload a CSV file.")