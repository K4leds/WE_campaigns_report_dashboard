import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO

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

# Upload CSV
uploaded_file = st.file_uploader("Upload WebEngage CSV", type="csv")

def clean_data(df):
    # Convert date columns to datetime
    date_cols = ['Reporting Period Start Date', 'Reporting Period End Date', 'Campaign Start Date', 'Campaign End Date']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Convert percentage columns to float
    pct_cols = [col for col in df.columns if 'Rate' in col or 'Rate' in col.lower()]
    for col in pct_cols:
        df[col] = df[col].astype(str).str.rstrip('%').astype(float) / 100
    
    # Convert revenue columns to float
    revenue_cols = [col for col in df.columns if 'Revenue' in col]
    for col in revenue_cols:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Convert numeric columns
    numeric_cols = ['Total in Control Group', 'Unique Control Group Conversions', 'Sent', 'Failed', 'Delivered', 
                    'Unique Impressions', 'Total Impressions', 'Unique Clicks', 'Total Clicks', 
                    'Unique Conversions', 'Total Conversions', 'Unique Impression-Through Conversions', 
                    'Total Impression-Through Conversions', 'Unique Click-Through Conversions', 
                    'Total Click-Through Conversions']
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Fill NaN with 0 for numeric columns only
    df[numeric_cols] = df[numeric_cols].fillna(0)
    df[revenue_cols] = df[revenue_cols].fillna(0)
    df[pct_cols] = df[pct_cols].fillna(0)
    
    # Add total revenue column
    if 'Revenue (SAR)' in df.columns and 'Click-Through Revenue (SAR)' in df.columns and 'Open-Through Revenue (SAR)' in df.columns:
        df['Total Revenue (SAR)'] = df['Revenue (SAR)'] + df['Click-Through Revenue (SAR)'] + df['Open-Through Revenue (SAR)']
    else:
        df['Total Revenue (SAR)'] = df.get('Revenue (SAR)', 0)
    
    # Add calculated metrics
    if 'Unique Clicks' in df.columns and 'Unique Impressions' in df.columns:
        df['CTR'] = np.where(df['Unique Impressions'] > 0, df['Unique Clicks'] / df['Unique Impressions'], 0)
    if 'Unique Conversions' in df.columns and 'Unique Clicks' in df.columns:
        df['Conversion Rate'] = np.where(df['Unique Clicks'] > 0, df['Unique Conversions'] / df['Unique Clicks'], 0)
    if 'Delivered' in df.columns and 'Sent' in df.columns:
        df['Delivery Rate'] = np.where(df['Sent'] > 0, df['Delivered'] / df['Sent'], 0)
    
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
        'Unique Conversions': 'sum',
        'Total Conversions': 'sum'
    }
    if 'Revenue (SAR)' in df.columns:
        agg_dict['Revenue (SAR)'] = 'sum'
    if 'Click-Through Revenue (SAR)' in df.columns:
        agg_dict['Click-Through Revenue (SAR)'] = 'sum'
    if 'Open-Through Revenue (SAR)' in df.columns:
        agg_dict['Open-Through Revenue (SAR)'] = 'sum'
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
    if 'Revenue (SAR)' in df.columns:
        agg_dict['Revenue (SAR)'] = 'sum'
    if 'Click-Through Revenue (SAR)' in df.columns:
        agg_dict['Click-Through Revenue (SAR)'] = 'sum'
    if 'Open-Through Revenue (SAR)' in df.columns:
        agg_dict['Open-Through Revenue (SAR)'] = 'sum'
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

    # Tabs
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8, tab9, tab10, tab11, tab12, tab13 = st.tabs(["Overview", "Campaigns", "Journeys", "Segments", "Channels", "Time Series", "Correlations", "A/B Testing", "Attribution", "Failed Reasons", "ESP Performance", "Export", "Comparisons"])

    with tab1:
        st.header("Overview")
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("Total Revenue", format_metric(filtered_df['Total Revenue (SAR)'].sum(), "SAR"))
        with col2:
            st.metric("Total Conversions", format_metric(filtered_df['Unique Conversions'].sum()))
        with col3:
            st.metric("Total Clicks", format_metric(filtered_df['Unique Clicks'].sum()))
        with col4:
            st.metric("Average CTR", f"{filtered_df['CTR'].mean():.2%}")
        with col5:
            st.metric("Average Conversion Rate", f"{filtered_df['Conversion Rate'].mean():.2%}")
        with col6:
            st.metric("Average Delivery Rate", f"{filtered_df['Delivery Rate'].mean():.2%}")

        # Conversion Funnel
        st.subheader("Conversion Funnel")
        funnel_data = {
            'Stage': ['Impressions', 'Clicks', 'Conversions'],
            'Count': [filtered_df['Unique Impressions'].sum(), filtered_df['Unique Clicks'].sum(), filtered_df['Unique Conversions'].sum()]
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

    with tab2:
        st.header("Campaign Analysis")
        
        # Top Campaigns
        st.subheader("Top Campaigns")
        camp_metric = st.selectbox("Metric", ['Unique Conversions', 'Total Revenue (SAR)', 'Unique Clicks', 'Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Open-Through Revenue (SAR)', 'CTR', 'Conversion Rate'], key='camp_metric')
        top_camp = top_campaigns(filtered_df, camp_metric)
        # Format the metric column for display
        if 'Revenue' in camp_metric:
            top_camp[camp_metric] = top_camp[camp_metric].apply(lambda x: format_metric(x, "SAR"))
        elif camp_metric in ['Unique Conversions', 'Unique Clicks']:
            top_camp[camp_metric] = top_camp[camp_metric].apply(format_metric)
        # For rates, keep as is
        st.dataframe(top_camp)
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

    with tab3:
        st.header("Journey Analysis")
        
        # Top Journeys
        st.subheader("Top Journeys")
        jour_metric = st.selectbox("Metric", ['Delivered Rate', 'Unique Clicks', 'Unique Conversions', 'Total Revenue (SAR)'], key='jour_metric')
        top_jour = top_journeys(filtered_df, jour_metric)
        # Format the metric column for display
        if 'Revenue' in jour_metric:
            top_jour[jour_metric] = top_jour[jour_metric].apply(lambda x: format_metric(x, "SAR"))
        elif jour_metric in ['Unique Clicks', 'Unique Conversions']:
            top_jour[jour_metric] = top_jour[jour_metric].apply(format_metric)
        # For rates, keep as is
        st.dataframe(top_jour)
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
                st.metric("Total Revenue", format_metric(jour_details['Total Revenue (SAR)'].sum(), "SAR"))
            
            # Performance by Channel
            st.subheader("Performance by Channel")
            chan_perf_jour = jour_details.groupby('Channel').agg({
                'Sent': 'sum',
                'Delivered': 'sum',
                'Unique Conversions': 'sum',
                'Total Revenue (SAR)': 'sum'
            }).reset_index()
            # Format columns
            chan_perf_jour['Sent'] = chan_perf_jour['Sent'].apply(format_metric)
            chan_perf_jour['Delivered'] = chan_perf_jour['Delivered'].apply(format_metric)
            chan_perf_jour['Unique Conversions'] = chan_perf_jour['Unique Conversions'].apply(format_metric)
            chan_perf_jour['Total Revenue (SAR)'] = chan_perf_jour['Total Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            st.dataframe(chan_perf_jour)
            fig_chan_jour = px.bar(chan_perf_jour, x='Channel', y='Unique Conversions', title="Conversions by Channel for Selected Journeys")
            st.plotly_chart(fig_chan_jour)
            
            # Time Series for Selected Journeys
            st.subheader("Time Series Performance")
            ts_jour = jour_details.groupby(['Reporting Period Start Date', 'Journey Name'])[jour_metric].sum().reset_index()
            if not ts_jour.empty:
                fig_ts_jour = px.line(ts_jour, x='Reporting Period Start Date', y=jour_metric, color='Journey Name', title=f"{jour_metric} Over Time for Selected Journeys")
                st.plotly_chart(fig_ts_jour)
            
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

    with tab4:
        st.header("Top Segments")
        seg_metric = st.selectbox("Metric", ['Unique Conversions', 'Total Revenue (SAR)', 'Unique Clicks', 'Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Open-Through Revenue (SAR)'], key='seg_metric')
        top_seg = top_segments(filtered_df, seg_metric)
        # Format the metric column for display
        if 'Revenue' in seg_metric:
            top_seg[seg_metric] = top_seg[seg_metric].apply(lambda x: format_metric(x, "SAR"))
        elif seg_metric in ['Unique Conversions', 'Unique Clicks']:
            top_seg[seg_metric] = top_seg[seg_metric].apply(format_metric)
        st.dataframe(top_seg)
        fig3 = px.bar(top_seg, x='Segment Name', y=seg_metric, title=f"Top Segments by {seg_metric}")
        st.plotly_chart(fig3)

    with tab5:
        st.header("Channel Analysis")
        chan_df = channel_analysis(filtered_df)
        # Format numeric columns for display
        numeric_cols = ['Sent', 'Delivered', 'Unique Impressions', 'Unique Clicks', 'Unique Conversions', 'Total Conversions']
        for col in numeric_cols:
            if col in chan_df.columns:
                chan_df[col] = chan_df[col].apply(format_metric)
        revenue_cols = [col for col in chan_df.columns if 'Revenue' in col]
        for col in revenue_cols:
            chan_df[col] = chan_df[col].apply(lambda x: format_metric(x, "SAR"))
        st.dataframe(chan_df)
        fig4 = px.bar(chan_df, x='Channel', y='Unique Conversions', title="Conversions by Channel")
        st.plotly_chart(fig4)
        if 'Total Revenue (SAR)' in chan_df.columns:
            fig_rev = px.bar(chan_df, x='Channel', y='Total Revenue (SAR)', title="Revenue by Channel")
            st.plotly_chart(fig_rev)
        
        # ESP Analysis
        esp_df = esp_analysis(filtered_df)
        if not esp_df.empty:
            st.subheader("ESP/SSP Analysis")
            # Format numeric columns
            numeric_cols = ['Sent', 'Delivered', 'Unique Conversions']
            for col in numeric_cols:
                if col in esp_df.columns:
                    esp_df[col] = esp_df[col].apply(format_metric)
            revenue_cols = [col for col in esp_df.columns if 'Revenue' in col]
            for col in revenue_cols:
                esp_df[col] = esp_df[col].apply(lambda x: format_metric(x, "SAR"))
            st.dataframe(esp_df)
            fig_esp = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Delivered', title="Delivered by ESP")
            st.plotly_chart(fig_esp)
            if 'Total Revenue (SAR)' in esp_df.columns:
                fig_esp_rev = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Total Revenue (SAR)', title="Revenue by ESP")
                st.plotly_chart(fig_esp_rev)

    with tab6:
        st.header("Time Series Analysis")
        ts_metric = st.selectbox("Metric", ['Unique Conversions', 'Total Revenue (SAR)', 'Unique Clicks', 'Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Open-Through Revenue (SAR)'], key='ts_metric')
        ts_df = time_series_analysis(filtered_df, ts_metric)
        if not ts_df.empty:
            fig_ts = px.line(ts_df, x='Reporting Period Start Date', y=ts_metric, title=f"{ts_metric} Over Time")
            st.plotly_chart(fig_ts)
        else:
            st.write("No time series data available.")

    with tab7:
        st.header("Correlations")
        numeric_df = filtered_df.select_dtypes(include=[np.number])
        if not numeric_df.empty:
            corr = numeric_df.corr()
            fig_corr = px.imshow(corr, text_auto=True, title="Correlation Matrix")
            st.plotly_chart(fig_corr)
        else:
            st.write("No numeric data for correlation.")

    with tab8:
        st.header("A/B Testing Analysis")
        ab_df = ab_testing_analysis(filtered_df)
        if not ab_df.empty:
            st.dataframe(ab_df)
            fig_ab = px.bar(ab_df, x='Campaign Name', y='Lift', title="Conversion Lift by Campaign")
            st.plotly_chart(fig_ab)
        else:
            st.write("No A/B testing data available (no control groups).")

    with tab9:
        st.header("Attribution Analysis")
        attr_df = attribution_analysis(filtered_df)
        attr_df['Conversions'] = attr_df['Conversions'].apply(format_metric)
        st.dataframe(attr_df)
        fig_attr = px.pie(attr_df, names='Source', values='Conversions', title="Conversions by Attribution Source")
        st.plotly_chart(fig_attr)

    with tab10:
        st.header("Failed Reasons Analysis")
        failed_df = failed_reasons_analysis(filtered_df)
        if not failed_df.empty:
            # Format counts
            failed_df['Count'] = failed_df['Count'].apply(format_metric)
            st.dataframe(failed_df)
            fig_fail = px.bar(failed_df, x='Reason', y='Count', title="Failed Reasons Breakdown")
            st.plotly_chart(fig_fail)
            
        # Drill-down: Failed reasons by channel
            st.subheader("Failed Reasons by Channel")
            failed_cols = [col for col in filtered_df.columns if 'Failed' in col and col != 'Failed']
            if failed_cols:
                failed_by_channel = filtered_df.groupby('Channel')[failed_cols].sum().reset_index()
                # Format failed counts
                for col in failed_cols:
                    failed_by_channel[col] = failed_by_channel[col].apply(format_metric)
                st.dataframe(failed_by_channel)
                # Melt for plotting
                failed_melt = failed_by_channel.melt(id_vars='Channel', var_name='Reason', value_name='Count')
                fig_fail_chan = px.bar(failed_melt, x='Channel', y='Count', color='Reason', title="Failed Reasons by Channel")
                st.plotly_chart(fig_fail_chan)
        else:
            st.write("No failed reasons data available.")

    with tab11:
        st.header("ESP Performance")
        esp_df = esp_analysis(filtered_df)
        if not esp_df.empty:
            # Format numeric columns
            numeric_cols = ['Sent', 'Delivered', 'Unique Conversions']
            for col in numeric_cols:
                if col in esp_df.columns:
                    esp_df[col] = esp_df[col].apply(format_metric)
            revenue_cols = [col for col in esp_df.columns if 'Revenue' in col]
            for col in revenue_cols:
                esp_df[col] = esp_df[col].apply(lambda x: format_metric(x, "SAR"))
            st.dataframe(esp_df)
            fig_esp = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Delivered', title="Delivered by ESP")
            st.plotly_chart(fig_esp)
            if 'Total Revenue (SAR)' in esp_df.columns:
                fig_esp_rev = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Total Revenue (SAR)', title="Revenue by ESP")
                st.plotly_chart(fig_esp_rev)
        else:
            st.write("No ESP data available.")

    with tab12:
        st.header("Export")
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

    with tab13:
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

else:
    st.write("Please upload a CSV file.")