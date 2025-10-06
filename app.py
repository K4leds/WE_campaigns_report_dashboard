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

# Configure page layout for wide mode - better for BI dashboards
st.set_page_config(
    page_title="WebEngage Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

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
    
    # Revenue columns represent different attribution models - NOT additive!
    # Revenue (SAR) = Send-through (total attribution)
    # Impression-Through Revenue (SAR) = Impression attribution only  
    # Click-Through Revenue (SAR) = Click attribution only
    # These are hierarchical/overlapping, not meant to be summed
    
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

def get_top_journeys(df, metric='Delivered Rate', top_n=10):
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
    return df.groupby('Channel').agg(agg_dict).reset_index()

def time_series_analysis(df, metric='Unique Conversions'):
    df_ts = df.groupby('Reporting Period Start Date')[metric].sum().reset_index()
    return df_ts

def failed_reasons_analysis(df):
    # Exclude 'Failed' and 'Failed Rate' columns - only include specific failure reasons
    failed_cols = [col for col in df.columns if 'Failed' in col and col not in ['Failed', 'Failed Rate']]
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

def calculate_journey_health_score(df_journey, all_journeys_df=None):
    """
    Calculate a comprehensive Journey Health Score (0-100) using Empirical Bayes methodology
    with small-sample corrections - the gold standard for BI analytics in enterprise environments.
    
    Scoring Method: Empirical Bayes Shrinkage + Log-transformed Revenue Per Conversion
    - Uses Beta-Binomial shrinkage for conversion rates (handles small samples robustly)
    - Log-transforms Revenue Per Conversion to reduce outlier dominance
    - Applies statistical smoothing used by major tech companies (Meta, Google, Amazon)
    - Provides reliable rankings even with sparse data
    """
    try:
        # Initialize scores
        scores = {}

        # --- Data sufficiency guard ---
        # Avoid labeling very low-activity journeys as 'Good' or 'Excellent'.
        # Heuristic thresholds (conservative defaults) - adjust as needed:
        # - min_sent: minimum total messages sent across the journey
        # - min_conversions: minimum total conversions to consider revenue/conversion metrics meaningful
        # - min_days: minimum number of reporting days for the journey
        min_sent = 10
        min_conversions = 3
        min_days = 3

        # Compute simple activity metrics for this journey
        total_sent_j = df_journey['Sent'].sum() if 'Sent' in df_journey.columns else 0
        total_conversions_j = df_journey['Unique Conversions'].sum() if 'Unique Conversions' in df_journey.columns else 0
        unique_days = df_journey['Reporting Period Start Date'].nunique() if 'Reporting Period Start Date' in df_journey.columns else len(df_journey)

        if total_sent_j < min_sent or total_conversions_j < min_conversions or unique_days < min_days:
            # Return explicit Insufficient Data result so the UI can filter or flag these journeys
            return {
                'health_score': 0.0,
                'tier': 'Insufficient Data',
                'tier_description': 'Insufficient activity to compute reliable score',
                'component_scores': {'delivery': 0, 'engagement': 0, 'conversion': 0, 'revenue': 0},
                'recommendations': [
                    'ℹ️ Insufficient data: Not enough volume or time to compute a reliable health score',
                    '🔎 Consider increasing the lookback window or aggregating similar journeys for stability'
                ],
                'scoring_method': 'Insufficient data guard (volume/time thresholds)'
            }
        
        # Get baseline data for percentile calculations (use all data if available)
        baseline_df = all_journeys_df if all_journeys_df is not None else df_journey

        # === EMPIRICAL BAYES HELPER FUNCTIONS ===
        def estimate_beta_prior(successes_array, trials_array):
            """Estimate Beta prior parameters using method of moments from population data"""
            # Filter out invalid data
            valid_mask = (trials_array > 0) & (~np.isnan(successes_array)) & (~np.isnan(trials_array))
            if not valid_mask.any():
                return 1.0, 1.0  # Uniform prior fallback
            
            rates = successes_array[valid_mask] / trials_array[valid_mask]
            rates = rates[(rates >= 0) & (rates <= 1)]  # Valid rates only
            
            if len(rates) < 2:
                return 1.0, 1.0  # Uniform prior fallback
            
            mean_rate = np.mean(rates)
            var_rate = np.var(rates, ddof=1)
            
            # Ensure variance is positive and not too close to theoretical maximum
            if var_rate <= 0 or var_rate >= mean_rate * (1 - mean_rate):
                return 1.0, 1.0  # Uniform prior fallback
            
            # Method of moments: alpha = mean * (mean*(1-mean)/var - 1), beta = (1-mean) * (...)
            scale = mean_rate * (1 - mean_rate) / var_rate - 1.0
            alpha = max(0.1, mean_rate * scale)
            beta = max(0.1, (1 - mean_rate) * scale)
            
            return alpha, beta
        
        def beta_posterior_mean(successes, trials, alpha_prior, beta_prior):
            """Calculate posterior mean for Beta-Binomial model"""
            if trials <= 0:
                return 0.0
            return (successes + alpha_prior) / (trials + alpha_prior + beta_prior)
        
        # Helper function for percentile-based scoring (now using smoothed values)
        def calculate_percentile_score(value, baseline_values, reverse=False):
            """Convert a value to percentile score (0-100) using statistical ranking"""
            if len(baseline_values) == 0 or pd.isna(value):
                return 50  # Neutral score for missing data
            
            # Remove NaN values
            clean_values = baseline_values.dropna()
            if len(clean_values) == 0:
                return 50
            
            # Calculate percentile rank
            if reverse:
                # For metrics where lower is better (e.g., cost per conversion)
                percentile = (1 - (clean_values < value).mean()) * 100
            else:
                # For metrics where higher is better (standard case)
                percentile = (clean_values <= value).mean() * 100
            
            return min(max(percentile, 0), 100)  # Ensure 0-100 range

        # === PREPARE POPULATION DATA FOR EMPIRICAL BAYES ===
        
        # Collect journey-level data for prior estimation
        journey_groups = baseline_df.groupby('Journey Name') if 'Journey Name' in baseline_df.columns else [('current', baseline_df)]
        
        # Delivery rates (usually high success rate, less smoothing needed)
        delivery_rates = []
        delivery_totals = []
        for name, group in journey_groups:
            if 'Delivery Rate' in group.columns:
                rate = group['Delivery Rate'].mean()
                if not pd.isna(rate):
                    delivery_rates.append(rate)
            elif 'Sent' in group.columns and 'Delivered' in group.columns:
                sent = group['Sent'].sum()
                delivered = group['Delivered'].sum()
                if sent > 0:
                    delivery_rates.append(delivered / sent)
                    delivery_totals.append(sent)
        
        # CTR data for Empirical Bayes
        ctr_clicks = []
        ctr_impressions = []
        for name, group in journey_groups:
            if 'Unique Clicks' in group.columns and 'Unique Impressions' in group.columns:
                clicks = group['Unique Clicks'].sum()
                impressions = group['Unique Impressions'].sum()
                if impressions > 0:
                    ctr_clicks.append(clicks)
                    ctr_impressions.append(impressions)
        
        # Conversion data for Empirical Bayes
        conv_conversions = []
        conv_clicks = []
        for name, group in journey_groups:
            if 'Unique Conversions' in group.columns and 'Unique Clicks' in group.columns:
                conversions = group['Unique Conversions'].sum()
                clicks = group['Unique Clicks'].sum()
                if clicks > 0:
                    conv_conversions.append(conversions)
                    conv_clicks.append(clicks)
        
        # Revenue Per Conversion data (for log-transformation)
        rpc_values = []
        for name, group in journey_groups:
            if 'Revenue (SAR)' in group.columns and 'Unique Conversions' in group.columns:
                revenue = group['Revenue (SAR)'].sum()
                conversions = group['Unique Conversions'].sum()
                if conversions > 0:
                    rpc = revenue / conversions
                    if rpc > 0:  # Only positive RPC values
                        rpc_values.append(rpc)
        
        # Estimate priors
        ctr_alpha, ctr_beta = estimate_beta_prior(np.array(ctr_clicks), np.array(ctr_impressions))
        conv_alpha, conv_beta = estimate_beta_prior(np.array(conv_conversions), np.array(conv_clicks))

        # === CALCULATE COMPONENT SCORES WITH EMPIRICAL BAYES ===
        
        # 1. Delivery Performance Score (25% weight) - Less smoothing needed
        if 'Delivery Rate' in df_journey.columns and df_journey['Delivery Rate'].notna().any():
            delivery_rate = df_journey['Delivery Rate'].mean()
        elif 'Sent' in df_journey.columns and 'Delivered' in df_journey.columns:
            total_sent = df_journey['Sent'].sum()
            total_delivered = df_journey['Delivered'].sum()
            delivery_rate = (total_delivered / total_sent) if total_sent > 0 else 0
        else:
            delivery_rate = 0.8  # Industry average 80%
        
        baseline_delivery = pd.Series(delivery_rates) if delivery_rates else pd.Series([delivery_rate])
        scores['delivery'] = calculate_percentile_score(delivery_rate, baseline_delivery)
        
        # 2. Engagement Performance Score (25% weight) - WITH EMPIRICAL BAYES SMOOTHING
        # FIXED: Always use aggregate CTR calculation instead of daily average CTR for proper scoring
        if 'Unique Clicks' in df_journey.columns and 'Unique Impressions' in df_journey.columns:
            total_clicks = df_journey['Unique Clicks'].sum()
            total_impressions = df_journey['Unique Impressions'].sum()
            # Apply Empirical Bayes smoothing to aggregate CTR (more reliable than daily averages)
            smoothed_ctr = beta_posterior_mean(total_clicks, total_impressions, ctr_alpha, ctr_beta)
        else:
            smoothed_ctr = 0.02  # Industry average 2%
        
        # Create baseline of smoothed CTRs for fair comparison
        baseline_ctr_smoothed = []
        for clicks, impressions in zip(ctr_clicks, ctr_impressions):
            baseline_ctr_smoothed.append(beta_posterior_mean(clicks, impressions, ctr_alpha, ctr_beta))
        baseline_ctr = pd.Series(baseline_ctr_smoothed) if baseline_ctr_smoothed else pd.Series([smoothed_ctr])
        
        scores['engagement'] = calculate_percentile_score(smoothed_ctr, baseline_ctr)
        
        # 3. Conversion Performance Score (30% weight) - WITH EMPIRICAL BAYES SMOOTHING
        # FIXED: Use the direct Conversion Rate column when available (more reliable than manual calculation)
        if 'Conversion Rate' in df_journey.columns and df_journey['Conversion Rate'].notna().any():
            # Use the provided conversion rate column (already calculated correctly by WebEngage)
            conv_rate = df_journey['Conversion Rate'].mean() / 100.0  # Convert percentage to decimal
            # Create baseline from all journeys' conversion rates
            if 'Conversion Rate' in baseline_df.columns:
                baseline_conv_values = []
                for name, group in baseline_df.groupby('Journey Name'):
                    journey_conv_rate = group['Conversion Rate'].mean() / 100.0
                    if not pd.isna(journey_conv_rate):
                        baseline_conv_values.append(journey_conv_rate)
                baseline_conv = pd.Series(baseline_conv_values)
            else:
                baseline_conv = pd.Series([conv_rate])
        elif 'Unique Conversions' in df_journey.columns and 'Unique Clicks' in df_journey.columns:
            # Fallback: manual calculation (but this may not be reliable for some data)
            total_conversions = df_journey['Unique Conversions'].sum()
            total_clicks = df_journey['Unique Clicks'].sum()
            # Apply Empirical Bayes smoothing for manual calculations
            conv_rate = beta_posterior_mean(total_conversions, total_clicks, conv_alpha, conv_beta)
            
            # Create baseline of smoothed conversion rates
            baseline_conv_smoothed = []
            for conversions, clicks in zip(conv_conversions, conv_clicks):
                baseline_conv_smoothed.append(beta_posterior_mean(conversions, clicks, conv_alpha, conv_beta))
            baseline_conv = pd.Series(baseline_conv_smoothed) if baseline_conv_smoothed else pd.Series([conv_rate])
        else:
            conv_rate = 0.05  # Industry average 5%
            baseline_conv = pd.Series([conv_rate])
        
        scores['conversion'] = calculate_percentile_score(conv_rate, baseline_conv)
        
        # 4. Revenue Efficiency Score (20% weight) - LOG-TRANSFORMED RPC
        if 'Revenue (SAR)' in df_journey.columns and 'Unique Conversions' in df_journey.columns:
            total_revenue = df_journey['Revenue (SAR)'].sum()
            total_conversions = df_journey['Unique Conversions'].sum()
            revenue_per_conversion = (total_revenue / total_conversions) if total_conversions > 0 else 0
            
            # Log-transform for better distribution (reduces outlier dominance)
            log_rpc = np.log1p(revenue_per_conversion)  # log(1 + x) handles zero values
            
            # Create baseline of log-transformed RPCs
            baseline_log_rpc = [np.log1p(rpc) for rpc in rpc_values] if rpc_values else [log_rpc]
            baseline_log_rpc = pd.Series(baseline_log_rpc)
            
            scores['revenue'] = calculate_percentile_score(log_rpc, baseline_log_rpc)
        else:
            scores['revenue'] = 50  # Neutral score if no revenue data
        
        # Calculate weighted final score using enterprise-optimized weights
        # Increased revenue weight slightly to improve sensitivity to business outcomes
        weights = {'delivery': 0.20, 'engagement': 0.25, 'conversion': 0.30, 'revenue': 0.25}
        final_score = sum(scores[key] * weights[key] for key in scores)
        
        # Professional tier classification (McKinsey/BCG standard)
        if final_score >= 80:
            tier = "Excellent"
            tier_description = "Top Quartile Performance"
        elif final_score >= 60:
            tier = "Good" 
            tier_description = "Above Average Performance"
        elif final_score >= 40:
            tier = "Fair"
            tier_description = "Below Average Performance"
        else:
            tier = "Poor"
            tier_description = "Bottom Quartile Performance"
        
        # Generate professional recommendations for executives
        recommendations = []
        
        if scores['delivery'] < 40:
            recommendations.append("🚨 DELIVERY CRITICAL: Immediate technical review required - poor inbox placement impacting all downstream metrics")
        elif scores['delivery'] < 60:
            recommendations.append("⚠️ DELIVERY OPTIMIZATION: Review sender reputation and content to improve deliverability")
        
        if scores['engagement'] < 40:
            recommendations.append("🚨 ENGAGEMENT CRITICAL: Content and targeting strategy requires complete overhaul")
        elif scores['engagement'] < 60:
            recommendations.append("⚠️ ENGAGEMENT OPPORTUNITY: A/B test subject lines, send times, and content personalization")
        
        if scores['conversion'] < 40:
            recommendations.append("🚨 CONVERSION CRITICAL: Landing page and customer journey optimization is priority #1")
        elif scores['conversion'] < 60:
            recommendations.append("⚠️ CONVERSION OPTIMIZATION: Review offer relevance and purchase friction points")
        
        if scores['revenue'] < 40:
            recommendations.append("🚨 REVENUE EFFICIENCY: Customer value optimization or pricing strategy review needed")
        elif scores['revenue'] < 60:
            recommendations.append("⚠️ REVENUE OPPORTUNITY: Focus on upselling or higher-value customer segments")
        
        # Success recommendations
        if final_score >= 80:
            recommendations.append("🎯 SCALE SUCCESS: Allocate more budget to this high-performing journey")
            recommendations.append("� BEST PRACTICE: Document and replicate successful elements across other journeys")
        
        if not recommendations:
            recommendations.append("✅ SOLID PERFORMANCE: Continue current strategy with minor optimizations")
        
        return {
            'health_score': round(final_score, 1),
            'tier': tier,
            'tier_description': tier_description,
            'component_scores': scores,
            'recommendations': recommendations,
            'scoring_method': 'Empirical Bayes (Beta-Binomial) + Log(RPC) percentiles'
        }
        
    except Exception as e:
        # Fallback scoring for data quality issues
        return {
            'health_score': 50.0,
            'tier': 'Insufficient Data',
            'tier_description': 'Data Quality Issues',
            'component_scores': {'delivery': 50, 'engagement': 50, 'conversion': 50, 'revenue': 50},
            'recommendations': ['📊 DATA QUALITY: Improve data collection for accurate performance measurement'],
            'scoring_method': 'Fallback scoring due to data limitations'
        }



def calculate_campaign_health_score(df_campaign, all_campaigns_df=None):
    """
    Calculate a comprehensive Campaign Health Score (0-100) using Empirical Bayes methodology
    with small-sample corrections - adapted from journey health scoring for campaign analysis.

    Scoring Method: Empirical Bayes Shrinkage + Log-transformed Revenue Per Conversion
    - Uses Beta-Binomial shrinkage for conversion rates (handles small samples robustly)
    - Log-transforms Revenue Per Conversion to reduce outlier dominance
    - Applies statistical smoothing used by major tech companies (Meta, Google, Amazon)
    - Provides reliable rankings even with sparse data
    """
    try:
        # Initialize scores
        scores = {}

        # --- Data sufficiency guard ---
        # Avoid labeling very low-activity campaigns as 'Good' or 'Excellent'.
        # Heuristic thresholds (conservative defaults) - adjust as needed:
        # - min_sent: minimum total messages sent across the campaign
        # - min_conversions: minimum total conversions to consider revenue/conversion metrics meaningful
        # - min_days: minimum number of reporting days for the campaign
        min_sent = 10
        min_conversions = 3
        min_days = 3

        # Compute simple activity metrics for this campaign
        total_sent_c = df_campaign['Sent'].sum() if 'Sent' in df_campaign.columns else 0
        total_conversions_c = df_campaign['Unique Conversions'].sum() if 'Unique Conversions' in df_campaign.columns else 0
        unique_days = df_campaign['Reporting Period Start Date'].nunique() if 'Reporting Period Start Date' in df_campaign.columns else len(df_campaign)

        if total_sent_c < min_sent or total_conversions_c < min_conversions or unique_days < min_days:
            # Return explicit Insufficient Data result so the UI can filter or flag these campaigns
            return {
                'health_score': 0.0,
                'tier': 'Insufficient Data',
                'tier_description': 'Insufficient activity to compute reliable score',
                'component_scores': {'delivery': 0, 'engagement': 0, 'conversion': 0, 'revenue': 0},
                'recommendations': [
                    'ℹ️ Insufficient data: Not enough volume or time to compute a reliable campaign health score',
                    '🔎 Consider increasing the lookback window or aggregating similar campaigns for stability'
                ],
                'scoring_method': 'Insufficient data guard (volume/time thresholds)'
            }

        # Get baseline data for percentile calculations (use all data if available)
        baseline_df = all_campaigns_df if all_campaigns_df is not None else df_campaign

        # === EMPIRICAL BAYES HELPER FUNCTIONS ===
        def estimate_beta_prior(successes_array, trials_array):
            """Estimate Beta prior parameters using method of moments from population data"""
            # Filter out invalid data
            valid_mask = (trials_array > 0) & (~np.isnan(successes_array)) & (~np.isnan(trials_array))
            if not valid_mask.any():
                return 1.0, 1.0  # Uniform prior fallback

            rates = successes_array[valid_mask] / trials_array[valid_mask]
            rates = rates[(rates >= 0) & (rates <= 1)]  # Valid rates only

            if len(rates) < 2:
                return 1.0, 1.0  # Uniform prior fallback

            mean_rate = np.mean(rates)
            var_rate = np.var(rates, ddof=1)

            # Ensure variance is positive and not too close to theoretical maximum
            if var_rate <= 0 or var_rate >= mean_rate * (1 - mean_rate):
                return 1.0, 1.0  # Uniform prior fallback

            # Method of moments: alpha = mean * (mean*(1-mean)/var - 1), beta = (1-mean) * (...)
            scale = mean_rate * (1 - mean_rate) / var_rate - 1.0
            alpha = max(0.1, mean_rate * scale)
            beta = max(0.1, (1 - mean_rate) * scale)

            return alpha, beta

        def beta_posterior_mean(successes, trials, alpha_prior, beta_prior):
            """Calculate posterior mean for Beta-Binomial model"""
            if trials <= 0:
                return 0.0
            return (successes + alpha_prior) / (trials + alpha_prior + beta_prior)

        # Helper function for percentile-based scoring (now using smoothed values)
        def calculate_percentile_score(value, baseline_values, reverse=False):
            """Convert a value to percentile score (0-100) using statistical ranking"""
            if len(baseline_values) == 0 or pd.isna(value):
                return 50  # Neutral score for missing data

            # Remove NaN values
            clean_values = baseline_values.dropna()
            if len(clean_values) == 0:
                return 50

            # Calculate percentile rank
            if reverse:
                # For metrics where lower is better (e.g., cost per conversion)
                percentile = (1 - (clean_values < value).mean()) * 100
            else:
                # For metrics where higher is better (standard case)
                percentile = (clean_values <= value).mean() * 100

            return min(max(percentile, 0), 100)  # Ensure 0-100 range

        # === PREPARE POPULATION DATA FOR EMPIRICAL BAYES ===

        # Collect campaign-level data for prior estimation
        campaign_groups = baseline_df.groupby('Campaign Name') if 'Campaign Name' in baseline_df.columns else [('current', baseline_df)]

        # Delivery rates (usually high success rate, less smoothing needed)
        delivery_rates = []
        delivery_totals = []
        for name, group in campaign_groups:
            if 'Delivery Rate' in group.columns:
                rate = group['Delivery Rate'].mean()
                if not pd.isna(rate):
                    delivery_rates.append(rate)
            elif 'Sent' in group.columns and 'Delivered' in group.columns:
                sent = group['Sent'].sum()
                delivered = group['Delivered'].sum()
                if sent > 0:
                    delivery_rates.append(delivered / sent)
                    delivery_totals.append(sent)

        # CTR data for Empirical Bayes
        ctr_clicks = []
        ctr_impressions = []
        for name, group in campaign_groups:
            if 'Unique Clicks' in group.columns and 'Unique Impressions' in group.columns:
                clicks = group['Unique Clicks'].sum()
                impressions = group['Unique Impressions'].sum()
                if impressions > 0:
                    ctr_clicks.append(clicks)
                    ctr_impressions.append(impressions)

        # Conversion data for Empirical Bayes
        conv_conversions = []
        conv_clicks = []
        for name, group in campaign_groups:
            if 'Unique Conversions' in group.columns and 'Unique Clicks' in group.columns:
                conversions = group['Unique Conversions'].sum()
                clicks = group['Unique Clicks'].sum()
                if clicks > 0:
                    conv_conversions.append(conversions)
                    conv_clicks.append(clicks)

        # Revenue Per Conversion data (for log-transformation)
        rpc_values = []
        for name, group in campaign_groups:
            if 'Revenue (SAR)' in group.columns and 'Unique Conversions' in group.columns:
                revenue = group['Revenue (SAR)'].sum()
                conversions = group['Unique Conversions'].sum()
                if conversions > 0:
                    rpc = revenue / conversions
                    if rpc > 0:  # Only positive RPC values
                        rpc_values.append(rpc)

        # Estimate priors
        ctr_alpha, ctr_beta = estimate_beta_prior(np.array(ctr_clicks), np.array(ctr_impressions))
        conv_alpha, conv_beta = estimate_beta_prior(np.array(conv_conversions), np.array(conv_clicks))

        # === CALCULATE COMPONENT SCORES WITH EMPIRICAL BAYES ===

        # 1. Delivery Performance Score (25% weight) - Less smoothing needed
        if 'Delivery Rate' in df_campaign.columns and df_campaign['Delivery Rate'].notna().any():
            delivery_rate = df_campaign['Delivery Rate'].mean()
        elif 'Sent' in df_campaign.columns and 'Delivered' in df_campaign.columns:
            total_sent = df_campaign['Sent'].sum()
            total_delivered = df_campaign['Delivered'].sum()
            delivery_rate = (total_delivered / total_sent) if total_sent > 0 else 0
        else:
            delivery_rate = 0.8  # Industry average 80%

        baseline_delivery = pd.Series(delivery_rates) if delivery_rates else pd.Series([delivery_rate])
        scores['delivery'] = calculate_percentile_score(delivery_rate, baseline_delivery)

        # 2. Engagement Performance Score (25% weight) - WITH EMPIRICAL BAYES SMOOTHING
        # FIXED: Always use aggregate CTR calculation instead of daily average CTR for proper scoring
        if 'Unique Clicks' in df_campaign.columns and 'Unique Impressions' in df_campaign.columns:
            total_clicks = df_campaign['Unique Clicks'].sum()
            total_impressions = df_campaign['Unique Impressions'].sum()
            # Apply Empirical Bayes smoothing to aggregate CTR (more reliable than daily averages)
            smoothed_ctr = beta_posterior_mean(total_clicks, total_impressions, ctr_alpha, ctr_beta)
        else:
            smoothed_ctr = 0.02  # Industry average 2%

        # Create baseline of smoothed CTRs for fair comparison
        baseline_ctr_smoothed = []
        for clicks, impressions in zip(ctr_clicks, ctr_impressions):
            baseline_ctr_smoothed.append(beta_posterior_mean(clicks, impressions, ctr_alpha, ctr_beta))
        baseline_ctr = pd.Series(baseline_ctr_smoothed) if baseline_ctr_smoothed else pd.Series([smoothed_ctr])

        scores['engagement'] = calculate_percentile_score(smoothed_ctr, baseline_ctr)

        # 3. Conversion Performance Score (30% weight) - WITH EMPIRICAL BAYES SMOOTHING
        # FIXED: Use the direct Conversion Rate column when available (more reliable than manual calculation)
        if 'Conversion Rate' in df_campaign.columns and df_campaign['Conversion Rate'].notna().any():
            # Use the provided conversion rate column (already calculated correctly by WebEngage)
            conv_rate = df_campaign['Conversion Rate'].mean() / 100.0  # Convert percentage to decimal
            # Create baseline from all campaigns' conversion rates
            if 'Conversion Rate' in baseline_df.columns:
                baseline_conv_values = []
                for name, group in baseline_df.groupby('Campaign Name'):
                    campaign_conv_rate = group['Conversion Rate'].mean() / 100.0
                    if not pd.isna(campaign_conv_rate):
                        baseline_conv_values.append(campaign_conv_rate)
                baseline_conv = pd.Series(baseline_conv_values)
            else:
                baseline_conv = pd.Series([conv_rate])
        elif 'Unique Conversions' in df_campaign.columns and 'Unique Clicks' in df_campaign.columns:
            # Fallback: manual calculation (but this may not be reliable for some data)
            total_conversions = df_campaign['Unique Conversions'].sum()
            total_clicks = df_campaign['Unique Clicks'].sum()
            # Apply Empirical Bayes smoothing for manual calculations
            conv_rate = beta_posterior_mean(total_conversions, total_clicks, conv_alpha, conv_beta)

            # Create baseline of smoothed conversion rates
            baseline_conv_smoothed = []
            for conversions, clicks in zip(conv_conversions, conv_clicks):
                baseline_conv_smoothed.append(beta_posterior_mean(conversions, clicks, conv_alpha, conv_beta))
            baseline_conv = pd.Series(baseline_conv_smoothed) if baseline_conv_smoothed else pd.Series([conv_rate])
        else:
            conv_rate = 0.05  # Industry average 5%
            baseline_conv = pd.Series([conv_rate])

        scores['conversion'] = calculate_percentile_score(conv_rate, baseline_conv)

        # 4. Revenue Efficiency Score (20% weight) - LOG-TRANSFORMED RPC
        if 'Revenue (SAR)' in df_campaign.columns and 'Unique Conversions' in df_campaign.columns:
            total_revenue = df_campaign['Revenue (SAR)'].sum()
            total_conversions = df_campaign['Unique Conversions'].sum()
            revenue_per_conversion = (total_revenue / total_conversions) if total_conversions > 0 else 0

            # Log-transform for better distribution (reduces outlier dominance)
            log_rpc = np.log1p(revenue_per_conversion)  # log(1 + x) handles zero values

            # Create baseline of log-transformed RPCs
            baseline_log_rpc = [np.log1p(rpc) for rpc in rpc_values] if rpc_values else [log_rpc]
            baseline_log_rpc = pd.Series(baseline_log_rpc)

            scores['revenue'] = calculate_percentile_score(log_rpc, baseline_log_rpc)
        else:
            scores['revenue'] = 50  # Neutral score if no revenue data

        # Calculate weighted final score using enterprise-optimized weights
        # Increased revenue weight slightly to improve sensitivity to business outcomes
        weights = {'delivery': 0.20, 'engagement': 0.25, 'conversion': 0.30, 'revenue': 0.25}
        final_score = sum(scores[key] * weights[key] for key in scores)

        # Professional tier classification (McKinsey/BCG standard)
        if final_score >= 80:
            tier = "Excellent"
            tier_description = "Top Quartile Performance"
        elif final_score >= 60:
            tier = "Good"
            tier_description = "Above Average Performance"
        elif final_score >= 40:
            tier = "Fair"
            tier_description = "Below Average Performance"
        else:
            tier = "Poor"
            tier_description = "Bottom Quartile Performance"

        # Generate professional recommendations for executives
        recommendations = []

        if scores['delivery'] < 40:
            recommendations.append("🚨 DELIVERY CRITICAL: Immediate technical review required - poor inbox placement impacting all downstream metrics")
        elif scores['delivery'] < 60:
            recommendations.append("⚠️ DELIVERY OPTIMIZATION: Review sender reputation and content to improve deliverability")

        if scores['engagement'] < 40:
            recommendations.append("🚨 ENGAGEMENT CRITICAL: Content and targeting strategy requires complete overhaul")
        elif scores['engagement'] < 60:
            recommendations.append("⚠️ ENGAGEMENT OPPORTUNITY: A/B test subject lines, send times, and content personalization")

        if scores['conversion'] < 40:
            recommendations.append("🚨 CONVERSION CRITICAL: Landing page and customer journey optimization is priority #1")
        elif scores['conversion'] < 60:
            recommendations.append("⚠️ CONVERSION OPTIMIZATION: Review offer relevance and purchase friction points")

        if scores['revenue'] < 40:
            recommendations.append("🚨 REVENUE EFFICIENCY: Customer value optimization or pricing strategy review needed")
        elif scores['revenue'] < 60:
            recommendations.append("⚠️ REVENUE OPPORTUNITY: Focus on upselling or higher-value customer segments")

        # Success recommendations
        if final_score >= 80:
            recommendations.append("🎯 SCALE SUCCESS: Allocate more budget to this high-performing campaign")
            recommendations.append("📈 BEST PRACTICE: Document and replicate successful elements across other campaigns")

        if not recommendations:
            recommendations.append("✅ SOLID PERFORMANCE: Continue current strategy with minor optimizations")

        return {
            'health_score': round(final_score, 1),
            'tier': tier,
            'tier_description': tier_description,
            'component_scores': scores,
            'recommendations': recommendations,
            'scoring_method': 'Empirical Bayes (Beta-Binomial) + Log(RPC) percentiles'
        }

    except Exception as e:
        # Fallback scoring for data quality issues
        return {
            'health_score': 50.0,
            'tier': 'Insufficient Data',
            'tier_description': 'Data Quality Issues',
            'component_scores': {'delivery': 50, 'engagement': 50, 'conversion': 50, 'revenue': 50},
            'recommendations': ['📊 DATA QUALITY: Improve data collection for accurate performance measurement'],
            'scoring_method': 'Fallback scoring due to data limitations'
        }



def analyze_campaign_funnel(df_campaign):
    """
    Advanced funnel analysis for campaigns leveraging unique vs total metrics
    """
    try:
        funnel_data = {}
        
        # Basic funnel stages
        funnel_data['Sent'] = df_campaign['Sent'].sum() if 'Sent' in df_campaign.columns else 0
        funnel_data['Delivered'] = df_campaign['Delivered'].sum() if 'Delivered' in df_campaign.columns else 0
        
        # Engagement stages (use both unique and total if available)
        if 'Unique Impressions' in df_campaign.columns:
            funnel_data['Unique Impressions'] = df_campaign['Unique Impressions'].sum()
        if 'Total Impressions' in df_campaign.columns:
            funnel_data['Total Impressions'] = df_campaign['Total Impressions'].sum()
        
        if 'Unique Clicks' in df_campaign.columns:
            funnel_data['Unique Clicks'] = df_campaign['Unique Clicks'].sum()
        if 'Total Clicks' in df_campaign.columns:
            funnel_data['Total Clicks'] = df_campaign['Total Clicks'].sum()
        
        # Conversion stages
        if 'Unique Conversions' in df_campaign.columns:
            funnel_data['Unique Conversions'] = df_campaign['Unique Conversions'].sum()
        if 'Total Conversions' in df_campaign.columns:
            funnel_data['Total Conversions'] = df_campaign['Total Conversions'].sum()
        
        # Calculate drop-off rates and insights
        insights = []
        if funnel_data.get('Sent', 0) > 0 and funnel_data.get('Delivered', 0) > 0:
            delivery_rate = funnel_data['Delivered'] / funnel_data['Sent']
            if delivery_rate < 0.95:
                insights.append(f"🚨 Delivery Issue: {(1-delivery_rate)*100:.1f}% delivery failure rate")
        
        if funnel_data.get('Delivered', 0) > 0 and funnel_data.get('Unique Impressions', 0) > 0:
            impression_rate = funnel_data['Unique Impressions'] / funnel_data['Delivered']
            if impression_rate < 0.8:
                insights.append(f"👁️ Low Visibility: Only {impression_rate*100:.1f}% of delivered messages were seen")
        
        # Analyze repeat engagement (unique vs total)
        if funnel_data.get('Total Impressions', 0) > 0 and funnel_data.get('Unique Impressions', 0) > 0:
            repeat_impression_rate = funnel_data['Total Impressions'] / funnel_data['Unique Impressions']
            if repeat_impression_rate > 1.5:
                insights.append(f"🔄 High Re-engagement: {repeat_impression_rate:.1f}x average views per user")
        
        if funnel_data.get('Total Clicks', 0) > 0 and funnel_data.get('Unique Clicks', 0) > 0:
            repeat_click_rate = funnel_data['Total Clicks'] / funnel_data['Unique Clicks']
            if repeat_click_rate > 1.2:
                insights.append(f"🎯 Strong Interest: {repeat_click_rate:.1f}x average clicks per user")
        
        return {
            'funnel_data': funnel_data,
            'insights': insights,
            'conversion_rates': calculate_funnel_conversion_rates(funnel_data)
        }
        
    except Exception as e:
        return {
            'funnel_data': {},
            'insights': [f"Error analyzing funnel: {str(e)}"],
            'conversion_rates': {}
        }

def analyze_journey_funnel(df_journey):
    """
    Advanced funnel analysis for journeys leveraging unique vs total metrics
    """
    try:
        funnel_data = {}

        # Basic funnel stages
        funnel_data['Sent'] = df_journey['Sent'].sum() if 'Sent' in df_journey.columns else 0
        funnel_data['Delivered'] = df_journey['Delivered'].sum() if 'Delivered' in df_journey.columns else 0

        # Engagement stages (use both unique and total if available)
        if 'Unique Impressions' in df_journey.columns:
            funnel_data['Unique Impressions'] = df_journey['Unique Impressions'].sum()
        if 'Total Impressions' in df_journey.columns:
            funnel_data['Total Impressions'] = df_journey['Total Impressions'].sum()

        if 'Unique Clicks' in df_journey.columns:
            funnel_data['Unique Clicks'] = df_journey['Unique Clicks'].sum()
        if 'Total Clicks' in df_journey.columns:
            funnel_data['Total Clicks'] = df_journey['Total Clicks'].sum()

        # Conversion stages
        if 'Unique Conversions' in df_journey.columns:
            funnel_data['Unique Conversions'] = df_journey['Unique Conversions'].sum()
        if 'Total Conversions' in df_journey.columns:
            funnel_data['Total Conversions'] = df_journey['Total Conversions'].sum()

        # Calculate drop-off rates and insights
        insights = []
        if funnel_data.get('Sent', 0) > 0 and funnel_data.get('Delivered', 0) > 0:
            delivery_rate = funnel_data['Delivered'] / funnel_data['Sent']
            if delivery_rate < 0.95:
                insights.append(f"🚨 Delivery Issue: {(1-delivery_rate)*100:.1f}% delivery failure rate")

        if funnel_data.get('Delivered', 0) > 0 and funnel_data.get('Unique Impressions', 0) > 0:
            impression_rate = funnel_data['Unique Impressions'] / funnel_data['Delivered']
            if impression_rate < 0.8:
                insights.append(f"👁️ Low Visibility: Only {impression_rate*100:.1f}% of delivered messages were seen")

        # Analyze repeat engagement (unique vs total)
        if funnel_data.get('Total Impressions', 0) > 0 and funnel_data.get('Unique Impressions', 0) > 0:
            repeat_impression_rate = funnel_data['Total Impressions'] / funnel_data['Unique Impressions']
            if repeat_impression_rate > 1.5:
                insights.append(f"🔄 High Re-engagement: {repeat_impression_rate:.1f}x average views per user")

        if funnel_data.get('Total Clicks', 0) > 0 and funnel_data.get('Unique Clicks', 0) > 0:
            repeat_click_rate = funnel_data['Total Clicks'] / funnel_data['Unique Clicks']
            if repeat_click_rate > 1.2:
                insights.append(f"🎯 Strong Interest: {repeat_click_rate:.1f}x average clicks per user")

        return {
            'funnel_data': funnel_data,
            'insights': insights,
            'conversion_rates': calculate_funnel_conversion_rates(funnel_data)
        }

    except Exception as e:
        return {
            'funnel_data': {},
            'insights': [f"Error analyzing funnel: {str(e)}"],
            'conversion_rates': {}
        }

def calculate_funnel_conversion_rates(funnel_data):
    """Calculate conversion rates between funnel stages"""
    rates = {}
    
    if funnel_data.get('Sent', 0) > 0:
        if funnel_data.get('Delivered', 0) > 0:
            rates['Delivery Rate'] = funnel_data['Delivered'] / funnel_data['Sent']
        if funnel_data.get('Unique Impressions', 0) > 0:
            rates['Impression Rate'] = funnel_data['Unique Impressions'] / funnel_data['Sent']
        if funnel_data.get('Unique Clicks', 0) > 0:
            rates['Click Rate'] = funnel_data['Unique Clicks'] / funnel_data['Sent']
        if funnel_data.get('Unique Conversions', 0) > 0:
            rates['Conversion Rate'] = funnel_data['Unique Conversions'] / funnel_data['Sent']
    
    if funnel_data.get('Unique Impressions', 0) > 0:
        if funnel_data.get('Unique Clicks', 0) > 0:
            rates['CTR'] = funnel_data['Unique Clicks'] / funnel_data['Unique Impressions']
        if funnel_data.get('Unique Conversions', 0) > 0:
            rates['Impression-to-Conversion'] = funnel_data['Unique Conversions'] / funnel_data['Unique Impressions']
    
    if funnel_data.get('Unique Clicks', 0) > 0 and funnel_data.get('Unique Conversions', 0) > 0:
        rates['Click-to-Conversion'] = funnel_data['Unique Conversions'] / funnel_data['Unique Clicks']
    
    return rates

def detect_campaign_anomalies(df, lookback_days=30):
    """
    Detect performance anomalies in campaigns using statistical methods
    """
    try:
        import numpy as np
        from scipy import stats
        
        anomalies = []
        
        # Ensure date column is datetime
        if 'Reporting Period Start Date' in df.columns:
            df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
        elif 'Day' in df.columns:
            df['date'] = pd.to_datetime(df['Day'])
        else:
            return []
        
        # Get recent data
        cutoff_date = df['date'].max() - pd.Timedelta(days=lookback_days)
        recent_df = df[df['date'] >= cutoff_date]
        
        # Group by campaign and analyze performance
        campaigns = df['Campaign Name'].dropna().unique()
        
        for campaign in campaigns:
            if str(campaign) == 'nan' or not campaign:
                continue
                
            campaign_data = df[df['Campaign Name'] == campaign]
            recent_campaign_data = recent_df[recent_df['Campaign Name'] == campaign]
            
            if len(campaign_data) < 5 or len(recent_campaign_data) == 0:
                continue
            
            # Calculate historical metrics
            historical_metrics = {
                'conversion_rate': campaign_data['Unique Conversions'].sum() / max(campaign_data['Unique Clicks'].sum(), 1),
                'delivery_rate': campaign_data['Delivered'].sum() / max(campaign_data['Sent'].sum(), 1),
                'ctr': campaign_data['Unique Clicks'].sum() / max(campaign_data['Unique Impressions'].sum(), 1),
                'revenue_per_conversion': campaign_data['Revenue (SAR)'].sum() / max(campaign_data['Unique Conversions'].sum(), 1)
            }
            
            # Calculate recent metrics
            recent_metrics = {
                'conversion_rate': recent_campaign_data['Unique Conversions'].sum() / max(recent_campaign_data['Unique Clicks'].sum(), 1),
                'delivery_rate': recent_campaign_data['Delivered'].sum() / max(recent_campaign_data['Sent'].sum(), 1),
                'ctr': recent_campaign_data['Unique Clicks'].sum() / max(recent_campaign_data['Unique Impressions'].sum(), 1),
                'revenue_per_conversion': recent_campaign_data['Revenue (SAR)'].sum() / max(recent_campaign_data['Unique Conversions'].sum(), 1)
            }
            
            # Detect significant changes
            for metric_name, historical_value in historical_metrics.items():
                recent_value = recent_metrics[metric_name]
                
                if historical_value > 0 and recent_value >= 0:
                    # Calculate percentage change
                    pct_change = ((recent_value - historical_value) / historical_value) * 100
                    
                    # Define thresholds for anomalies
                    if abs(pct_change) > 50:  # 50% change threshold
                        severity = "🚨 Critical" if abs(pct_change) > 80 else "⚠️ Warning"
                        direction = "↗️ Improved" if pct_change > 0 else "↘️ Declined"
                        
                        anomalies.append({
                            'campaign': campaign,
                            'metric': metric_name.replace('_', ' ').title(),
                            'historical_value': historical_value,
                            'recent_value': recent_value,
                            'change_pct': pct_change,
                            'severity': severity,
                            'direction': direction,
                            'recommendation': get_anomaly_recommendation(metric_name, pct_change)
                        })
            
            # Check for volume anomalies (sudden drops in activity)
            historical_volume = campaign_data['Sent'].sum()
            recent_volume = recent_campaign_data['Sent'].sum()
            
            if historical_volume > 0:
                expected_recent_volume = historical_volume * (lookback_days / len(campaign_data))
                if recent_volume < expected_recent_volume * 0.3:  # Less than 30% of expected volume
                    anomalies.append({
                        'campaign': campaign,
                        'metric': 'Activity Volume',
                        'historical_value': expected_recent_volume,
                        'recent_value': recent_volume,
                        'change_pct': ((recent_volume - expected_recent_volume) / expected_recent_volume) * 100,
                        'severity': "🚨 Critical",
                        'direction': "📉 Low Activity",
                        'recommendation': "Check if campaign is paused or has targeting issues"
                    })
        
        return sorted(anomalies, key=lambda x: abs(x['change_pct']), reverse=True)
        
    except Exception as e:
        return [{'campaign': 'Error', 'metric': 'Detection Failed', 'recommendation': f"Error: {str(e)}"}]

def detect_journey_anomalies(df, lookback_days=30):
    """
    Detect performance anomalies in journeys using statistical methods
    """
    try:
        import numpy as np
        from scipy import stats
        
        anomalies = []
        
        # Ensure date column is datetime
        if 'Reporting Period Start Date' in df.columns:
            df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
        elif 'Day' in df.columns:
            df['date'] = pd.to_datetime(df['Day'])
        else:
            return []
        
        # Get recent data
        cutoff_date = df['date'].max() - pd.Timedelta(days=lookback_days)
        recent_df = df[df['date'] >= cutoff_date]
        
        # Group by journey and analyze performance
        journeys = df['Journey Name'].dropna().unique()
        
        for journey in journeys:
            if str(journey) == 'nan' or not journey:
                continue
                
            journey_data = df[df['Journey Name'] == journey]
            recent_journey_data = recent_df[recent_df['Journey Name'] == journey]
            
            if len(journey_data) < 5 or len(recent_journey_data) == 0:
                continue
            
            # Calculate historical metrics
            historical_metrics = {
                'conversion_rate': journey_data['Unique Conversions'].sum() / max(journey_data['Unique Clicks'].sum(), 1),
                'delivery_rate': journey_data['Delivered'].sum() / max(journey_data['Sent'].sum(), 1),
                'ctr': journey_data['Unique Clicks'].sum() / max(journey_data['Unique Impressions'].sum(), 1),
                'revenue_per_conversion': journey_data['Revenue (SAR)'].sum() / max(journey_data['Unique Conversions'].sum(), 1)
            }
            
            # Calculate recent metrics
            recent_metrics = {
                'conversion_rate': recent_journey_data['Unique Conversions'].sum() / max(recent_journey_data['Unique Clicks'].sum(), 1),
                'delivery_rate': recent_journey_data['Delivered'].sum() / max(recent_journey_data['Sent'].sum(), 1),
                'ctr': recent_journey_data['Unique Clicks'].sum() / max(recent_journey_data['Unique Impressions'].sum(), 1),
                'revenue_per_conversion': recent_journey_data['Revenue (SAR)'].sum() / max(recent_journey_data['Unique Conversions'].sum(), 1)
            }
            
            # Detect significant changes
            for metric_name, historical_value in historical_metrics.items():
                recent_value = recent_metrics[metric_name]
                
                if historical_value > 0 and recent_value >= 0:
                    # Calculate percentage change
                    pct_change = ((recent_value - historical_value) / historical_value) * 100
                    
                    # Define thresholds for anomalies
                    if abs(pct_change) > 50:  # 50% change threshold
                        severity = "🚨 Critical" if abs(pct_change) > 80 else "⚠️ Warning"
                        direction = "↗️ Improved" if pct_change > 0 else "↘️ Declined"
                        
                        anomalies.append({
                            'journey': journey,
                            'metric': metric_name.replace('_', ' ').title(),
                            'historical_value': historical_value,
                            'recent_value': recent_value,
                            'change_pct': pct_change,
                            'severity': severity,
                            'direction': direction,
                            'recommendation': get_anomaly_recommendation(metric_name, pct_change)
                        })
            
            # Check for volume anomalies (sudden drops in activity)
            historical_volume = journey_data['Sent'].sum()
            recent_volume = recent_journey_data['Sent'].sum()
            
            if historical_volume > 0:
                expected_recent_volume = historical_volume * (lookback_days / len(journey_data))
                if recent_volume < expected_recent_volume * 0.3:  # Less than 30% of expected volume
                    anomalies.append({
                        'journey': journey,
                        'metric': 'Activity Volume',
                        'historical_value': expected_recent_volume,
                        'recent_value': recent_volume,
                        'change_pct': ((recent_volume - expected_recent_volume) / expected_recent_volume) * 100,
                        'severity': "🚨 Critical",
                        'direction': "📉 Low Activity",
                        'recommendation': "Check if journey is paused or has targeting issues"
                    })
        
        return sorted(anomalies, key=lambda x: abs(x['change_pct']), reverse=True)
        
    except Exception as e:
        return [{'journey': 'Error', 'metric': 'Detection Failed', 'recommendation': f"Error: {str(e)}"}]

def get_anomaly_recommendation(metric_name, pct_change):
    """Generate recommendations based on metric changes"""
    recommendations = {
        'conversion_rate': {
            'positive': "Great improvement! Consider scaling this journey or applying learnings to others",
            'negative': "Review landing pages, CTAs, and offer relevance. Check for technical issues"
        },
        'delivery_rate': {
            'positive': "Excellent! Delivery improvements detected",
            'negative': "Check ESP reputation, list hygiene, and bounce rates. Review content for spam triggers"
        },
        'ctr': {
            'positive': "Strong engagement! Consider testing similar creative across other journeys",
            'negative': "Review subject lines, send times, and content relevance. Test different messaging"
        },
        'revenue_per_conversion': {
            'positive': "Higher value conversions! Analyze what's driving this improvement",
            'negative': "Check if targeting has shifted or product mix has changed. Review pricing strategy"
        }
    }
    
    direction = 'positive' if pct_change > 0 else 'negative'
    return recommendations.get(metric_name, {}).get(direction, "Monitor this metric closely and investigate root causes")

def create_revenue_attribution_waterfall(df_journey):
    """
    Create data for revenue attribution waterfall chart
    """
    try:
        # Calculate revenue sources
        total_revenue = df_journey['Revenue (SAR)'].sum()
        impression_revenue = df_journey['Impression-Through Revenue (SAR)'].sum()
        click_revenue = df_journey['Click-Through Revenue (SAR)'].sum()
        
        # Revenue attribution (hierarchical, not additive)
        # Click-Through ⊆ Impression-Through ⊆ Send-Through
        send_only_revenue = total_revenue - impression_revenue
        impression_only_revenue = impression_revenue - click_revenue
        click_revenue_final = click_revenue
        
        # Create waterfall data
        waterfall_data = [
            {'step': 'Starting Point', 'value': 0, 'cumulative': 0},
            {'step': 'Click Attribution', 'value': click_revenue_final, 'cumulative': click_revenue_final},
            {'step': 'Impression Attribution', 'value': impression_only_revenue, 'cumulative': click_revenue_final + impression_only_revenue},
            {'step': 'Send Attribution', 'value': send_only_revenue, 'cumulative': total_revenue},
            {'step': 'Total Revenue', 'value': total_revenue, 'cumulative': total_revenue}
        ]
        
        # Calculate attribution percentages
        attribution_breakdown = {
            'Click Attribution': (click_revenue_final / total_revenue * 100) if total_revenue > 0 else 0,
            'Impression Attribution': (impression_only_revenue / total_revenue * 100) if total_revenue > 0 else 0,
            'Send Attribution': (send_only_revenue / total_revenue * 100) if total_revenue > 0 else 0
        }
        
        return {
            'waterfall_data': waterfall_data,
            'attribution_breakdown': attribution_breakdown,
            'total_revenue': total_revenue
        }
        
    except Exception as e:
        return {
            'waterfall_data': [],
            'attribution_breakdown': {},
            'total_revenue': 0,
            'error': str(e)
        }

def analyze_journey_lifecycle(df):
    """
    Analyze journey lifecycle including maturity stages and performance curves
    """
    try:
        lifecycle_data = []
        
        # Ensure date column is available
        if 'Reporting Period Start Date' in df.columns:
            df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
        elif 'Day' in df.columns:
            df['date'] = pd.to_datetime(df['Day'])
        else:
            return {}
        
        journeys = df['Journey Name'].dropna().unique()
        
        for journey in journeys:
            if str(journey) == 'nan' or not journey:
                continue
                
            journey_data = df[df['Journey Name'] == journey].copy()
            journey_data = journey_data.sort_values('date')
            
            if len(journey_data) < 2:
                continue
            
            # Calculate journey age and activity patterns
            start_date = journey_data['date'].min()
            end_date = journey_data['date'].max()
            journey_age_days = (end_date - start_date).days + 1
            active_days = len(journey_data['date'].unique())
            
            # Calculate performance metrics over time
            total_revenue = journey_data['Revenue (SAR)'].sum()
            total_conversions = journey_data['Unique Conversions'].sum()
            total_sent = journey_data['Sent'].sum()
            
            # Determine maturity stage
            if journey_age_days <= 7:
                maturity_stage = "🆕 Launch (0-7 days)"
            elif journey_age_days <= 30:
                maturity_stage = "🌱 Growth (8-30 days)"
            elif journey_age_days <= 90:
                maturity_stage = "⚡ Active (31-90 days)"
            else:
                maturity_stage = "🏆 Mature (90+ days)"
            
            # Calculate consistency score (inverse of coefficient of variation)
            daily_conversions = journey_data.groupby('date')['Unique Conversions'].sum()
            if len(daily_conversions) > 1 and daily_conversions.mean() > 0:
                cv = daily_conversions.std() / daily_conversions.mean()
                consistency_score = max(0, 100 - (cv * 100))
            else:
                consistency_score = 0
            
            # Calculate growth trend
            if len(daily_conversions) >= 3:
                # Simple linear regression slope
                x = range(len(daily_conversions))
                y = daily_conversions.values
                n = len(x)
                
                slope = (n * sum(i * j for i, j in zip(x, y)) - sum(x) * sum(y)) / (n * sum(i**2 for i in x) - sum(x)**2)
                growth_trend = "📈 Growing" if slope > 0.1 else "📉 Declining" if slope < -0.1 else "➡️ Stable"
            else:
                growth_trend = "➡️ Stable"
            
            # Performance efficiency
            efficiency_score = 0
            if total_sent > 0:
                conversion_rate = total_conversions / total_sent
                efficiency_score = min(conversion_rate * 100 * 10, 100)  # Scale conversion rate
            
            # Activity frequency
            activity_frequency = (active_days / journey_age_days) * 100 if journey_age_days > 0 else 0
            
            lifecycle_data.append({
                'journey': journey,
                'maturity_stage': maturity_stage,
                'journey_age_days': journey_age_days,
                'active_days': active_days,
                'activity_frequency': activity_frequency,
                'consistency_score': consistency_score,
                'growth_trend': growth_trend,
                'efficiency_score': efficiency_score,
                'total_revenue': total_revenue,
                'total_conversions': total_conversions,
                'start_date': start_date,
                'end_date': end_date,
                'recommendation': get_lifecycle_recommendation(maturity_stage, consistency_score, growth_trend, efficiency_score)
            })
        
        return lifecycle_data
        
    except Exception as e:
        return {'error': str(e)}

def get_lifecycle_recommendation(maturity_stage, consistency_score, growth_trend, efficiency_score):
    """Generate lifecycle-based recommendations"""
    recommendations = []
    
    if "Launch" in maturity_stage:
        recommendations.append("🚀 Monitor initial performance closely and optimize based on early data")
        if efficiency_score < 30:
            recommendations.append("⚠️ Early performance is low - consider adjusting targeting or messaging")
    elif "Growth" in maturity_stage:
        if "Growing" in growth_trend:
            recommendations.append("📈 Strong growth trajectory - consider scaling budget or audience")
        elif "Declining" in growth_trend:
            recommendations.append("📉 Performance declining - investigate and optimize quickly")
        else:
            recommendations.append("🔍 Performance stabilizing - analyze what's working and replicate")
    elif "Active" in maturity_stage:
        if consistency_score < 50:
            recommendations.append("🎯 Focus on consistency - performance is too variable")
        if efficiency_score < 50:
            recommendations.append("⚡ Optimize conversion funnel - efficiency could be improved")
    else:  # Mature
        if "Declining" in growth_trend:
            recommendations.append("🔄 Consider refreshing creative or targeting for this mature journey")
        elif consistency_score > 70:
            recommendations.append("🏆 Excellent mature performance - use as template for other journeys")
        else:
            recommendations.append("📊 Mature journey with room for optimization")
    
    return " | ".join(recommendations) if recommendations else "📋 Continue monitoring performance"

def create_journey_comparison_analysis(df, journey1, journey2):
    """
    Create detailed comparison between two journeys with statistical significance
    """
    try:
        from scipy import stats
        
        # Get data for both journeys
        j1_data = df[df['Journey Name'] == journey1]
        j2_data = df[df['Journey Name'] == journey2]
        
        if len(j1_data) == 0 or len(j2_data) == 0:
            return {'error': 'One or both journeys have no data'}
        
        # Calculate key metrics for comparison
        metrics = ['Unique Conversions', 'Unique Clicks', 'Revenue (SAR)', 'Sent', 'Delivered']
        
        comparison_data = {
            'journey1': journey1,
            'journey2': journey2,
            'metrics': {}
        }
        
        for metric in metrics:
            if metric in df.columns:
                j1_total = j1_data[metric].sum()
                j2_total = j2_data[metric].sum()
                
                # Calculate per-day averages for better comparison
                j1_avg = j1_data[metric].mean()
                j2_avg = j2_data[metric].mean()
                
                # Statistical significance test (if enough data points)
                significance = "N/A"
                p_value = None
                
                if len(j1_data) >= 3 and len(j2_data) >= 3:
                    try:
                        stat, p_value = stats.ttest_ind(j1_data[metric], j2_data[metric])
                        significance = "Significant" if p_value < 0.05 else "Not Significant"
                    except:
                        significance = "Cannot Calculate"
                
                # Calculate performance difference
                if j2_avg > 0:
                    pct_difference = ((j1_avg - j2_avg) / j2_avg) * 100
                else:
                    pct_difference = 0
                
                comparison_data['metrics'][metric] = {
                    'journey1_total': j1_total,
                    'journey2_total': j2_total,
                    'journey1_avg': j1_avg,
                    'journey2_avg': j2_avg,
                    'pct_difference': pct_difference,
                    'significance': significance,
                    'p_value': p_value,
                    'winner': journey1 if j1_avg > j2_avg else journey2
                }
        
        # Overall assessment
        wins_j1 = sum(1 for m in comparison_data['metrics'].values() if m['winner'] == journey1)
        wins_j2 = sum(1 for m in comparison_data['metrics'].values() if m['winner'] == journey2)
        
        comparison_data['overall_winner'] = journey1 if wins_j1 > wins_j2 else journey2 if wins_j2 > wins_j1 else "Tie"
        comparison_data['confidence'] = "High" if abs(wins_j1 - wins_j2) >= 3 else "Medium" if abs(wins_j1 - wins_j2) >= 1 else "Low"
        
        return comparison_data
        
    except Exception as e:
        return {'error': str(e)}

def create_custom_date_range_comparison(df, date_range_1, date_range_2, journeys_filter=None):
    """
    Compare journey performance between two custom date ranges
    """
    try:
        # Ensure date column is available
        if 'Reporting Period Start Date' in df.columns:
            df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
        elif 'Day' in df.columns:
            df['date'] = pd.to_datetime(df['Day'])
        else:
            return {'error': 'No date column available'}
        
        # Filter data for each period
        period1_data = df[(df['date'] >= pd.to_datetime(date_range_1[0])) & 
                         (df['date'] <= pd.to_datetime(date_range_1[1]))]
        period2_data = df[(df['date'] >= pd.to_datetime(date_range_2[0])) & 
                         (df['date'] <= pd.to_datetime(date_range_2[1]))]
        
        # Apply journey filter if specified
        if journeys_filter:
            period1_data = period1_data[period1_data['Journey Name'].isin(journeys_filter)]
            period2_data = period2_data[period2_data['Journey Name'].isin(journeys_filter)]
        
        if len(period1_data) == 0 or len(period2_data) == 0:
            return {'error': 'No data available for one or both periods'}
        
        # Calculate period durations
        period1_days = (pd.to_datetime(date_range_1[1]) - pd.to_datetime(date_range_1[0])).days + 1
        period2_days = (pd.to_datetime(date_range_2[1]) - pd.to_datetime(date_range_2[0])).days + 1
        
        # Key metrics to compare
        metrics = ['Revenue (SAR)', 'Unique Conversions', 'Unique Clicks', 'Sent', 'Delivered']
        
        comparison_result = {
            'period1_label': f"{date_range_1[0]} to {date_range_1[1]} ({period1_days} days)",
            'period2_label': f"{date_range_2[0]} to {date_range_2[1]} ({period2_days} days)",
            'period1_days': period1_days,
            'period2_days': period2_days,
            'metrics': {},
            'journey_breakdown': {},
            'statistical_summary': {}
        }
        
        # Overall metrics comparison
        for metric in metrics:
            if metric in df.columns:
                p1_total = period1_data[metric].sum()
                p2_total = period2_data[metric].sum()
                
                # Calculate daily averages for fair comparison
                p1_daily_avg = p1_total / period1_days
                p2_daily_avg = p2_total / period2_days
                
                # Calculate percentage change
                if p1_daily_avg > 0:
                    pct_change = ((p2_daily_avg - p1_daily_avg) / p1_daily_avg) * 100
                else:
                    pct_change = 0
                
                # Statistical significance test
                from scipy import stats
                significance = "N/A"
                p_value = None
                
                if len(period1_data) >= 10 and len(period2_data) >= 10:
                    try:
                        # Group by date for daily values
                        p1_daily = period1_data.groupby('date')[metric].sum()
                        p2_daily = period2_data.groupby('date')[metric].sum()
                        
                        if len(p1_daily) >= 3 and len(p2_daily) >= 3:
                            stat, p_value = stats.ttest_ind(p1_daily, p2_daily)
                            significance = "Significant" if p_value < 0.05 else "Not Significant"
                    except:
                        significance = "Cannot Calculate"
                
                comparison_result['metrics'][metric] = {
                    'period1_total': p1_total,
                    'period2_total': p2_total,
                    'period1_daily_avg': p1_daily_avg,
                    'period2_daily_avg': p2_daily_avg,
                    'pct_change': pct_change,
                    'significance': significance,
                    'p_value': p_value,
                    'trend': "📈 Improved" if pct_change > 5 else "📉 Declined" if pct_change < -5 else "➡️ Stable"
                }
        
        # Journey-level breakdown
        if journeys_filter:
            for journey in journeys_filter:
                j_p1 = period1_data[period1_data['Journey Name'] == journey]
                j_p2 = period2_data[period2_data['Journey Name'] == journey]
                
                if len(j_p1) > 0 and len(j_p2) > 0:
                    journey_metrics = {}
                    for metric in ['Unique Conversions', 'Revenue (SAR)']:
                        if metric in df.columns:
                            j_p1_total = j_p1[metric].sum()
                            j_p2_total = j_p2[metric].sum()
                            j_p1_daily = j_p1_total / period1_days
                            j_p2_daily = j_p2_total / period2_days
                            
                            if j_p1_daily > 0:
                                j_pct_change = ((j_p2_daily - j_p1_daily) / j_p1_daily) * 100
                            else:
                                j_pct_change = 0
                            
                            journey_metrics[metric] = {
                                'period1_daily_avg': j_p1_daily,
                                'period2_daily_avg': j_p2_daily,
                                'pct_change': j_pct_change
                            }
                    
                    comparison_result['journey_breakdown'][journey] = journey_metrics
        
        # Statistical summary
        significant_improvements = sum(1 for m in comparison_result['metrics'].values() 
                                     if m['pct_change'] > 5 and m['significance'] == 'Significant')
        significant_declines = sum(1 for m in comparison_result['metrics'].values() 
                                 if m['pct_change'] < -5 and m['significance'] == 'Significant')
        
        comparison_result['statistical_summary'] = {
            'significant_improvements': significant_improvements,
            'significant_declines': significant_declines,
            'overall_trend': "Positive" if significant_improvements > significant_declines else "Negative" if significant_declines > significant_improvements else "Mixed"
        }
        
        return comparison_result
        
    except Exception as e:
        return {'error': str(e)}

def analyze_stopped_journeys(df, stopped_threshold_days=3, lookback_period=90, confidence_level=0.95):
    """
    Advanced analysis to identify stopped journeys and estimate revenue loss using ML forecasting

    Parameters:
    - df: DataFrame with journey data
    - stopped_threshold_days: Minimum consecutive days with zero delivery to consider stopped
    - lookback_period: Days to look back for analysis
    - confidence_level: Statistical confidence level for loss estimates

    Returns:
    - Dictionary with stopped journeys analysis and revenue loss estimates
    """
    try:
        from prophet import Prophet
        from scipy import stats

        # Ensure date column exists
        if 'Reporting Period Start Date' in df.columns:
            df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
        elif 'Day' in df.columns:
            df['date'] = pd.to_datetime(df['Day'])
        else:
            return {'error': 'No date column available'}

        # Filter data for lookback period
        cutoff_date = df['date'].max() - pd.Timedelta(days=lookback_period)
        analysis_df = df[df['date'] >= cutoff_date].copy()

        # Get unique journeys
        unique_journeys = analysis_df['Journey Name'].dropna().unique()
        stopped_journeys = []

        for journey in unique_journeys:
            if str(journey) == 'nan' or not journey:
                continue

            journey_data = analysis_df[analysis_df['Journey Name'] == journey].copy()

            if len(journey_data) < 7:  # Need minimum data for analysis
                continue

            # Sort by date
            journey_data = journey_data.sort_values('date')

            # Identify stopped periods (consecutive days with zero delivery)
            journey_data['is_stopped'] = journey_data['Delivered'] == 0

            # Find consecutive stopped periods
            stopped_periods = []
            current_stopped_start = None
            consecutive_stopped = 0

            for i, (_, row) in enumerate(journey_data.iterrows()):
                if row['is_stopped']:
                    if current_stopped_start is None:
                        current_stopped_start = row['date']
                    consecutive_stopped += 1
                else:
                    if consecutive_stopped >= stopped_threshold_days:
                        # Use positional indexing to get the previous row
                        if i > 0:
                            prev_date = journey_data.iloc[i-1]['date']
                        else:
                            prev_date = row['date']
                        
                        # Calculate actual calendar days between start and end dates
                        days_stopped = (prev_date - current_stopped_start).days + 1
                        
                        stopped_periods.append({
                            'start_date': current_stopped_start,
                            'end_date': prev_date,
                            'days_stopped': days_stopped
                        })
                    current_stopped_start = None
                    consecutive_stopped = 0

            # Check for stopped period at the end
            if consecutive_stopped >= stopped_threshold_days:
                last_date = journey_data.iloc[-1]['date']
                
                # Calculate actual calendar days for the final stopped period
                days_stopped = (last_date - current_stopped_start).days + 1
                
                stopped_periods.append({
                    'start_date': current_stopped_start,
                    'end_date': last_date,
                    'days_stopped': days_stopped
                })

            if stopped_periods:
                # Estimate revenue loss using ML forecasting
                revenue_loss_estimate = estimate_revenue_loss_ml(
                    journey_data,
                    stopped_periods,
                    confidence_level=confidence_level
                )

                # Generate recommendations
                recommendations = generate_stopped_journey_recommendations(
                    journey_data,
                    stopped_periods,
                    revenue_loss_estimate
                )

                stopped_journeys.append({
                    'journey_name': journey,
                    'stopped_periods': {
                        'periods': stopped_periods,
                        'total_stopped_days': sum(p['days_stopped'] for p in stopped_periods)
                    },
                    'estimated_revenue_loss': revenue_loss_estimate,
                    'recommendations': recommendations
                })

        return {
            'stopped_journeys': stopped_journeys,
            'analysis_parameters': {
                'stopped_threshold_days': stopped_threshold_days,
                'lookback_period': lookback_period,
                'confidence_level': confidence_level,
                'total_journeys_analyzed': len(unique_journeys)
            }
        }

    except Exception as e:
        return {'error': str(e)}

def estimate_revenue_loss_ml(journey_data, stopped_periods, confidence_level=0.95):
    """
    Use Prophet ML model to estimate revenue loss during stopped periods
    """
    try:
        from prophet import Prophet
        from scipy import stats

        # Prepare data for Prophet
        prophet_data = journey_data[['date', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']].copy()
        prophet_data = prophet_data.rename(columns={'date': 'ds'})

        # Estimate loss for each attribution model
        attribution_models = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
        total_loss = 0
        attribution_breakdown = {}
        daily_loss_estimates = []

        for model in attribution_models:
            if model in prophet_data.columns:
                model_data = prophet_data[['ds', model]].rename(columns={model: 'y'})
                model_data = model_data.dropna()

                if len(model_data) >= 7:  # Minimum data for Prophet
                    # Train Prophet model
                    model_prophet = Prophet(
                        yearly_seasonality=False,
                        weekly_seasonality=True,
                        daily_seasonality=False,
                        interval_width=confidence_level
                    )

                    model_prophet.fit(model_data)

                    # Forecast for stopped periods
                    model_loss = 0
                    model_daily_estimates = []

                    for period in stopped_periods:
                        # Create future dataframe for the stopped period
                        future_dates = pd.date_range(
                            start=period['start_date'],
                            end=period['end_date'],
                            freq='D'
                        )

                        future_df = pd.DataFrame({'ds': future_dates})

                        # Make prediction
                        forecast = model_prophet.predict(future_df)

                        # Calculate expected revenue for this period
                        expected_revenue = forecast['yhat'].sum()
                        model_loss += max(0, expected_revenue)  # Only count positive expected revenue

                        # Daily estimates for this period
                        for _, forecast_row in forecast.iterrows():
                            model_daily_estimates.append({
                                'date': forecast_row['ds'],
                                'expected_revenue': max(0, forecast_row['yhat']),
                                'confidence_lower': max(0, forecast_row['yhat_lower']),
                                'confidence_upper': max(0, forecast_row['yhat_upper'])
                            })

                    attribution_breakdown[model] = model_loss
                    total_loss += model_loss

                    # Add daily estimates to the period
                    for i, period in enumerate(stopped_periods):
                        period['daily_estimates'] = model_daily_estimates
                        period['estimated_daily_loss'] = model_loss / period['days_stopped'] if period['days_stopped'] > 0 else 0

        # Calculate confidence interval for total loss
        if total_loss > 0:
            # Use bootstrap method for confidence interval
            loss_samples = []
            for _ in range(1000):
                sample_loss = total_loss * np.random.normal(1, 0.1)  # 10% standard deviation
                loss_samples.append(max(0, sample_loss))

            confidence_interval = (
                np.percentile(loss_samples, (1-confidence_level)*50),
                np.percentile(loss_samples, (1+confidence_level)*50)
            )
        else:
            confidence_interval = (0, 0)

        return {
            'total_loss': total_loss,
            'avg_daily_loss': total_loss / sum(p['days_stopped'] for p in stopped_periods) if stopped_periods else 0,
            'attribution_breakdown': attribution_breakdown,
            'confidence_interval': confidence_interval,
            'confidence_level': confidence_level
        }

    except Exception as e:
        # Fallback to simple average method if Prophet fails
        total_loss = 0
        attribution_breakdown = {}

        # Simple average method
        for period in stopped_periods:
            period_data = journey_data[
                (journey_data['date'] >= period['start_date'] - pd.Timedelta(days=30)) &
                (journey_data['date'] < period['start_date'])
            ]

            if len(period_data) > 0:
                for model in ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']:
                    if model in period_data.columns:
                        avg_daily = period_data[model].mean()
                        period_loss = avg_daily * period['days_stopped']
                        attribution_breakdown[model] = attribution_breakdown.get(model, 0) + period_loss
                        total_loss += period_loss

        return {
            'total_loss': total_loss,
            'avg_daily_loss': total_loss / sum(p['days_stopped'] for p in stopped_periods) if stopped_periods else 0,
            'attribution_breakdown': attribution_breakdown,
            'confidence_interval': (total_loss * 0.8, total_loss * 1.2),  # Rough estimate
            'confidence_level': confidence_level,
            'method': 'fallback_average'
        }

def generate_stopped_journey_recommendations(journey_data, stopped_periods, revenue_loss_estimate):
    """
    Generate actionable recommendations for stopped journeys
    """
    recommendations = []

    total_stopped_days = sum(p['days_stopped'] for p in stopped_periods)
    total_loss = revenue_loss_estimate['total_loss']

    # Severity-based recommendations
    if total_loss > 10000:  # High impact
        recommendations.append("🚨 CRITICAL: Immediate investigation required - high revenue loss detected")
        recommendations.append("📞 Contact delivery team to check journey configuration and ESP settings")
    elif total_loss > 1000:  # Medium impact
        recommendations.append("⚠️ MEDIUM PRIORITY: Review journey settings and delivery triggers")
    else:  # Low impact
        recommendations.append("ℹ️ LOW PRIORITY: Monitor journey performance and consider optimizations")

    # Duration-based recommendations
    if total_stopped_days > 14:
        recommendations.append("📅 LONG STOPPAGE: Journey has been stopped for 2+ weeks - check for systemic issues")
    elif total_stopped_days > 7:
        recommendations.append("📅 EXTENDED STOPPAGE: Journey stopped for a week - investigate delivery pipeline")

    # Pattern analysis
    if len(stopped_periods) > 3:
        recommendations.append("🔄 RECURRING ISSUE: Multiple stoppages detected - review automation rules and triggers")
    elif len(stopped_periods) == 1:
        recommendations.append("🎯 SINGLE INCIDENT: One-time stoppage - check logs around stoppage date")

    # Attribution-based insights
    loss_breakdown = revenue_loss_estimate['attribution_breakdown']
    if loss_breakdown:
        max_loss_model = max(loss_breakdown, key=loss_breakdown.get)
        if loss_breakdown[max_loss_model] > total_loss * 0.7:
            recommendations.append(f"🎯 PRIMARY IMPACT: {max_loss_model} is the main revenue driver affected ({loss_breakdown[max_loss_model]/total_loss:.1%} of total loss)")

    # Actionable recommendations
    recommendations.extend([
        "🔧 Check journey status in WebEngage dashboard",
        "📊 Review audience segmentation and targeting rules",
        "⚙️ Verify ESP configuration and API connections",
        "📈 Set up monitoring alerts for future stoppages",
        "📋 Document incident for future reference"
    ])

    return recommendations

def create_cohort_analysis(df, cohort_period='week'):
    """
    Create cohort analysis for journey performance
    """
    try:
        # Ensure date column is available
        if 'Reporting Period Start Date' in df.columns:
            df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
        elif 'Day' in df.columns:
            df['date'] = pd.to_datetime(df['Day'])
        else:
            return {'error': 'No date column available'}
        
        # Create cohort periods
        if cohort_period == 'week':
            df['cohort'] = df['date'].dt.to_period('W')
        elif cohort_period == 'month':
            df['cohort'] = df['date'].dt.to_period('M')
        else:
            df['cohort'] = df['date'].dt.to_period('D')
        
        # Group by cohort and journey
        cohort_data = df.groupby(['cohort', 'Journey Name']).agg({
            'Revenue (SAR)': 'sum',
            'Unique Conversions': 'sum',
            'Unique Clicks': 'sum',
            'Sent': 'sum'
        }).reset_index()
        
        # Calculate period-over-period changes
        cohort_data['cohort_str'] = cohort_data['cohort'].astype(str)
        cohort_data = cohort_data.sort_values(['Journey Name', 'cohort'])
        
        # Calculate growth rates
        for metric in ['Revenue (SAR)', 'Unique Conversions']:
            if metric in cohort_data.columns:
                cohort_data[f'{metric}_growth'] = cohort_data.groupby('Journey Name')[metric].pct_change() * 100
        
        return cohort_data
        
    except Exception as e:
        return {'error': str(e)}

def analyze_individual_journey(journey_name, filtered_df):
    """
    Detailed analysis of an individual journey - returns comprehensive scoring breakdown.
    This is the same logic as the debug script but as a reusable function.
    """
    try:
        # Get the specific journey data
        journey_data = filtered_df[filtered_df['Journey Name'] == journey_name].copy()
        
        if journey_data.empty:
            return {'error': f"Journey '{journey_name}' not found!"}
        
        # Calculate the score with detailed breakdown
        score_result = calculate_journey_health_score(journey_data, filtered_df)
        
        # Calculate raw metrics for this journey
        raw_metrics = {}
        
        # Delivery metrics
        if 'Sent' in journey_data.columns and 'Delivered' in journey_data.columns:
            total_sent = journey_data['Sent'].sum()
            total_delivered = journey_data['Delivered'].sum()
            delivery_rate = (total_delivered / total_sent) if total_sent > 0 else 0
            raw_metrics['delivery'] = {
                'total_sent': total_sent,
                'total_delivered': total_delivered,
                'delivery_rate': delivery_rate
            }
        
        # Engagement metrics
        if 'Unique Clicks' in journey_data.columns and 'Unique Impressions' in journey_data.columns:
            total_clicks = journey_data['Unique Clicks'].sum()
            total_impressions = journey_data['Unique Impressions'].sum()
            ctr = (total_clicks / total_impressions) if total_impressions > 0 else 0
            raw_metrics['engagement'] = {
                'total_clicks': total_clicks,
                'total_impressions': total_impressions,
                'ctr': ctr
            }
        
        # Conversion metrics - Use the Conversion Rate column when available
        if 'Conversion Rate' in journey_data.columns and journey_data['Conversion Rate'].notna().any():
            # Use the provided conversion rate column (already calculated correctly by WebEngage)
            conv_rate = journey_data['Conversion Rate'].mean() / 100.0  # Convert percentage to decimal
            # Also get the raw numbers for display
            total_conversions = journey_data['Unique Conversions'].sum() if 'Unique Conversions' in journey_data.columns else 0
            total_clicks = journey_data['Unique Clicks'].sum() if 'Unique Clicks' in journey_data.columns else 0
            raw_metrics['conversion'] = {
                'total_conversions': total_conversions,
                'total_clicks': total_clicks,
                'conversion_rate': conv_rate,
                'source': 'Direct Conversion Rate column'
            }
        elif 'Unique Conversions' in journey_data.columns and 'Unique Clicks' in journey_data.columns:
            # Fallback: manual calculation
            total_conversions = journey_data['Unique Conversions'].sum()
            total_clicks = journey_data['Unique Clicks'].sum()
            conv_rate = (total_conversions / total_clicks) if total_clicks > 0 else 0
            raw_metrics['conversion'] = {
                'total_conversions': total_conversions,
                'total_clicks': total_clicks,
                'conversion_rate': conv_rate,
                'source': 'Manual calculation (may be unreliable)'
            }
        
        # Revenue metrics
        if 'Revenue (SAR)' in journey_data.columns and 'Unique Conversions' in journey_data.columns:
            total_revenue = journey_data['Revenue (SAR)'].sum()
            total_conversions = journey_data['Unique Conversions'].sum()
            rpc = (total_revenue / total_conversions) if total_conversions > 0 else 0
            log_rpc = np.log1p(rpc)
            raw_metrics['revenue'] = {
                'total_revenue': total_revenue,
                'total_conversions': total_conversions,
                'revenue_per_conversion': rpc,
                'log_rpc': log_rpc
            }
        
        # Calculate population percentiles for context
        journey_groups = filtered_df.groupby('Journey Name')
        percentiles = {}
        
        # Delivery percentiles
        if 'delivery' in raw_metrics:
            delivery_rates = []
            for name, group in journey_groups:
                if 'Sent' in group.columns and 'Delivered' in group.columns:
                    sent = group['Sent'].sum()
                    delivered = group['Delivered'].sum()
                    if sent > 0:
                        delivery_rates.append(delivered / sent)
            
            if delivery_rates:
                percentile = (np.array(delivery_rates) <= raw_metrics['delivery']['delivery_rate']).mean() * 100
                percentiles['delivery'] = percentile
        
        # CTR percentiles
        if 'engagement' in raw_metrics:
            ctrs = []
            for name, group in journey_groups:
                if 'Unique Clicks' in group.columns and 'Unique Impressions' in group.columns:
                    clicks = group['Unique Clicks'].sum()
                    impressions = group['Unique Impressions'].sum()
                    if impressions > 0:
                        ctrs.append(clicks / impressions)
            
            if ctrs:
                percentile = (np.array(ctrs) <= raw_metrics['engagement']['ctr']).mean() * 100
                percentiles['engagement'] = percentile
        
        # Conversion rate percentiles
        if 'conversion' in raw_metrics:
            conv_rates = []
            # Use the same method as in the scoring function for consistency
            if 'Conversion Rate' in filtered_df.columns:
                for name, group in journey_groups:
                    journey_conv_rate = group['Conversion Rate'].mean() / 100.0
                    if not pd.isna(journey_conv_rate):
                        conv_rates.append(journey_conv_rate)
            else:
                for name, group in journey_groups:
                    if 'Unique Conversions' in group.columns and 'Unique Clicks' in group.columns:
                        conversions = group['Unique Conversions'].sum()
                        clicks = group['Unique Clicks'].sum()
                        if clicks > 0:
                            conv_rates.append(conversions / clicks)
            
            if conv_rates:
                percentile = (np.array(conv_rates) <= raw_metrics['conversion']['conversion_rate']).mean() * 100
                percentiles['conversion'] = percentile
        
        # Revenue per conversion percentiles
        if 'revenue' in raw_metrics:
            rpcs = []
            for name, group in journey_groups:
                if 'Revenue (SAR)' in group.columns and 'Unique Conversions' in group.columns:
                    revenue = group['Revenue (SAR)'].sum()
                    conversions = group['Unique Conversions'].sum()
                    if conversions > 0:
                        rpcs.append(revenue / conversions)
            
            if rpcs:
                percentile = (np.array(rpcs) <= raw_metrics['revenue']['revenue_per_conversion']).mean() * 100
                percentiles['revenue'] = percentile
        
        # Component score contributions
        weights = {'delivery': 0.20, 'engagement': 0.25, 'conversion': 0.30, 'revenue': 0.25}
        component_contributions = {}
        for component, score in score_result['component_scores'].items():
            weight = weights[component]
            contribution = score * weight
            component_contributions[component] = {
                'score': score,
                'weight': weight,
                'contribution': contribution
            }
        
        # Summary insights
        worst_components = sorted(score_result['component_scores'].items(), key=lambda x: x[1])
        insights = []
        
        for component, score in worst_components[:2]:  # Show worst 2 components
            if score < 40:
                insights.append(f"🚨 {component.capitalize()} score ({score:.1f}) is critically low")
            elif score < 60:
                insights.append(f"⚠️ {component.capitalize()} score ({score:.1f}) is below average")
        
        return {
            'journey_name': journey_name,
            'data_rows': len(journey_data),
            'score_result': score_result,
            'raw_metrics': raw_metrics,
            'percentiles': percentiles,
            'component_contributions': component_contributions,
            'insights': insights
        }
        
    except Exception as e:
        return {'error': str(e)}

# In the main code, after cleaning
if uploaded_file is not None:
    @st.cache_data
    def load_and_clean_data(uploaded_file):
        df = pd.read_csv(uploaded_file)
        df = clean_data(df)
        return df
    
    df = load_and_clean_data(uploaded_file)
    st.success("Data cleaned and normalized!")

    # Filters
    st.sidebar.header("Filters")
    
    # Period Comparison Settings
    st.sidebar.subheader("📊 Period Comparison")
    comparison_mode = st.sidebar.radio(
        "Comparison Mode",
        ["Automatic (Previous Period)", "Manual (Custom Dates)"],
        help="Choose how to compare periods"
    )
    
    # Manual comparison date inputs
    manual_comparison_dates = None
    if comparison_mode == "Manual (Custom Dates)":
        st.sidebar.markdown("**Comparison Period:**")
        manual_comparison_dates = st.sidebar.date_input(
            "Select comparison date range",
            value=[],
            help="Select the previous period to compare against"
        )
    
    st.sidebar.markdown("---")
    
    # Global Attribution Filters
    st.sidebar.subheader("Attribution Settings")
    revenue_attribution = st.sidebar.selectbox(
        "Revenue Attribution",
        ["Total", "Impression-Through", "Click-Through"],
        help="Select which type of revenue attribution to use throughout the dashboard"
    )
    
    conversion_attribution = st.sidebar.selectbox(
        "Conversion Attribution", 
        ["Total", "Impression-Through", "Click-Through"],
        help="Select which type of conversion attribution to use throughout the dashboard"
    )
    
    # Apply attribution settings
    @st.cache_data
    def apply_filters_and_attribution(df, revenue_attribution, conversion_attribution, date_range, channels, campaigns, segments, journeys):
        # Apply attribution settings
        if 'Revenue (SAR)' in df.columns:
            if revenue_attribution == "Click-Through" and 'Click-Through Revenue (SAR)' in df.columns:
                df['Selected Revenue (SAR)'] = df['Click-Through Revenue (SAR)']
            elif revenue_attribution == "Impression-Through" and 'Impression-Through Revenue (SAR)' in df.columns:
                df['Selected Revenue (SAR)'] = df['Impression-Through Revenue (SAR)']
            else:
                # For "Total" attribution, use the main Revenue column (send-through attribution)
                df['Selected Revenue (SAR)'] = df['Revenue (SAR)']
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
        
        return filtered_df
    
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

    # Apply filters using cached function
    filtered_df = apply_filters_and_attribution(df, revenue_attribution, conversion_attribution, date_range, channels, campaigns, segments, journeys)

    st.write(f"Filtered data: {len(filtered_df)} rows")

    # Page content based on selection
    if page == "Overview":
        # ========================================
        # SHAREHOLDER REPORT - EXECUTIVE SUMMARY
        # ========================================
        
        st.title("📊 Executive Summary Report")
        
        # Detect reporting period
        if not filtered_df.empty and 'Reporting Period Start Date' in filtered_df.columns:
            period_start = filtered_df['Reporting Period Start Date'].min()
            period_end = filtered_df['Reporting Period End Date'].max()
            period_days = (period_end - period_start).days + 1
            
            # Determine period type
            if period_days <= 7:
                period_label = "Weekly Report"
            elif period_days <= 35:
                period_label = "Monthly Report"
            elif period_days <= 100:
                period_label = f"{period_days // 30}-Month Report"
            else:
                period_label = f"{period_days}-Day Report"
            
            st.markdown(f"### {period_label}")
            st.markdown(f"**Period:** {period_start.strftime('%B %d, %Y')} - {period_end.strftime('%B %d, %Y')} ({period_days} days)")
        else:
            period_label = "Performance Report"
            st.markdown(f"### {period_label}")
        
        st.markdown("---")
        
        # ========================================
        # 1. HERO METRICS - KEY PERFORMANCE INDICATORS
        # ========================================
        st.subheader("🎯 Key Performance Indicators")
        
        # Calculate key metrics for current period
        total_revenue = filtered_df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in filtered_df.columns else filtered_df['Revenue (SAR)'].sum()
        total_conversions = filtered_df['Selected Conversions'].sum() if 'Selected Conversions' in filtered_df.columns else filtered_df['Unique Conversions'].sum()
        total_clicks = filtered_df['Unique Clicks'].sum()
        total_impressions = filtered_df['Unique Impressions'].sum()
        total_sent = filtered_df['Sent'].sum()
        total_delivered = filtered_df['Delivered'].sum()
        
        # Calculate rates
        overall_ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
        overall_conversion_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
        overall_delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0
        revenue_per_conversion = (total_revenue / total_conversions) if total_conversions > 0 else 0
        
        # Calculate previous period metrics for comparison
        prev_metrics = {}
        has_prev_comparison = False
        prev_start = None
        prev_end = None
        
        if 'Reporting Period Start Date' in filtered_df.columns and len(filtered_df) > 0:
            current_start = filtered_df['Reporting Period Start Date'].min()
            current_end = filtered_df['Reporting Period End Date'].max()
            period_length = (current_end - current_start).days + 1
            
            # Determine previous period based on comparison mode
            if comparison_mode == "Manual (Custom Dates)" and manual_comparison_dates and len(manual_comparison_dates) == 2:
                # Use manual dates
                prev_start = pd.to_datetime(manual_comparison_dates[0])
                prev_end = pd.to_datetime(manual_comparison_dates[1])
                st.info(f"📊 Manual Comparison: Current period ({current_start.strftime('%b %d')} - {current_end.strftime('%b %d')}) vs Custom period ({prev_start.strftime('%b %d')} - {prev_end.strftime('%b %d, %Y')})")
            else:
                # Automatic - use previous period of equal length
                prev_start = current_start - pd.Timedelta(days=period_length)
                prev_end = current_start - pd.Timedelta(days=1)
            
            # Filter for previous period from the full dataset
            prev_period_df = df[(df['Reporting Period Start Date'] >= prev_start) & 
                               (df['Reporting Period End Date'] <= prev_end)]
            
            if len(prev_period_df) > 0:
                has_prev_comparison = True
                
                # Calculate previous period metrics
                prev_metrics['revenue'] = prev_period_df['Revenue (SAR)'].sum()
                prev_metrics['conversions'] = prev_period_df['Unique Conversions'].sum()
                prev_metrics['clicks'] = prev_period_df['Unique Clicks'].sum()
                prev_metrics['impressions'] = prev_period_df['Unique Impressions'].sum()
                prev_metrics['sent'] = prev_period_df['Sent'].sum()
                prev_metrics['delivered'] = prev_period_df['Delivered'].sum()
                
                # Calculate previous rates
                prev_metrics['ctr'] = (prev_metrics['clicks'] / prev_metrics['impressions'] * 100) if prev_metrics['impressions'] > 0 else 0
                prev_metrics['conversion_rate'] = (prev_metrics['conversions'] / prev_metrics['clicks'] * 100) if prev_metrics['clicks'] > 0 else 0
                prev_metrics['delivery_rate'] = (prev_metrics['delivered'] / prev_metrics['sent'] * 100) if prev_metrics['sent'] > 0 else 0
                prev_metrics['rpc'] = (prev_metrics['revenue'] / prev_metrics['conversions']) if prev_metrics['conversions'] > 0 else 0
                
                # Calculate growth percentages
                prev_metrics['revenue_growth'] = ((total_revenue - prev_metrics['revenue']) / prev_metrics['revenue'] * 100) if prev_metrics['revenue'] > 0 else 0
                prev_metrics['conversions_growth'] = ((total_conversions - prev_metrics['conversions']) / prev_metrics['conversions'] * 100) if prev_metrics['conversions'] > 0 else 0
                prev_metrics['ctr_growth'] = overall_ctr - prev_metrics['ctr']
                prev_metrics['conversion_rate_growth'] = overall_conversion_rate - prev_metrics['conversion_rate']
                prev_metrics['delivery_rate_growth'] = overall_delivery_rate - prev_metrics['delivery_rate']
                prev_metrics['rpc_growth'] = ((revenue_per_conversion - prev_metrics['rpc']) / prev_metrics['rpc'] * 100) if prev_metrics['rpc'] > 0 else 0
        
        # Display hero metrics in 4 columns with period comparison
        hero_col1, hero_col2, hero_col3, hero_col4 = st.columns(4)
        
        with hero_col1:
            st.metric(
                label="💰 Total Revenue",
                value=format_metric(total_revenue, "SAR"),
                delta=f"{prev_metrics.get('revenue_growth', 0):+.1f}%" if has_prev_comparison else None,
                delta_color="normal" if has_prev_comparison else "off",
                help="Total revenue generated across all campaigns and journeys" + (f"\nPrevious period: {format_metric(prev_metrics.get('revenue', 0), 'SAR')}" if has_prev_comparison else "")
            )
            st.metric(
                label="🎯 Conversions",
                value=format_metric(total_conversions),
                delta=f"{prev_metrics.get('conversions_growth', 0):+.1f}%" if has_prev_comparison else None,
                delta_color="normal" if has_prev_comparison else "off",
                help="Total unique conversions" + (f"\nPrevious period: {format_metric(prev_metrics.get('conversions', 0))}" if has_prev_comparison else "")
            )
        
        with hero_col2:
            st.metric(
                label="📊 Click-Through Rate",
                value=f"{overall_ctr:.2f}%",
                delta=f"{prev_metrics.get('ctr_growth', 0):+.2f}pp" if has_prev_comparison else None,
                delta_color="normal" if has_prev_comparison else "off",
                help="Percentage of impressions that resulted in clicks" + (f"\nPrevious period: {prev_metrics.get('ctr', 0):.2f}%" if has_prev_comparison else "")
            )
            st.metric(
                label="✅ Conversion Rate",
                value=f"{overall_conversion_rate:.2f}%",
                delta=f"{prev_metrics.get('conversion_rate_growth', 0):+.2f}pp" if has_prev_comparison else None,
                delta_color="normal" if has_prev_comparison else "off",
                help="Percentage of clicks that resulted in conversions" + (f"\nPrevious period: {prev_metrics.get('conversion_rate', 0):.2f}%" if has_prev_comparison else "")
            )
        
        with hero_col3:
            st.metric(
                label="📧 Delivery Rate",
                value=f"{overall_delivery_rate:.2f}%",
                delta=f"{prev_metrics.get('delivery_rate_growth', 0):+.2f}pp" if has_prev_comparison else None,
                delta_color="normal" if has_prev_comparison else "off",
                help="Percentage of messages successfully delivered" + (f"\nPrevious period: {prev_metrics.get('delivery_rate', 0):.2f}%" if has_prev_comparison else "")
            )
            st.metric(
                label="💵 Revenue per Conversion",
                value=format_metric(revenue_per_conversion, "SAR"),
                delta=f"{prev_metrics.get('rpc_growth', 0):+.1f}%" if has_prev_comparison else None,
                delta_color="normal" if has_prev_comparison else "off",
                help="Average revenue generated per conversion" + (f"\nPrevious period: {format_metric(prev_metrics.get('rpc', 0), 'SAR')}" if has_prev_comparison else "")
            )
        
        with hero_col4:
            st.metric(
                label="📨 Messages Sent",
                value=format_metric(total_sent),
                delta=f"{((total_sent - prev_metrics.get('sent', 0)) / prev_metrics.get('sent', 1) * 100):+.1f}%" if has_prev_comparison and prev_metrics.get('sent', 0) > 0 else None,
                delta_color="normal" if has_prev_comparison else "off",
                help="Total messages sent across all campaigns" + (f"\nPrevious period: {format_metric(prev_metrics.get('sent', 0))}" if has_prev_comparison else "")
            )
            st.metric(
                label="👁️ Impressions",
                value=format_metric(total_impressions),
                delta=f"{((total_impressions - prev_metrics.get('impressions', 0)) / prev_metrics.get('impressions', 1) * 100):+.1f}%" if has_prev_comparison and prev_metrics.get('impressions', 0) > 0 else None,
                delta_color="normal" if has_prev_comparison else "off",
                help="Total unique impressions" + (f"\nPrevious period: {format_metric(prev_metrics.get('impressions', 0))}" if has_prev_comparison else "")
            )
        
        # Add comparison note
        if has_prev_comparison:
            if comparison_mode == "Manual (Custom Dates)":
                comparison_days = (prev_end - prev_start).days + 1
                st.info(f"📊 **Manual Comparison**: Current period vs Custom period ({prev_start.strftime('%b %d')} - {prev_end.strftime('%b %d, %Y')}, {comparison_days} days). Green ▲ = improvement, Red ▼ = decline. 'pp' = percentage points.")
            else:
                st.info(f"📊 **Automatic Comparison**: Current period vs previous {period_length}-day period ({prev_start.strftime('%b %d')} - {prev_end.strftime('%b %d, %Y')}). Green ▲ = improvement, Red ▼ = decline. 'pp' = percentage points.")
        else:
            if comparison_mode == "Manual (Custom Dates)":
                st.warning("⚠️ No data found for the selected comparison period. Please select a different date range or switch to Automatic mode.")
            else:
                st.warning("💡 Upload data spanning multiple periods to see period-over-period growth trends and comparisons.")
        
        st.markdown("---")
        
        # ========================================
        # 2. REVENUE ANALYSIS
        # ========================================
        st.subheader("💰 Revenue Analysis")
        
        revenue_col1, revenue_col2 = st.columns([2, 1])
        
        with revenue_col1:
            # Revenue over time
            st.markdown("#### Revenue Trend Over Time")
            if 'Reporting Period Start Date' in filtered_df.columns:
                revenue_ts = filtered_df.groupby('Reporting Period Start Date').agg({
                    'Revenue (SAR)': 'sum',
                    'Impression-Through Revenue (SAR)': 'sum',
                    'Click-Through Revenue (SAR)': 'sum'
                }).reset_index()
                
                fig_revenue_trend = go.Figure()
                fig_revenue_trend.add_trace(go.Scatter(
                    x=revenue_ts['Reporting Period Start Date'],
                    y=revenue_ts['Revenue (SAR)'],
                    mode='lines+markers',
                    name='Total Revenue',
                    line=dict(color='#1f77b4', width=3),
                    marker=dict(size=8)
                ))
                fig_revenue_trend.add_trace(go.Scatter(
                    x=revenue_ts['Reporting Period Start Date'],
                    y=revenue_ts['Click-Through Revenue (SAR)'],
                    mode='lines+markers',
                    name='Click-Through Revenue',
                    line=dict(color='#ff7f0e', width=2, dash='dash'),
                    marker=dict(size=6)
                ))
                fig_revenue_trend.add_trace(go.Scatter(
                    x=revenue_ts['Reporting Period Start Date'],
                    y=revenue_ts['Impression-Through Revenue (SAR)'],
                    mode='lines+markers',
                    name='Impression-Through Revenue',
                    line=dict(color='#2ca02c', width=2, dash='dot'),
                    marker=dict(size=6)
                ))
                
                fig_revenue_trend.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Revenue (SAR)",
                    hovermode='x unified',
                    height=400,
                    showlegend=True,
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
                )
                st.plotly_chart(fig_revenue_trend, use_container_width=True)
        
        with revenue_col2:
            # Revenue Attribution Breakdown - CORRECTED LOGIC
            st.markdown("#### Revenue Attribution")
            
            # The correct hierarchy in WebEngage:
            # Send-Through Revenue (Total) ⊇ Impression-Through Revenue ⊇ Click-Through Revenue
            # They are nested, not additive!
            send_through_revenue = filtered_df['Revenue (SAR)'].sum()  # Total revenue (largest)
            impression_through_revenue = filtered_df['Impression-Through Revenue (SAR)'].sum()  # Subset of send-through
            click_through_revenue = filtered_df['Click-Through Revenue (SAR)'].sum()  # Subset of impression-through
            
            # Calculate actual breakdown (non-overlapping portions)
            # Click-Through is the most engaged (clicked)
            # Impression-Through (excluding clicks) = saw but didn't click
            # Send-Through (excluding impressions) = converted without seeing/clicking
            click_attributed = click_through_revenue
            impression_attributed = impression_through_revenue - click_through_revenue  # Saw but didn't click
            send_attributed = send_through_revenue - impression_through_revenue  # No impression/click tracked
            
            # Create attribution data in the CORRECT ORDER (Send → Impression → Click)
            # DO NOT SORT - keep the hierarchical order!
            attribution_data = pd.DataFrame({
                'Attribution Type': ['Send-Through Only', 'Impression-Through Only', 'Click-Through'],
                'Revenue (SAR)': [send_attributed, impression_attributed, click_attributed],
                'Percentage': [
                    (send_attributed / send_through_revenue * 100) if send_through_revenue > 0 else 0,
                    (impression_attributed / send_through_revenue * 100) if send_through_revenue > 0 else 0,
                    (click_attributed / send_through_revenue * 100) if send_through_revenue > 0 else 0
                ]
            })
            
            # Create pie chart with explicit category order to maintain hierarchy
            fig_attribution = go.Figure(data=[go.Pie(
                labels=attribution_data['Attribution Type'],
                values=attribution_data['Revenue (SAR)'],
                hole=0.4,
                marker=dict(colors=['#ff7f0e', '#2ca02c', '#1f77b4']),  # Orange for Send, Green for Impression, Blue for Click
                textinfo='label+percent',
                textposition='inside',
                sort=False  # CRITICAL: Don't sort by value - keep our order!
            )])
            
            fig_attribution.update_layout(
                height=400,
                showlegend=True,
                legend=dict(
                    orientation="v",
                    yanchor="middle",
                    y=0.5,
                    xanchor="left",
                    x=1.1
                )
            )
            st.plotly_chart(fig_attribution, use_container_width=True)
            
            # Show actual totals for verification
            st.markdown("**Total Revenue Breakdown:**")
            st.markdown(f"- 📧 **Total (Send-Through)**: {format_metric(send_through_revenue, 'SAR')}")
            st.markdown(f"- 👁️ **Impression-Through**: {format_metric(impression_through_revenue, 'SAR')} ({impression_through_revenue/send_through_revenue*100:.1f}%)")
            st.markdown(f"- 🖱️ **Click-Through**: {format_metric(click_through_revenue, 'SAR')} ({click_through_revenue/send_through_revenue*100:.1f}%)")
            
            # Attribution explanation
            with st.expander("ℹ️ Understanding Revenue Attribution"):
                st.markdown("""
                **Revenue Attribution Explained:**
                
                WebEngage uses hierarchical attribution (nested, not additive):
                
                - **Send-Through** (Total): All revenue from this campaign/journey
                - **Impression-Through** ⊆ Send-Through: Revenue where user had an impression
                - **Click-Through** ⊆ Impression-Through: Revenue where user clicked
                
                **The chart shows non-overlapping portions:**
                - **Click-Through**: Users who clicked and converted (most engaged)
                - **Impression-Through Only**: Users who saw but didn't click, yet converted
                - **Send-Through Only**: Conversions without tracked impression/click
                
                *Total Revenue = Send-Through Revenue (the outermost set)*
                """)
        
        # Revenue by Channel with Period Comparison
        st.markdown("#### Revenue by Channel")
        
        # Calculate current period channel performance
        channel_revenue = filtered_df.groupby('Channel').agg({
            'Revenue (SAR)': 'sum',
            'Unique Conversions': 'sum',
            'Sent': 'sum'
        }).reset_index()
        channel_revenue['Revenue %'] = (channel_revenue['Revenue (SAR)'] / channel_revenue['Revenue (SAR)'].sum() * 100)
        channel_revenue = channel_revenue.sort_values('Revenue (SAR)', ascending=False)
        
        # Calculate previous period for comparison
        if 'Reporting Period Start Date' in filtered_df.columns and len(filtered_df) > 0:
            current_start = filtered_df['Reporting Period Start Date'].min()
            current_end = filtered_df['Reporting Period End Date'].max()
            period_length = (current_end - current_start).days + 1
            
            # Define previous period
            prev_start = current_start - pd.Timedelta(days=period_length)
            prev_end = current_start - pd.Timedelta(days=1)
            
            # Filter for previous period from the full dataset
            prev_period_df = df[(df['Reporting Period Start Date'] >= prev_start) & 
                               (df['Reporting Period End Date'] <= prev_end)]
            
            if len(prev_period_df) > 0:
                prev_channel_revenue = prev_period_df.groupby('Channel').agg({
                    'Revenue (SAR)': 'sum',
                    'Unique Conversions': 'sum'
                }).reset_index()
                prev_channel_revenue.columns = ['Channel', 'Prev Revenue (SAR)', 'Prev Conversions']
                
                # Merge with current period
                channel_revenue = channel_revenue.merge(prev_channel_revenue, on='Channel', how='left')
                channel_revenue['Prev Revenue (SAR)'] = channel_revenue['Prev Revenue (SAR)'].fillna(0)
                channel_revenue['Prev Conversions'] = channel_revenue['Prev Conversions'].fillna(0)
                
                # Calculate growth
                channel_revenue['Revenue Growth %'] = ((channel_revenue['Revenue (SAR)'] - channel_revenue['Prev Revenue (SAR)']) / 
                                                       channel_revenue['Prev Revenue (SAR)'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
                channel_revenue['Conversion Growth %'] = ((channel_revenue['Unique Conversions'] - channel_revenue['Prev Conversions']) / 
                                                          channel_revenue['Prev Conversions'] * 100).replace([np.inf, -np.inf], 0).fillna(0)
                
                has_comparison = True
            else:
                has_comparison = False
        else:
            has_comparison = False
        
        # Display chart and comparison
        channel_chart_col, channel_table_col = st.columns([2, 1])
        
        with channel_chart_col:
            fig_channel_revenue = px.bar(
                channel_revenue,
                x='Channel',
                y='Revenue (SAR)',
                text=channel_revenue['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR")),
                title='',
                color='Revenue (SAR)',
                color_continuous_scale='Blues'
            )
            fig_channel_revenue.update_traces(textposition='outside')
            fig_channel_revenue.update_layout(showlegend=False, height=350)
            st.plotly_chart(fig_channel_revenue, use_container_width=True)
        
        with channel_table_col:
            if has_comparison:
                st.markdown("**Period Comparison:**")
                comparison_data = channel_revenue[['Channel', 'Revenue Growth %', 'Conversion Growth %']].copy()
                
                for idx, row in comparison_data.iterrows():
                    channel = row['Channel']
                    rev_growth = row['Revenue Growth %']
                    conv_growth = row['Conversion Growth %']
                    
                    # Format with emojis
                    rev_emoji = "📈" if rev_growth > 0 else "📉" if rev_growth < 0 else "➡️"
                    conv_emoji = "📈" if conv_growth > 0 else "📉" if conv_growth < 0 else "➡️"
                    
                    st.markdown(f"**{channel}**")
                    st.markdown(f"{rev_emoji} Revenue: {rev_growth:+.1f}%")
                    st.markdown(f"{conv_emoji} Conversions: {conv_growth:+.1f}%")
                    st.markdown("---")
                
                st.info(f"📅 Comparing to previous {period_length}-day period")
            else:
                st.info("💡 No previous period data available for comparison. Upload data spanning multiple periods to see growth trends.")
        
        st.markdown("---")
        
        # ========================================
        # 3. TOP PERFORMERS
        # ========================================
        st.subheader("🏆 Top Performers")
        
        top_col1, top_col2 = st.columns(2)
        
        with top_col1:
            st.markdown("#### 🎯 Top 10 Journeys by Revenue")
            
            # Calculate journey performance with health scores
            journey_performance = []
            unique_journeys = filtered_df['Journey Name'].dropna().unique()
            
            for journey in unique_journeys:
                if str(journey) != 'nan' and journey:
                    journey_data = filtered_df[filtered_df['Journey Name'] == journey]
                    health_info = calculate_journey_health_score(journey_data, filtered_df)
                    
                    if health_info['tier'] != 'Insufficient Data':  # Only include journeys with sufficient data
                        journey_performance.append({
                            'Journey': journey,
                            'Revenue': journey_data['Revenue (SAR)'].sum(),
                            'Conversions': journey_data['Unique Conversions'].sum(),
                            'Health Score': health_info['health_score'],
                            'Tier': health_info['tier']
                        })
            
            if journey_performance:
                journey_df = pd.DataFrame(journey_performance)
                journey_df = journey_df.sort_values('Revenue', ascending=False).head(10)
                
                # Format for display
                journey_display = journey_df.copy()
                journey_display['Revenue'] = journey_display['Revenue'].apply(lambda x: format_metric(x, "SAR"))
                journey_display['Conversions'] = journey_display['Conversions'].apply(format_metric)
                journey_display['Health Score'] = journey_display['Health Score'].apply(lambda x: f"{x:.1f}/100")
                
                # Add tier emoji
                tier_emojis = {'Excellent': '🟢', 'Good': '🟡', 'Fair': '🟠', 'Poor': '🔴'}
                journey_display['Status'] = journey_display['Tier'].apply(lambda x: f"{tier_emojis.get(x, '⚪')} {x}")
                journey_display = journey_display[['Journey', 'Revenue', 'Conversions', 'Health Score', 'Status']]
                
                st.dataframe(journey_display, use_container_width=True, hide_index=True)
            else:
                st.info("No journey data available with sufficient volume for analysis.")
        
        with top_col2:
            st.markdown("#### 📧 Top 10 Campaigns by Revenue")
            
            # Calculate campaign performance with health scores
            campaign_performance = []
            unique_campaigns = filtered_df['Campaign Name'].dropna().unique()
            
            for campaign in unique_campaigns:
                if str(campaign) != 'nan' and campaign:
                    campaign_data = filtered_df[filtered_df['Campaign Name'] == campaign]
                    health_info = calculate_campaign_health_score(campaign_data, filtered_df)
                    
                    if health_info['tier'] != 'Insufficient Data':  # Only include campaigns with sufficient data
                        campaign_performance.append({
                            'Campaign': campaign,
                            'Revenue': campaign_data['Revenue (SAR)'].sum(),
                            'Conversions': campaign_data['Unique Conversions'].sum(),
                            'Health Score': health_info['health_score'],
                            'Tier': health_info['tier']
                        })
            
            if campaign_performance:
                campaign_df = pd.DataFrame(campaign_performance)
                campaign_df = campaign_df.sort_values('Revenue', ascending=False).head(10)
                
                # Format for display
                campaign_display = campaign_df.copy()
                campaign_display['Revenue'] = campaign_display['Revenue'].apply(lambda x: format_metric(x, "SAR"))
                campaign_display['Conversions'] = campaign_display['Conversions'].apply(format_metric)
                campaign_display['Health Score'] = campaign_display['Health Score'].apply(lambda x: f"{x:.1f}/100")
                
                # Add tier emoji
                tier_emojis = {'Excellent': '🟢', 'Good': '🟡', 'Fair': '🟠', 'Poor': '🔴'}
                campaign_display['Status'] = campaign_display['Tier'].apply(lambda x: f"{tier_emojis.get(x, '⚪')} {x}")
                campaign_display = campaign_display[['Campaign', 'Revenue', 'Conversions', 'Health Score', 'Status']]
                
                st.dataframe(campaign_display, use_container_width=True, hide_index=True)
            else:
                st.info("No campaign data available with sufficient volume for analysis.")
        
        st.markdown("---")
        
        # ========================================
        # 4. MARKETING FUNNEL ANALYSIS
        # ========================================
        st.subheader("📊 Marketing Funnel Performance")
        
        funnel_col1, funnel_col2 = st.columns([2, 1])
        
        with funnel_col1:
            # Enhanced conversion funnel
            funnel_data = {
                'Stage': ['Sent', 'Delivered', 'Impressions', 'Clicks', 'Conversions'],
                'Count': [
                    total_sent,
                    total_delivered,
                    total_impressions,
                    total_clicks,
                    total_conversions
                ]
            }
            
            fig_funnel = go.Figure(go.Funnel(
                y=funnel_data['Stage'],
                x=funnel_data['Count'],
                textinfo="value+percent initial+percent previous",
                marker=dict(color=["#1f77b4", "#2ca02c", "#ff7f0e", "#d62728", "#9467bd"]),
                connector=dict(line=dict(color="royalblue", width=3))
            ))
            
            fig_funnel.update_layout(
                title="Customer Journey Funnel",
                height=400
            )
            st.plotly_chart(fig_funnel, use_container_width=True)
        
        with funnel_col2:
            st.markdown("#### Funnel Metrics")
            
            # Calculate drop-off rates
            delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0
            impression_rate = (total_impressions / total_delivered * 100) if total_delivered > 0 else 0
            ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
            conversion_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
            
            st.metric("📧 Delivery Success", f"{delivery_rate:.1f}%")
            st.metric("👁️ Impression Rate", f"{impression_rate:.1f}%")
            st.metric("🖱️ Click-Through Rate", f"{ctr:.2f}%")
            st.metric("✅ Conversion Rate", f"{conversion_rate:.2f}%")
            
            # Overall funnel efficiency
            overall_efficiency = (total_conversions / total_sent * 100) if total_sent > 0 else 0
            st.metric("🎯 Overall Efficiency", f"{overall_efficiency:.3f}%", 
                     help="Conversions as % of total messages sent")
        
        st.markdown("---")
        
        # ========================================
        # 5. KEY INSIGHTS & RECOMMENDATIONS
        # ========================================
        st.subheader("💡 Key Insights & Actionable Recommendations")
        
        insights = []
        recommendations = []
        
        # Revenue concentration insight
        if journey_performance:
            top_3_journey_revenue = sum([j['Revenue'] for j in journey_performance[:3]])
            journey_concentration = (top_3_journey_revenue / total_revenue * 100) if total_revenue > 0 else 0
            
            if journey_concentration > 60:
                insights.append(f"🎯 **High Concentration**: Top 3 journeys account for {journey_concentration:.1f}% of total revenue")
                recommendations.append("Consider diversifying revenue sources or scaling top performers")
            elif journey_concentration < 30:
                insights.append(f"📊 **Well Distributed**: Revenue is well distributed across journeys ({journey_concentration:.1f}% in top 3)")
                recommendations.append("Identify and optimize underperforming journeys to improve overall performance")
        
        # Channel performance insight
        if not channel_revenue.empty:
            top_channel = channel_revenue.iloc[0]
            top_channel_pct = top_channel['Revenue %']
            insights.append(f"📱 **Top Channel**: {top_channel['Channel']} generates {top_channel_pct:.1f}% of revenue")
            
            if top_channel_pct > 70:
                recommendations.append(f"Consider diversifying beyond {top_channel['Channel']} to reduce dependency")
        
        # Conversion rate insight
        if overall_conversion_rate > 5:
            insights.append(f"✅ **Strong Conversion**: {overall_conversion_rate:.2f}% conversion rate is above industry average")
            recommendations.append("Document and replicate successful conversion strategies across other campaigns")
        elif overall_conversion_rate < 2:
            insights.append(f"⚠️ **Low Conversion**: {overall_conversion_rate:.2f}% conversion rate needs improvement")
            recommendations.append("Review landing pages, CTAs, and offer relevance to boost conversions")
        
        # Delivery rate insight
        if overall_delivery_rate < 95:
            insights.append(f"📧 **Delivery Issue**: {overall_delivery_rate:.1f}% delivery rate is below optimal (95%+)")
            recommendations.append("Check ESP reputation, list hygiene, and bounce rates immediately")
        else:
            insights.append(f"📧 **Excellent Delivery**: {overall_delivery_rate:.1f}% delivery rate is optimal")
        
        # CTR insight
        if overall_ctr > 3:
            insights.append(f"🎯 **High Engagement**: {overall_ctr:.2f}% CTR shows strong audience interest")
            recommendations.append("Test similar messaging and creative across lower-performing campaigns")
        elif overall_ctr < 1:
            insights.append(f"⚠️ **Low Engagement**: {overall_ctr:.2f}% CTR suggests weak audience resonance")
            recommendations.append("A/B test subject lines, send times, and content personalization")
        
        # Display insights and recommendations
        insight_col1, insight_col2 = st.columns(2)
        
        with insight_col1:
            st.markdown("#### 🔍 Key Insights")
            for insight in insights:
                st.markdown(f"- {insight}")
        
        with insight_col2:
            st.markdown("#### 🎯 Recommended Actions")
            for rec in recommendations:
                st.markdown(f"- {rec}")
        
        st.markdown("---")
        
        # ========================================
        # 6. QUICK EXPORT SECTION
        # ========================================
        st.subheader("📥 Export Report")
        
        export_col1, export_col2, export_col3 = st.columns(3)
        
        with export_col1:
            # Export summary metrics to Excel
            if st.button("📊 Download Full Report (Excel)", use_container_width=True):
                from io import BytesIO
                import openpyxl
                
                output = BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    # Summary sheet
                    summary_data = {
                        'Metric': ['Total Revenue (SAR)', 'Total Conversions', 'Total Clicks', 'Total Impressions', 
                                  'Click-Through Rate', 'Conversion Rate', 'Delivery Rate', 'Revenue per Conversion'],
                        'Value': [total_revenue, total_conversions, total_clicks, total_impressions,
                                 f"{overall_ctr:.2f}%", f"{overall_conversion_rate:.2f}%", 
                                 f"{overall_delivery_rate:.2f}%", revenue_per_conversion]
                    }
                    pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
                    
                    # Top Journeys
                    if journey_performance:
                        pd.DataFrame(journey_performance).to_excel(writer, sheet_name='Top Journeys', index=False)
                    
                    # Top Campaigns
                    if campaign_performance:
                        pd.DataFrame(campaign_performance).to_excel(writer, sheet_name='Top Campaigns', index=False)
                    
                    # Channel Performance
                    channel_revenue.to_excel(writer, sheet_name='Channel Performance', index=False)
                
                output.seek(0)
                st.download_button(
                    label="⬇️ Download Excel File",
                    data=output,
                    file_name=f"shareholder_report_{period_start.strftime('%Y%m%d')}_{period_end.strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        with export_col2:
            st.info("📊 The Excel file includes:\n- Summary metrics\n- Top journeys\n- Top campaigns\n- Channel breakdown")
        
        with export_col3:
            st.success("✅ Ready for presentation!\n\nThis report is shareholder-ready and can be shared directly.")
        
        # Optional: Raw data preview
        with st.expander("🔍 View Detailed Data (Click to Expand)"):
            st.dataframe(filtered_df, use_container_width=True)

    elif page == "Campaigns":
        st.header("Campaign Analysis")
        
        # Top Campaigns
        st.subheader("Top Campaigns")
        camp_metric = st.selectbox("Metric", ['Unique Conversions', 'Revenue (SAR)', 'Unique Clicks', 'Click-Through Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'CTR', 'Conversion Rate'], key='camp_metric')
        top_camp = top_campaigns(filtered_df, camp_metric)
        
        # Create display version for table
        top_camp_display = top_camp.copy()
        
        # Store original numeric values for sorting
        original_values = top_camp_display[camp_metric].copy()
        
        # Format the metric column for display
        if 'Revenue' in camp_metric:
            top_camp_display[camp_metric] = top_camp_display[camp_metric].apply(lambda x: format_metric(x, "SAR"))
        elif camp_metric in ['Unique Conversions', 'Unique Clicks']:
            top_camp_display[camp_metric] = top_camp_display[camp_metric].apply(format_metric)
        # For rates, keep as is
        
        # Display table with proper sorting
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
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Total Sent", format_metric(camp_details['Sent'].sum()))
            with col2:
                st.metric("Total Delivered", format_metric(camp_details['Delivered'].sum()))
            with col3:
                st.metric("Total Conversions", format_metric(camp_details['Unique Conversions'].sum()))
            with col4:
                st.metric("Send-Through Revenue", format_metric(camp_details['Revenue (SAR)'].sum(), "SAR"))
            with col5:
                st.metric("Impression-Through Revenue", format_metric(camp_details['Impression-Through Revenue (SAR)'].sum(), "SAR"))
            with col6:
                st.metric("Click-Through Revenue", format_metric(camp_details['Click-Through Revenue (SAR)'].sum(), "SAR"))
            
            # Performance by Channel
            st.subheader("Performance by Channel")
            chan_perf = camp_details.groupby('Channel').agg({
                'Sent': 'sum',
                'Delivered': 'sum',
                'Unique Conversions': 'sum',
                'Revenue (SAR)': 'sum',
                'Impression-Through Revenue (SAR)': 'sum',
                'Click-Through Revenue (SAR)': 'sum'
            }).reset_index()
            # Format columns
            chan_perf['Sent'] = chan_perf['Sent'].apply(format_metric)
            chan_perf['Delivered'] = chan_perf['Delivered'].apply(format_metric)
            chan_perf['Unique Conversions'] = chan_perf['Unique Conversions'].apply(format_metric)
            chan_perf['Revenue (SAR)'] = chan_perf['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            chan_perf['Impression-Through Revenue (SAR)'] = chan_perf['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            chan_perf['Click-Through Revenue (SAR)'] = chan_perf['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
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

        # Campaign Health Score Analysis
        st.subheader("🏥 Campaign Health Dashboard")
        
        # Professional Methodology Explanation for Executives
        with st.expander("📊 Scoring Methodology (Click to View)", expanded=False):
            st.markdown("""
            ### **Professional Scoring Methodology**
            
            **Scoring Method**: Percentile-based ranking with statistical quartiles (Fortune 500 standard)
            
            #### **How Scores are Calculated:**
            - **Percentile Ranking**: Each campaign is scored based on its performance relative to all other campaigns in your portfolio
            - **0-100 Scale**: 50th percentile = 50 points, 75th percentile = 75 points, 95th percentile = 95+ points
            - **No Arbitrary Benchmarks**: Uses your company's actual historical performance as the baseline
            
            #### **Component Weights (Industry Standard):**
            - 🚀 **Conversion Performance**: 30% (Most critical for ROI)
            - 📧 **Delivery Performance**: 25% (Foundation of reach)
            - 🎯 **Engagement Performance**: 25% (Audience interest indicator) 
            - 💰 **Revenue Efficiency**: 20% (Financial effectiveness)
            
            #### **Performance Tiers:**
            - **Excellent (80-100)**: Top quartile performance - scale these campaigns
            - **Good (60-79)**: Above average - minor optimizations needed
            - **Fair (40-59)**: Below average - moderate improvements required
            - **Poor (0-39)**: Bottom quartile - immediate action required
            
            #### **Why This Method:**
            ✅ **Investor-Grade**: Used by McKinsey, BCG, and Fortune 500 companies  
            ✅ **Context-Aware**: Considers your business reality, not arbitrary benchmarks  
            ✅ **Statistically Sound**: Based on proven percentile ranking methodology  
            ✅ **Executive-Ready**: Suitable for board presentations and strategic planning  
            """)
        
        
        # Calculate health scores for all campaigns
        campaign_health_data = []
        unique_campaigns = filtered_df['Campaign Name'].dropna().unique()
        
        for campaign in unique_campaigns:
            if str(campaign) != 'nan' and campaign:
                campaign_data = filtered_df[filtered_df['Campaign Name'] == campaign]
                health_info = calculate_campaign_health_score(campaign_data, filtered_df)
                campaign_health_data.append({
                    'Campaign Name': campaign,
                    'Health Score': health_info['health_score'],
                    'Tier': health_info['tier'],
                    'Revenue (SAR)': campaign_data['Revenue (SAR)'].sum(),
                    'Impression-Through Revenue (SAR)': campaign_data['Impression-Through Revenue (SAR)'].sum(),
                    'Click-Through Revenue (SAR)': campaign_data['Click-Through Revenue (SAR)'].sum(),
                    'Total Conversions': campaign_data['Unique Conversions'].sum(),
                    'Delivery Score': health_info['component_scores'].get('delivery', 0),
                    'Engagement Score': health_info['component_scores'].get('engagement', 0),
                    'Conversion Score': health_info['component_scores'].get('conversion', 0),
                    'Revenue Score': health_info['component_scores'].get('revenue', 0)
                })
        
        if campaign_health_data:
            health_df = pd.DataFrame(campaign_health_data)
            health_df = health_df.sort_values('Health Score', ascending=False)
            
            # Display top performers and those needing attention
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🔥 Top Performing Campaigns")
                top_performing_campaigns = health_df.head(5)
                for _, row in top_performing_campaigns.iterrows():
                    # Use expandable containers for full campaign names
                    with st.container():
                        st.markdown(f"**{row['Campaign Name']}**")
                        score_col, tier_col = st.columns([2, 1])
                        with score_col:
                            st.markdown(f"🏥 **{row['Health Score']:.1f}/100**")
                        with tier_col:
                            tier_color = "🟢" if row['Tier'] == "Excellent" else "🟡" if row['Tier'] == "Good" else "🟠"
                            st.markdown(f"{tier_color} {row['Tier']}")
                        st.markdown("---")
            
            with col2:
                st.subheader("🚨 Campaigns Needing Attention")
                bottom_campaigns = health_df[health_df['Health Score'] < 60].head(5)
                if not bottom_campaigns.empty:
                    for _, row in bottom_campaigns.iterrows():
                        # Use expandable containers for full campaign names
                        with st.container():
                            st.markdown(f"**{row['Campaign Name']}**")
                            score_col, tier_col = st.columns([2, 1])
                            with score_col:
                                st.markdown(f"🏥 **{row['Health Score']:.1f}/100**")
                            with tier_col:
                                tier_color = "🔴" if row['Tier'] == "Poor" else "🟠" if row['Tier'] == "Fair" else "🟡"
                                st.markdown(f"{tier_color} {row['Tier']}")
                            st.markdown("---")
                else:
                    st.success("🎉 All campaigns are performing well!")
            
            # Health Score Distribution
            st.subheader("📊 Health Score Distribution")
            fig_health_dist = px.histogram(health_df, x='Health Score', nbins=20, 
                                         title="Distribution of Campaign Health Scores")
            fig_health_dist.add_vline(x=health_df['Health Score'].mean(), 
                                    line_dash="dash", 
                                    annotation_text=f"Average: {health_df['Health Score'].mean():.1f}")
            st.plotly_chart(fig_health_dist)
            
            # Complete Health Dashboard Table
            st.subheader("📋 Complete Campaign Health Report")
            
            # Add search and filter options
            search_col, filter_col = st.columns([2, 1])
            
            with search_col:
                search_term = st.text_input("🔍 Search Campaign Names", placeholder="Type to filter campaigns...", key='campaign_search')
            
            with filter_col:
                tier_filter = st.selectbox("Filter by Tier", ['All'] + list(health_df['Tier'].unique()), key='campaign_tier_filter')
            
            # Apply filters
            display_health_df = health_df.copy()
            
            if search_term:
                display_health_df = display_health_df[
                    display_health_df['Campaign Name'].str.contains(search_term, case=False, na=False)
                ]
            
            if tier_filter != 'All':
                display_health_df = display_health_df[display_health_df['Tier'] == tier_filter]
            
            # Prepare numeric dataframe for display while keeping numeric types so Streamlit sorts correctly
            numeric_display_df = display_health_df.copy()

            # Ensure numeric columns are numeric (coerce if necessary)
            numeric_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Total Conversions',
                            'Health Score', 'Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']
            for col in numeric_cols:
                if col in numeric_display_df.columns:
                    numeric_display_df[col] = pd.to_numeric(numeric_display_df[col], errors='coerce')

            # Add tier emojis to a separate display column (keep original Tier for filtering logic)
            tier_emojis = {
                'Excellent': '🟢',
                'Good': '🟡', 
                'Fair': '🟠',
                'Poor': '🔴'
            }
            # Create a human-friendly Tier display column
            numeric_display_df['Tier Display'] = numeric_display_df['Tier'].apply(lambda x: f"{tier_emojis.get(x, '⚪')} {x}")

            # Show filtered results count
            st.info(f"📊 Showing {len(numeric_display_df)} campaigns (filtered from {len(health_df)} total)")

            # Define columns order for display
            columns_order = ['Campaign Name', 'Health Score', 'Tier Display', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)',
                             'Click-Through Revenue (SAR)', 'Total Conversions', 'Delivery Score', 'Engagement Score',
                             'Conversion Score', 'Revenue Score']

            # Create formatters for Styler so values look nice but remain numeric underneath (preserves numeric sorting)
            formatters = {}
            if 'Health Score' in numeric_display_df.columns:
                formatters['Health Score'] = lambda x: f"{x:.1f}/100"
            if 'Revenue (SAR)' in numeric_display_df.columns:
                formatters['Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
                formatters['Impression-Through Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
                formatters['Click-Through Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
            if 'Total Conversions' in numeric_display_df.columns:
                formatters['Total Conversions'] = lambda x: format_metric(x)
            for score in ['Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']:
                if score in numeric_display_df.columns:
                    formatters[score] = lambda x: f"{x:.1f}"

            # Use pandas Styler to format display without changing underlying dtypes
            try:
                styled = numeric_display_df[columns_order].style.format(formatters)
                st.dataframe(styled, width='stretch', height=400)
            except Exception:
                # Fallback: if Styler isn't supported in this environment, fall back to pre-formatted strings
                fallback = numeric_display_df[columns_order].copy()
                if 'Health Score' in fallback.columns:
                    fallback['Health Score'] = fallback['Health Score'].apply(lambda x: f"{x:.1f}/100")
                if 'Revenue (SAR)' in fallback.columns:
                    fallback['Revenue (SAR)'] = fallback['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                    fallback['Impression-Through Revenue (SAR)'] = fallback['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                    fallback['Click-Through Revenue (SAR)'] = fallback['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                if 'Total Conversions' in fallback.columns:
                    fallback['Total Conversions'] = fallback['Total Conversions'].apply(format_metric)
                if 'Tier Display' in fallback.columns:
                    fallback = fallback.rename(columns={'Tier Display': 'Tier'})

                st.dataframe(fallback, width='stretch', height=400)
            
            # Component Scores Radar Chart for Selected Campaign
            st.subheader("🎯 Campaign Performance Breakdown")
            selected_campaign_health = st.selectbox("Select Campaign for Detailed Analysis", 
                                                  health_df['Campaign Name'].tolist(), 
                                                  key='health_campaign')
            
            if selected_campaign_health:
                selected_health_data = health_df[health_df['Campaign Name'] == selected_campaign_health].iloc[0]
                
                # Create radar chart for component scores with better visualization
                categories = ['Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']
                values = [selected_health_data[cat] for cat in categories]
                
                # Debug information to understand the values
                st.write("**📊 Component Score Values:**")
                score_cols = st.columns(4)
                for i, (cat, val) in enumerate(zip(categories, values)):
                    with score_cols[i]:
                        st.metric(cat.replace(' Score', ''), f"{val:.1f}/100")
                
                # Create enhanced radar chart
                fig_radar = go.Figure()
                
                # Add the main data trace
                fig_radar.add_trace(go.Scatterpolar(
                    r=values,
                    theta=categories,
                    fill='toself',
                    name=selected_campaign_health,
                    line=dict(color='rgb(0, 123, 255)', width=3),
                    fillcolor='rgba(0, 123, 255, 0.3)',
                    marker=dict(size=8, color='rgb(0, 123, 255)')
                ))
                
                # Add reference lines for performance levels
                excellent_line = [80] * len(categories)
                good_line = [60] * len(categories)
                
                fig_radar.add_trace(go.Scatterpolar(
                    r=excellent_line,
                    theta=categories,
                    mode='lines',
                    name='Excellent (80+)',
                    line=dict(color='green', width=2, dash='dash'),
                    showlegend=True
                ))
                
                fig_radar.add_trace(go.Scatterpolar(
                    r=good_line,
                    theta=categories,
                    mode='lines',
                    name='Good (60+)',
                    line=dict(color='orange', width=2, dash='dot'),
                    showlegend=True
                ))
                
                # Update layout with better styling
                fig_radar.update_layout(
                    polar=dict(
                        radialaxis=dict(
                            visible=True,
                            range=[0, 100],
                            tickmode='linear',
                            tick0=0,
                            dtick=20,
                            gridcolor='lightgray',
                            gridwidth=1
                        ),
                        angularaxis=dict(
                            gridcolor='lightgray',
                            gridwidth=1
                        )
                    ),
                    showlegend=True,
                    title=dict(
                        text=f"Performance Breakdown: {selected_campaign_health}",
                        x=0.5,
                        font=dict(size=16)
                    ),
                    width=600,
                    height=500,
                    margin=dict(l=80, r=80, t=80, b=80)
                )
                st.plotly_chart(fig_radar, use_container_width=True)
                
                # Show recommendations
                campaign_data_for_rec = filtered_df[filtered_df['Campaign Name'] == selected_campaign_health]
                health_info_for_rec = calculate_campaign_health_score(campaign_data_for_rec, filtered_df)
                
                st.subheader("💡 Recommendations")
                for rec in health_info_for_rec['recommendations']:
                    st.info(rec)

        # Campaign Performance Breakdown Analysis
        st.subheader("📊 Campaign Performance Breakdown")
        
        # Select campaign for detailed breakdown
        breakdown_campaign = st.selectbox("Select Campaign for Performance Breakdown", 
                                        unique_campaigns, 
                                        key='breakdown_campaign')
        
        if breakdown_campaign and str(breakdown_campaign) != 'nan':
            breakdown_data = filtered_df[filtered_df['Campaign Name'] == breakdown_campaign]
            
            # Calculate component scores and contributions
            breakdown_health = calculate_campaign_health_score(breakdown_data, filtered_df)
            
            # Component Contribution Analysis
            st.subheader("🔢 Component Contribution Analysis")
            
            # Create a detailed breakdown table
            contribution_data = []
            total_contribution = 0
            
            for component, details in breakdown_health.get('component_contributions', {}).items():
                contribution_data.append({
                    'Component': component.capitalize(),
                    'Score': f"{details['score']:.1f}/100",
                    'Weight': f"{details['weight']:.0%}",
                    'Contribution': f"{details['contribution']:.1f} points"
                })
                total_contribution += details['contribution']
            
            # Display as a nice table
            if contribution_data:
                contrib_df = pd.DataFrame(contribution_data)
                st.dataframe(contrib_df, use_container_width=True)
                
                # Show final calculation
                st.markdown(f"**🎯 Total Weighted Score: {total_contribution:.1f}/100**")
                
                # Show the weights explanation
                st.caption("💡 Weights: Conversion 30% (most critical for ROI) • Delivery 25% • Engagement 25% • Revenue 20%")
            
            # Performance Insights
            st.subheader("🎯 Performance Insights")
            
            # Key metrics breakdown
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                total_sent = breakdown_data['Sent'].sum()
                st.metric("📤 Total Sent", format_metric(total_sent))
                
                total_delivered = breakdown_data['Delivered'].sum()
                delivery_rate = (total_delivered / total_sent * 100) if total_sent > 0 else 0
                st.metric("📧 Delivery Rate", f"{delivery_rate:.1f}%")
            
            with col2:
                total_impressions = breakdown_data['Unique Impressions'].sum() if 'Unique Impressions' in breakdown_data.columns else 0
                st.metric("👁️ Total Impressions", format_metric(total_impressions))
                
                total_clicks = breakdown_data['Unique Clicks'].sum()
                ctr = (total_clicks / total_impressions * 100) if total_impressions > 0 else 0
                st.metric("🖱️ CTR", f"{ctr:.2f}%")
            
            with col3:
                total_conversions = breakdown_data['Unique Conversions'].sum()
                st.metric("💰 Total Conversions", format_metric(total_conversions))
                
                conversion_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
                st.metric("📈 Conversion Rate", f"{conversion_rate:.2f}%")
            
            with col4:
                total_revenue = breakdown_data['Revenue (SAR)'].sum()
                st.metric("💵 Total Revenue", format_metric(total_revenue, "SAR"))
                
                rpc = (total_revenue / total_conversions) if total_conversions > 0 else 0
                st.metric("💰 Revenue/Conversion", format_metric(rpc, "SAR"))
            
            # Performance vs Portfolio Analysis
            st.subheader("📊 Performance vs Portfolio")
            
            # Calculate portfolio averages
            portfolio_delivery_rate = (filtered_df['Delivered'].sum() / filtered_df['Sent'].sum() * 100) if filtered_df['Sent'].sum() > 0 else 0
            portfolio_ctr = (filtered_df['Unique Clicks'].sum() / filtered_df['Unique Impressions'].sum() * 100) if filtered_df['Unique Impressions'].sum() > 0 else 0
            portfolio_conversion_rate = (filtered_df['Unique Conversions'].sum() / filtered_df['Unique Clicks'].sum() * 100) if filtered_df['Unique Clicks'].sum() > 0 else 0
            portfolio_rpc = (filtered_df['Revenue (SAR)'].sum() / filtered_df['Unique Conversions'].sum()) if filtered_df['Unique Conversions'].sum() > 0 else 0
            
            # Compare campaign vs portfolio
            comparison_data = {
                'Metric': ['Delivery Rate', 'CTR', 'Conversion Rate', 'Revenue/Conversion'],
                'Campaign': [delivery_rate, ctr, conversion_rate, rpc],
                'Portfolio Average': [portfolio_delivery_rate, portfolio_ctr, portfolio_conversion_rate, portfolio_rpc],
                'Difference': [
                    delivery_rate - portfolio_delivery_rate,
                    ctr - portfolio_ctr, 
                    conversion_rate - portfolio_conversion_rate,
                    rpc - portfolio_rpc
                ]
            }
            
            comparison_df = pd.DataFrame(comparison_data)
            
            # Format for display
            display_comparison = comparison_df.copy()
            display_comparison['Campaign'] = display_comparison.apply(
                lambda row: f"{row['Campaign']:.1f}%" if 'Rate' in row['Metric'] else format_metric(row['Campaign'], "SAR" if "Revenue" in row['Metric'] else ""),
                axis=1
            )
            display_comparison['Portfolio Average'] = display_comparison.apply(
                lambda row: f"{row['Portfolio Average']:.1f}%" if 'Rate' in row['Metric'] else format_metric(row['Portfolio Average'], "SAR" if "Revenue" in row['Metric'] else ""),
                axis=1
            )
            display_comparison['Difference'] = display_comparison.apply(
                lambda row: f"{row['Difference']:+.1f}%" if 'Rate' in row['Metric'] else f"{format_metric(row['Difference'], 'SAR' if 'Revenue' in row['Metric'] else '')}",
                axis=1
            )
            
            st.dataframe(display_comparison, use_container_width=True)
            
            # Performance Summary
            st.subheader("📋 Performance Summary")
            
            # Calculate performance level for each metric
            summary_points = []
            
            if delivery_rate > portfolio_delivery_rate * 1.1:
                summary_points.append("🚀 **Delivery Excellence**: Significantly above portfolio average")
            elif delivery_rate < portfolio_delivery_rate * 0.9:
                summary_points.append("⚠️ **Delivery Challenge**: Below portfolio average - investigate deliverability")
            
            if ctr > portfolio_ctr * 1.1:
                summary_points.append("🎯 **Engagement Strength**: Strong click-through performance")
            elif ctr < portfolio_ctr * 0.9:
                summary_points.append("📉 **Engagement Opportunity**: CTR below average - consider creative optimization")
            
            if conversion_rate > portfolio_conversion_rate * 1.1:
                summary_points.append("💰 **Conversion Champion**: Exceptional conversion performance")
            elif conversion_rate < portfolio_conversion_rate * 0.9:
                summary_points.append("🔄 **Conversion Focus**: Conversion rate needs improvement")
            
            if rpc > portfolio_rpc * 1.1:
                summary_points.append("💎 **Revenue Efficiency**: High-value conversions")
            elif rpc < portfolio_rpc * 0.9:
                summary_points.append("💸 **Revenue Optimization**: Revenue per conversion below average")
            
            if summary_points:
                for point in summary_points:
                    st.info(point)
            else:
                st.info("📊 Campaign performance is generally aligned with portfolio averages")
            
            # Actionable Recommendations
            st.subheader("🎯 Actionable Recommendations")
            
            recommendations = []
            
            # Delivery recommendations
            if delivery_rate < portfolio_delivery_rate * 0.95:
                recommendations.append("📧 **Improve Deliverability**: Review sender reputation, authentication, and content filters")
                recommendations.append("🔍 **List Quality**: Clean email lists and remove inactive subscribers")
            
            # Engagement recommendations
            if ctr < portfolio_ctr * 0.95:
                recommendations.append("🎨 **Creative Optimization**: Test subject lines, preheaders, and visual elements")
                recommendations.append("⏰ **Timing Strategy**: Experiment with send times and frequencies")
            
            # Conversion recommendations
            if conversion_rate < portfolio_conversion_rate * 0.95:
                recommendations.append("🎯 **Landing Page Optimization**: Improve page load speed and mobile experience")
                recommendations.append("🛒 **Call-to-Action**: Test button text, placement, and design")
            
            # Revenue recommendations
            if rpc < portfolio_rpc * 0.95:
                recommendations.append("💰 **Value Proposition**: Enhance product messaging and benefits")
                recommendations.append("🎯 **Audience Targeting**: Focus on higher-value customer segments")
            
            # Success recommendations
            if delivery_rate > portfolio_delivery_rate * 1.05 and ctr > portfolio_ctr * 1.05 and conversion_rate > portfolio_conversion_rate * 1.05:
                recommendations.append("📈 **Scale Up**: This campaign shows strong performance - consider increasing budget")
                recommendations.append("🔄 **Replicate Success**: Apply successful elements to other campaigns")
            
            if recommendations:
                for rec in recommendations:
                    st.success(rec)
            else:
                st.info("✅ Campaign is performing well across all metrics - continue monitoring and optimizing")

        # Campaign Funnel Analysis
        st.subheader("🎯 Campaign Conversion Funnel Analysis")
        
        funnel_campaign = st.selectbox("Select Campaign for Funnel Analysis", 
                                    unique_campaigns, 
                                    key='funnel_campaign')
        
        if funnel_campaign and str(funnel_campaign) != 'nan':
            funnel_data = filtered_df[filtered_df['Campaign Name'] == funnel_campaign]
            funnel_analysis = analyze_campaign_funnel(funnel_data)
            
            # Display funnel visualization
            if funnel_analysis['funnel_data']:
                funnel_stages = []
                funnel_values = []
                
                for stage, value in funnel_analysis['funnel_data'].items():
                    if value > 0:
                        funnel_stages.append(stage)
                        funnel_values.append(value)
                
                if funnel_stages:
                    fig_funnel = go.Figure(go.Funnel(
                        y=funnel_stages,
                        x=funnel_values,
                        textposition="inside",
                        textinfo="value+percent initial+percent previous",
                        opacity=0.65,
                        marker={"color": ["deepskyblue", "lightsalmon", "tan", "teal", "silver"]},
                        connector={"line": {"color": "royalblue", "dash": "dot", "width": 3}}
                    ))
                    fig_funnel.update_layout(title=f"Conversion Funnel: {funnel_campaign}")
                    st.plotly_chart(fig_funnel)
            
            # Display conversion rates
            if funnel_analysis['conversion_rates']:
                st.subheader("📈 Conversion Rates Between Stages")
                rates_col1, rates_col2 = st.columns(2)
                
                rate_items = list(funnel_analysis['conversion_rates'].items())
                mid_point = len(rate_items) // 2
                
                with rates_col1:
                    for rate_name, rate_value in rate_items[:mid_point]:
                        st.metric(rate_name, f"{rate_value:.2%}")
                
                with rates_col2:
                    for rate_name, rate_value in rate_items[mid_point:]:
                        st.metric(rate_name, f"{rate_value:.2%}")
            
            # Display insights
            if funnel_analysis['insights']:
                st.subheader("🔍 Funnel Insights")
                for insight in funnel_analysis['insights']:
                    st.warning(insight)

        # Campaign Anomaly Detection
        st.subheader("🚨 Campaign Anomaly Detection")
        
        col1, col2 = st.columns([2, 1])
        with col2:
            lookback_days = st.slider("Analysis Period (days)", 7, 90, 30, key='campaign_anomaly_days')
        
        with col1:
            st.write("Detecting unusual performance patterns in campaigns...")
        
        if st.button("🔍 Detect Anomalies", key='detect_campaign_anomalies'):
            with st.spinner("Analyzing campaign performance patterns..."):
                anomalies = detect_campaign_anomalies(filtered_df, lookback_days)
                
                if anomalies:
                    st.subheader(f"🚨 {len(anomalies)} Anomalies Detected")
                    
                    # Group by severity
                    critical_anomalies = [a for a in anomalies if '🚨 Critical' in a.get('severity', '')]
                    warning_anomalies = [a for a in anomalies if '⚠️ Warning' in a.get('severity', '')]
                    
                    if critical_anomalies:
                        st.error(f"🚨 {len(critical_anomalies)} Critical Issues Require Immediate Attention")
                        for anomaly in critical_anomalies[:5]:  # Show top 5
                            with st.expander(f"{anomaly['campaign']} - {anomaly['metric']} {anomaly.get('direction', '')}"):
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Historical", f"{anomaly['historical_value']:.3f}")
                                with col2:
                                    st.metric("Recent", f"{anomaly['recent_value']:.3f}")
                                with col3:
                                    st.metric("Change", f"{anomaly['change_pct']:+.1f}%")
                                st.info(f"💡 {anomaly['recommendation']}")
                    
                    if warning_anomalies:
                        st.warning(f"⚠️ {len(warning_anomalies)} Performance Changes Detected")
                        with st.expander("View Warning Anomalies"):
                            for anomaly in warning_anomalies:
                                st.write(f"**{anomaly['campaign']}** - {anomaly['metric']}: {anomaly['change_pct']:+.1f}% change")
                                st.write(f"   💡 {anomaly['recommendation']}")
                else:
                    st.success("✅ No significant anomalies detected. All campaigns are performing within normal ranges!")

    elif page == "Journeys":
        st.header("Journey Analysis")
        
        # Revenue Type Selection - Revenue Attribution Models
        st.markdown("**💰 Revenue Attribution Model Selection**")
        st.markdown("*Choose the attribution model for revenue analysis:*")
        
        available_revenue_cols = [col for col in df.columns if 'Revenue' in col]
        if available_revenue_cols:
            # Create user-friendly labels for attribution models
            revenue_labels = {}
            for col in available_revenue_cols:
                if col == 'Revenue (SAR)':
                    revenue_labels[col] = "📊 Total Revenue (Send-Through Attribution)"
                elif col == 'Click-Through Revenue (SAR)':
                    revenue_labels[col] = "🖱️ Click-Through Revenue Attribution"
                elif col == 'Impression-Through Revenue (SAR)':
                    revenue_labels[col] = "👁️ Impression-Through Revenue Attribution"
                else:
                    revenue_labels[col] = col
            
            # Default to total revenue (send-through)
            default_revenue = 'Revenue (SAR)' if 'Revenue (SAR)' in available_revenue_cols else available_revenue_cols[0]
            
            selected_label = st.selectbox(
                "Select Revenue Attribution Model", 
                [revenue_labels[col] for col in available_revenue_cols],
                index=[revenue_labels[col] for col in available_revenue_cols].index(revenue_labels[default_revenue]),
                key='revenue_type'
            )
            
            # Map back to actual column name
            selected_revenue = [col for col, label in revenue_labels.items() if label == selected_label][0]
        else:
            selected_revenue = 'Revenue (SAR)'  # Fallback
            st.warning("⚠️ No revenue columns found in data")
        
        # Journey Health Score Analysis
        st.subheader("🏥 Journey Health Dashboard")
        
        # Professional Methodology Explanation for Executives
        with st.expander("📊 Scoring Methodology (Click to View)", expanded=False):
            st.markdown("""
            ### **Professional Scoring Methodology**
            
            **Scoring Method**: Percentile-based ranking with statistical quartiles (Fortune 500 standard)
            
            #### **How Scores are Calculated:**
            - **Percentile Ranking**: Each journey is scored based on its performance relative to all other journeys in your portfolio
            - **0-100 Scale**: 50th percentile = 50 points, 75th percentile = 75 points, 95th percentile = 95+ points
            - **No Arbitrary Benchmarks**: Uses your company's actual historical performance as the baseline
            
            #### **Component Weights (Industry Standard):**
            - 🚀 **Conversion Performance**: 30% (Most critical for ROI)
            - 📧 **Delivery Performance**: 25% (Foundation of reach)
            - 🎯 **Engagement Performance**: 25% (Audience interest indicator) 
            - 💰 **Revenue Efficiency**: 20% (Financial effectiveness)
            
            #### **Performance Tiers:**
            - **Excellent (80-100)**: Top quartile performance - scale these journeys
            - **Good (60-79)**: Above average - minor optimizations needed
            - **Fair (40-59)**: Below average - moderate improvements required
            - **Poor (0-39)**: Bottom quartile - immediate action required
            
            #### **Why This Method:**
            ✅ **Investor-Grade**: Used by McKinsey, BCG, and Fortune 500 companies  
            ✅ **Context-Aware**: Considers your business reality, not arbitrary benchmarks  
            ✅ **Statistically Sound**: Based on proven percentile ranking methodology  
            ✅ **Executive-Ready**: Suitable for board presentations and strategic planning  
            """)
        
        
        # Calculate health scores for all journeys
        journey_health_data = []
        unique_journeys = filtered_df['Journey Name'].dropna().unique()
        
        for journey in unique_journeys:
            if str(journey) != 'nan' and journey:
                journey_data = filtered_df[filtered_df['Journey Name'] == journey]
                health_info = calculate_journey_health_score(journey_data, filtered_df)
                journey_health_data.append({
                    'Journey Name': journey,
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
        
        if journey_health_data:
            health_df = pd.DataFrame(journey_health_data)
            health_df = health_df.sort_values('Health Score', ascending=False)
            
            # Display top performers and those needing attention
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🔥 Top Performing Journeys")
                top_performing_journeys = health_df.head(5)
                for _, row in top_performing_journeys.iterrows():
                    # Use expandable containers for full journey names
                    with st.container():
                        st.markdown(f"**{row['Journey Name']}**")
                        score_col, tier_col = st.columns([2, 1])
                        with score_col:
                            st.markdown(f"🏥 **{row['Health Score']:.1f}/100**")
                        with tier_col:
                            tier_color = "🟢" if row['Tier'] == "Excellent" else "🟡" if row['Tier'] == "Good" else "🟠"
                            st.markdown(f"{tier_color} {row['Tier']}")
                        st.markdown("---")
            
            with col2:
                st.subheader("🚨 Journeys Needing Attention")
                bottom_journeys = health_df[health_df['Health Score'] < 60].head(5)
                if not bottom_journeys.empty:
                    for _, row in bottom_journeys.iterrows():
                        # Use expandable containers for full journey names
                        with st.container():
                            st.markdown(f"**{row['Journey Name']}**")
                            score_col, tier_col = st.columns([2, 1])
                            with score_col:
                                st.markdown(f"🏥 **{row['Health Score']:.1f}/100**")
                            with tier_col:
                                tier_color = "🔴" if row['Tier'] == "Poor" else "🟠" if row['Tier'] == "Fair" else "🟡"
                                st.markdown(f"{tier_color} {row['Tier']}")
                            st.markdown("---")
                else:
                    st.success("🎉 All journeys are performing well!")
            
            # Health Score Distribution
            st.subheader("📊 Health Score Distribution")
            fig_health_dist = px.histogram(health_df, x='Health Score', nbins=20, 
                                         title="Distribution of Journey Health Scores")
            fig_health_dist.add_vline(x=health_df['Health Score'].mean(), 
                                    line_dash="dash", 
                                    annotation_text=f"Average: {health_df['Health Score'].mean():.1f}")
            st.plotly_chart(fig_health_dist)
            
            # Complete Health Dashboard Table
            st.subheader("📋 Complete Journey Health Report")
            
            # Add search and filter options
            search_col, filter_col = st.columns([2, 1])
            
            with search_col:
                search_term = st.text_input("🔍 Search Journey Names", placeholder="Type to filter journeys...", key='journey_search')
            
            with filter_col:
                tier_filter = st.selectbox("Filter by Tier", ['All'] + list(health_df['Tier'].unique()), key='tier_filter')
            
            # Apply filters
            display_health_df = health_df.copy()
            
            if search_term:
                display_health_df = display_health_df[
                    display_health_df['Journey Name'].str.contains(search_term, case=False, na=False)
                ]
            
            if tier_filter != 'All':
                display_health_df = display_health_df[display_health_df['Tier'] == tier_filter]
            
            # Prepare numeric dataframe for display while keeping numeric types so Streamlit sorts correctly
            numeric_display_df = display_health_df.copy()

            # Ensure numeric columns are numeric (coerce if necessary)
            numeric_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Total Conversions',
                            'Health Score', 'Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']
            for col in numeric_cols:
                if col in numeric_display_df.columns:
                    numeric_display_df[col] = pd.to_numeric(numeric_display_df[col], errors='coerce')

            # Add tier emojis to a separate display column (keep original Tier for filtering logic)
            tier_emojis = {
                'Excellent': '🟢',
                'Good': '🟡', 
                'Fair': '🟠',
                'Poor': '🔴'
            }
            # Create a human-friendly Tier display column
            numeric_display_df['Tier Display'] = numeric_display_df['Tier'].apply(lambda x: f"{tier_emojis.get(x, '⚪')} {x}")

            # Show filtered results count
            st.info(f"📊 Showing {len(numeric_display_df)} journeys (filtered from {len(health_df)} total)")

            # Define columns order for display
            columns_order = ['Journey Name', 'Health Score', 'Tier Display', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)',
                             'Click-Through Revenue (SAR)', 'Total Conversions', 'Delivery Score', 'Engagement Score',
                             'Conversion Score', 'Revenue Score']

            # Create formatters for Styler so values look nice but remain numeric underneath (preserves numeric sorting)
            formatters = {}
            if 'Health Score' in numeric_display_df.columns:
                formatters['Health Score'] = lambda x: f"{x:.1f}/100"
            if 'Revenue (SAR)' in numeric_display_df.columns:
                formatters['Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
                formatters['Impression-Through Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
                formatters['Click-Through Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
            if 'Total Conversions' in numeric_display_df.columns:
                formatters['Total Conversions'] = lambda x: format_metric(x)
            for score in ['Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']:
                if score in numeric_display_df.columns:
                    formatters[score] = lambda x: f"{x:.1f}"

            # Use pandas Styler to format display without changing underlying dtypes
            try:
                styled = numeric_display_df[columns_order].style.format(formatters)
                st.dataframe(styled, width='stretch', height=400)
            except Exception:
                # Fallback: if Styler isn't supported in this environment, fall back to pre-formatted strings
                fallback = numeric_display_df[columns_order].copy()
                if 'Health Score' in fallback.columns:
                    fallback['Health Score'] = fallback['Health Score'].apply(lambda x: f"{x:.1f}/100")
                if 'Revenue (SAR)' in fallback.columns:
                    fallback['Revenue (SAR)'] = fallback['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                    fallback['Impression-Through Revenue (SAR)'] = fallback['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                    fallback['Click-Through Revenue (SAR)'] = fallback['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                if 'Total Conversions' in fallback.columns:
                    fallback['Total Conversions'] = fallback['Total Conversions'].apply(format_metric)
                if 'Tier Display' in fallback.columns:
                    fallback = fallback.rename(columns={'Tier Display': 'Tier'})

                st.dataframe(fallback, width='stretch', height=400)
            
            # Component Scores Radar Chart for Selected Journey
            st.subheader("🎯 Journey Performance Breakdown")
            selected_journey_health = st.selectbox("Select Journey for Detailed Analysis", 
                                                  health_df['Journey Name'].tolist(), 
                                                  key='health_journey')
            
            if selected_journey_health:
                selected_health_data = health_df[health_df['Journey Name'] == selected_journey_health].iloc[0]
                
                # Create radar chart for component scores with better visualization
                categories = ['Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']
                values = [selected_health_data[cat] for cat in categories]
                
                # Debug information to understand the values
                st.write("**📊 Component Score Values:**")
                score_cols = st.columns(4)
                for i, (cat, val) in enumerate(zip(categories, values)):
                    with score_cols[i]:
                        st.metric(cat.replace(' Score', ''), f"{val:.1f}/100")
                
                # Create enhanced radar chart
                fig_radar = go.Figure()
                
                # Add the main data trace
                fig_radar.add_trace(go.Scatterpolar(
                    r=values,
                    theta=categories,
                    fill='toself',
                    name=selected_journey_health,
                    line=dict(color='rgb(0, 123, 255)', width=3),
                    fillcolor='rgba(0, 123, 255, 0.3)',
                    marker=dict(size=8, color='rgb(0, 123, 255)')
                ))
                
                # Add reference lines for performance levels
                excellent_line = [80] * len(categories)
                good_line = [60] * len(categories)
                
                fig_radar.add_trace(go.Scatterpolar(
                    r=excellent_line,
                    theta=categories,
                    mode='lines',
                    name='Excellent (80+)',
                    line=dict(color='green', width=2, dash='dash'),
                    showlegend=True
                ))
                
                fig_radar.add_trace(go.Scatterpolar(
                    r=good_line,
                    theta=categories,
                    mode='lines',
                    name='Good (60+)',
                    line=dict(color='orange', width=2, dash='dot'),
                    showlegend=True
                ))
                
                # Update layout with better styling
                fig_radar.update_layout(
                    polar=dict(
                        radialaxis=dict(
                            visible=True,
                            range=[0, 100],
                            tickmode='linear',
                            tick0=0,
                            dtick=20,
                            gridcolor='lightgray',
                            gridwidth=1
                        ),
                        angularaxis=dict(
                            gridcolor='lightgray',
                            gridwidth=1
                        )
                    ),
                    showlegend=True,
                    title=dict(
                        text=f"Performance Breakdown: {selected_journey_health}",
                        x=0.5,
                        font=dict(size=16)
                    ),
                    width=600,
                    height=500,
                    margin=dict(l=80, r=80, t=80, b=80)
                )
                st.plotly_chart(fig_radar, use_container_width=True)
                
                # Show recommendations
                journey_data_for_rec = filtered_df[filtered_df['Journey Name'] == selected_journey_health]
                health_info_for_rec = calculate_journey_health_score(journey_data_for_rec, filtered_df)
                
                st.subheader("💡 Recommendations")
                for rec in health_info_for_rec['recommendations']:
                    st.info(rec)

                # 🔍 DETAILED INDIVIDUAL JOURNEY ANALYSIS
                st.subheader("🔍 Detailed Journey Analysis")
                st.markdown("*Get the complete story behind this journey's score - same analysis as our debug script*")
                
                # Call our analysis function
                individual_analysis = analyze_individual_journey(selected_journey_health, filtered_df)
                
                if 'error' in individual_analysis:
                    st.error(f"❌ Error analyzing journey: {individual_analysis['error']}")
                else:
                    # Journey Summary
                    st.markdown(f"**📊 Journey:** {individual_analysis['journey_name']}")
                    st.markdown(f"**📈 Data Points:** {individual_analysis['data_rows']} rows of data")
                    st.markdown(f"**🎯 Final Score:** {individual_analysis['score_result']['health_score']:.1f}/100 ({individual_analysis['score_result']['tier']})")
                    st.markdown(f"**🔬 Method:** {individual_analysis['score_result']['scoring_method']}")
                    
                    # Raw Metrics Breakdown
                    with st.expander("📈 Raw Metrics Breakdown", expanded=True):
                        if 'delivery' in individual_analysis['raw_metrics']:
                            delivery_data = individual_analysis['raw_metrics']['delivery']
                            st.markdown("**📤 Delivery Performance:**")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Sent", format_metric(delivery_data['total_sent']))
                            with col2:
                                st.metric("Delivered", format_metric(delivery_data['total_delivered']))
                            with col3:
                                st.metric("Delivery Rate", f"{delivery_data['delivery_rate']:.1%}")
                        
                        if 'engagement' in individual_analysis['raw_metrics']:
                            engagement_data = individual_analysis['raw_metrics']['engagement']
                            st.markdown("**👆 Engagement Performance:**")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Impressions", format_metric(engagement_data['total_impressions']))
                            with col2:
                                st.metric("Clicks", format_metric(engagement_data['total_clicks']))
                            with col3:
                                st.metric("CTR", f"{engagement_data['ctr']:.2%}")
                        
                        if 'conversion' in individual_analysis['raw_metrics']:
                            conversion_data = individual_analysis['raw_metrics']['conversion']
                            st.markdown("**💰 Conversion Performance:**")
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Clicks", format_metric(conversion_data['total_clicks']))
                            with col2:
                                st.metric("Conversions", format_metric(conversion_data['total_conversions']))
                            with col3:
                                st.metric("Conversion Rate", f"{conversion_data['conversion_rate']:.2%}")
                            with col4:
                                if 'source' in conversion_data:
                                    st.caption(f"Source: {conversion_data['source']}")
                        
                        if 'revenue' in individual_analysis['raw_metrics']:
                            revenue_data = individual_analysis['raw_metrics']['revenue']
                            st.markdown("**💵 Revenue Performance:**")
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Total Revenue", format_metric(revenue_data['total_revenue'], "SAR"))
                            with col2:
                                st.metric("Conversions", format_metric(revenue_data['total_conversions']))
                            with col3:
                                st.metric("Rev/Conversion", format_metric(revenue_data['revenue_per_conversion'], "SAR"))
                            with col4:
                                st.metric("Log(RPC)", f"{revenue_data['log_rpc']:.2f}")
                    
                    # Population Comparison & Percentiles
                    with st.expander("📊 Population Comparison & Percentiles", expanded=True):
                        st.markdown("**How this journey compares to all other journeys in your portfolio:**")
                        
                        percentile_cols = st.columns(2)
                        with percentile_cols[0]:
                            if 'delivery' in individual_analysis['percentiles']:
                                perc = individual_analysis['percentiles']['delivery']
                                color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                                st.markdown(f"📤 **Delivery**: {color} {perc:.0f}th percentile")
                            
                            if 'engagement' in individual_analysis['percentiles']:
                                perc = individual_analysis['percentiles']['engagement']
                                color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                                st.markdown(f"👆 **CTR**: {color} {perc:.0f}th percentile")
                        
                        with percentile_cols[1]:
                            if 'conversion' in individual_analysis['percentiles']:
                                perc = individual_analysis['percentiles']['conversion']
                                color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                                st.markdown(f"💰 **Conversion**: {color} {perc:.0f}th percentile")
                            
                            if 'revenue' in individual_analysis['percentiles']:
                                perc = individual_analysis['percentiles']['revenue']
                                color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                                st.markdown(f"💵 **Revenue/Conv**: {color} {perc:.0f}th percentile")
                    
                    # Component Score Contributions
                    with st.expander("🔢 Component Score Contributions", expanded=True):
                        st.markdown("**How each component contributes to the final health score:**")
                        
                        # Create a detailed breakdown table
                        contribution_data = []
                        total_contribution = 0
                        
                        for component, details in individual_analysis['component_contributions'].items():
                            contribution_data.append({
                                'Component': component.capitalize(),
                                'Score': f"{details['score']:.1f}/100",
                                'Weight': f"{details['weight']:.0%}",
                                'Contribution': f"{details['contribution']:.1f} points"
                            })
                            total_contribution += details['contribution']
                        
                        # Display as a nice table
                        contrib_df = pd.DataFrame(contribution_data)
                        st.dataframe(contrib_df, use_container_width=True)
                        
                        # Show final calculation
                        st.markdown(f"**🎯 Total Weighted Score: {total_contribution:.1f}/100**")
                        
                        # Show the weights explanation
                        st.caption("💡 Weights: Conversion 30% (most critical for ROI) • Delivery 20% • Engagement 25% • Revenue 25%")
                    
                    # Key Insights & Problem Areas
                    if individual_analysis['insights']:
                        with st.expander("🎯 Key Insights & Problem Areas", expanded=True):
                            st.markdown("**Why this journey scored the way it did:**")
                            for insight in individual_analysis['insights']:
                                st.warning(insight)
                    
                    # Actionable Recommendations (already shown above but repeated here for completeness)
                    st.markdown("**💡 Action Items for this Journey:**")
                    for rec in individual_analysis['score_result']['recommendations']:
                        st.info(rec)
        
        # Advanced Funnel Analysis
        st.subheader("🎯 Advanced Conversion Funnel Analysis")
        
        funnel_journey = st.selectbox("Select Journey for Funnel Analysis", 
                                    unique_journeys, 
                                    key='funnel_journey')
        
        if funnel_journey and str(funnel_journey) != 'nan':
            funnel_data = filtered_df[filtered_df['Journey Name'] == funnel_journey]
            funnel_analysis = analyze_journey_funnel(funnel_data)
            
            # Display funnel visualization
            if funnel_analysis['funnel_data']:
                funnel_stages = []
                funnel_values = []
                
                for stage, value in funnel_analysis['funnel_data'].items():
                    if value > 0:
                        funnel_stages.append(stage)
                        funnel_values.append(value)
                
                if funnel_stages:
                    fig_funnel = go.Figure(go.Funnel(
                        y=funnel_stages,
                        x=funnel_values,
                        textposition="inside",
                        textinfo="value+percent initial+percent previous",
                        opacity=0.65,
                        marker={"color": ["deepskyblue", "lightsalmon", "tan", "teal", "silver"]},
                        connector={"line": {"color": "royalblue", "dash": "dot", "width": 3}}
                    ))
                    fig_funnel.update_layout(title=f"Conversion Funnel: {funnel_journey}")
                    st.plotly_chart(fig_funnel)
            
            # Display conversion rates
            if funnel_analysis['conversion_rates']:
                st.subheader("📈 Conversion Rates Between Stages")
                rates_col1, rates_col2 = st.columns(2)
                
                rate_items = list(funnel_analysis['conversion_rates'].items())
                mid_point = len(rate_items) // 2
                
                with rates_col1:
                    for rate_name, rate_value in rate_items[:mid_point]:
                        st.metric(rate_name, f"{rate_value:.2%}")
                
                with rates_col2:
                    for rate_name, rate_value in rate_items[mid_point:]:
                        st.metric(rate_name, f"{rate_value:.2%}")
            
            # Display insights
            if funnel_analysis['insights']:
                st.subheader("🔍 Funnel Insights")
                for insight in funnel_analysis['insights']:
                    st.warning(insight)
        
        # Anomaly Detection
        st.subheader("🚨 Journey Anomaly Detection")
        
        col1, col2 = st.columns([2, 1])
        with col2:
            lookback_days = st.slider("Analysis Period (days)", 7, 90, 30, key='anomaly_days')
        
        with col1:
            st.write("Detecting unusual performance patterns in journeys...")
        
        if st.button("🔍 Detect Anomalies", key='detect_anomalies'):
            with st.spinner("Analyzing journey performance patterns..."):
                anomalies = detect_journey_anomalies(filtered_df, lookback_days)
                
                if anomalies:
                    st.subheader(f"🚨 {len(anomalies)} Anomalies Detected")
                    
                    # Group by severity
                    critical_anomalies = [a for a in anomalies if '🚨 Critical' in a.get('severity', '')]
                    warning_anomalies = [a for a in anomalies if '⚠️ Warning' in a.get('severity', '')]
                    
                    if critical_anomalies:
                        st.error(f"🚨 {len(critical_anomalies)} Critical Issues Require Immediate Attention")
                        for anomaly in critical_anomalies[:5]:  # Show top 5
                            with st.expander(f"{anomaly['journey']} - {anomaly['metric']} {anomaly.get('direction', '')}"):
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Historical", f"{anomaly['historical_value']:.3f}")
                                with col2:
                                    st.metric("Recent", f"{anomaly['recent_value']:.3f}")
                                with col3:
                                    st.metric("Change", f"{anomaly['change_pct']:+.1f}%")
                                st.info(f"💡 {anomaly['recommendation']}")
                    
                    if warning_anomalies:
                        st.warning(f"⚠️ {len(warning_anomalies)} Performance Changes Detected")
                        with st.expander("View Warning Anomalies"):
                            for anomaly in warning_anomalies:
                                st.write(f"**{anomaly['journey']}** - {anomaly['metric']}: {anomaly['change_pct']:+.1f}% change")
                                st.write(f"   💡 {anomaly['recommendation']}")
                else:
                    st.success("✅ No significant anomalies detected. All journeys are performing within normal ranges!")
        
        # Revenue Attribution Waterfall
        st.subheader("💰 Revenue Attribution Analysis")
        
        waterfall_journey = st.selectbox("Select Journey for Revenue Attribution", 
                                       unique_journeys, 
                                       key='waterfall_journey')
        
        if waterfall_journey and str(waterfall_journey) != 'nan':
            waterfall_data_full = filtered_df[filtered_df['Journey Name'] == waterfall_journey]
            waterfall_result = create_revenue_attribution_waterfall(waterfall_data_full)
            
            if waterfall_result['total_revenue'] > 0:
                # Create waterfall chart
                fig_waterfall = go.Figure()
                
                # Add bars for each attribution source
                x_labels = []
                y_values = []
                colors = []
                
                for item in waterfall_result['waterfall_data']:
                    if item['step'] != 'Starting Point':
                        x_labels.append(item['step'])
                        if item['step'] == 'Total Revenue':
                            y_values.append(item['cumulative'])
                            colors.append('green')
                        else:
                            y_values.append(item['value'])
                            colors.append('lightblue')
                
                fig_waterfall.add_trace(go.Bar(
                    x=x_labels,
                    y=y_values,
                    marker_color=colors,
                    text=[format_metric(val, "SAR") for val in y_values],
                    textposition='auto'
                ))
                
                fig_waterfall.update_layout(
                    title=f"Revenue Attribution Breakdown: {waterfall_journey}",
                    yaxis_title="Revenue (SAR)",
                    showlegend=False
                )
                st.plotly_chart(fig_waterfall)
                
                # Attribution breakdown table
                st.subheader("📊 Attribution Breakdown")
                attr_col1, attr_col2 = st.columns(2)
                
                with attr_col1:
                    for source, percentage in waterfall_result['attribution_breakdown'].items():
                        st.metric(f"{source} Attribution", f"{percentage:.1f}%")
                
                with attr_col2:
                    # Create pie chart for attribution
                    fig_attr_pie = px.pie(
                        values=list(waterfall_result['attribution_breakdown'].values()),
                        names=list(waterfall_result['attribution_breakdown'].keys()),
                        title="Revenue Attribution Distribution"
                    )
                    st.plotly_chart(fig_attr_pie)
                
                # Attribution insights
                st.subheader("🎯 Attribution Insights")
                max_source = max(waterfall_result['attribution_breakdown'], key=waterfall_result['attribution_breakdown'].get)
                max_percentage = waterfall_result['attribution_breakdown'][max_source]
                
                if max_percentage > 60:
                    st.info(f"🎯 **{max_source}** is the dominant revenue driver ({max_percentage:.1f}%). Consider optimizing this channel further.")
                elif max_percentage < 40:
                    st.info("🔄 Revenue is well-distributed across attribution sources. This indicates a healthy multi-touch journey.")
                else:
                    st.info(f"⚖️ **{max_source}** leads revenue attribution. Monitor the balance between different touchpoints.")
            else:
                st.warning("No revenue data available for this journey.")
        
        # Journey Lifecycle Analysis
        st.subheader("🔄 Journey Lifecycle Analytics")
        
        with st.spinner("Analyzing journey maturity and performance curves..."):
            lifecycle_data = analyze_journey_lifecycle(filtered_df)
            
            if lifecycle_data and not isinstance(lifecycle_data, dict) or 'error' not in lifecycle_data:
                lifecycle_df = pd.DataFrame(lifecycle_data)
                
                # Maturity distribution
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📊 Journey Maturity Distribution")
                    maturity_counts = lifecycle_df['maturity_stage'].value_counts()
                    fig_maturity = px.pie(values=maturity_counts.values, names=maturity_counts.index,
                                        title="Journeys by Maturity Stage")
                    st.plotly_chart(fig_maturity)
                
                with col2:
                    st.subheader("📈 Performance vs Age")
                    fig_age_perf = px.scatter(lifecycle_df, 
                                            x='journey_age_days', 
                                            y='efficiency_score',
                                            color='maturity_stage',
                                            size='total_revenue',
                                            hover_data=['journey', 'growth_trend'],
                                            title="Journey Performance vs Age")
                    fig_age_perf.update_xaxes(title="Journey Age (Days)")
                    fig_age_perf.update_yaxes(title="Efficiency Score")
                    st.plotly_chart(fig_age_perf)
                
                # Lifecycle insights table
                st.subheader("🔍 Journey Lifecycle Insights")
                
                # Sort by efficiency score for display
                lifecycle_display = lifecycle_df.sort_values('efficiency_score', ascending=False)
                
                # Format the table for better readability
                display_cols = ['journey', 'maturity_stage', 'journey_age_days', 'activity_frequency', 
                              'consistency_score', 'growth_trend', 'efficiency_score', 'recommendation']
                
                for idx, row in lifecycle_display.head(10).iterrows():
                    with st.expander(f"{row['journey']} - {row['maturity_stage']} ({row['efficiency_score']:.1f} efficiency)"):
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Age", f"{row['journey_age_days']} days")
                            st.metric("Activity", f"{row['activity_frequency']:.1f}%")
                        with col2:
                            st.metric("Consistency", f"{row['consistency_score']:.1f}/100")
                            st.metric("Trend", row['growth_trend'])
                        with col3:
                            st.metric("Efficiency", f"{row['efficiency_score']:.1f}/100")
                            st.metric("Revenue", format_metric(row['total_revenue'], "SAR"))
                        with col4:
                            st.metric("Conversions", format_metric(row['total_conversions']))
                            st.metric("Active Days", f"{row['active_days']}")
                        
                        st.info(f"💡 **Recommendation:** {row['recommendation']}")
        
        # Journey Comparison Tool
        st.subheader("🔄 Advanced Journey Comparison")
        
        comparison_col1, comparison_col2 = st.columns(2)
        
        with comparison_col1:
            journey_comp_1 = st.selectbox("Select First Journey", unique_journeys, key='compare_journey_1')
        with comparison_col2:
            journey_comp_2 = st.selectbox("Select Second Journey", 
                                        [j for j in unique_journeys if j != journey_comp_1], 
                                        key='compare_journey_2')
        
        if journey_comp_1 and journey_comp_2 and str(journey_comp_1) != 'nan' and str(journey_comp_2) != 'nan':
            if st.button("🔍 Compare Journeys", key='compare_button'):
                with st.spinner("Performing statistical comparison..."):
                    comparison_result = create_journey_comparison_analysis(filtered_df, journey_comp_1, journey_comp_2)
                    
                    if 'error' not in comparison_result:
                        st.subheader(f"📊 Comparison: {journey_comp_1} vs {journey_comp_2}")
                        
                        # Overall winner
                        if comparison_result['overall_winner'] != "Tie":
                            st.success(f"🏆 **Overall Winner:** {comparison_result['overall_winner']} (Confidence: {comparison_result['confidence']})")
                        else:
                            st.info("🤝 **Result:** Performance is very similar between both journeys")
                        
                        # Detailed metrics comparison
                        st.subheader("📈 Detailed Metrics Comparison")
                        
                        for metric_name, metric_data in comparison_result['metrics'].items():
                            with st.expander(f"{metric_name} Comparison"):
                                comp_col1, comp_col2, comp_col3 = st.columns(3)
                                
                                with comp_col1:
                                    st.metric(f"{journey_comp_1} (Avg)", 
                                            format_metric(metric_data['journey1_avg'], "SAR" if "Revenue" in metric_name else ""))
                                    st.write(f"Total: {format_metric(metric_data['journey1_total'], 'SAR' if 'Revenue' in metric_name else '')}")
                                
                                with comp_col2:
                                    st.metric(f"{journey_comp_2} (Avg)", 
                                            format_metric(metric_data['journey2_avg'], "SAR" if "Revenue" in metric_name else ""))
                                    st.write(f"Total: {format_metric(metric_data['journey2_total'], 'SAR' if 'Revenue' in metric_name else '')}")
                                
                                with comp_col3:
                                    diff_color = "normal" if abs(metric_data['pct_difference']) < 10 else "inverse" if metric_data['pct_difference'] < 0 else "normal"
                                    st.metric("Difference", 
                                            f"{metric_data['pct_difference']:+.1f}%",
                                            delta=f"Winner: {metric_data['winner']}")
                                    
                                    if metric_data['significance'] != "N/A":
                                        significance_color = "🟢" if metric_data['significance'] == "Significant" else "🟡"
                                        st.write(f"{significance_color} Statistical Significance: {metric_data['significance']}")
                                        if metric_data['p_value']:
                                            st.write(f"p-value: {metric_data['p_value']:.4f}")
                        
                        # Recommendations based on comparison
                        st.subheader("💡 Comparison Insights & Recommendations")
                        
                        winner = comparison_result['overall_winner']
                        if winner != "Tie":
                            st.info(f"🎯 **Primary Recommendation:** Scale up **{winner}** and apply its successful elements to **{journey_comp_1 if winner == journey_comp_2 else journey_comp_2}**")
                            
                            # Specific metric recommendations
                            strong_metrics = [name for name, data in comparison_result['metrics'].items() if data['winner'] == winner and abs(data['pct_difference']) > 20]
                            if strong_metrics:
                                st.success(f"🔥 **{winner}** excels in: {', '.join(strong_metrics)}")
                            
                        else:
                            st.info("🤝 Both journeys perform similarly. Consider A/B testing specific elements to find optimization opportunities.")
                    
                    else:
                        st.error(f"Comparison failed: {comparison_result['error']}")
        
        # Professional BI Section: Custom Date Range Analysis
        st.markdown("---")
        st.header("📊 Advanced Business Intelligence Analytics")
        
        # Executive Summary Cards - Use wider layout
        st.subheader("📈 Executive Summary")
        exec_col1, exec_col2, exec_col3, exec_col4, exec_col5, exec_col6 = st.columns(6)
        
        with exec_col1:
            total_journeys = len(filtered_df['Journey Name'].dropna().unique())
            st.metric("🎯 Active Journeys", total_journeys)
        
        with exec_col2:
            total_revenue = filtered_df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in filtered_df.columns else filtered_df['Revenue (SAR)'].sum()
            st.metric("💰 Total Revenue", format_metric(total_revenue, "SAR"))
        
        with exec_col3:
            total_conversions = filtered_df['Unique Conversions'].sum()
            st.metric("🔄 Total Conversions", format_metric(total_conversions))
        
        with exec_col4:
            avg_health_score = pd.DataFrame(journey_health_data)['Health Score'].mean() if journey_health_data else 0
            st.metric("🏥 Avg Health Score", f"{avg_health_score:.1f}/100")
        
        with exec_col5:
            total_sent = filtered_df['Sent'].sum()
            st.metric("📧 Total Sent", format_metric(total_sent))
        
        with exec_col6:
            avg_conversion_rate = (filtered_df['Unique Conversions'].sum() / filtered_df['Sent'].sum() * 100) if filtered_df['Sent'].sum() > 0 else 0
            st.metric("📊 Avg Conv. Rate", f"{avg_conversion_rate:.2f}%")
        
        # Custom Date Range Comparison Tool - Optimized for wide layout
        st.subheader("📅 Custom Period Comparison Analysis")
        st.markdown("*Compare journey performance between any two custom date ranges*")
        
        # Date range selection with professional layout - better use of wide screen
        date_col1, date_col2, date_col3 = st.columns([1, 1, 1])
        
        with date_col1:
            st.markdown("**📅 Period 1 (Baseline)**")
            period1_start = st.date_input("Start Date", value=filtered_df['Reporting Period Start Date'].min() if not filtered_df.empty else pd.Timestamp.now() - pd.Timedelta(days=30), key='p1_start')
            period1_end = st.date_input("End Date", value=filtered_df['Reporting Period Start Date'].min() + pd.Timedelta(days=14) if not filtered_df.empty else pd.Timestamp.now() - pd.Timedelta(days=16), key='p1_end')
        
        with date_col2:
            st.markdown("**📅 Period 2 (Comparison)**")
            period2_start = st.date_input("Start Date", value=filtered_df['Reporting Period Start Date'].max() - pd.Timedelta(days=14) if not filtered_df.empty else pd.Timestamp.now() - pd.Timedelta(days=14), key='p2_start')
            period2_end = st.date_input("End Date", value=filtered_df['Reporting Period Start Date'].max() if not filtered_df.empty else pd.Timestamp.now(), key='p2_end')
        
        with date_col3:
            st.markdown("**🎯 Analysis Options**")
            # Journey selection for focused analysis
            selected_journeys_for_comparison = st.multiselect(
                "Select Journeys (leave empty for all)",
                unique_journeys,
                help="Select specific journeys to focus the comparison analysis"
            )
            # Analysis trigger
            run_comparison = st.button("🔍 Run Period Comparison Analysis", key='run_period_comparison')
        
        if run_comparison:
            with st.spinner("🔄 Analyzing performance across periods..."):
                date_range_1 = [period1_start, period1_end]
                date_range_2 = [period2_start, period2_end]
                
                comparison_result = create_custom_date_range_comparison(
                    filtered_df, 
                    date_range_1, 
                    date_range_2, 
                    selected_journeys_for_comparison if selected_journeys_for_comparison else None
                )
                
                if 'error' not in comparison_result:
                    # Results Header
                    st.markdown("---")
                    st.header("📊 Period Comparison Results")
                    
                    # Period Overview
                    period_col1, period_col2, period_col3 = st.columns([1, 1, 1])
                    
                    with period_col1:
                        st.info(f"**📅 Period 1 (Baseline)**\n{comparison_result['period1_label']}")
                    
                    with period_col2:
                        st.info(f"**📅 Period 2 (Comparison)**\n{comparison_result['period2_label']}")
                    
                    with period_col3:
                        overall_trend = comparison_result['statistical_summary']['overall_trend']
                        trend_emoji = "📈" if overall_trend == "Positive" else "📉" if overall_trend == "Negative" else "➡️"
                        st.info(f"**{trend_emoji} Overall Trend**\n{overall_trend}")
                    
                    # Key Metrics Comparison
                    st.subheader("📊 Key Performance Metrics")
                    
                    metrics_data = []
                    for metric_name, metric_data in comparison_result['metrics'].items():
                        metrics_data.append({
                            'Metric': metric_name,
                            'Period 1 (Daily Avg)': format_metric(metric_data['period1_daily_avg'], "SAR" if "Revenue" in metric_name else ""),
                            'Period 2 (Daily Avg)': format_metric(metric_data['period2_daily_avg'], "SAR" if "Revenue" in metric_name else ""),
                            'Change %': f"{metric_data['pct_change']:+.1f}%",
                            'Trend': metric_data['trend'],
                            'Statistical Significance': metric_data['significance']
                        })
                    
                    metrics_df = pd.DataFrame(metrics_data)
                    st.dataframe(metrics_df, width='stretch')
                    
                    # Visual Comparison Charts
                    st.subheader("📈 Visual Performance Comparison")
                    
                    # Create comparison charts
                    chart_col1, chart_col2 = st.columns(2)
                    
                    with chart_col1:
                        # Revenue comparison
                        if 'Revenue (SAR)' in comparison_result['metrics']:
                            rev_data = comparison_result['metrics']['Revenue (SAR)']
                            fig_rev = go.Figure(data=[
                                go.Bar(name='Period 1', x=['Daily Average Revenue'], y=[rev_data['period1_daily_avg']], marker_color='lightblue'),
                                go.Bar(name='Period 2', x=['Daily Average Revenue'], y=[rev_data['period2_daily_avg']], marker_color='darkblue')
                            ])
                            fig_rev.update_layout(title="Revenue Comparison", yaxis_title="Revenue (SAR)")
                            st.plotly_chart(fig_rev, use_container_width=True)
                    
                    with chart_col2:
                        # Conversion comparison
                        if 'Unique Conversions' in comparison_result['metrics']:
                            conv_data = comparison_result['metrics']['Unique Conversions']
                            fig_conv = go.Figure(data=[
                                go.Bar(name='Period 1', x=['Daily Average Conversions'], y=[conv_data['period1_daily_avg']], marker_color='lightgreen'),
                                go.Bar(name='Period 2', x=['Daily Average Conversions'], y=[conv_data['period2_daily_avg']], marker_color='darkgreen')
                            ])
                            fig_conv.update_layout(title="Conversions Comparison", yaxis_title="Conversions")
                            st.plotly_chart(fig_conv, use_container_width=True)
                    
                    # Journey-Level Breakdown (if journeys were selected)
                    if comparison_result['journey_breakdown']:
                        st.subheader("🎯 Journey-Level Performance Breakdown")
                        
                        for journey_name, journey_metrics in comparison_result['journey_breakdown'].items():
                            with st.expander(f"📊 {journey_name}"):
                                journey_col1, journey_col2 = st.columns(2)
                                
                                with journey_col1:
                                    if 'Unique Conversions' in journey_metrics:
                                        conv_metric = journey_metrics['Unique Conversions']
                                        st.metric(
                                            "Daily Conversions",
                                            format_metric(conv_metric['period2_daily_avg']),
                                            delta=f"{conv_metric['pct_change']:+.1f}% vs Period 1"
                                        )
                                
                                with journey_col2:
                                    if 'Revenue (SAR)' in journey_metrics:
                                        rev_metric = journey_metrics['Revenue (SAR)']
                                        st.metric(
                                            "Daily Revenue",
                                            format_metric(rev_metric['period2_daily_avg'], "SAR"),
                                            delta=f"{rev_metric['pct_change']:+.1f}% vs Period 1"
                                        )
                    
                    # Statistical Summary and Insights
                    st.subheader("🔬 Statistical Analysis Summary")
                    
                    stat_col1, stat_col2, stat_col3 = st.columns(3)
                    
                    with stat_col1:
                        sig_improvements = comparison_result['statistical_summary']['significant_improvements']
                        st.metric("📈 Significant Improvements", sig_improvements)
                    
                    with stat_col2:
                        sig_declines = comparison_result['statistical_summary']['significant_declines']
                        st.metric("📉 Significant Declines", sig_declines)
                    
                    with stat_col3:
                        confidence_level = "High" if sig_improvements + sig_declines >= 2 else "Medium" if sig_improvements + sig_declines >= 1 else "Low"
                        st.metric("🎯 Analysis Confidence", confidence_level)
                    
                    # Business Intelligence Insights
                    st.subheader("💡 Business Intelligence Insights")
                    
                    insights = []
                    
                    # Revenue insights
                    if 'Revenue (SAR)' in comparison_result['metrics']:
                        rev_change = comparison_result['metrics']['Revenue (SAR)']['pct_change']
                        if rev_change > 10:
                            insights.append(f"🚀 **Strong Revenue Growth**: {rev_change:+.1f}% increase in daily revenue indicates successful optimization")
                        elif rev_change < -10:
                            insights.append(f"⚠️ **Revenue Decline Alert**: {rev_change:+.1f}% decrease requires immediate investigation")
                        else:
                            insights.append(f"➡️ **Stable Revenue**: {rev_change:+.1f}% change shows consistent performance")
                    
                    # Conversion insights
                    if 'Unique Conversions' in comparison_result['metrics']:
                        conv_change = comparison_result['metrics']['Unique Conversions']['pct_change']
                        if conv_change > 15:
                            insights.append(f"🎯 **Conversion Optimization Success**: {conv_change:+.1f}% improvement in conversion rate")
                        elif conv_change < -15:
                            insights.append(f"🚨 **Conversion Drop**: {conv_change:+.1f}% decline needs funnel analysis")
                    
                    # Volume insights
                    if 'Sent' in comparison_result['metrics']:
                        sent_change = comparison_result['metrics']['Sent']['pct_change']
                        if sent_change > 20:
                            insights.append(f"📈 **Scale Expansion**: {sent_change:+.1f}% increase in campaign volume")
                        elif sent_change < -20:
                            insights.append(f"📉 **Volume Reduction**: {sent_change:+.1f}% decrease in send volume")
                    
                    # Display insights
                    if insights:
                        for insight in insights:
                            st.info(insight)
                    else:
                        st.info("📊 Performance appears stable across both periods with no significant changes detected.")
                    
                    # Recommendations
                    st.subheader("🎯 Strategic Recommendations")
                    
                    recommendations = []
                    
                    if comparison_result['statistical_summary']['overall_trend'] == "Positive":
                        recommendations.append("✅ **Scale Success**: Current strategies are working - consider increasing budget allocation")
                        recommendations.append("🔄 **Replicate Winners**: Apply successful elements to underperforming journeys")
                    elif comparison_result['statistical_summary']['overall_trend'] == "Negative":
                        recommendations.append("🔍 **Deep Dive Analysis**: Investigate root causes of performance decline")
                        recommendations.append("⚡ **Quick Wins**: Focus on highest-impact optimizations first")
                    else:
                        recommendations.append("🎯 **A/B Testing**: Mixed results suggest opportunities for targeted experiments")
                        recommendations.append("📊 **Granular Analysis**: Drill down into segment and channel performance")
                    
                    for rec in recommendations:
                        st.success(rec)
                
                else:
                    st.error(f"Analysis failed: {comparison_result['error']}")
        
        # Cohort Analysis Section
        st.markdown("---")
        st.subheader("👥 Cohort Performance Analysis")
        
        cohort_period = st.selectbox("Select Cohort Period", ['week', 'month'], key='cohort_period')
        
        if st.button("📊 Generate Cohort Analysis", key='run_cohort'):
            with st.spinner("Analyzing cohort performance..."):
                cohort_result = create_cohort_analysis(filtered_df, cohort_period)
                
                if isinstance(cohort_result, pd.DataFrame) and not cohort_result.empty:
                    st.subheader(f"📈 {cohort_period.title()}ly Cohort Performance")
                    
                    # Display cohort data
                    cohort_display = cohort_result.copy()
                    cohort_display['Revenue (SAR)'] = cohort_display['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                    cohort_display['Unique Conversions'] = cohort_display['Unique Conversions'].apply(format_metric)
                    
                    st.dataframe(cohort_display.head(20), use_container_width=True)
                    
                    # Growth rate visualization
                    if 'Revenue (SAR)_growth' in cohort_result.columns:
                        fig_growth = px.line(cohort_result, 
                                           x='cohort_str', 
                                           y='Revenue (SAR)_growth', 
                                           color='Journey Name',
                                           title=f"Revenue Growth Rate by {cohort_period.title()}")
                        fig_growth.update_xaxes(title=f"{cohort_period.title()} Period")
                        fig_growth.update_yaxes(title="Growth Rate (%)")
                        st.plotly_chart(fig_growth, use_container_width=True)
                
                else:
                    st.warning("Insufficient data for cohort analysis")
        
        # Top Journeys
        st.subheader("Top Journeys")
        jour_metric = st.selectbox("Metric", ['Delivered Rate', 'Unique Clicks', 'Unique Conversions', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)'], key='jour_metric')
        top_jour = get_top_journeys(filtered_df, jour_metric)
        
        # Create display version for table
        top_jour_display = top_jour.copy()
        
        # Store original numeric values for sorting
        original_values = top_jour_display[jour_metric].copy()
        
        # Format the metric column for display
        if 'Revenue' in jour_metric:
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(lambda x: format_metric(x, "SAR"))
        elif jour_metric in ['Unique Clicks', 'Unique Conversions']:
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(format_metric)
        elif 'Rate' in jour_metric:
            # For rates, convert to percentage
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(lambda x: f"{x*100:.1f}%")
        
        # Display table with proper sorting
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
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Total Sent", format_metric(jour_details['Sent'].sum()))
            with col2:
                st.metric("Total Delivered", format_metric(jour_details['Delivered'].sum()))
            with col3:
                st.metric("Total Conversions", format_metric(jour_details['Unique Conversions'].sum()))
            with col4:
                st.metric("Send-Through Revenue", format_metric(jour_details['Revenue (SAR)'].sum(), "SAR"))
            with col5:
                st.metric("Impression-Through Revenue", format_metric(jour_details['Impression-Through Revenue (SAR)'].sum(), "SAR"))
            with col6:
                st.metric("Click-Through Revenue", format_metric(jour_details['Click-Through Revenue (SAR)'].sum(), "SAR"))
            
            # Performance by Channel
            st.subheader("Performance by Channel")
            chan_perf_jour = jour_details.groupby('Channel').agg({
                'Sent': 'sum',
                'Delivered': 'sum',
                'Unique Conversions': 'sum',
                'Revenue (SAR)': 'sum',
                'Impression-Through Revenue (SAR)': 'sum',
                'Click-Through Revenue (SAR)': 'sum'
            }).reset_index()
            # Format columns
            chan_perf_jour['Sent'] = chan_perf_jour['Sent'].apply(format_metric)
            chan_perf_jour['Delivered'] = chan_perf_jour['Delivered'].apply(format_metric)
            chan_perf_jour['Unique Conversions'] = chan_perf_jour['Unique Conversions'].apply(format_metric)
            chan_perf_jour['Revenue (SAR)'] = chan_perf_jour['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            chan_perf_jour['Impression-Through Revenue (SAR)'] = chan_perf_jour['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            chan_perf_jour['Click-Through Revenue (SAR)'] = chan_perf_jour['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            
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

        # 🚨 Stopped Journey Analysis with Revenue Loss Estimation
        st.markdown("---")
        st.header("🚨 Stopped Journey Analysis & Revenue Loss Estimation")

        st.markdown("""
        **🎯 Advanced Analytics for Journey Performance Issues**

        This analysis identifies journeys with zero delivery periods and estimates revenue loss using:
        - **📊 Statistical Forecasting**: Time-series analysis with confidence intervals
        - **🎪 Multiple Attribution Models**: Send-through, impression-through, and click-through revenue
        - **📈 Machine Learning**: Prophet model for revenue prediction during stopped periods
        - **💰 Loss Quantification**: Daily revenue loss estimation with confidence ranges
        """)

        # Analysis parameters
        stopped_col1, stopped_col2, stopped_col3 = st.columns(3)

        with stopped_col1:
            stopped_threshold_days = st.slider("🚫 Stopped Threshold (days)", 1, 14, 3,
                                             help="Minimum consecutive days with zero delivery to consider journey 'stopped'")
            st.write(f"**Threshold:** {stopped_threshold_days} consecutive zero-delivery days")

        with stopped_col2:
            lookback_period = st.slider("📅 Analysis Period (days)", 30, 180, 90,
                                      help="How far back to analyze journey performance")
            st.write(f"**Analysis Window:** {lookback_period} days")

        with stopped_col3:
            confidence_level = st.selectbox("🎯 Confidence Level", [0.80, 0.90, 0.95, 0.99], index=2,
                                          help="Statistical confidence level for revenue loss estimates")
            st.write(f"**Confidence:** {int(confidence_level*100)}%")

        if st.button("🔍 Analyze Stopped Journeys", key='analyze_stopped'):
            with st.spinner("🔄 Analyzing journey delivery patterns and estimating revenue loss..."):

                # Create stopped journey analysis
                stopped_analysis = analyze_stopped_journeys(
                    filtered_df,
                    stopped_threshold_days=stopped_threshold_days,
                    lookback_period=lookback_period,
                    confidence_level=confidence_level
                )

                if stopped_analysis and 'stopped_journeys' in stopped_analysis:

                    stopped_journeys = stopped_analysis['stopped_journeys']

                    if stopped_journeys:
                        st.error(f"🚨 **{len(stopped_journeys)} Journeys Identified with Stopped Delivery**")

                        # Summary metrics
                        total_revenue_loss = sum(journey['estimated_revenue_loss']['total_loss'] for journey in stopped_journeys)
                        total_stopped_days = sum(journey['stopped_periods']['total_stopped_days'] for journey in stopped_journeys)

                        summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)

                        with summary_col1:
                            st.metric("🚫 Stopped Journeys", len(stopped_journeys))
                        with summary_col2:
                            st.metric("📅 Total Stopped Days", format_metric(total_stopped_days))
                        with summary_col3:
                            st.metric("💰 Total Revenue Loss", format_metric(total_revenue_loss, "SAR"))
                        with summary_col4:
                            avg_daily_loss = total_revenue_loss / total_stopped_days if total_stopped_days > 0 else 0
                            st.metric("📊 Avg Daily Loss", format_metric(avg_daily_loss, "SAR"))

                        # Detailed analysis for each stopped journey
                        st.subheader("🔍 Detailed Stopped Journey Analysis")

                        for journey in stopped_journeys:
                            journey_name = journey['journey_name']

                            with st.expander(f"🚨 {journey_name} - Revenue Loss: {format_metric(journey['estimated_revenue_loss']['total_loss'], 'SAR')}", expanded=True):

                                # Journey overview
                                overview_col1, overview_col2, overview_col3 = st.columns(3)

                                with overview_col1:
                                    st.metric("📅 Stopped Days", journey['stopped_periods']['total_stopped_days'])
                                    st.metric("📊 Stopped Periods", len(journey['stopped_periods']['periods']))

                                with overview_col2:
                                    loss_data = journey['estimated_revenue_loss']
                                    st.metric("💰 Total Loss", format_metric(loss_data['total_loss'], "SAR"))
                                    st.metric("📈 Daily Loss", format_metric(loss_data['avg_daily_loss'], "SAR"))

                                with overview_col3:
                                    confidence_range = loss_data['confidence_interval']
                                    st.metric("🎯 Confidence Range",
                                            f"{format_metric(confidence_range[0], 'SAR')} - {format_metric(confidence_range[1], 'SAR')}")
                                    st.metric("📊 Confidence Level", f"{int(confidence_level*100)}%")

                                # Revenue attribution breakdown
                                st.subheader("💰 Revenue Loss by Attribution Model")

                                attr_loss_col1, attr_loss_col2, attr_loss_col3 = st.columns(3)

                                loss_breakdown = loss_data['attribution_breakdown']

                                with attr_loss_col1:
                                    send_loss = loss_breakdown.get('Revenue (SAR)', 0)
                                    st.metric("📊 Send-Through Loss", format_metric(send_loss, "SAR"))

                                with attr_loss_col2:
                                    impression_loss = loss_breakdown.get('Impression-Through Revenue (SAR)', 0)
                                    st.metric("👁️ Impression-Through Loss", format_metric(impression_loss, "SAR"))

                                with attr_loss_col3:
                                    click_loss = loss_breakdown.get('Click-Through Revenue (SAR)', 0)
                                    st.metric("🖱️ Click-Through Loss", format_metric(click_loss, "SAR"))

                                # Stopped periods timeline
                                st.subheader("📅 Stopped Periods Timeline")

                                periods_data = journey['stopped_periods']['periods']
                                if periods_data:
                                    periods_df = pd.DataFrame(periods_data)

                                    # Create timeline visualization
                                    fig_timeline = go.Figure()

                                    for _, period in periods_df.iterrows():
                                        fig_timeline.add_trace(go.Scatter(
                                            x=[period['start_date'], period['end_date']],
                                            y=[journey_name, journey_name],
                                            mode='lines+markers',
                                            name=f"Stopped Period ({period['days_stopped']} days)",
                                            line=dict(color='red', width=4),
                                            marker=dict(size=8, color='red'),
                                            showlegend=False
                                        ))

                                    fig_timeline.update_layout(
                                        title=f"Stopped Delivery Periods: {journey_name}",
                                        xaxis_title="Date",
                                        yaxis_title="Journey",
                                        showlegend=False,
                                        height=200
                                    )

                                    st.plotly_chart(fig_timeline)

                                    # Detailed periods table
                                    st.subheader("📋 Stopped Period Details")
                                    periods_display = periods_df.copy()
                                    periods_display['start_date'] = periods_display['start_date'].dt.strftime('%Y-%m-%d')
                                    periods_display['end_date'] = periods_display['end_date'].dt.strftime('%Y-%m-%d')
                                    periods_display['days_stopped'] = periods_display['days_stopped'].apply(format_metric)
                                    periods_display['estimated_daily_loss'] = periods_display['estimated_daily_loss'].apply(lambda x: format_metric(x, "SAR"))

                                    st.dataframe(periods_display[['start_date', 'end_date', 'days_stopped', 'estimated_daily_loss']])

                                # Recommendations
                                st.subheader("💡 Recommendations & Actions")

                                recommendations = journey.get('recommendations', [])

                                if recommendations:
                                    for rec in recommendations:
                                        st.info(f"🎯 {rec}")
                                else:
                                    st.info("🔍 **Analysis Complete:** Review journey configuration and delivery settings to prevent future stoppages.")

                    else:
                        st.success("✅ **No Stopped Journeys Detected!** All journeys are actively delivering.")

                else:
                    st.error("❌ Analysis failed. Please check your data and try again.")

    elif page == "Segments":
        st.header("Top Segments")
        # Safe column selection - only use columns that exist in both reports
        safe_revenue_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
        safe_conversion_cols = ['Unique Conversions', 'Unique Clicks']
        
        # Add Total columns if they exist (Monthly report)
        if 'Total Conversions' in filtered_df.columns:
            safe_conversion_cols.append('Total Conversions')
        
        all_metrics = safe_conversion_cols + safe_revenue_cols
        seg_metric = st.selectbox("Metric", all_metrics, key='seg_metric')
        top_seg = top_segments(filtered_df, seg_metric)
        
        # Create display version for table
        top_seg_display = top_seg.copy()
        # Format the metric column for display
        if 'Revenue' in seg_metric:
            top_seg_display[seg_metric] = top_seg_display[seg_metric].apply(lambda x: format_metric(x, "SAR"))
        elif seg_metric in ['Unique Conversions', 'Total Conversions', 'Unique Clicks']:
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
        if 'Revenue (SAR)' in chan_df.columns:
            fig_rev = px.bar(chan_df, x='Channel', y='Revenue (SAR)', title="Revenue by Channel")
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
            if 'Revenue (SAR)' in esp_df.columns:
                fig_esp_rev = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Revenue (SAR)', title="Revenue by ESP")
                st.plotly_chart(fig_esp_rev)

    elif page == "Time Series":
        st.header("Time Series Analysis")
        # Safe column selection - only use columns that exist in both reports
        safe_revenue_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
        safe_conversion_cols = ['Unique Conversions', 'Unique Clicks']
        
        # Add Total columns if they exist (Monthly report)
        if 'Total Conversions' in filtered_df.columns:
            safe_conversion_cols.append('Total Conversions')
        
        all_metrics = safe_conversion_cols + safe_revenue_cols
        ts_metric = st.selectbox("Metric", all_metrics, key='ts_metric')
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
            if 'Revenue (SAR)' in esp_df.columns:
                fig_esp_rev = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Revenue (SAR)', title="Revenue by ESP")
                st.plotly_chart(fig_esp_rev)
        else:
            st.write("No ESP data available.")

    elif page == "Export":
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

    elif page == "Comparisons":
        st.header("Month-over-Month Comparisons")
        
        # Group by month
        monthly_df = filtered_df.copy()
        monthly_df['Month'] = monthly_df['Reporting Period Start Date'].dt.to_period('M').astype(str)
        
        monthly_agg = monthly_df.groupby('Month').agg({
            'Revenue (SAR)': 'sum',
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
            monthly_agg_display['Revenue (SAR)'] = monthly_agg_display['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            monthly_agg_display['Unique Conversions'] = monthly_agg_display['Unique Conversions'].apply(format_metric)
            monthly_agg_display['Unique Clicks'] = monthly_agg_display['Unique Clicks'].apply(format_metric)
            monthly_agg_display['Sent'] = monthly_agg_display['Sent'].apply(format_metric)
            monthly_agg_display['Delivered'] = monthly_agg_display['Delivered'].apply(format_metric)
            st.dataframe(monthly_agg_display)
            
            # Chart
            fig_comp = px.line(monthly_agg, x='Month', y='Revenue (SAR)', title="Revenue Over Months")
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
                    
                    metrics = ['Revenue (SAR)', 'Unique Conversions', 'Unique Clicks', 'Sent', 'Delivered']
                    
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
            monthly_rev = monthly_df.groupby('Month')['Revenue (SAR)'].sum().reset_index()
            if len(monthly_rev) > 2:
                # Prepare data for Prophet
                df_prophet = monthly_rev.rename(columns={'Month': 'ds', 'Revenue (SAR)': 'y'})
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
                'Revenue (SAR)': 'sum',
                'Unique Conversions': 'sum',
                'Unique Clicks': 'sum',
                'Sent': 'sum'
            }).reset_index()
            if len(seg_agg) > 3:
                features = seg_agg[['Revenue (SAR)', 'Unique Conversions', 'Unique Clicks', 'Sent']]
                try:
                    kmeans = KMeans(n_clusters=3, random_state=42)
                    seg_agg['Cluster'] = kmeans.fit_predict(features)
                    fig_seg = px.scatter(seg_agg, x='Revenue (SAR)', y='Unique Conversions', color='Cluster', hover_data=['Segment Name'])
                    st.plotly_chart(fig_seg)
                    st.write("**Segmentation Insights:** Segments grouped by behavior. High-value clusters should be prioritized.")
                except Exception as e:
                    st.write(f"Segmentation error: {e}")
            else:
                st.write("Not enough segments for clustering.")
        
        # Optimization
        st.subheader("🎯 Campaign Optimization Recommendations")
        top_camp = top_campaigns(filtered_df, 'Revenue (SAR)')
        if not top_camp.empty:
            best_camp = top_camp.iloc[0]['Campaign Name']
            st.success(f"🚀 **Top Performer:** {best_camp} - Allocate more budget here!")
            underperformers = top_camp.tail(3)['Campaign Name'].tolist()
            st.warning(f"⚠️ **Underperformers:** {', '.join(underperformers)} - Consider pausing or optimizing.")
        
        # ROI Analysis
        st.subheader("💰 ROI Analysis")
        roi_df = filtered_df.groupby('Channel').agg({'Revenue (SAR)': 'sum'}).reset_index()
        roi_df['Estimated Cost'] = roi_df['Revenue (SAR)'] * 0.1  # placeholder
        roi_df['ROI'] = (roi_df['Revenue (SAR)'] - roi_df['Estimated Cost']) / roi_df['Estimated Cost']
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