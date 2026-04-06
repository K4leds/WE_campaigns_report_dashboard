import streamlit as st
import streamlit.components.v1 as components
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
try:
    from prophet import Prophet
except ImportError:
    Prophet = None
import warnings
warnings.filterwarnings('ignore')

# Import centralized configuration and attribution logic
from config import CHANNEL_COSTS, REQUIRED_COLUMNS, COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import apply_attribution, apply_dimension_filters, get_attribution_display_label, get_selected_revenue_display_name, get_selected_conversion_display_name, resolve_source_column

# Register a global Plotly template for consistent styling
import plotly.io as pio

_we_template = go.layout.Template()
_we_template.layout = go.Layout(
    font=dict(family='Inter, Segoe UI, Roboto, sans-serif', size=13, color='#1F2937'),
    title=dict(font=dict(size=18, color='#111827'), x=0, xanchor='left'),
    paper_bgcolor='white',
    plot_bgcolor='white',
    colorway=COLOR_SEQUENCE,
    xaxis=dict(showgrid=False, linecolor='#E5E7EB', linewidth=1),
    yaxis=dict(gridcolor='#F3F4F6', gridwidth=1, linecolor='#E5E7EB', linewidth=1, zerolinecolor='#E5E7EB'),
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1, bgcolor='rgba(0,0,0,0)'),
    margin=dict(l=40, r=20, t=50, b=40),
    hovermode='x unified',
)
pio.templates['we_dashboard'] = _we_template
pio.templates.default = 'plotly_white+we_dashboard'


def export_chart_image(fig, filename='chart', fmt='png', width=1200, height=600):
    """Export a Plotly figure as a downloadable image buffer.
    Returns BytesIO buffer or None if kaleido is not installed."""
    try:
        buf = BytesIO()
        fig.write_image(buf, format=fmt, width=width, height=height, scale=2)
        buf.seek(0)
        return buf
    except Exception:
        return None


def style_total_row(df):
    """Apply bold + light background styling to the last row (Total row) of a DataFrame.
    Returns a pandas Styler object suitable for st.dataframe()."""
    def _highlight_last(row):
        if row.name == len(df) - 1:
            return ['font-weight: bold; background-color: #0EA5E9; color: #FFFFFF'] * len(row)
        return [''] * len(row)
    return df.style.apply(_highlight_last, axis=1)


# Import our new insights engine
from insights_engine import (
    generate_narrative_insights,
    predict_revenue_forecast,
    generate_top_actions,
    generate_executive_summary
)

# Configure page layout for wide mode - better for BI dashboards
st.set_page_config(
    page_title="WebEngage Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

def format_metric(value, unit="", abbreviate=True):
    """
    Format metric values for display.
    
    Args:
        value: The numeric value to format
        unit: Optional unit label (e.g., "SAR")
        abbreviate: If True, use K/M abbreviations. If False, show full number with commas
    """
    if isinstance(value, (int, float, np.integer, np.floating)) and not pd.isna(value):
        if abbreviate:
            abs_val = abs(value)
            if abs_val >= 1e6:
                return f"{value/1e6:.1f}M {unit}".strip()
            elif abs_val >= 1e3:
                return f"{value/1e3:.1f}K {unit}".strip()
            else:
                return f"{value:,.0f} {unit}".strip()
        else:
            # Show full number with thousand separators
            return f"{value:,.0f} {unit}".strip()
    else:
        return f"{value} {unit}".strip()

def _month_range_options(start_date, end_date):
    if pd.isna(start_date) or pd.isna(end_date):
        return []
    start = pd.Period(pd.to_datetime(start_date), freq='M')
    end = pd.Period(pd.to_datetime(end_date), freq='M')
    months = pd.period_range(start, end, freq='M')
    return [m.to_timestamp() for m in months]

st.title("WebEngage CSV Dashboard")

# Sidebar navigation
page = st.sidebar.selectbox("Navigate to", [
    "🎯 Automated Insights",  # NEW: Featured at top
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
        df['CTR'] = np.where(df['Unique Impressions'] > 0, np.minimum(df['Unique Clicks'] / df['Unique Impressions'], 1.0), 0)
    else:
        df['CTR'] = 0
    
    if 'Unique Conversions' in df.columns and 'Unique Clicks' in df.columns:
        df['Conversion Rate'] = np.where(df['Unique Clicks'] > 0, np.minimum(df['Unique Conversions'] / df['Unique Clicks'], 1.0), 0)
    else:
        df['Conversion Rate'] = 0
    
    if 'Delivered' in df.columns and 'Sent' in df.columns:
        df['Delivery Rate'] = np.where(df['Sent'] > 0, np.minimum(df['Delivered'] / df['Sent'], 1.0), 0)
    else:
        df['Delivery Rate'] = 0
    
    # Add new business metrics
    # Revenue Per Click (RPC) - Shows quality of clicks
    revenue_cols = [col for col in df.columns if 'Revenue' in col and 'Rate' not in col]
    if revenue_cols and 'Unique Clicks' in df.columns:
        revenue_col = revenue_cols[0]
        df['Revenue Per Click'] = np.where(df['Unique Clicks'] > 0, df[revenue_col] / df['Unique Clicks'], 0)
    else:
        df['Revenue Per Click'] = 0
    
    # Average Order Value (AOV) - Revenue per conversion
    if revenue_cols and 'Unique Conversions' in df.columns:
        revenue_col = revenue_cols[0]
        df['AOV'] = np.where(df['Unique Conversions'] > 0, df[revenue_col] / df['Unique Conversions'], 0)
    else:
        df['AOV'] = 0
    
    # Engagement Rate - Combined engagement metric
    # For channels with Opens (Email, Push): (Clicks + Opens) / Impressions
    # For channels without Opens: Clicks / Impressions (same as CTR)
    if 'Unique Opens' in df.columns and 'Unique Impressions' in df.columns and 'Unique Clicks' in df.columns:
        df['Engagement Rate'] = np.where(
            df['Unique Impressions'] > 0, 
            (df['Unique Clicks'] + df['Unique Opens']) / df['Unique Impressions'], 
            0
        )
    elif 'Unique Clicks' in df.columns and 'Unique Impressions' in df.columns:
        df['Engagement Rate'] = np.where(df['Unique Impressions'] > 0, df['Unique Clicks'] / df['Unique Impressions'], 0)
    else:
        df['Engagement Rate'] = 0
    
    # === COST-BASED METRICS ===
    # Calculate campaign cost based on channel and sends (uses centralized CHANNEL_COSTS)
    if 'Channel' in df.columns and 'Sent' in df.columns:
        df['Campaign Cost'] = df.apply(
            lambda row: (row['Sent'] / 1000) * CHANNEL_COSTS.get(row['Channel'], 0),
            axis=1
        )
    else:
        df['Campaign Cost'] = 0
    
    # Revenue Per Send (RPS) - KEY EFFICIENCY METRIC
    if revenue_cols and 'Sent' in df.columns:
        revenue_col = revenue_cols[0]
        df['Revenue Per Send'] = np.where(df['Sent'] > 0, df[revenue_col] / df['Sent'], 0)
    else:
        df['Revenue Per Send'] = 0
    
    # ROAS - Return on Ad Spend (Revenue / Cost)
    if revenue_cols:
        revenue_col = revenue_cols[0]
        df['ROAS'] = np.where(df['Campaign Cost'] > 0, df[revenue_col] / df['Campaign Cost'], 0)
    else:
        df['ROAS'] = 0
    
    # Cost Per Conversion (CPC)
    if 'Unique Conversions' in df.columns:
        df['Cost Per Conversion'] = np.where(
            df['Unique Conversions'] > 0, 
            df['Campaign Cost'] / df['Unique Conversions'], 
            0
        )
    else:
        df['Cost Per Conversion'] = 0
    
    # Cost Per Click
    if 'Unique Clicks' in df.columns:
        df['Cost Per Click'] = np.where(
            df['Unique Clicks'] > 0, 
            df['Campaign Cost'] / df['Unique Clicks'], 
            0
        )
    else:
        df['Cost Per Click'] = 0
    
    # Convert object columns to string for Arrow compatibility
    object_cols = df.select_dtypes(include='object').columns
    df[object_cols] = df[object_cols].astype(str)
    
    return df

# Rate columns should be averaged; absolute columns should be summed
_RATE_KEYWORDS = {'rate', 'ctr', 'roas', 'aov', 'rpc', 'rps', 'engagement rate', 'revenue per'}

def _metric_agg(metric):
    """Return 'mean' for rate/ratio metrics, 'sum' for absolute metrics."""
    lower = metric.lower()
    if any(kw in lower for kw in _RATE_KEYWORDS):
        return 'mean'
    return 'sum'

def top_campaigns(df, metric='Unique Conversions', top_n=10):
    agg = _metric_agg(metric)
    return df.groupby('Campaign Name')[metric].agg(agg).nlargest(top_n).reset_index()

def get_top_journeys(df, metric='Delivered Rate', top_n=10):
    agg = _metric_agg(metric)
    df_filtered = df[df['Journey Name'].notna() & (df['Journey Name'] != 'nan') & (df['Journey Name'] != '')]
    if df_filtered.empty:
        return pd.DataFrame(columns=['Journey Name', metric])
    return df_filtered.groupby('Journey Name')[metric].agg(agg).nlargest(top_n).reset_index()

def top_segments(df, metric='Unique Conversions', top_n=10):
    agg = _metric_agg(metric)
    df_filtered = df[df['Segment Name'].notna() & (df['Segment Name'] != 'nan') & (df['Segment Name'] != '')]
    if df_filtered.empty:
        return pd.DataFrame(columns=['Segment Name', metric])
    return df_filtered.groupby('Segment Name')[metric].agg(agg).nlargest(top_n).reset_index()

def channel_analysis(df):
    agg_dict = {
        'Sent': 'sum',
        'Delivered': 'sum',
        'Unique Impressions': 'sum',
        'Unique Clicks': 'sum',
        'Selected Conversions': 'sum' if 'Selected Conversions' in df.columns else 'Unique Conversions',
    }
    # Remove the old conversions field if we have the selected one
    if 'Selected Conversions' not in df.columns:
        agg_dict['Unique Conversions'] = 'sum'
    
    # Only add columns that exist in the dataframe
    if 'Total Conversions' in df.columns:
        agg_dict['Total Conversions'] = 'sum'
    if 'Selected Revenue (SAR)' in df.columns:
        agg_dict['Selected Revenue (SAR)'] = 'sum'
    elif 'Revenue (SAR)' in df.columns:
        agg_dict['Revenue (SAR)'] = 'sum'
    
    # Keep original columns for reference but they won't be displayed by default
    if 'Click-Through Revenue (SAR)' in df.columns:
        agg_dict['Click-Through Revenue (SAR)'] = 'sum'
    if 'Impression-Through Revenue (SAR)' in df.columns:
        agg_dict['Impression-Through Revenue (SAR)'] = 'sum'

    result = df.groupby('Channel').agg(agg_dict).reset_index()

    # Calculate AOV using selected metrics
    if 'Selected Revenue (SAR)' in result.columns and 'Selected Conversions' in result.columns:
        result['AOV (SAR)'] = np.where(
            result['Selected Conversions'] > 0,
            result['Selected Revenue (SAR)'] / result['Selected Conversions'], 0
        )

    return result

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
    # Filter out nan/empty ESP values
    if 'ESP/SSP/WSP/RSP name' not in df.columns:
        return pd.DataFrame()
    df_filtered = df[df['ESP/SSP/WSP/RSP name'].notna() & (df['ESP/SSP/WSP/RSP name'] != 'nan') & (df['ESP/SSP/WSP/RSP name'] != '')]
    if df_filtered.empty:
        return pd.DataFrame()

    agg_dict = {
        'Sent': 'sum',
        'Delivered': 'sum',
        'Selected Conversions': 'sum' if 'Selected Conversions' in df_filtered.columns else 'Unique Conversions',
    }
    if 'Selected Conversions' not in df_filtered.columns:
        agg_dict['Unique Conversions'] = 'sum'

    # Only add columns that exist in the dataframe
    if 'Total Conversions' in df_filtered.columns:
        agg_dict['Total Conversions'] = 'sum'
    if 'Selected Revenue (SAR)' in df_filtered.columns:
        agg_dict['Selected Revenue (SAR)'] = 'sum'
    elif 'Revenue (SAR)' in df_filtered.columns:
        agg_dict['Revenue (SAR)'] = 'sum'

    # Keep original columns for reference
    if 'Click-Through Revenue (SAR)' in df_filtered.columns:
        agg_dict['Click-Through Revenue (SAR)'] = 'sum'
    if 'Impression-Through Revenue (SAR)' in df_filtered.columns:
        agg_dict['Impression-Through Revenue (SAR)'] = 'sum'

    return df_filtered.groupby('ESP/SSP/WSP/RSP name').agg(agg_dict).reset_index()

def ab_testing_analysis(df):
    """Calculate lift and statistical significance for campaigns with control groups."""
    df_ab = df[df['Total in Control Group'] > 0].copy()
    if not df_ab.empty:
        df_ab['Test Conversion Rate'] = df_ab['Unique Conversions'] / df_ab['Sent']
        df_ab['Control Conversion Rate'] = df_ab['Unique Control Group Conversions'] / df_ab['Total in Control Group']
        df_ab['Lift'] = np.where(df_ab['Control Conversion Rate'] > 0,
                                (df_ab['Test Conversion Rate'] - df_ab['Control Conversion Rate']) / df_ab['Control Conversion Rate'],
                                np.nan)

        # Statistical significance using two-proportion z-test
        p_values = []
        significant = []
        for _, row in df_ab.iterrows():
            n_test = row['Sent']
            n_control = row['Total in Control Group']
            x_test = row['Unique Conversions']
            x_control = row['Unique Control Group Conversions']
            if n_test > 0 and n_control > 0:
                p_test = x_test / n_test
                p_control = x_control / n_control
                p_pooled = (x_test + x_control) / (n_test + n_control)
                se = np.sqrt(p_pooled * (1 - p_pooled) * (1/n_test + 1/n_control))
                if se > 0:
                    z_stat = (p_test - p_control) / se
                    # Two-tailed p-value using normal approximation
                    from scipy import stats as scipy_stats
                    p_val = 2 * (1 - scipy_stats.norm.cdf(abs(z_stat)))
                    p_values.append(p_val)
                    significant.append(p_val < 0.05)
                else:
                    p_values.append(np.nan)
                    significant.append(False)
            else:
                p_values.append(np.nan)
                significant.append(False)

        df_ab['P-Value'] = p_values
        df_ab['Significant (95%)'] = significant

        return df_ab[['Campaign Name', 'Test Conversion Rate', 'Control Conversion Rate',
                       'Lift', 'P-Value', 'Significant (95%)']].dropna(subset=['Lift'])
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
        total_conversions_j = df_journey['Selected Conversions'].sum() if 'Selected Conversions' in df_journey.columns else (df_journey['Unique Conversions'].sum() if 'Unique Conversions' in df_journey.columns else 0)
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
                conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
                clicks = group['Unique Clicks'].sum()
                if clicks > 0:
                    conv_conversions.append(conversions)
                    conv_clicks.append(clicks)
        
        # Revenue Per Conversion data (for log-transformation)
        rpc_values = []
        for name, group in journey_groups:
            if 'Revenue (SAR)' in group.columns and 'Unique Conversions' in group.columns:
                revenue = group['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in group.columns else group['Revenue (SAR)'].sum()
                conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
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
        
        # 3. Conversion Performance Score (30% weight) - ALWAYS CALCULATE FROM RAW FIELDS
        # Use Selected Conversions if available (attribution-aware), otherwise fall back to Unique Conversions
        if 'Unique Conversions' in df_journey.columns and 'Unique Clicks' in df_journey.columns:
            total_conversions = df_journey['Selected Conversions'].sum() if 'Selected Conversions' in df_journey.columns else df_journey['Unique Conversions'].sum()
            total_clicks = df_journey['Unique Clicks'].sum()
            # Apply Empirical Bayes smoothing
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
        # Use Selected Revenue and Selected Conversions if available (attribution-aware)
        if 'Revenue (SAR)' in df_journey.columns and 'Unique Conversions' in df_journey.columns:
            total_revenue = df_journey['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in df_journey.columns else df_journey['Revenue (SAR)'].sum()
            total_conversions = df_journey['Selected Conversions'].sum() if 'Selected Conversions' in df_journey.columns else df_journey['Unique Conversions'].sum()
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
        total_conversions_c = df_campaign['Selected Conversions'].sum() if 'Selected Conversions' in df_campaign.columns else (df_campaign['Unique Conversions'].sum() if 'Unique Conversions' in df_campaign.columns else 0)
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
                conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
                clicks = group['Unique Clicks'].sum()
                if clicks > 0:
                    conv_conversions.append(conversions)
                    conv_clicks.append(clicks)

        # Revenue Per Conversion data (for log-transformation)
        rpc_values = []
        for name, group in campaign_groups:
            if 'Revenue (SAR)' in group.columns and 'Unique Conversions' in group.columns:
                revenue = group['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in group.columns else group['Revenue (SAR)'].sum()
                conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
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
        # Use the Conversion Rate column when available (calculated in clean_data as decimal: conversions/clicks)
        if 'Conversion Rate' in df_campaign.columns and df_campaign['Conversion Rate'].notna().any():
            # Conversion Rate is already a decimal from clean_data() (e.g., 0.05 = 5%)
            conv_rate = df_campaign['Conversion Rate'].mean()
            # Create baseline from all campaigns' conversion rates
            if 'Conversion Rate' in baseline_df.columns:
                baseline_conv_values = []
                for name, group in baseline_df.groupby('Campaign Name'):
                    campaign_conv_rate = group['Conversion Rate'].mean()
                    if not pd.isna(campaign_conv_rate):
                        baseline_conv_values.append(campaign_conv_rate)
                baseline_conv = pd.Series(baseline_conv_values)
            else:
                baseline_conv = pd.Series([conv_rate])
        elif 'Unique Conversions' in df_campaign.columns and 'Unique Clicks' in df_campaign.columns:
            # Fallback: manual calculation (but this may not be reliable for some data)
            total_conversions = df_campaign['Selected Conversions'].sum() if 'Selected Conversions' in df_campaign.columns else df_campaign['Unique Conversions'].sum()
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
            total_revenue = df_campaign['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in df_campaign.columns else df_campaign['Revenue (SAR)'].sum()
            total_conversions = df_campaign['Selected Conversions'].sum() if 'Selected Conversions' in df_campaign.columns else df_campaign['Unique Conversions'].sum()
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

            # Sort by date and reset index for proper iteration
            journey_data = journey_data.sort_values('date').reset_index(drop=True)

            # Identify stopped periods (consecutive days with zero delivery)
            if 'Delivered' not in journey_data.columns:
                continue

            # Aggregate multiple rows per calendar date into a single daily record
            # (Some journeys have multiple campaign rows on the same date)
            daily = journey_data.groupby('date', as_index=False).agg({
                'Delivered': 'sum',
                'Revenue (SAR)': 'sum'  # Also track revenue to validate stops
            })
            daily = daily.sort_values('date').reset_index(drop=True)
            daily['Delivered'] = daily['Delivered'].fillna(0)
            daily['Revenue (SAR)'] = daily['Revenue (SAR)'].fillna(0)
            daily['is_stopped'] = (daily['Delivered'] == 0)

            # Find consecutive stopped periods on daily aggregated data
            stopped_periods = []
            current_stopped_start = None
            current_stopped_start_idx = None
            consecutive_stopped = 0
            had_activity_before = False  # Track if journey was active before this stopped period

            for idx in range(len(daily)):
                row = daily.iloc[idx]

                if row['is_stopped']:
                    if current_stopped_start is None:
                        current_stopped_start = row['date']
                        current_stopped_start_idx = idx
                    consecutive_stopped += 1
                else:
                    # Journey is active (has delivery)
                    if consecutive_stopped >= stopped_threshold_days and current_stopped_start is not None and had_activity_before:
                        prev_row = daily.iloc[idx - 1]
                        prev_date = prev_row['date']

                        # Calculate actual calendar days between start and end
                        actual_calendar_days = (prev_date - current_stopped_start).days + 1

                        # Check how much activity was before the stop (based on daily aggregated data)
                        activity_before = daily.iloc[:current_stopped_start_idx]
                        active_days_before = (activity_before['Delivered'] > 0).sum()
                        avg_delivery_before = activity_before[activity_before['Delivered'] > 0]['Delivered'].mean()

                        # Validate: Check if revenue continues beyond conversion window (7 days)
                        # If so, the journey likely has active campaigns and isn't truly stopped
                        conversion_window_days = 7
                        revenue_after_window_start = current_stopped_start + pd.Timedelta(days=conversion_window_days)
                        stopped_period_data = daily[(daily['date'] >= revenue_after_window_start) & (daily['date'] <= prev_date)]
                        
                        # Calculate total revenue beyond conversion window
                        revenue_beyond_window = stopped_period_data['Revenue (SAR)'].sum() if len(stopped_period_data) > 0 else 0
                        revenue_before_stop = activity_before['Revenue (SAR)'].mean() if len(activity_before) > 0 else 0
                        
                        # Only include stop if revenue beyond window is minimal (<10% of pre-stop average per day)
                        days_beyond_window = max(1, actual_calendar_days - conversion_window_days)
                        avg_revenue_during_stop = revenue_beyond_window / days_beyond_window if days_beyond_window > 0 else 0
                        
                        is_truly_stopped = True
                        if revenue_before_stop > 0 and avg_revenue_during_stop > (revenue_before_stop * 0.1):
                            # Revenue continues at significant level - likely has active campaigns
                            is_truly_stopped = False
                        
                        if is_truly_stopped:
                            stopped_periods.append({
                                'start_date': current_stopped_start,
                                'end_date': prev_date,
                                'days_stopped': actual_calendar_days,  # Calendar days between dates
                                'was_active_before': True,
                                'active_days_before_stop': int(active_days_before),
                                'avg_delivery_before_stop': float(avg_delivery_before) if not pd.isna(avg_delivery_before) else 0
                            })

                    # Mark that we've seen activity
                    had_activity_before = True
                    current_stopped_start = None
                    current_stopped_start_idx = None
                    consecutive_stopped = 0

            # Check for stopped period at the end (only if journey was active before)
            if consecutive_stopped >= stopped_threshold_days and current_stopped_start is not None and had_activity_before:
                last_row = daily.iloc[-1]
                last_date = last_row['date']

                # Calculate actual calendar days
                actual_calendar_days = (last_date - current_stopped_start).days + 1

                # Check activity before the stop
                activity_before = daily.iloc[:current_stopped_start_idx]
                active_days_before = (activity_before['Delivered'] > 0).sum()
                avg_delivery_before = activity_before[activity_before['Delivered'] > 0]['Delivered'].mean()

                # Validate: Check if revenue continues beyond conversion window
                conversion_window_days = 7
                revenue_after_window_start = current_stopped_start + pd.Timedelta(days=conversion_window_days)
                stopped_period_data = daily[(daily['date'] >= revenue_after_window_start) & (daily['date'] <= last_date)]
                
                revenue_beyond_window = stopped_period_data['Revenue (SAR)'].sum() if len(stopped_period_data) > 0 else 0
                revenue_before_stop = activity_before['Revenue (SAR)'].mean() if len(activity_before) > 0 else 0
                
                days_beyond_window = max(1, actual_calendar_days - conversion_window_days)
                avg_revenue_during_stop = revenue_beyond_window / days_beyond_window if days_beyond_window > 0 else 0
                
                is_truly_stopped = True
                if revenue_before_stop > 0 and avg_revenue_during_stop > (revenue_before_stop * 0.1):
                    # Revenue continues at significant level - likely has active campaigns
                    is_truly_stopped = False
                
                if is_truly_stopped:
                    stopped_periods.append({
                        'start_date': current_stopped_start,
                        'end_date': last_date,
                        'days_stopped': actual_calendar_days,  # Calendar days between dates
                        'was_active_before': True,
                        'active_days_before_stop': int(active_days_before),
                        'avg_delivery_before_stop': float(avg_delivery_before) if not pd.isna(avg_delivery_before) else 0
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
        
        # Aggregate journey data by date first (handle multiple rows per day)
        daily_data = journey_data.groupby('date', as_index=False).agg({
            'Revenue (SAR)': 'sum',
            'Impression-Through Revenue (SAR)': 'sum',
            'Click-Through Revenue (SAR)': 'sum'
        })
        daily_data = daily_data.sort_values('date').reset_index(drop=True)

        # Prepare data for Prophet
        prophet_data = daily_data[['date', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']].copy()
        prophet_data = prophet_data.rename(columns={'date': 'ds'})

        # Estimate loss for each attribution model
        attribution_models = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
        total_loss = 0
        attribution_breakdown = {}
        model_success = {}

        for model in attribution_models:
            if model not in prophet_data.columns:
                continue
                
            model_data = prophet_data[['ds', model]].rename(columns={model: 'y'})
            model_data = model_data.dropna()
            
            # Filter out negative values
            model_data = model_data[model_data['y'] >= 0]
            
            # CRITICAL: Exclude stopped periods from training
            # Mark stopped periods so Prophet doesn't learn the "stopped = low revenue" pattern
            for period in stopped_periods:
                # Exclude from training: stopped period dates
                mask = (model_data['ds'] >= period['start_date']) & (model_data['ds'] <= period['end_date'])
                model_data = model_data[~mask]

            if len(model_data) < 14:  # Need at least 2 weeks for reliable forecasting
                model_success[model] = False
                continue
            
            # Outlier detection and capping using IQR method
            Q1 = model_data['y'].quantile(0.25)
            Q3 = model_data['y'].quantile(0.75)
            IQR = Q3 - Q1
            upper_bound = Q3 + 3 * IQR  # Use 3*IQR for less aggressive capping
            lower_bound = max(0, Q1 - 3 * IQR)
            
            # Cap outliers
            model_data['y'] = model_data['y'].clip(lower=lower_bound, upper=upper_bound)
            
            # Calculate baseline statistics for validation
            # Use wider window excluding immediate pre-stop spikes
            baseline_window = model_data.iloc[-60:] if len(model_data) >= 60 else model_data
            baseline_mean = baseline_window['y'].mean()
            baseline_std = baseline_window['y'].std()
            baseline_median = baseline_window['y'].median()
            
            # Use median if highly volatile (coefficient of variation > 1)
            cv = baseline_std / baseline_mean if baseline_mean > 0 else float('inf')
            use_median = cv > 1.0
            baseline_value = baseline_median if use_median else baseline_mean
            
            try:
                # Configure Prophet with conservative settings
                model_prophet = Prophet(
                    growth='linear',  # Linear growth for stability
                    yearly_seasonality=False,
                    weekly_seasonality=True,
                    daily_seasonality=False,
                    seasonality_mode='additive',  # More stable than multiplicative
                    interval_width=confidence_level,
                    changepoint_prior_scale=0.01,  # Lower = less flexible = more stable
                    seasonality_prior_scale=1.0
                )
                
                # Set floor to prevent negative predictions
                model_data['floor'] = 0
                model_prophet.fit(model_data)

                # Forecast for stopped periods
                model_loss = 0
                model_valid = True

                for period_idx, period in enumerate(stopped_periods):
                    # Create future dataframe for the stopped period
                    future_dates = pd.date_range(
                        start=period['start_date'],
                        end=period['end_date'],
                        freq='D'
                    )

                    future_df = pd.DataFrame({'ds': future_dates})
                    future_df['floor'] = 0

                    # Make prediction
                    forecast = model_prophet.predict(future_df)
                    
                    # Validate predictions - reject if unreasonable
                    predicted_mean = forecast['yhat'].mean()
                    predicted_daily = forecast['yhat'].values
                    
                    # Sanity checks
                    if predicted_mean < 0:
                        # Negative predictions - fall back to average
                        model_valid = False
                        break
                    
                    # Conservative validation: Check for unrealistic predictions
                    # Calculate pre-stop baseline (last 14 days before this specific stop)
                    pre_stop_data = model_data[model_data['ds'] < period['start_date']].tail(14)
                    if len(pre_stop_data) > 0:
                        pre_stop_baseline = pre_stop_data['y'].median() if use_median else pre_stop_data['y'].mean()
                    else:
                        pre_stop_baseline = baseline_value
                    
                    # If prediction is way off pre-stop baseline, use conservative estimate
                    if predicted_mean > pre_stop_baseline * 2:
                        # Cap at 1.5x pre-stop baseline for conservative CEO/CMO reporting
                        predicted_daily = np.clip(predicted_daily, 0, pre_stop_baseline * 1.5)
                    elif predicted_mean < pre_stop_baseline * 0.1 and pre_stop_baseline > 0:
                        # Too low - use pre-stop baseline
                        predicted_daily = np.full(len(predicted_daily), pre_stop_baseline)
                    
                    # Ensure non-negative
                    predicted_daily = np.maximum(predicted_daily, 0)
                    
                    # Calculate period loss
                    period_loss = predicted_daily.sum()
                    model_loss += period_loss

                    # Store daily estimates for this specific period
                    if 'daily_estimates' not in period:
                        period['daily_estimates'] = {}
                    
                    period['daily_estimates'][model] = []
                    for idx, (_, forecast_row) in enumerate(forecast.iterrows()):
                        period['daily_estimates'][model].append({
                            'date': forecast_row['ds'],
                            'expected_revenue': predicted_daily[idx],
                            'confidence_lower': max(0, forecast_row['yhat_lower']),
                            'confidence_upper': min(baseline_mean * 3, forecast_row['yhat_upper'])  # Cap upper bound
                        })
                    
                    # Track period loss by model (don't overwrite, accumulate)
                    if 'model_losses' not in period:
                        period['model_losses'] = {}
                    period['model_losses'][model] = period_loss
                
                if model_valid:
                    attribution_breakdown[model] = model_loss
                    model_success[model] = True
                else:
                    # Fall back to simple average for this model
                    model_loss = baseline_median if use_median else baseline_mean
                    model_loss = model_loss * sum(p['days_stopped'] for p in stopped_periods)
                    attribution_breakdown[model] = model_loss
                    model_success[model] = False
                    
            except Exception as model_error:
                # Prophet failed for this model - use fallback
                fallback_value = baseline_median if use_median else baseline_mean
                model_loss = fallback_value * sum(p['days_stopped'] for p in stopped_periods)
                attribution_breakdown[model] = model_loss
                model_success[model] = False

        # CRITICAL: Use Send-Through Revenue as primary metric (NOT sum of attributions!)
        # Attribution models are alternative views, not additive
        primary_model = 'Revenue (SAR)'
        total_loss = attribution_breakdown.get(primary_model, 0)
        
        # Calculate estimated_daily_loss for each period using PRIMARY model only
        for period in stopped_periods:
            if 'model_losses' in period and primary_model in period['model_losses']:
                period['estimated_daily_loss'] = period['model_losses'][primary_model] / period['days_stopped'] if period['days_stopped'] > 0 else 0
            else:
                # No model succeeded for this period
                period['estimated_daily_loss'] = 0

        # Calculate confidence interval based on model success and data quality
        if total_loss > 0:
            # Adaptive confidence interval based on data quality
            if all(model_success.values()):
                # All models succeeded - tighter interval
                lower_pct, upper_pct = 0.80, 1.20
            elif any(model_success.values()):
                # Some models succeeded - moderate interval
                lower_pct, upper_pct = 0.70, 1.40
            else:
                # All models failed - wider interval
                lower_pct, upper_pct = 0.50, 1.50
            
            confidence_interval = (
                total_loss * lower_pct,
                total_loss * upper_pct
            )
        else:
            confidence_interval = (0, 0)

        return {
            'total_loss': total_loss,
            'avg_daily_loss': total_loss / sum(p['days_stopped'] for p in stopped_periods) if stopped_periods else 0,
            'attribution_breakdown': attribution_breakdown,
            'confidence_interval': confidence_interval,
            'confidence_level': confidence_level,
            'model_quality': 'high' if all(model_success.values()) else ('medium' if any(model_success.values()) else 'low'),
            'method': 'prophet_robust'
        }

    except Exception as e:
        # Fallback to improved average method if Prophet fails entirely
        total_loss = 0
        attribution_breakdown = {}
        
        # Aggregate journey data by date
        daily_data = journey_data.groupby('date', as_index=False).agg({
            'Revenue (SAR)': 'sum',
            'Impression-Through Revenue (SAR)': 'sum',
            'Click-Through Revenue (SAR)': 'sum'
        })
        daily_data = daily_data.sort_values('date').reset_index(drop=True)
        
        # Get total stopped days for average calculation
        total_stopped_days = sum(p['days_stopped'] for p in stopped_periods)

        # Improved fallback method with outlier handling
        for period in stopped_periods:
            # Get 30-60 days before stop for baseline calculation
            period_data = daily_data[
                (daily_data['date'] >= period['start_date'] - pd.Timedelta(days=60)) &
                (daily_data['date'] < period['start_date'])
            ]

            if len(period_data) >= 7:  # Need minimum data
                period_loss = 0
                for model in ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']:
                    if model in period_data.columns:
                        # Use robust statistics (median + IQR outlier filtering)
                        model_values = period_data[model].fillna(0)
                        model_values = model_values[model_values >= 0]  # Remove negatives
                        
                        if len(model_values) > 0:
                            # Remove outliers using IQR
                            Q1 = model_values.quantile(0.25)
                            Q3 = model_values.quantile(0.75)
                            IQR = Q3 - Q1
                            
                            # Filter outliers
                            filtered_values = model_values[
                                (model_values >= Q1 - 1.5 * IQR) &
                                (model_values <= Q3 + 1.5 * IQR)
                            ]
                            
                            if len(filtered_values) > 0:
                                # Use median for robustness
                                avg_daily = filtered_values.median()
                            else:
                                avg_daily = model_values.median()
                            
                            # Recent trend adjustment (last 7 days vs previous)
                            if len(period_data) >= 14:
                                recent = period_data[model].iloc[-7:].median()
                                earlier = period_data[model].iloc[:-7].median()
                                
                                # If recent is much different, blend the two
                                if earlier > 0:
                                    trend_ratio = recent / earlier
                                    # Cap trend adjustment to ±50%
                                    trend_ratio = np.clip(trend_ratio, 0.5, 1.5)
                                    avg_daily = avg_daily * trend_ratio
                            
                            model_period_loss = max(0, avg_daily * period['days_stopped'])
                            attribution_breakdown[model] = attribution_breakdown.get(model, 0) + model_period_loss
                            
                            # Track by model for period (don't sum!)
                            if 'model_losses' not in period:
                                period['model_losses'] = {}
                            period['model_losses'][model] = model_period_loss
                
                # Use primary model (Send-Through Revenue) for period total
                primary_model = 'Revenue (SAR)'
                if 'model_losses' in period and primary_model in period['model_losses']:
                    period['estimated_daily_loss'] = period['model_losses'][primary_model] / period['days_stopped'] if period['days_stopped'] > 0 else 0
                else:
                    period['estimated_daily_loss'] = 0
            else:
                period['estimated_daily_loss'] = 0

        # Use primary attribution model for total loss
        primary_model = 'Revenue (SAR)'
        total_loss = attribution_breakdown.get(primary_model, 0)

        return {
            'total_loss': total_loss,
            'avg_daily_loss': total_loss / total_stopped_days if total_stopped_days > 0 else 0,
            'attribution_breakdown': attribution_breakdown,
            'confidence_interval': (max(0, total_loss * 0.6), total_loss * 1.4),  # Wider interval for fallback
            'confidence_level': confidence_level,
            'model_quality': 'low',
            'method': 'fallback_robust_average'
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

def calculate_comparison_periods(df, current_date_range, comparison_mode, custom_comparison_range=None):
    """
    Calculate the comparison period based on the selected mode.
    
    Args:
        df: Full dataframe
        current_date_range: Tuple of (start_date, end_date) for current period
        comparison_mode: String indicating comparison type
        custom_comparison_range: Tuple for custom comparison range
        
    Returns:
        dict with current_period_data, comparison_period_data, and metadata
    """
    try:
        if not current_date_range or len(current_date_range) != 2:
            return None
        
        current_start = pd.to_datetime(current_date_range[0])
        current_end = pd.to_datetime(current_date_range[1])
        current_days = (current_end - current_start).days + 1
        
        # Get current period data
        current_data = df[(df['Reporting Period Start Date'] >= current_start) & 
                         (df['Reporting Period End Date'] <= current_end)]
        
        # Calculate comparison period based on mode
        if comparison_mode == "None":
            return None
        
        elif comparison_mode == "Previous Period (Auto)":
            # Same duration as current, immediately before
            comp_end = current_start - pd.Timedelta(days=1)
            comp_start = comp_end - pd.Timedelta(days=current_days - 1)
            comp_label = f"Previous {current_days} days"
        
        elif comparison_mode == "Week over Week":
            # Previous week (7 days back)
            comp_end = current_start - pd.Timedelta(days=1)
            comp_start = comp_end - pd.Timedelta(days=6)
            comp_label = "Previous Week"
        
        elif comparison_mode == "Month over Month":
            # Previous month (approximately)
            comp_end = current_start - pd.Timedelta(days=1)
            comp_start = comp_end - pd.Timedelta(days=29)
            comp_label = "Previous Month"
        
        elif comparison_mode == "Quarter over Quarter":
            # Previous quarter (90 days back)
            comp_end = current_start - pd.Timedelta(days=1)
            comp_start = comp_end - pd.Timedelta(days=89)
            comp_label = "Previous Quarter"
        
        elif comparison_mode == "Custom Date Range":
            if not custom_comparison_range or len(custom_comparison_range) != 2:
                return None
            comp_start = pd.to_datetime(custom_comparison_range[0])
            comp_end = pd.to_datetime(custom_comparison_range[1])
            comp_label = f"Custom: {comp_start.strftime('%b %d')} - {comp_end.strftime('%b %d')}"
        
        else:
            return None
        
        # Get comparison period data
        comparison_data = df[(df['Reporting Period Start Date'] >= comp_start) & 
                            (df['Reporting Period End Date'] <= comp_end)]
        
        comp_days = (comp_end - comp_start).days + 1
        
        return {
            'current_data': current_data,
            'comparison_data': comparison_data,
            'current_start': current_start,
            'current_end': current_end,
            'current_days': current_days,
            'comparison_start': comp_start,
            'comparison_end': comp_end,
            'comparison_days': comp_days,
            'comparison_label': comp_label,
            'current_label': f"{current_start.strftime('%b %d')} - {current_end.strftime('%b %d')}"
        }
    
    except Exception as e:
        return None


def calculate_uplift_significance(test_conversions, test_total, control_conversions, control_total):
    """
    Calculate statistical significance of uplift using two-proportion z-test.
    Returns (p_value, is_significant, reliability_status)
    """
    if control_conversions < 30:
        reliability = "🔴 Insufficient"
    elif control_conversions < 100:
        reliability = "🟡 Moderate"
    else:
        reliability = "🟢 Reliable"
    
    # Calculate p-value if we have enough data
    if test_total > 0 and control_total > 0 and (test_conversions + control_conversions) >= 30:
        try:
            from scipy import stats as scipy_stats
            p_test = test_conversions / test_total
            p_control = control_conversions / control_total
            p_pooled = (test_conversions + control_conversions) / (test_total + control_total)
            se = np.sqrt(p_pooled * (1 - p_pooled) * (1/test_total + 1/control_total))
            
            if se > 0:
                z_stat = (p_test - p_control) / se
                p_value = 2 * (1 - scipy_stats.norm.cdf(abs(z_stat)))
                is_significant = p_value < 0.05
                return p_value, is_significant, reliability
        except:
            pass
    
    return None, False, reliability


def calculate_period_metrics(period_data, period_days, conversion_attribution='Total'):
    """
    Calculate key metrics for a given period with daily averages.
    
    Args:
        period_data: DataFrame for the period
        period_days: Number of days in the period
        conversion_attribution: Attribution model for conversions ('Total', 'Impression-Through', 'Click-Through')
        
    Returns:
        dict with all key metrics
    """
    metrics = {}
    
    # Revenue metrics
    metrics['total_revenue'] = period_data['Revenue (SAR)'].sum() if 'Revenue (SAR)' in period_data.columns else 0
    metrics['impression_revenue'] = period_data['Impression-Through Revenue (SAR)'].sum() if 'Impression-Through Revenue (SAR)' in period_data.columns else 0
    metrics['click_revenue'] = period_data['Click-Through Revenue (SAR)'].sum() if 'Click-Through Revenue (SAR)' in period_data.columns else 0
    metrics['selected_revenue'] = period_data['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in period_data.columns else metrics['total_revenue']
    
    # Conversion metrics
    metrics['total_conversions'] = period_data['Unique Conversions'].sum() if 'Unique Conversions' in period_data.columns else 0
    metrics['selected_conversions'] = period_data['Selected Conversions'].sum() if 'Selected Conversions' in period_data.columns else metrics['total_conversions']
    
    # Engagement metrics
    metrics['total_clicks'] = period_data['Unique Clicks'].sum() if 'Unique Clicks' in period_data.columns else 0
    metrics['total_impressions'] = period_data['Unique Impressions'].sum() if 'Unique Impressions' in period_data.columns else 0
    
    # Delivery metrics
    metrics['total_sent'] = period_data['Sent'].sum() if 'Sent' in period_data.columns else 0
    metrics['total_delivered'] = period_data['Delivered'].sum() if 'Delivered' in period_data.columns else 0
    metrics['total_failed'] = period_data['Failed'].sum() if 'Failed' in period_data.columns else 0
    
    # Calculate rates
    metrics['ctr'] = (metrics['total_clicks'] / metrics['total_impressions']) if metrics['total_impressions'] > 0 else 0
    metrics['conversion_rate'] = (metrics['selected_conversions'] / metrics['total_clicks']) if metrics['total_clicks'] > 0 else 0
    metrics['delivery_rate'] = (metrics['total_delivered'] / metrics['total_sent']) if metrics['total_sent'] > 0 else 0
    
    # Revenue per conversion (AOV)
    metrics['revenue_per_conversion'] = (metrics['selected_revenue'] / metrics['selected_conversions']) if metrics['selected_conversions'] > 0 else 0
    metrics['aov'] = metrics['revenue_per_conversion']  # Same as AOV
    
    # Revenue Per Click (RPC)
    metrics['revenue_per_click'] = (metrics['selected_revenue'] / metrics['total_clicks']) if metrics['total_clicks'] > 0 else 0
    
    # Engagement Rate (includes Opens if available)
    total_opens = period_data['Unique Opens'].sum() if 'Unique Opens' in period_data.columns else 0
    if total_opens > 0 and metrics['total_impressions'] > 0:
        metrics['engagement_rate'] = (metrics['total_clicks'] + total_opens) / metrics['total_impressions']
    else:
        metrics['engagement_rate'] = metrics['ctr']  # Fallback to CTR if no opens data
    
    # === COST-BASED METRICS ===
    metrics['total_cost'] = period_data['Campaign Cost'].sum() if 'Campaign Cost' in period_data.columns else 0
    
    # ROAS - Return on Ad Spend (Industry standard: 4:1 is good)
    metrics['roas'] = (metrics['selected_revenue'] / metrics['total_cost']) if metrics['total_cost'] > 0 else 0
    
    # Revenue Per Send (RPS) - Key efficiency metric
    metrics['revenue_per_send'] = (metrics['selected_revenue'] / metrics['total_sent']) if metrics['total_sent'] > 0 else 0
    
    # Cost Per Conversion
    metrics['cost_per_conversion'] = (metrics['total_cost'] / metrics['selected_conversions']) if metrics['selected_conversions'] > 0 else 0
    
    # Cost Per Click
    metrics['cost_per_click'] = (metrics['total_cost'] / metrics['total_clicks']) if metrics['total_clicks'] > 0 else 0
    
    # Profit (Revenue - Cost)
    metrics['profit'] = metrics['selected_revenue'] - metrics['total_cost']
    
    # Profit Margin
    metrics['profit_margin'] = (metrics['profit'] / metrics['selected_revenue']) if metrics['selected_revenue'] > 0 else 0
    
    # Daily averages
    metrics['daily_revenue'] = metrics['selected_revenue'] / period_days if period_days > 0 else 0
    metrics['daily_conversions'] = metrics['selected_conversions'] / period_days if period_days > 0 else 0
    metrics['daily_clicks'] = metrics['total_clicks'] / period_days if period_days > 0 else 0
    metrics['daily_sent'] = metrics['total_sent'] / period_days if period_days > 0 else 0
    metrics['daily_cost'] = metrics['total_cost'] / period_days if period_days > 0 else 0
    
    # Control Group Uplift (for A/B testing analysis) - uses Selected Conversions to respect attribution
    if 'Total in Control Group' in period_data.columns and 'Unique Control Group Conversions' in period_data.columns:
        control_campaigns = period_data[period_data['Total in Control Group'] > 0]
        if not control_campaigns.empty:
            total_control_group = control_campaigns['Total in Control Group'].sum()
            total_control_conversions = control_campaigns['Unique Control Group Conversions'].sum()
            
            # Use Selected Conversions to respect attribution setting (campaign/targeted group)
            campaign_conversions = control_campaigns['Selected Conversions'].sum() if 'Selected Conversions' in control_campaigns.columns else control_campaigns['Unique Conversions'].sum()
            
            # Denominator based on attribution parameter
            if conversion_attribution == "Impression-Through":
                campaign_denominator = control_campaigns['Unique Impressions'].sum()
            elif conversion_attribution == "Click-Through":
                campaign_denominator = control_campaigns['Unique Clicks'].sum()
            else:  # Total
                campaign_denominator = control_campaigns['Sent'].sum()
            
            if campaign_denominator > 0 and total_control_group > 0 and total_control_conversions > 0:
                campaign_conv_rate = campaign_conversions / campaign_denominator
                control_conv_rate = total_control_conversions / total_control_group
                uplift = ((campaign_conv_rate - control_conv_rate) / control_conv_rate) * 100
                metrics['control_group_uplift'] = uplift
            else:
                metrics['control_group_uplift'] = None
        else:
            metrics['control_group_uplift'] = None
    else:
        metrics['control_group_uplift'] = None
    
    return metrics


def calculate_metric_changes(current_metrics, comparison_metrics):
    """
    Calculate changes and percentage changes between two periods.
    
    Args:
        current_metrics: Dict of metrics for current period
        comparison_metrics: Dict of metrics for comparison period
        
    Returns:
        dict with absolute changes, percentage changes, and trend indicators
    """
    changes = {}
    
    for key in current_metrics.keys():
        current_val = current_metrics[key]
        comparison_val = comparison_metrics.get(key, 0)
        
        # Handle None values
        if current_val is None:
            current_val = 0
        if comparison_val is None:
            comparison_val = 0
        
        # Absolute change
        absolute_change = current_val - comparison_val
        
        # Percentage change
        if comparison_val != 0:
            pct_change = ((current_val - comparison_val) / comparison_val) * 100
        else:
            pct_change = 0 if current_val == 0 else 100
        
        # Trend indicator
        if abs(pct_change) < 1:
            trend = "→"  # Stable
            trend_color = "blue"
        elif pct_change > 0:
            trend = "↗"  # Increasing
            trend_color = "green"
        else:
            trend = "↘"  # Decreasing
            trend_color = "red"
        
        changes[key] = {
            'current': current_val,
            'comparison': comparison_val,
            'absolute_change': absolute_change,
            'pct_change': pct_change,
            'trend': trend,
            'trend_color': trend_color
        }
    
    return changes


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
        
        # Conversion metrics - ALWAYS CALCULATE FROM RAW FIELDS
        if 'Unique Conversions' in journey_data.columns and 'Unique Clicks' in journey_data.columns:
            total_conversions = journey_data['Unique Conversions'].sum()
            total_clicks = journey_data['Unique Clicks'].sum()
            conv_rate = (total_conversions / total_clicks) if total_clicks > 0 else 0
            raw_metrics['conversion'] = {
                'total_conversions': total_conversions,
                'total_clicks': total_clicks,
                'conversion_rate': conv_rate,
                'source': 'Calculated: Unique Conversions / Unique Clicks'
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
                    journey_conv_rate = group['Conversion Rate'].mean()
                    if not pd.isna(journey_conv_rate):
                        conv_rates.append(journey_conv_rate)
            else:
                for name, group in journey_groups:
                    if 'Unique Conversions' in group.columns and 'Unique Clicks' in group.columns:
                        conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
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
                    revenue = group['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in group.columns else group['Revenue (SAR)'].sum()
                    conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
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

    # Validate required columns exist
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        st.error(
            f"**Missing required columns:** {', '.join(missing_cols)}. "
            f"This does not appear to be a standard WebEngage daily campaign export. "
            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}"
        )
        st.stop()

    # Warn about recommended columns
    recommended_cols = ['Unique Impressions', 'Unique Clicks', 'Unique Conversions', 'Revenue (SAR)', 'Journey Name']
    missing_recommended = [col for col in recommended_cols if col not in df.columns]
    if missing_recommended:
        st.warning(f"**Optional columns missing** (some features will be limited): {', '.join(missing_recommended)}")

    st.success("Data cleaned and normalized!")

    # Filters
    st.sidebar.header("Filters")
    
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

    # Display-friendly labels for the selected attribution model
    _REV_ATTR_LABELS = {"Total": "Revenue (SAR)", "Click-Through": "Click-Through Revenue (SAR)", "Impression-Through": "Impression-Through Revenue (SAR)"}
    _CONV_ATTR_LABELS = {"Total": "Unique Conversions", "Click-Through": "Click-Through Conversions", "Impression-Through": "Impression-Through Conversions"}
    selected_rev_label = _REV_ATTR_LABELS.get(revenue_attribution, "Selected Revenue (SAR)")
    selected_conv_label = _CONV_ATTR_LABELS.get(conversion_attribution, "Selected Conversions")
    attribution_rename = {'Selected Revenue (SAR)': selected_rev_label, 'Selected Conversions': selected_conv_label}

    def _attribution_display(col_name):
        """Map internal 'Selected Revenue/Conversions' column names to the user-selected attribution label."""
        return get_attribution_display_label(col_name, revenue_attribution, conversion_attribution)

    # Shared attribution + filter helpers (single source of truth)
    def _apply_attribution(df, revenue_attribution, conversion_attribution):
        """Map selected attribution model to 'Selected Revenue/Conversions' columns."""
        return apply_attribution(df, revenue_attribution, conversion_attribution)

    def _apply_dimension_filters(df, channels, campaign_types, campaigns, segments, journeys, conversion_events=None):
        """Apply sidebar dimension filters."""
        return apply_dimension_filters(df, channels, campaign_types, campaigns, segments, journeys, conversion_events)

    @st.cache_data
    def apply_filters_and_attribution(df, revenue_attribution, conversion_attribution, date_range, channels, campaign_types, campaigns, segments, journeys, conversion_events=None):
        df = df.copy()
        df = _apply_attribution(df, revenue_attribution, conversion_attribution)
        filtered_df = df.copy()
        if date_range and len(date_range) == 2:
            start_dt = pd.to_datetime(date_range[0])
            end_dt = pd.to_datetime(date_range[1])
            # Filter by the Day column (reporting date) to include all attribution window days
            if 'Day' in filtered_df.columns:
                filtered_df = filtered_df[(filtered_df['Day'] >= start_dt) & (filtered_df['Day'] <= end_dt)]
            elif 'Reporting Period Start Date' in filtered_df.columns:
                filtered_df = filtered_df[(filtered_df['Reporting Period Start Date'] >= start_dt) &
                                          (filtered_df['Reporting Period End Date'] <= end_dt)]
        filtered_df = _apply_dimension_filters(filtered_df, channels, campaign_types, campaigns, segments, journeys, conversion_events)
        return filtered_df
    
    if not df.empty:
        min_date = df['Reporting Period Start Date'].min()
        max_date = df['Reporting Period End Date'].max()
        use_month_picker = st.sidebar.toggle("Use Month Picker", value=False)
        if use_month_picker:
            month_options = _month_range_options(min_date, max_date)
            month_labels = [m.strftime('%b %Y') for m in month_options]
            start_month_label = st.sidebar.selectbox("Start Month", month_labels, index=0)
            end_month_label = st.sidebar.selectbox("End Month", month_labels, index=len(month_labels) - 1)
            start_month = month_options[month_labels.index(start_month_label)]
            end_month = month_options[month_labels.index(end_month_label)]
            date_range = (start_month, (end_month + pd.offsets.MonthEnd(0)).date())
        else:
            date_range = st.sidebar.date_input("Date Range", value=(min_date, max_date))
    else:
        use_month_picker = False
        date_range = st.sidebar.date_input("Date Range", [])
    
    # Comparison Period Settings
    st.sidebar.subheader("📊 Comparison Settings")
    comparison_mode = st.sidebar.selectbox(
        "Compare With",
        ["None", "Previous Period (Auto)", "Week over Week", "Month over Month", "Quarter over Quarter", "Custom Date Range"],
        help="Select a comparison period to see trends and changes"
    )
    
    # Custom comparison date range (only show if Custom is selected)
    comparison_date_range = None
    if comparison_mode == "Custom Date Range":
        st.sidebar.markdown("**Comparison Period:**")
        if not df.empty:
            if use_month_picker:
                month_options = _month_range_options(min_date, max_date)
                month_labels = [m.strftime('%b %Y') for m in month_options]
                comp_start_label = st.sidebar.selectbox("Comparison Start Month", month_labels, index=0, key="comp_start_month")
                comp_end_label = st.sidebar.selectbox("Comparison End Month", month_labels, index=min(1, len(month_labels) - 1), key="comp_end_month")
                comp_start = month_options[month_labels.index(comp_start_label)]
                comp_end = month_options[month_labels.index(comp_end_label)]
                comparison_date_range = (comp_start, (comp_end + pd.offsets.MonthEnd(0)).date())
            else:
                comparison_date_range = st.sidebar.date_input(
                    "Custom Comparison Range", 
                    value=(min_date, min_date + pd.Timedelta(days=7)),
                    key="comparison_date_range"
                )
        else:
            comparison_date_range = st.sidebar.date_input("Custom Comparison Range", [], key="comparison_date_range")
    
    channels = st.sidebar.multiselect("Channels", sorted(df['Channel'].dropna().unique().tolist()) if not df.empty else [])
    # Campaign Type filter (Journey vs One-Time)
    campaign_types_available = sorted(df['Type of Campaign'].dropna().unique().tolist()) if (not df.empty and 'Type of Campaign' in df.columns) else []
    campaign_types = st.sidebar.multiselect("Campaign Type", campaign_types_available, help="Filter by Journey or One-Time campaigns")
    campaigns = st.sidebar.multiselect("Campaigns", sorted([c for c in df['Campaign Name'].dropna().unique().tolist() if c != 'nan']) if not df.empty else [])
    segments = st.sidebar.multiselect("Segments", sorted([s for s in df['Segment Name'].dropna().unique().tolist() if s != 'nan']) if not df.empty else [])
    journeys = st.sidebar.multiselect("Journeys", sorted([j for j in df['Journey Name'].dropna().unique().tolist() if j != 'nan']) if not df.empty else [])
    conversion_events_available = sorted(df['Conversion Event'].dropna().unique().tolist()) if (not df.empty and 'Conversion Event' in df.columns) else []
    conversion_events = st.sidebar.multiselect("Conversion Event", conversion_events_available, help="Filter by conversion event type (e.g., Order Completed, Cart Submitted)")

    # Apply filters using cached function
    filtered_df = apply_filters_and_attribution(df, revenue_attribution, conversion_attribution, date_range, channels, campaign_types, campaigns, segments, journeys, conversion_events)

    # Calculate comparison data if comparison mode is enabled
    comparison_result = None
    if comparison_mode != "None":
        df_with_attribution = df.copy()
        df_with_attribution = _apply_attribution(df_with_attribution, revenue_attribution, conversion_attribution)
        df_with_attribution = _apply_dimension_filters(df_with_attribution, channels, campaign_types, campaigns, segments, journeys, conversion_events)

        comparison_result = calculate_comparison_periods(
            df_with_attribution,
            date_range,
            comparison_mode,
            comparison_date_range
        )

    st.write(f"Filtered data: {len(filtered_df)} rows")
    if comparison_result:
        st.info(f"📊 Comparing **{comparison_result['current_label']}** vs **{comparison_result['comparison_label']}**")

    # Page content based on selection
    if page == "🎯 Automated Insights":
        st.header("🎯 Automated Insights & Recommendations")
        st.markdown("*AI-powered narrative insights, predictions, and prioritized actions - like having a super team of analysts*")
        
        # Generate executive summary
        with st.spinner("🧠 Analyzing data and generating insights..."):
            exec_summary = generate_executive_summary(filtered_df)
        
        # === EXECUTIVE SUMMARY CARD ===
        st.markdown("---")
        st.subheader("📊 Executive Summary")
        
        col1, col2 = st.columns([2, 1])
        
        with col1:
            if exec_summary.get('period'):
                st.info(f"📅 **Analysis Period:** {exec_summary['period']}")
            
            # Display headline metrics in a clean grid
            metrics = exec_summary.get('headline_metrics', {})
            met_col1, met_col2, met_col3 = st.columns(3)
            
            with met_col1:
                st.metric(f"💰 {selected_rev_label}", format_metric(metrics.get('total_revenue', 0), "SAR"))
                st.metric(f"🔄 {selected_conv_label}", format_metric(metrics.get('total_conversions', 0)))
            
            with met_col2:
                st.metric("📧 Total Sent", format_metric(metrics.get('total_sent', 0)))
                st.metric("📨 Avg Delivery Rate", f"{metrics.get('avg_delivery_rate', 0):.1%}")
            
            with met_col3:
                st.metric("👆 Avg CTR", f"{metrics.get('avg_ctr', 0):.2%}")
                st.metric("💵 Avg Conv Rate", f"{metrics.get('avg_conversion_rate', 0):.2%}")
        
        with col2:
            # Alerts count
            alerts_count = exec_summary.get('alerts_count', 0)
            if alerts_count > 0:
                st.error(f"🚨 **{alerts_count} Critical Alerts**\nRequire Immediate Attention")
            else:
                st.success("✅ **No Critical Alerts**\nAll Systems Performing Well")
            
            st.metric("📈 Generated At", exec_summary.get('timestamp', 'N/A'))
        
        # === HEADLINE NARRATIVE INSIGHTS (Like the example images) ===
        st.markdown("---")
        st.subheader("📰 What's Happening: Narrative Insights")
        st.markdown("*Automated explanations of your performance - no manual analysis needed*")
        
        insights = exec_summary.get('narrative_insights', {})
        
        # Headline Insights
        headline_insights = insights.get('headline_insights', [])
        if headline_insights:
            for insight in headline_insights:
                emoji = insight.get('emoji', 'ℹ️')
                title = insight.get('title', '')
                message = insight.get('message', '')
                severity = insight.get('severity', 'info')
                
                if severity == 'positive':
                    st.success(f"{emoji} **{title}**\n\n{message}")
                elif severity == 'critical':
                    st.error(f"{emoji} **{title}**\n\n{message}")
                elif severity == 'warning':
                    st.warning(f"{emoji} **{title}**\n\n{message}")
                else:
                    st.info(f"{emoji} **{title}**\n\n{message}")
        
        # Trend Analysis (Like: "Gradual Recovery")
        trend_analysis = insights.get('trend_analysis', [])
        if trend_analysis:
            st.markdown("### 📈 Trend Analysis")
            for trend in trend_analysis:
                emoji = trend.get('emoji', '📊')
                title = trend.get('title', '')
                message = trend.get('message', '')
                detail = trend.get('detail', '')
                severity = trend.get('severity', 'info')
                
                with st.expander(f"{emoji} {title}", expanded=True):
                    st.markdown(f"**{message}**")
                    if detail:
                        st.caption(detail)
        
        # Performance Alerts
        performance_alerts = insights.get('performance_alerts', [])
        if performance_alerts:
            st.markdown("### 🚨 Performance Alerts")
            for alert in performance_alerts:
                emoji = alert.get('emoji', '⚠️')
                title = alert.get('title', '')
                message = alert.get('message', '')
                action = alert.get('action', '')
                severity = alert.get('severity', 'warning')
                
                if severity == 'critical':
                    st.error(f"{emoji} **{title}**\n\n{message}")
                else:
                    st.warning(f"{emoji} **{title}**\n\n{message}")
                
                if action:
                    st.caption(f"💡 **Action:** {action}")
        
        # Optimization Opportunities
        opportunities = insights.get('opportunities', [])
        if opportunities:
            st.markdown("### 🎯 Optimization Opportunities")
            for opp in opportunities:
                emoji = opp.get('emoji', '💡')
                title = opp.get('title', '')
                message = opp.get('message', '')
                action = opp.get('action', '')
                expected_impact = opp.get('expected_impact', '')
                
                with st.expander(f"{emoji} {title}"):
                    st.markdown(f"**Observation:** {message}")
                    if action:
                        st.info(f"**Recommended Action:** {action}")
                    if expected_impact:
                        st.success(f"**Expected Impact:** {expected_impact}")
        
        # Business Context Notes
        context_notes = insights.get('context_notes', [])
        if context_notes:
            st.markdown("### 🌍 Business Context")
            for note in context_notes:
                emoji = note.get('emoji', 'ℹ️')
                title = note.get('title', '')
                message = note.get('message', '')
                st.info(f"{emoji} **{title}**\n\n{message}")
        
        # === REVENUE FORECAST ===
        st.markdown("---")
        st.subheader("📈 Revenue Forecast")
        st.markdown("*Predictive analytics for proactive planning*")
        
        forecast_col1, forecast_col2 = st.columns([1, 3])
        
        with forecast_col1:
            forecast_days = st.selectbox("Forecast Horizon", [7, 14, 30], index=1, key='forecast_horizon')
            
            if st.button("🔮 Generate Forecast", key='run_forecast'):
                with st.spinner("Running Prophet forecast model..."):
                    forecast_result = predict_revenue_forecast(filtered_df, forecast_days=forecast_days)
                    
                    if forecast_result:
                        st.session_state['forecast_result'] = forecast_result
                    else:
                        st.error("❌ Unable to generate forecast. Need at least 14 days of historical data.")
        
        with forecast_col2:
            if 'forecast_result' in st.session_state and st.session_state['forecast_result']:
                forecast = st.session_state['forecast_result']
                
                # Display forecast insight
                insight = forecast.get('insight', {})
                emoji = insight.get('emoji', '📊')
                message = insight.get('message', '')
                severity = insight.get('severity', 'info')
                
                if severity == 'positive':
                    st.success(f"{emoji} {message}")
                elif severity == 'warning':
                    st.warning(f"{emoji} {message}")
                else:
                    st.info(f"{emoji} {message}")
                
                # Display forecast metrics
                fcol1, fcol2, fcol3 = st.columns(3)
                
                with fcol1:
                    st.metric("Total Predicted", format_metric(forecast.get('total_predicted', 0), "SAR"))
                
                with fcol2:
                    st.metric("Daily Average", format_metric(forecast.get('daily_average', 0), "SAR"))
                
                with fcol3:
                    trend_pct = forecast.get('trend_pct', 0)
                    st.metric("Trend", f"{trend_pct:+.1f}%")
                
                # Plot forecast
                forecast_df = forecast.get('forecast_df')
                if forecast_df is not None and not forecast_df.empty:
                    fig_forecast = go.Figure()
                    
                    # Add predicted revenue line
                    fig_forecast.add_trace(go.Scatter(
                        x=forecast_df['ds'],
                        y=forecast_df['yhat'],
                        mode='lines',
                        name='Predicted Revenue',
                        line=dict(color=COLORS['primary'], width=2)
                    ))

                    # Add confidence interval
                    fig_forecast.add_trace(go.Scatter(
                        x=forecast_df['ds'],
                        y=forecast_df['yhat_upper'],
                        mode='lines',
                        name='Upper Bound (95%)',
                        line=dict(color=COLORS['info'], width=1, dash='dash'),
                        showlegend=False
                    ))

                    fig_forecast.add_trace(go.Scatter(
                        x=forecast_df['ds'],
                        y=forecast_df['yhat_lower'],
                        mode='lines',
                        name='Lower Bound (95%)',
                        line=dict(color=COLORS['info'], width=1, dash='dash'),
                        fill='tonexty',
                        fillcolor='rgba(8, 145, 178, 0.15)',
                        showlegend=False
                    ))
                    
                    fig_forecast.update_layout(
                        title=f"{forecast.get('forecast_days', 0)}-Day Revenue Forecast",
                        xaxis_title="Date",
                        yaxis_title="Revenue (SAR)",
                        hovermode='x unified'
                    )
                    
                    st.plotly_chart(fig_forecast, use_container_width=True)
                    forecast_img = export_chart_image(fig_forecast, 'revenue_forecast')
                    if forecast_img:
                        st.download_button("Download Forecast Chart", forecast_img, "revenue_forecast.png", "image/png", key='dl_forecast')

                    # Show confidence interval info
                    st.caption(f"📊 95% Confidence Interval: {format_metric(forecast.get('confidence_lower', 0), 'SAR')} - {format_metric(forecast.get('confidence_upper', 0), 'SAR')}")
        
        # === TOP ACTIONS (Like the example: "Add reminder blocks") ===
        st.markdown("---")
        st.subheader("🎯 Top 5 Prioritized Actions")
        st.markdown("*Specific, actionable recommendations with expected ROI*")
        
        top_actions = exec_summary.get('top_actions', [])
        
        if top_actions:
            for idx, action in enumerate(top_actions, 1):
                priority = action.get('priority', 'MEDIUM')
                title = action.get('title', '')
                action_text = action.get('action', '')
                expected_impact = action.get('expected_impact', '')
                confidence = action.get('confidence', '')
                impl_time = action.get('implementation_time', '')
                
                # Color code by priority
                if priority == 'HIGH':
                    priority_color = '🔴'
                    container_type = st.error
                elif priority == 'MEDIUM':
                    priority_color = '🟡'
                    container_type = st.warning
                else:
                    priority_color = '🟢'
                    container_type = st.info
                
                with st.expander(f"{idx}. {priority_color} [{priority}] {title}", expanded=(idx <= 2)):
                    st.markdown(f"**Action:** {action_text}")
                    
                    act_col1, act_col2, act_col3 = st.columns(3)
                    
                    with act_col1:
                        st.metric("Expected Impact", expected_impact)
                    
                    with act_col2:
                        st.metric("Confidence", confidence)
                    
                    with act_col3:
                        st.metric("Implementation Time", impl_time)
        else:
            st.info("✅ No critical actions needed at this time. Continue monitoring performance.")
        
        # === JOURNEY-SPECIFIC INSIGHTS ===
        st.markdown("---")
        st.subheader("🔍 Journey-Specific Deep Dive")
        st.markdown("*Analyze individual journeys with automated insights*")
        
        if 'Journey Name' in filtered_df.columns:
            unique_journeys = filtered_df['Journey Name'].dropna().unique()
            
            selected_journey_insights = st.selectbox(
                "Select Journey for Detailed Insights",
                [''] + list(unique_journeys),
                key='journey_insights_selector'
            )
            
            if selected_journey_insights:
                with st.spinner(f"Generating insights for {selected_journey_insights}..."):
                    journey_insights = generate_narrative_insights(
                        filtered_df,
                        journey_name=selected_journey_insights,
                        lookback_days=30
                    )
                    
                    # Display journey-specific insights
                    for category, items in journey_insights.items():
                        if items and category != 'context_notes':
                            st.markdown(f"**{category.replace('_', ' ').title()}:**")
                            for item in items:
                                if isinstance(item, dict):
                                    emoji = item.get('emoji', '')
                                    title = item.get('title', '')
                                    message = item.get('message', '')
                                    st.info(f"{emoji} **{title}**: {message}")
                    
                    # Generate journey-specific forecast
                    st.markdown("### 📈 Journey Revenue Forecast")
                    journey_forecast = predict_revenue_forecast(
                        filtered_df,
                        journey_name=selected_journey_insights,
                        forecast_days=14
                    )
                    
                    if journey_forecast:
                        insight = journey_forecast.get('insight', {})
                        st.info(f"{insight.get('emoji', '')} {insight.get('message', '')}")
                        
                        jf_col1, jf_col2 = st.columns(2)
                        with jf_col1:
                            st.metric("14-Day Predicted Total", 
                                    format_metric(journey_forecast.get('total_predicted', 0), "SAR"))
                        with jf_col2:
                            st.metric("Trend", f"{journey_forecast.get('trend_pct', 0):+.1f}%")
                    
                    # Generate journey-specific actions
                    st.markdown("### 🎯 Recommended Actions for This Journey")
                    journey_actions = generate_top_actions(
                        filtered_df,
                        journey_name=selected_journey_insights,
                        max_actions=3
                    )
                    
                    if journey_actions:
                        for action in journey_actions:
                            st.success(f"**{action.get('title', '')}**\n\n{action.get('action', '')}\n\n*Expected Impact: {action.get('expected_impact', '')}*")
                    else:
                        st.info("✅ Journey is performing well. Continue current strategy.")
        
        # === DOWNLOAD INSIGHTS REPORT ===
        st.markdown("---")
        st.subheader("📄 Export Insights Report")
        
        if st.button("📥 Download Full Insights Report (PDF-Ready)", key='download_insights'):
            st.info("💡 **Export Feature**: Copy the insights above or use browser print (Ctrl+P) to save as PDF")

    elif page == "Overview":
        st.header("Overview")

        # Executive narrative summary
        _total_rev = filtered_df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in filtered_df.columns else filtered_df['Revenue (SAR)'].sum()
        _total_conv = int(filtered_df['Selected Conversions'].sum() if 'Selected Conversions' in filtered_df.columns else filtered_df['Unique Conversions'].sum())
        _total_sent = int(filtered_df['Sent'].sum()) if 'Sent' in filtered_df.columns else 0
        _n_campaigns = filtered_df['Campaign Name'].nunique() if 'Campaign Name' in filtered_df.columns else 0
        _n_channels = filtered_df['Channel'].nunique() if 'Channel' in filtered_df.columns else 0
        _date_min = filtered_df['Reporting Period Start Date'].min().strftime('%b %d, %Y') if 'Reporting Period Start Date' in filtered_df.columns else ''
        _date_max = filtered_df['Reporting Period Start Date'].max().strftime('%b %d, %Y') if 'Reporting Period Start Date' in filtered_df.columns else ''

        st.markdown(
            f"**{_date_min} - {_date_max}** | "
            f"**{format_metric(_total_rev, 'SAR')}** revenue from "
            f"**{_total_conv:,}** conversions across "
            f"**{_n_campaigns:,}** campaigns on **{_n_channels}** channels "
            f"({format_metric(_total_sent)} messages sent)"
        )
        st.markdown("---")

        # Calculate metrics with comparison
        if comparison_result:
            current_metrics = calculate_period_metrics(comparison_result['current_data'], comparison_result['current_days'], conversion_attribution)
            comp_metrics = calculate_period_metrics(comparison_result['comparison_data'], comparison_result['comparison_days'], conversion_attribution)
            metric_changes = calculate_metric_changes(current_metrics, comp_metrics)
            
            # Display metrics with comparisons
            col1, col2, col3 = st.columns(3)
            with col1:
                change_data = metric_changes['selected_revenue']
                st.metric(
                    selected_rev_label, 
                    f"{change_data['current']:,.0f} SAR",
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
                )
                change_data = metric_changes['selected_conversions']
                st.metric(
                    selected_conv_label, 
                    f"{change_data['current']:,.0f}",
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
                )
            with col2:
                change_data = metric_changes['total_clicks']
                st.metric(
                    "Total Clicks", 
                    f"{change_data['current']:,.0f}",
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
                )
                change_data = metric_changes['total_impressions']
                st.metric(
                    "Total Impressions", 
                    f"{change_data['current']:,.0f}",
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
                )
            with col3:
                change_data = metric_changes['ctr']
                st.metric(
                    "Avg CTR", 
                    f"{change_data['current']:.2%}",
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
                )
                change_data = metric_changes['conversion_rate']
                st.metric(
                    "Avg Conversion Rate", 
                    f"{change_data['current']:.2%}",
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
                )
                
                # Control Group Uplift
                if 'control_group_uplift' in metric_changes:
                    change_data = metric_changes['control_group_uplift']
                    st.metric(
                        "Control Group Uplift",
                        f"{change_data['current']:+.1f}%" if change_data['current'] is not None else "N/A",
                        delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})" if change_data['comparison'] is not None else None,
                        delta_color="normal" if change_data.get('pct_change', 0) >= 0 else "inverse",
                        help="Uplift vs Control Group: (Test Conv Rate - Control Conv Rate) / Control Conv Rate"
                    )
                else:
                    change_data = metric_changes['delivery_rate']
                    st.metric(
                        "Avg Delivery Rate", 
                        f"{change_data['current']:.2%}",
                        delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                        delta_color="normal" if change_data['pct_change'] >= 0 else "inverse"
                    )
            
            # NEW: Business Intelligence Metrics Row
            st.markdown("---")
            st.subheader("💰 Business Intelligence Metrics")
            biz_col1, biz_col2, biz_col3 = st.columns(3)
            
            with biz_col1:
                change_data = metric_changes['aov']
                st.metric(
                    "Average Order Value (AOV)", 
                    format_metric(change_data['current'], "SAR"),
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
                    help="Revenue per conversion - shows average customer purchase value"
                )
            
            with biz_col2:
                change_data = metric_changes['revenue_per_click']
                st.metric(
                    "Revenue Per Click (RPC)", 
                    format_metric(change_data['current'], "SAR"),
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
                    help="Revenue generated per click - measures click quality"
                )
            
            with biz_col3:
                change_data = metric_changes['engagement_rate']
                st.metric(
                    "Engagement Rate", 
                    f"{change_data['current']:.2%}",
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
                    help="Combined engagement metric (clicks + opens) / impressions"
                )
            
            # NEW: ROI & Cost Efficiency Metrics
            st.markdown("---")
            st.subheader("💵 ROI & Cost Efficiency")
            cost_display = ", ".join(f"{ch} ({c} SAR/1k)" for ch, c in CHANNEL_COSTS.items() if c > 0)
            st.caption(f"*Based on channel costs: {cost_display}*")
            
            roi_col1, roi_col2, roi_col3, roi_col4 = st.columns(4)
            
            with roi_col1:
                change_data = metric_changes['roas']
                current_roas = change_data['current']
                # ROAS interpretation
                if current_roas >= 4:
                    roas_status = "🟢 Excellent"
                elif current_roas >= 2:
                    roas_status = "🟡 Good"
                elif current_roas >= 1:
                    roas_status = "🟠 Break-even"
                else:
                    roas_status = "🔴 Unprofitable"
                
                st.metric(
                    "ROAS (Return on Ad Spend)", 
                    f"{current_roas:.2f}x",
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
                    help=f"Revenue / Cost ratio. {roas_status}"
                )
                st.caption(f"Status: {roas_status}")
            
            with roi_col2:
                change_data = metric_changes['revenue_per_send']
                st.metric(
                    "Revenue Per Send (RPS)", 
                    f"{change_data['current']:.4f} SAR",
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
                    help="Revenue generated per message sent - KEY efficiency indicator"
                )
            
            with roi_col3:
                change_data = metric_changes['cost_per_conversion']
                st.metric(
                    "Cost Per Conversion", 
                    format_metric(change_data['current'], "SAR"),
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="inverse" if change_data['pct_change'] >= 0 else "normal",  # Lower is better
                    help="How much you spend to acquire each conversion"
                )
            
            with roi_col4:
                change_data = metric_changes['profit']
                st.metric(
                    "Profit (Revenue - Cost)", 
                    format_metric(change_data['current'], "SAR"),
                    delta=f"{change_data['pct_change']:+.1f}% ({change_data['trend']})",
                    delta_color="normal" if change_data['pct_change'] >= 0 else "inverse",
                    help="Net profit after campaign costs"
                )
            
            # Comparison summary card
            st.markdown("---")
            st.subheader("📊 Period Comparison Summary")
            sum_col1, sum_col2, sum_col3 = st.columns(3)
            
            with sum_col1:
                st.markdown(f"**Current Period:** {comparison_result['current_label']}")
                st.markdown(f"- Duration: {comparison_result['current_days']} days")
                st.markdown(f"- Daily Avg Revenue: {format_metric(current_metrics['daily_revenue'], 'SAR')}")
                st.markdown(f"- Daily Avg Conversions: {format_metric(current_metrics['daily_conversions'])}")
            
            with sum_col2:
                st.markdown(f"**Comparison Period:** {comparison_result['comparison_label']}")
                st.markdown(f"- Duration: {comparison_result['comparison_days']} days")
                st.markdown(f"- Daily Avg Revenue: {format_metric(comp_metrics['daily_revenue'], 'SAR')}")
                st.markdown(f"- Daily Avg Conversions: {format_metric(comp_metrics['daily_conversions'])}")
            
            with sum_col3:
                st.markdown("**Key Changes:**")
                revenue_change = metric_changes['selected_revenue']['pct_change']
                conv_change = metric_changes['selected_conversions']['pct_change']
                ctr_change = metric_changes['ctr']['pct_change']
                
                if revenue_change > 0:
                    st.success(f"✅ Revenue: {revenue_change:+.1f}%")
                else:
                    st.error(f"⚠️ Revenue: {revenue_change:+.1f}%")
                
                if conv_change > 0:
                    st.success(f"✅ Conversions: {conv_change:+.1f}%")
                else:
                    st.error(f"⚠️ Conversions: {conv_change:+.1f}%")
                
                if ctr_change > 0:
                    st.success(f"✅ CTR: {ctr_change:+.1f}%")
                else:
                    st.error(f"⚠️ CTR: {ctr_change:+.1f}%")
        
        else:
            # No comparison - show regular metrics
            col1, col2, col3 = st.columns(3)
            with col1:
                total_revenue = filtered_df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in filtered_df.columns else filtered_df['Revenue (SAR)'].sum()
                st.metric(selected_rev_label, f"{total_revenue:,.0f} SAR")
                total_conv = filtered_df['Selected Conversions'].sum() if 'Selected Conversions' in filtered_df.columns else filtered_df['Unique Conversions'].sum()
                st.metric(selected_conv_label, f"{total_conv:,.0f}")
            with col2:
                st.metric("Total Unique Clicks", f"{filtered_df['Unique Clicks'].sum():,.0f}")
                st.metric("Total Unique Impressions", f"{filtered_df['Unique Impressions'].sum():,.0f}")
            with col3:
                st.metric("Avg CTR", f"{filtered_df['CTR'].mean():.2%}")
                # Calculate conversion rate from raw data
                total_clicks = filtered_df['Unique Clicks'].sum()
                conv_col = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'
                total_conversions = filtered_df[conv_col].sum()
                avg_conv_rate = (total_conversions / total_clicks) if total_clicks > 0 else 0
                st.metric("Avg Conversion Rate", f"{avg_conv_rate:.2%}")
                
                # Calculate Control Group Uplift (respects attribution selection)
                if 'Total in Control Group' in filtered_df.columns and 'Unique Control Group Conversions' in filtered_df.columns:
                    # Filter campaigns with control groups
                    control_campaigns = filtered_df[filtered_df['Total in Control Group'] > 0]
                    if not control_campaigns.empty:
                        # Aggregate totals
                        total_control_group = control_campaigns['Total in Control Group'].sum()
                        total_control_conversions = control_campaigns['Unique Control Group Conversions'].sum()
                        
                        # Use selected conversions based on attribution
                        if 'Selected Conversions' in control_campaigns.columns:
                            test_conversions = control_campaigns['Selected Conversions'].sum()
                        else:
                            test_conversions = control_campaigns['Unique Conversions'].sum()
                        
                        # Determine denominator based on attribution type
                        if conversion_attribution == "Impression-Through":
                            test_denominator = control_campaigns['Unique Impressions'].sum()
                            denominator_label = "Impressions"
                        elif conversion_attribution == "Click-Through":
                            test_denominator = control_campaigns['Unique Clicks'].sum()
                            denominator_label = "Clicks"
                        else:  # Total
                            test_denominator = control_campaigns['Sent'].sum()
                            denominator_label = "Sent"
                        
                        # Calculate rates and significance
                        if test_denominator > 0 and total_control_group > 0 and total_control_conversions > 0:
                            test_conv_rate = test_conversions / test_denominator
                            control_conv_rate = total_control_conversions / total_control_group
                            uplift_pct = ((test_conv_rate - control_conv_rate) / control_conv_rate) * 100
                            
                            # Calculate statistical significance
                            p_value, is_significant, reliability = calculate_uplift_significance(
                                test_conversions, test_denominator,
                                total_control_conversions, total_control_group
                            )
                            
                            # Build help text with significance info
                            help_text = f"Uplift vs Control Group ({conversion_attribution})\n"
                            help_text += f"Campaign Conv Rate: {test_conv_rate:.2%} ({test_conversions:,.0f}/{test_denominator:,.0f} {denominator_label})\n"
                            help_text += f"Control Group Conv Rate: {control_conv_rate:.2%} ({total_control_conversions:,.0f}/{total_control_group:,.0f})\n"
                            help_text += f"\nReliability: {reliability}\n"
                            
                            if p_value is not None:
                                # Display p-value professionally
                                if p_value < 0.0001:
                                    p_display = "p < 0.0001"
                                else:
                                    p_display = f"p = {p_value:.4f}"
                                help_text += f"Statistical Significance: {p_display}\n"
                                help_text += f"{'✓ Significant' if is_significant else '✗ Not significant'} at 95% confidence\n"
                            
                            help_text += f"\nFormula: (Campaign Rate - Control Rate) / Control Rate"
                            
                            # Add asterisk for statistical significance (professional standard)
                            sig_indicator = "*" if is_significant and p_value is not None else ""
                            reliability_emoji = reliability.split()[0]  # Extract emoji from reliability string
                            
                            st.metric(
                                f"Control Group Uplift {reliability_emoji}", 
                                f"{uplift_pct:+.1f}%{sig_indicator}",
                                help=help_text
                            )
                            # Add small note below metric
                            st.caption("*Based on campaigns with control groups only. Other metrics show all campaigns.")
                        else:
                            st.metric("Avg Delivery Rate", f"{filtered_df['Delivery Rate'].mean():.2%}")
                    else:
                        st.metric("Avg Delivery Rate", f"{filtered_df['Delivery Rate'].mean():.2%}")
                else:
                    st.metric("Avg Delivery Rate", f"{filtered_df['Delivery Rate'].mean():.2%}")

        # Conversion Funnel - aggregate pipeline view
        st.markdown("---")
        st.subheader("Conversion Pipeline")
        funnel_sent = filtered_df['Sent'].sum() if 'Sent' in filtered_df.columns else 0
        funnel_delivered = filtered_df['Delivered'].sum() if 'Delivered' in filtered_df.columns else 0
        funnel_impressions = filtered_df['Unique Impressions'].sum() if 'Unique Impressions' in filtered_df.columns else 0
        funnel_clicks = filtered_df['Unique Clicks'].sum() if 'Unique Clicks' in filtered_df.columns else 0
        funnel_conversions = filtered_df['Unique Conversions'].sum() if 'Unique Conversions' in filtered_df.columns else 0

        funnel_stages = ['Sent', 'Delivered', 'Impressions', 'Clicks', 'Conversions']
        funnel_values = [funnel_sent, funnel_delivered, funnel_impressions, funnel_clicks, funnel_conversions]
        # Only show stages with data
        active_stages = [(s, v) for s, v in zip(funnel_stages, funnel_values) if v > 0]

        if active_stages:
            stages, values = zip(*active_stages)
            funnel_col1, funnel_col2 = st.columns([3, 2])
            with funnel_col1:
                fig_funnel = go.Figure(go.Funnel(
                    y=list(stages),
                    x=list(values),
                    textposition="inside",
                    textinfo="value+percent initial+percent previous",
                    opacity=0.85,
                    marker={"color": [COLORS['primary'], COLORS['info'], COLORS['warning'],
                                      COLORS['secondary'], COLORS['success']][:len(stages)]},
                    connector={"line": {"color": COLORS['muted'], "dash": "dot", "width": 2}}
                ))
                fig_funnel.update_layout(
                    title="Aggregate Conversion Funnel",
                    margin=dict(l=120, r=20, t=50, b=20),
                    height=350,
                )
                st.plotly_chart(fig_funnel, use_container_width=True)
                img_funnel = export_chart_image(fig_funnel)
                if img_funnel:
                    st.download_button("Download Funnel Chart", img_funnel, "conversion_funnel.png", "image/png", key='dl_funnel')

            with funnel_col2:
                st.markdown("**Stage-to-Stage Conversion Rates**")
                if funnel_sent > 0 and funnel_delivered > 0:
                    st.metric("Delivery Rate", f"{funnel_delivered / funnel_sent:.2%}",
                              help="Sent → Delivered")
                if funnel_delivered > 0 and funnel_impressions > 0:
                    st.metric("Impression Rate", f"{funnel_impressions / funnel_delivered:.2%}",
                              help="Delivered → Impressions (opened/viewed)")
                if funnel_impressions > 0 and funnel_clicks > 0:
                    st.metric("Click-Through Rate", f"{funnel_clicks / funnel_impressions:.2%}",
                              help="Impressions → Clicks")
                if funnel_clicks > 0 and funnel_conversions > 0:
                    st.metric("Conversion Rate", f"{funnel_conversions / funnel_clicks:.2%}",
                              help="Clicks → Conversions")
                if funnel_sent > 0 and funnel_conversions > 0:
                    st.metric("Overall Pipeline Rate", f"{funnel_conversions / funnel_sent:.4%}",
                              help="Sent → Conversions (end-to-end)")

        # Channels Overview Section
        st.markdown("---")
        st.subheader("📡 Channels Overview")
        st.markdown("*Performance breakdown by marketing channel*")
        
        if 'Channel' in filtered_df.columns:
            # Get channel data - determine revenue and conversion columns
            revenue_col_to_use = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
            conv_col_to_use = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'
            
            agg_dict = {
                'Sent': 'sum',
                'Delivered': 'sum',
                'Unique Impressions': 'sum',
                'Unique Clicks': 'sum',
            }
            
            # Always aggregate the conversion column being used
            agg_dict[conv_col_to_use] = 'sum'
            
            # Also aggregate Unique Conversions if it's different (needed for fallback calculations)
            if conv_col_to_use != 'Unique Conversions' and 'Unique Conversions' in filtered_df.columns:
                agg_dict['Unique Conversions'] = 'sum'
            
            # Add Click-Through Conversions if available (for accurate conversion rate)
            if 'Unique Click-Through Conversions' in filtered_df.columns:
                agg_dict['Unique Click-Through Conversions'] = 'sum'
            
            if revenue_col_to_use in filtered_df.columns:
                agg_dict[revenue_col_to_use] = 'sum'
            
            channel_data = filtered_df.groupby('Channel').agg(agg_dict).reset_index()
            
            # Calculate rates for each channel from raw counts (not pre-calculated rates)
            # Using raw metrics ensures correct calculation at channel level
            channel_data['Delivery Rate'] = np.where(
                channel_data['Sent'] > 0,
                (channel_data['Delivered'] / channel_data['Sent'] * 100),
                0
            ).round(1)
            
            channel_data['CTR'] = np.where(
                channel_data['Unique Impressions'] > 0,
                (channel_data['Unique Clicks'] / channel_data['Unique Impressions'] * 100),
                0
            ).round(2)
            
            # Conversion Rate - Use Click-Through Conversions for accurate rate
            # (Total conversions includes impression-through which didn't click)
            if 'Unique Click-Through Conversions' in channel_data.columns:
                channel_data['Conversion Rate'] = np.where(
                    channel_data['Unique Clicks'] > 0,
                    (channel_data['Unique Click-Through Conversions'] / channel_data['Unique Clicks'] * 100),
                    0
                ).round(2)
            else:
                # Fallback to total conversions if click-through not available
                channel_data['Conversion Rate'] = np.where(
                    channel_data['Unique Clicks'] > 0,
                    (channel_data['Unique Conversions'] / channel_data['Unique Clicks'] * 100),
                    0
                ).round(2)
            
            # Calculate business metrics for channels
            revenue_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in channel_data.columns else 'Revenue (SAR)'
            # Use the selected conversion column for calculations
            conv_col_for_calc = conv_col_to_use if conv_col_to_use in channel_data.columns else 'Unique Conversions'
            
            # AOV - Average Order Value (Revenue per Conversion) - uses selected attribution
            channel_data['AOV'] = np.where(
                channel_data[conv_col_for_calc] > 0,
                channel_data[revenue_col] / channel_data[conv_col_for_calc],
                0
            ).round(2)
            
            # RPC - Revenue Per Click
            channel_data['RPC'] = np.where(
                channel_data['Unique Clicks'] > 0,
                channel_data[revenue_col] / channel_data['Unique Clicks'],
                0
            ).round(2)
            
            # Calculate cost-based metrics for channels (uses centralized CHANNEL_COSTS)
            channel_data['Cost'] = channel_data.apply(
                lambda row: (row['Sent'] / 1000) * CHANNEL_COSTS.get(row['Channel'], 0),
                axis=1
            ).round(2)
            
            # ROAS - Return on Ad Spend
            channel_data['ROAS'] = np.where(
                channel_data['Cost'] > 0,
                channel_data[revenue_col] / channel_data['Cost'],
                0
            ).round(2)
            
            # Revenue Per Send (RPS)
            channel_data['RPS'] = np.where(
                channel_data['Sent'] > 0,
                channel_data[revenue_col] / channel_data['Sent'],
                0
            ).round(4)
            
            # Cost Per Conversion (CPC) - uses selected attribution
            channel_data['CPC'] = np.where(
                channel_data[conv_col_for_calc] > 0,
                channel_data['Cost'] / channel_data[conv_col_for_calc],
                0
            ).round(2)
            
            # Sort by revenue
            channel_data = channel_data.sort_values(revenue_col, ascending=False)
            
            # Define channel icons and status
            channel_icons = {
                'Email': '📧',
                'SMS': '💬',
                'Push': '🔔',
                'Web Push': '🌐',
                'Mobile Push': '📱',
                'App Push': '📱',
                'WhatsApp': '💚',
                'In-App': '📲',
                'On-Site': '🖥️',
                'Onsite': '🖥️',
                'On-site': '🖥️',
                'Facebook': '👤',
                'Google': '🔍'
            }
            
            # Check comparison data for channel performance
            channel_comparison = {}
            if comparison_result:
                # Determine columns for comparison
                comp_rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in comparison_result['current_data'].columns else 'Revenue (SAR)'
                comp_conv_col = 'Selected Conversions' if 'Selected Conversions' in comparison_result['current_data'].columns else 'Unique Conversions'
                
                current_channel_agg = {}
                comp_channel_agg = {}
                
                if comp_rev_col in comparison_result['current_data'].columns:
                    current_channel_agg[comp_rev_col] = 'sum'
                    comp_channel_agg[comp_rev_col] = 'sum'
                if comp_conv_col in comparison_result['current_data'].columns:
                    current_channel_agg[comp_conv_col] = 'sum'
                    comp_channel_agg[comp_conv_col] = 'sum'
                
                current_channel_data = comparison_result['current_data'].groupby('Channel').agg(current_channel_agg)
                comp_channel_data = comparison_result['comparison_data'].groupby('Channel').agg(comp_channel_agg)
                
                for channel in current_channel_data.index:
                    if channel in comp_channel_data.index:
                        curr_rev = current_channel_data.loc[channel, comp_rev_col]
                        comp_rev = comp_channel_data.loc[channel, comp_rev_col]
                        
                        if comp_rev > 0:
                            rev_change = ((curr_rev - comp_rev) / comp_rev) * 100
                        else:
                            rev_change = 0
                        
                        channel_comparison[channel] = {
                            'revenue_change': rev_change,
                            'trend': '↗' if rev_change > 1 else '↘' if rev_change < -1 else '→'
                        }
            
            # Display channel cards in a grid
            num_channels = len(channel_data)
            
            if num_channels > 0:
                # Show top-level summary
                st.markdown("#### Active Channels Performance")
                
                # Create channel cards
                cols_per_row = 4
                rows_needed = (num_channels + cols_per_row - 1) // cols_per_row
                
                idx = 0
                for row in range(rows_needed):
                    cols = st.columns(cols_per_row)
                    
                    for col_idx, col in enumerate(cols):
                        if idx < num_channels:
                            channel_row = channel_data.iloc[idx]
                            channel_name = channel_row['Channel']
                            
                            # Get icon
                            icon = channel_icons.get(channel_name, '📊')
                            
                            with col:
                                # Determine if channel is active (has recent data)
                                is_active = channel_row['Sent'] > 0
                                
                                # Card styling based on activity
                                if is_active:
                                    st.markdown(f"**{icon} {channel_name}**")
                                    
                                    # Show comparison if available
                                    if channel_name in channel_comparison:
                                        comp_info = channel_comparison[channel_name]
                                        trend_indicator = comp_info['trend']
                                        change_pct = comp_info['revenue_change']
                                        
                                        if change_pct > 0:
                                            st.success(f"{trend_indicator} {change_pct:+.1f}%")
                                        elif change_pct < 0:
                                            st.error(f"{trend_indicator} {change_pct:+.1f}%")
                                        else:
                                            st.info(f"{trend_indicator} {change_pct:+.1f}%")
                                    else:
                                        st.markdown("✅ **Active**")
                                    
                                    # Key metrics
                                    revenue_val = channel_row[revenue_col]
                                    # Use selected conversion column (respects attribution choice)
                                    conv_val = channel_row[conv_col_to_use] if conv_col_to_use in channel_row else channel_row.get('Unique Conversions', 0)
                                    delivery_rate = channel_row['Delivery Rate']
                                    ctr = channel_row['CTR']
                                    aov_val = channel_row['AOV']
                                    rpc_val = channel_row['RPC']
                                    cost_val = channel_row['Cost']
                                    roas_val = channel_row['ROAS']
                                    rps_val = channel_row['RPS']
                                    
                                    # Get raw counts for better display
                                    impressions = channel_row['Unique Impressions']
                                    clicks = channel_row['Unique Clicks']
                                    
                                    st.metric("Revenue", format_metric(revenue_val, "SAR"))
                                    st.metric("Conversions", format_metric(conv_val))
                                    
                                    # Always show AOV if there are conversions (important business metric)
                                    if conv_val > 0:
                                        st.markdown(f"<small>💰 <span title='Average Order Value - Revenue per conversion' style='cursor: help;'>AOV</span>: {format_metric(aov_val, 'SAR')}</small>", unsafe_allow_html=True)
                                    
                                    # Show cost efficiency (highlight for paid channels)
                                    if cost_val > 0:
                                        st.markdown(f"<small>💵 Cost: {format_metric(cost_val, 'SAR')}</small>", unsafe_allow_html=True)
                                        # ROAS color coding with tooltip
                                        if roas_val >= 4:
                                            st.markdown(f"<small>📈 <span title='Return on Ad Spend - Revenue earned per SAR spent (4x = 4 SAR revenue per 1 SAR cost)' style='cursor: help;'>ROAS</span>: **{roas_val:.1f}x** 🟢</small>", unsafe_allow_html=True)
                                        elif roas_val >= 2:
                                            st.markdown(f"<small>📈 <span title='Return on Ad Spend - Revenue earned per SAR spent (4x = 4 SAR revenue per 1 SAR cost)' style='cursor: help;'>ROAS</span>: **{roas_val:.1f}x** 🟡</small>", unsafe_allow_html=True)
                                        else:
                                            st.markdown(f"<small>📈 <span title='Return on Ad Spend - Revenue earned per SAR spent (4x = 4 SAR revenue per 1 SAR cost)' style='cursor: help;'>ROAS</span>: **{roas_val:.1f}x** 🔴</small>", unsafe_allow_html=True)
                                        st.markdown(f"<small>💰 <span title='Revenue Per Send - Revenue generated per message sent' style='cursor: help;'>RPS</span>: {rps_val:.4f} SAR</small>", unsafe_allow_html=True)
                                    else:
                                        # Free channels - show RPC
                                        if clicks > 0:
                                            st.markdown(f"<small>🎯 <span title='Revenue Per Click - Revenue generated per click' style='cursor: help;'>RPC</span>: {format_metric(rpc_val, 'SAR')}</small>", unsafe_allow_html=True)
                                    
                                    # Show rates in smaller text with context and tooltips
                                    st.markdown(f"<small>📨 Delivery: {delivery_rate:.1f}%</small>", unsafe_allow_html=True)
                                    
                                    # Show CTR with context and tooltip - some channels don't track impressions
                                    if impressions > 0:
                                        st.markdown(f"<small>👆 <span title='Click-Through Rate - Percentage of impressions that resulted in clicks' style='cursor: help;'>CTR</span>: {ctr:.2f}% ({format_metric(clicks)} clicks)</small>", unsafe_allow_html=True)
                                    else:
                                        st.markdown(f"<small>👆 <span title='Click-Through Rate - Percentage of impressions that resulted in clicks' style='cursor: help;'>CTR</span>: N/A (no impression tracking)</small>", unsafe_allow_html=True)
                                else:
                                    st.markdown(f"**{icon} {channel_name}**")
                                    st.warning("❌ Inactive")
                                    st.caption("No activity this period")
                            
                            idx += 1
                
                # Detailed channel comparison table
                st.markdown("---")
                st.markdown("#### Detailed Channel Metrics")
                st.caption("*Conversion Rate = Click-Through Conversions / Unique Clicks. Hover over abbreviated metrics for full names.*")
                
                # Create display dataframe
                channel_display = channel_data.copy()
                channel_display['Channel'] = channel_display['Channel'].apply(lambda x: f"{channel_icons.get(x, '📊')} {x}")
                channel_display['Sent'] = channel_display['Sent'].apply(format_metric)
                channel_display['Delivered'] = channel_display['Delivered'].apply(format_metric)
                channel_display['Unique Clicks'] = channel_display['Unique Clicks'].apply(format_metric)
                
                # Format the selected conversion column
                if conv_col_for_calc in channel_display.columns:
                    channel_display[conv_col_for_calc] = channel_display[conv_col_for_calc].apply(format_metric)
                
                channel_display[revenue_col] = channel_display[revenue_col].apply(lambda x: format_metric(x, "SAR"))
                
                # Select columns to display - use selected conversion column
                display_cols = ['Channel', 'Sent', 'Delivered', 'Delivery Rate', 'Unique Clicks', 
                               'CTR', conv_col_for_calc, 'Conversion Rate', revenue_col]
                channel_display = channel_display[display_cols]
                
                # Rename columns to show actual attribution model
                channel_display = channel_display.rename(columns=attribution_rename)
                
                st.dataframe(channel_display, use_container_width=True, hide_index=True)
                
                # Channel performance charts
                col1, col2 = st.columns(2)
                
                with col1:
                    # Revenue by channel - use consistent channel colors
                    rev_display_name = get_selected_revenue_display_name(revenue_attribution)
                    fig_channel_revenue = px.bar(
                        channel_data,
                        x='Channel',
                        y=revenue_col,
                        title=f"{rev_display_name} by Channel",
                        color='Channel',
                        color_discrete_map=CHANNEL_COLORS,
                        labels={revenue_col: rev_display_name}
                    )
                    fig_channel_revenue.update_layout(showlegend=False)
                    st.plotly_chart(fig_channel_revenue, use_container_width=True)

                with col2:
                    # Conversions by channel - use consistent channel colors
                    conv_display_name = get_selected_conversion_display_name(conversion_attribution)
                    fig_channel_conv = px.bar(
                        channel_data,
                        x='Channel',
                        y='Unique Conversions',
                        title=f"{conv_display_name} by Channel",
                        color='Channel',
                        color_discrete_map=CHANNEL_COLORS,
                        labels={'Unique Conversions': conv_display_name}
                    )
                    fig_channel_conv.update_layout(showlegend=False)
                    st.plotly_chart(fig_channel_conv, use_container_width=True)
                
                # Channel insights
                st.markdown("#### 💡 Channel Insights")
                
                # Find best and worst performing channels
                if len(channel_data) > 0:
                    best_revenue_channel = channel_data.iloc[0]
                    best_conv_rate_channel = channel_data.loc[channel_data['Conversion Rate'].idxmax()]
                    best_ctr_channel = channel_data.loc[channel_data['CTR'].idxmax()]
                    
                    insight_col1, insight_col2, insight_col3 = st.columns(3)
                    
                    with insight_col1:
                        st.success(f"**🏆 Top Revenue Channel**")
                        st.markdown(f"{channel_icons.get(best_revenue_channel['Channel'], '📊')} **{best_revenue_channel['Channel']}**")
                        st.markdown(f"Revenue: {format_metric(best_revenue_channel[revenue_col], 'SAR')}")
                    
                    with insight_col2:
                        st.success(f"**🎯 Best Conversion Rate**")
                        st.markdown(f"{channel_icons.get(best_conv_rate_channel['Channel'], '📊')} **{best_conv_rate_channel['Channel']}**")
                        st.markdown(f"Conv Rate: {best_conv_rate_channel['Conversion Rate']:.2f}%")
                    
                    with insight_col3:
                        st.success(f"**👆 Best Engagement**")
                        st.markdown(f"{channel_icons.get(best_ctr_channel['Channel'], '📊')} **{best_ctr_channel['Channel']}**")
                        st.markdown(f"CTR: {best_ctr_channel['CTR']:.2f}%")
                    
                    # Additional insights
                    st.markdown("**Key Observations:**")
                    observations = []
                    
                    # Check for inactive channels
                    inactive_channels = channel_data[channel_data['Sent'] == 0]['Channel'].tolist()
                    if inactive_channels:
                        observations.append(f"⚠️ **Inactive Channels**: {', '.join(inactive_channels)} - Consider reactivating or investigating")
                    
                    # Check for low delivery rates
                    low_delivery = channel_data[channel_data['Delivery Rate'] < 85]
                    if not low_delivery.empty:
                        for _, row in low_delivery.iterrows():
                            observations.append(f"🚨 **{row['Channel']}**: Low delivery rate ({row['Delivery Rate']:.1f}%) - Check ESP settings")
                    
                    # Check for high CTR but low conversions
                    high_ctr_low_conv = channel_data[(channel_data['CTR'] > 3) & (channel_data['Conversion Rate'] < 5)]
                    if not high_ctr_low_conv.empty:
                        for _, row in high_ctr_low_conv.iterrows():
                            observations.append(f"💡 **{row['Channel']}**: Good engagement ({row['CTR']:.2f}% CTR) but low conversion ({row['Conversion Rate']:.2f}%) - Optimize landing pages")
                    
                    # Show observations
                    if observations:
                        for obs in observations:
                            st.markdown(f"- {obs}")
                    else:
                        st.info("✅ All channels are performing well with no major issues detected")
            else:
                st.info("No channel data available for the selected period")
        else:
            st.warning("⚠️ Channel information not available in the dataset")

        # === REVENUE TREEMAP: Where does revenue come from? ===
        st.markdown("---")
        st.subheader("🗺️ Revenue Breakdown")
        st.caption("*Hierarchical view: Channel → Journey/Campaign (size = revenue)*")

        if 'Channel' in filtered_df.columns and 'Revenue (SAR)' in filtered_df.columns:
            rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
            # Build hierarchy: Channel > Campaign Name
            treemap_df = filtered_df.groupby(['Channel', 'Campaign Name'], dropna=False).agg({
                rev_col: 'sum', 'Unique Conversions': 'sum'
            }).reset_index()
            treemap_df = treemap_df[treemap_df[rev_col] > 0]

            if not treemap_df.empty:
                rev_display_name = get_selected_revenue_display_name(revenue_attribution)
                fig_treemap = px.treemap(
                    treemap_df,
                    path=['Channel', 'Campaign Name'],
                    values=rev_col,
                    color='Channel',
                    color_discrete_map=CHANNEL_COLORS,
                    title=f'{rev_display_name} by Channel & Campaign',
                )
                fig_treemap.update_traces(
                    textinfo='label+value+percent parent',
                    hovertemplate='<b>%{label}</b><br>' + rev_display_name + ': %{value:,.0f} SAR<br>%{percentParent:.1%} of parent<extra></extra>',
                )
                fig_treemap.update_layout(margin=dict(l=10, r=10, t=50, b=10))
                st.plotly_chart(fig_treemap, use_container_width=True)

                # Chart export button
                img_buf = export_chart_image(fig_treemap, 'revenue_treemap')
                if img_buf:
                    st.download_button("📥 Download Treemap (PNG)", img_buf, file_name="revenue_treemap.png", mime="image/png")

        # === CHANNEL MIX OVER TIME: Stacked area ===
        st.markdown("---")
        st.subheader("📊 Channel Mix Over Time")
        st.caption("*How your channel revenue distribution evolves*")

        if 'Channel' in filtered_df.columns and 'Reporting Period Start Date' in filtered_df.columns:
            rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
            time_channel = filtered_df.groupby(
                [pd.Grouper(key='Reporting Period Start Date', freq='W'), 'Channel']
            )[rev_col].sum().reset_index()
            time_channel.columns = ['Week', 'Channel', 'Revenue']

            if not time_channel.empty:
                rev_display_name = get_selected_revenue_display_name(revenue_attribution)
                fig_area = px.area(
                    time_channel,
                    x='Week', y='Revenue', color='Channel',
                    color_discrete_map=CHANNEL_COLORS,
                    title=f'Weekly {rev_display_name}',
                    labels={'Revenue': f'{rev_display_name} (SAR)', 'Week': ''},
                )
                fig_area.update_layout(hovermode='x unified')
                st.plotly_chart(fig_area, use_container_width=True)

                img_buf = export_chart_image(fig_area, 'channel_mix')
                if img_buf:
                    st.download_button("📥 Download Channel Mix (PNG)", img_buf, file_name="channel_mix.png", mime="image/png")

        # Conversion Funnel
        st.markdown("---")
        st.subheader("Conversion Funnel")
        funnel_data = {
            'Stage': ['Sent', 'Impressions', 'Clicks', 'Conversions'],
            'Count': [filtered_df['Sent'].sum(), filtered_df['Unique Impressions'].sum(), filtered_df['Unique Clicks'].sum(), filtered_df['Unique Conversions'].sum()]
        }
        fig_funnel = go.Figure(go.Funnel(
            y=funnel_data['Stage'],
            x=funnel_data['Count'],
            textinfo="value+percent initial",
            marker=dict(color=[COLORS['primary'], COLORS['info'], COLORS['warning'], COLORS['success']]),
        ))
        fig_funnel.update_layout(title='Conversion Funnel')
        st.plotly_chart(fig_funnel, use_container_width=True)

        img_buf = export_chart_image(fig_funnel, 'conversion_funnel')
        if img_buf:
            st.download_button("📥 Download Funnel (PNG)", img_buf, file_name="conversion_funnel.png", mime="image/png")

        # Failed reasons
        failed_df = failed_reasons_analysis(filtered_df)
        if not failed_df.empty:
            st.subheader("Failed Reasons Breakdown")
            fig_fail = px.pie(failed_df, names='Reason', values='Count', color_discrete_sequence=COLOR_SEQUENCE)
            st.plotly_chart(fig_fail, use_container_width=True)

        # Data Preview
        with st.expander("View Filtered Data"):
            st.dataframe(filtered_df)

    elif page == "Campaigns":
        st.header("Campaign Analysis")
        
        # Show comparison summary if enabled
        if comparison_result:
            st.info(f"📊 Period Comparison Active: {comparison_result['current_label']} vs {comparison_result['comparison_label']}")
            
            # Calculate campaign metrics for both periods
            current_metrics = calculate_period_metrics(comparison_result['current_data'], comparison_result['current_days'], conversion_attribution)
            comp_metrics = calculate_period_metrics(comparison_result['comparison_data'], comparison_result['comparison_days'], conversion_attribution)
            metric_changes = calculate_metric_changes(current_metrics, comp_metrics)
            
            # Show quick comparison
            comp_col1, comp_col2, comp_col3, comp_col4 = st.columns(4)
            with comp_col1:
                change_data = metric_changes['selected_revenue']
                st.metric("Revenue", format_metric(change_data['current'], "SAR"), 
                         delta=f"{change_data['pct_change']:+.1f}%")
            with comp_col2:
                change_data = metric_changes['selected_conversions']
                st.metric("Conversions", format_metric(change_data['current']), 
                         delta=f"{change_data['pct_change']:+.1f}%")
            with comp_col3:
                change_data = metric_changes['ctr']
                st.metric("CTR", f"{change_data['current']:.2%}", 
                         delta=f"{change_data['pct_change']:+.1f}%")
            with comp_col4:
                change_data = metric_changes['conversion_rate']
                st.metric("Conv Rate", f"{change_data['current']:.2%}", 
                         delta=f"{change_data['pct_change']:+.1f}%")
            
            st.markdown("---")
        
        # Top Campaigns
        st.subheader("Top Campaigns")
        camp_metric_options = [
            'Unique Conversions',
            'Selected Revenue (SAR)',
            'Revenue (SAR)',
            'Unique Clicks',
            'Click-Through Revenue (SAR)',
            'Impression-Through Revenue (SAR)',
            'CTR',
            'Conversion Rate',
            'AOV',
            'Revenue Per Click',
            'Engagement Rate'
        ]
        # Only show Selected Revenue if it exists in data
        if 'Selected Revenue (SAR)' not in filtered_df.columns:
            camp_metric_options = [m for m in camp_metric_options if m != 'Selected Revenue (SAR)']
        # Add conversion attribution options if they exist
        if 'Unique Click-Through Conversions' in filtered_df.columns:
            camp_metric_options.insert(1, 'Unique Click-Through Conversions')
        if 'Unique Impression-Through Conversions' in filtered_df.columns:
            camp_metric_options.insert(1, 'Unique Impression-Through Conversions')
        camp_metric = st.selectbox("Metric", camp_metric_options, key='camp_metric', format_func=_attribution_display)
        top_camp = top_campaigns(filtered_df, camp_metric)
        
        # Create display version for table
        top_camp_display = top_camp.copy()
        
        # Store original numeric values for sorting
        original_values = top_camp_display[camp_metric].copy()
        
        # Format the metric column for display
        if 'Revenue' in camp_metric:
            top_camp_display[camp_metric] = top_camp_display[camp_metric].apply(lambda x: format_metric(x, "SAR"))
        elif camp_metric in ['Unique Conversions', 'Unique Clicks', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions']:
            top_camp_display[camp_metric] = top_camp_display[camp_metric].apply(format_metric)
        # For rates, keep as is
        
        # Display table with proper sorting
        st.dataframe(top_camp_display.rename(columns=attribution_rename))

        # Create chart with original numeric values
        fig = px.bar(top_camp, x='Campaign Name', y=camp_metric, title=f"Top Campaigns by {_attribution_display(camp_metric)}",
                     color_discrete_sequence=COLOR_SEQUENCE)
        st.plotly_chart(fig, use_container_width=True)
        
        # Campaign Type Breakdown (Journey vs One-Time)
        if 'Type of Campaign' in filtered_df.columns:
            st.subheader("Performance by Campaign Type")
            type_agg_cols = {'Sent': 'sum', 'Delivered': 'sum', 'Unique Clicks': 'sum', 'Unique Conversions': 'sum'}
            if 'Revenue (SAR)' in filtered_df.columns:
                type_agg_cols['Revenue (SAR)'] = 'sum'
            if 'Click-Through Revenue (SAR)' in filtered_df.columns:
                type_agg_cols['Click-Through Revenue (SAR)'] = 'sum'
            if 'Impression-Through Revenue (SAR)' in filtered_df.columns:
                type_agg_cols['Impression-Through Revenue (SAR)'] = 'sum'
            if 'Selected Revenue (SAR)' in filtered_df.columns:
                type_agg_cols['Selected Revenue (SAR)'] = 'sum'
            type_breakdown = filtered_df.groupby('Type of Campaign').agg(type_agg_cols).reset_index()
            type_breakdown['Conversion Rate'] = np.where(
                type_breakdown['Unique Clicks'] > 0,
                type_breakdown['Unique Conversions'] / type_breakdown['Unique Clicks'], 0
            )

            # Calculate AOV for each revenue type
            if 'Revenue (SAR)' in type_breakdown.columns:
                type_breakdown['AOV (SAR)'] = np.where(
                    type_breakdown['Unique Conversions'] > 0,
                    type_breakdown['Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0
                )
            if 'Click-Through Revenue (SAR)' in type_breakdown.columns:
                type_breakdown['AOV Click-Through (SAR)'] = np.where(
                    type_breakdown['Unique Conversions'] > 0,
                    type_breakdown['Click-Through Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0
                )
            if 'Impression-Through Revenue (SAR)' in type_breakdown.columns:
                type_breakdown['AOV Impression-Through (SAR)'] = np.where(
                    type_breakdown['Unique Conversions'] > 0,
                    type_breakdown['Impression-Through Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0
                )
            if 'Selected Revenue (SAR)' in type_breakdown.columns:
                type_breakdown['AOV Selected (SAR)'] = np.where(
                    type_breakdown['Unique Conversions'] > 0,
                    type_breakdown['Selected Revenue (SAR)'] / type_breakdown['Unique Conversions'], 0
                )

            # Add total row
            total_row = {'Type of Campaign': 'Total'}
            total_conversions = type_breakdown['Unique Conversions'].sum()
            for col in type_breakdown.columns:
                if col == 'Type of Campaign':
                    continue
                elif col == 'Conversion Rate':
                    clicks_total = type_breakdown['Unique Clicks'].sum()
                    total_row[col] = type_breakdown['Unique Conversions'].sum() / clicks_total if clicks_total > 0 else 0
                elif 'AOV' in col:
                    # Calculate total AOV from total revenue / total conversions
                    if 'Click-Through' in col and 'Click-Through Revenue (SAR)' in type_breakdown.columns:
                        total_rev = type_breakdown['Click-Through Revenue (SAR)'].sum()
                    elif 'Impression-Through' in col and 'Impression-Through Revenue (SAR)' in type_breakdown.columns:
                        total_rev = type_breakdown['Impression-Through Revenue (SAR)'].sum()
                    elif 'Selected' in col and 'Selected Revenue (SAR)' in type_breakdown.columns:
                        total_rev = type_breakdown['Selected Revenue (SAR)'].sum()
                    elif 'Revenue (SAR)' in type_breakdown.columns:
                        total_rev = type_breakdown['Revenue (SAR)'].sum()
                    else:
                        total_rev = 0
                    total_row[col] = total_rev / total_conversions if total_conversions > 0 else 0
                else:
                    total_row[col] = type_breakdown[col].sum()
            type_breakdown = pd.concat([type_breakdown, pd.DataFrame([total_row])], ignore_index=True)

            # Display table - drop Selected Revenue/Conversions since all attribution types are shown
            type_display = type_breakdown.copy()
            for drop_col in ['Selected Revenue (SAR)', 'Selected Conversions']:
                if drop_col in type_display.columns:
                    type_display = type_display.drop(columns=[drop_col])
            for col in ['Sent', 'Delivered', 'Unique Clicks', 'Unique Conversions']:
                if col in type_display.columns:
                    type_display[col] = type_display[col].apply(format_metric)
            for col in [c for c in type_display.columns if 'Revenue' in c]:
                type_display[col] = type_display[col].apply(lambda x: format_metric(x, "SAR"))
            for col in [c for c in type_display.columns if 'AOV' in c]:
                type_display[col] = type_display[col].apply(lambda x: format_metric(x, "SAR"))
            type_display['Conversion Rate'] = type_display['Conversion Rate'].apply(lambda x: f"{x:.2%}")
            st.dataframe(style_total_row(type_display), use_container_width=True, hide_index=True)

            # Side-by-side charts (exclude Total row)
            type_chart_data = type_breakdown[type_breakdown['Type of Campaign'] != 'Total']
            type_col1, type_col2 = st.columns(2)
            rev_col_for_type = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in type_chart_data.columns else 'Revenue (SAR)'
            with type_col1:
                if rev_col_for_type in type_chart_data.columns:
                    rev_display_name = get_selected_revenue_display_name(revenue_attribution)
                    fig_type_rev = px.bar(type_chart_data, x='Type of Campaign', y=rev_col_for_type,
                                          title=f"{rev_display_name} by Campaign Type", color='Type of Campaign',
                                          color_discrete_sequence=COLOR_SEQUENCE,
                                          labels={rev_col_for_type: rev_display_name})
                    fig_type_rev.update_layout(showlegend=False)
                    st.plotly_chart(fig_type_rev, use_container_width=True)
            with type_col2:
                conv_display_name = get_selected_conversion_display_name(conversion_attribution)
                fig_type_conv = px.bar(type_chart_data, x='Type of Campaign', y='Unique Conversions',
                                       title=f"{conv_display_name} by Campaign Type", color='Type of Campaign',
                                       color_discrete_sequence=COLOR_SEQUENCE,
                                       labels={'Unique Conversions': conv_display_name})
                fig_type_conv.update_layout(showlegend=False)
                st.plotly_chart(fig_type_conv, use_container_width=True)

        # One-Time Campaigns Overview
        if 'Type of Campaign' in filtered_df.columns:
            onetime_df = filtered_df[filtered_df['Type of Campaign'].str.lower().str.contains('one-time', na=False)].copy()
            
            # Filter out likely test campaigns (low volume) - applied AFTER aggregation
            # to avoid excluding attribution-window rows where Sent=0
            min_sent_threshold = st.slider("Minimum Sent Threshold (exclude tests)", 0, 1000, 100, 
                                         help="Campaigns with fewer sends than this threshold will be excluded as potential tests")
            
            if not onetime_df.empty:
                st.subheader("🚀 One-Time Campaigns Overview")
                
                # Campaign details table
                st.markdown("#### Campaign Details")
                # Respect selected attribution if present
                agg_dict = {
                    'Sent': 'sum',
                    'Delivered': 'sum',
                    'Failed': 'sum',
                    'Unique Clicks': 'sum',
                    'Unique Conversions': 'sum',
                    'Channel': 'first',  # Take first channel if multiple
                    'Day': 'min'  # Launch date
                }
                if 'Selected Revenue (SAR)' in onetime_df.columns:
                    agg_dict['Selected Revenue (SAR)'] = 'sum'
                elif 'Revenue (SAR)' in onetime_df.columns:
                    agg_dict['Revenue (SAR)'] = 'sum'
                
                # Add selected conversions if available
                if 'Selected Conversions' in onetime_df.columns:
                    agg_dict['Selected Conversions'] = 'sum'
                
                # Add all revenue attribution types (summed totals across all dates)
                if 'Impression-Through Revenue (SAR)' in onetime_df.columns:
                    agg_dict['Impression-Through Revenue (SAR)'] = 'sum'
                if 'Click-Through Revenue (SAR)' in onetime_df.columns:
                    agg_dict['Click-Through Revenue (SAR)'] = 'sum'

                onetime_summary = onetime_df.groupby('Campaign Name').agg(agg_dict).reset_index()
                
                # Apply sent threshold AFTER aggregation so attribution-window rows (Sent=0) aren't lost
                onetime_summary = onetime_summary[onetime_summary['Sent'] >= min_sent_threshold]
                
                # Summary metrics (computed after aggregation so they reflect true totals)
                total_onetime_campaigns = len(onetime_summary)
                total_onetime_sent = onetime_summary['Sent'].sum()
                total_onetime_delivered = onetime_summary['Delivered'].sum()
                
                sum_col1, sum_col2, sum_col3, sum_col4 = st.columns(4)
                with sum_col1:
                    st.metric("One-Time Campaigns", format_metric(total_onetime_campaigns), 
                             help=f"Total unique one-time campaigns launched (sent ≥ {min_sent_threshold})")
                with sum_col2:
                    st.metric("Total Sent", format_metric(total_onetime_sent))
                with sum_col3:
                    st.metric("Total Delivered", format_metric(total_onetime_delivered))
                with sum_col4:
                    delivery_rate = total_onetime_delivered / total_onetime_sent if total_onetime_sent > 0 else 0
                    st.metric("Avg Delivery Rate", f"{delivery_rate:.1%}")
                
                # Debug: Show aggregation details
                with st.expander("🔍 Debug: Revenue Aggregation Details", expanded=False):
                    st.write("**Data before aggregation:**")
                    sample_campaign = onetime_df['Campaign Name'].iloc[0] if not onetime_df.empty else None
                    if sample_campaign:
                        sample_data = onetime_df[onetime_df['Campaign Name'] == sample_campaign][['Campaign Name', 'Day', 'Sent', 'Delivered', 'Revenue (SAR)'] + 
                                                                                                   ([col for col in ['Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Selected Revenue (SAR)'] if col in onetime_df.columns])]
                        st.write(f"Sample campaign: **{sample_campaign}**")
                        st.dataframe(sample_data, use_container_width=True)
                        
                        st.write("**After aggregation:**")
                        sample_agg = onetime_summary[onetime_summary['Campaign Name'] == sample_campaign]
                        st.dataframe(sample_agg, use_container_width=True)
                        
                        st.write(f"**Number of days in raw data:** {len(sample_data)}")
                        st.write(f"**Total campaigns in dataset:** {onetime_df['Campaign Name'].nunique()}")
                        st.write(f"**Total rows before aggregation:** {len(onetime_df)}")
                        st.write(f"**Total rows after aggregation:** {len(onetime_summary)}")
                
                # Add calculated columns
                onetime_summary['Delivery Rate'] = onetime_summary['Delivered'] / onetime_summary['Sent']
                onetime_summary['CTR'] = np.where(onetime_summary['Delivered'] > 0, 
                                                onetime_summary['Unique Clicks'] / onetime_summary['Delivered'], 0)
                
                # Use Selected Conversions for conversion rate if available
                conv_col_for_rate = 'Selected Conversions' if 'Selected Conversions' in onetime_summary.columns else 'Unique Conversions'
                onetime_summary['Conversion Rate'] = np.where(onetime_summary['Unique Clicks'] > 0,
                                                            onetime_summary[conv_col_for_rate] / onetime_summary['Unique Clicks'], 0)
                
                # Sort by sent volume descending
                onetime_summary = onetime_summary.sort_values('Sent', ascending=False)
                
                # Format for display
                # Use selected revenue column if available
                revenue_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in onetime_summary.columns else 'Revenue (SAR)'
                conv_col_display = 'Selected Conversions' if 'Selected Conversions' in onetime_summary.columns else 'Unique Conversions'
                
                # Build display columns dynamically to include all revenue types (but avoid duplicates)
                display_cols = ['Campaign Name', 'Channel', 'Sent', 'Delivered', 'Delivery Rate', 
                              'Unique Clicks', 'CTR', conv_col_display, 'Conversion Rate', revenue_col]
                
                # Add attribution revenue columns ONLY if they won't conflict after rename
                # revenue_col is 'Selected Revenue (SAR)' which will be renamed to selected_rev_label
                # So we need to check if selected_rev_label != the column we're trying to add
                if 'Impression-Through Revenue (SAR)' in onetime_summary.columns and selected_rev_label != 'Impression-Through Revenue (SAR)':
                    display_cols.append('Impression-Through Revenue (SAR)')
                if 'Click-Through Revenue (SAR)' in onetime_summary.columns and selected_rev_label != 'Click-Through Revenue (SAR)':
                    display_cols.append('Click-Through Revenue (SAR)')
                
                # Remove any duplicates while preserving order
                display_cols = list(dict.fromkeys(display_cols))
                onetime_display = onetime_summary[display_cols].copy()
                
                # Format columns (convert to strings for display with K/M abbreviations)
                onetime_display['Sent'] = onetime_display['Sent'].apply(format_metric)
                onetime_display['Delivered'] = onetime_display['Delivered'].apply(format_metric)
                onetime_display['Unique Clicks'] = onetime_display['Unique Clicks'].apply(format_metric)
                onetime_display[conv_col_display] = onetime_display[conv_col_display].apply(format_metric)
                onetime_display[revenue_col] = onetime_display[revenue_col].apply(lambda x: format_metric(x, "SAR"))
                
                # Format attribution revenue columns if they exist
                if 'Impression-Through Revenue (SAR)' in onetime_display.columns:
                    onetime_display['Impression-Through Revenue (SAR)'] = onetime_display['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                if 'Click-Through Revenue (SAR)' in onetime_display.columns:
                    onetime_display['Click-Through Revenue (SAR)'] = onetime_display['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                
                onetime_display['Delivery Rate'] = onetime_display['Delivery Rate'].apply(lambda x: f"{x:.1%}")
                onetime_display['CTR'] = onetime_display['CTR'].apply(lambda x: f"{x:.2%}")
                onetime_display['Conversion Rate'] = onetime_display['Conversion Rate'].apply(lambda x: f"{x:.2%}")
                
                # Rename columns to show actual attribution model
                onetime_display = onetime_display.rename(columns=attribution_rename)
                st.dataframe(onetime_display, use_container_width=True, hide_index=True)
                
                # Optional: Channel breakdown for one-time campaigns
                if st.checkbox("Show Channel Breakdown for One-Time Campaigns", key='onetime_channel_breakdown'):
                    st.markdown("#### Channel Performance")
                    # Respect selected revenue attribution
                    agg_cols = {
                        'Sent': 'sum',
                        'Delivered': 'sum',
                        'Unique Conversions': 'sum'
                    }
                    if 'Selected Revenue (SAR)' in onetime_df.columns:
                        agg_cols['Selected Revenue (SAR)'] = 'sum'
                        rev_col_channel = 'Selected Revenue (SAR)'
                    else:
                        agg_cols['Revenue (SAR)'] = 'sum'
                        rev_col_channel = 'Revenue (SAR)'

                    channel_breakdown = onetime_df.groupby('Channel').agg(agg_cols).reset_index()
                    
                    channel_breakdown['Delivery Rate'] = channel_breakdown['Delivered'] / channel_breakdown['Sent']
                    channel_breakdown['Conversions'] = channel_breakdown['Unique Conversions']
                    
                    # Format
                    channel_display = channel_breakdown.copy()
                    channel_display['Sent'] = channel_display['Sent'].apply(format_metric)
                    channel_display['Delivered'] = channel_display['Delivered'].apply(format_metric)
                    channel_display['Conversions'] = channel_display['Conversions'].apply(format_metric)
                    channel_display[rev_col_channel] = channel_display[rev_col_channel].apply(lambda x: format_metric(x, "SAR"))
                    channel_display['Delivery Rate'] = channel_display['Delivery Rate'].apply(lambda x: f"{x:.1%}")
                    
                    # Rename columns to show actual attribution model
                    channel_display = channel_display.rename(columns=attribution_rename)
                    st.dataframe(channel_display[['Channel', 'Sent', 'Delivered', 'Delivery Rate', 'Conversions', rev_col_channel]], 
                               use_container_width=True, hide_index=True)
            else:
                st.info("No one-time campaigns found matching the criteria.")
            
            # Monthly breakdown of unique one-time campaigns
            if not onetime_df.empty:
                st.markdown("#### 📅 Monthly One-Time Campaign Activity")
                
                # Extract month from date column
                if 'Day' in onetime_df.columns:
                    onetime_df['Month'] = onetime_df['Day'].dt.to_period('M').dt.strftime('%Y-%m')
                elif 'Reporting Period Start Date' in onetime_df.columns:
                    onetime_df['Month'] = onetime_df['Reporting Period Start Date'].dt.to_period('M').dt.strftime('%Y-%m')
                else:
                    st.info("No date column available for monthly breakdown.")
                
                if 'Month' in onetime_df.columns:
                    # Group by month and count unique campaigns
                    # Use selected revenue if present
                    monthly_agg = {
                        'Campaign Name': 'nunique',  # Count unique campaigns
                        'Sent': 'sum',
                        'Delivered': 'sum',
                        'Unique Conversions': 'sum'
                    }
                    if 'Selected Revenue (SAR)' in onetime_df.columns:
                        monthly_agg['Selected Revenue (SAR)'] = 'sum'
                        rev_col_month = 'Selected Revenue (SAR)'
                    else:
                        monthly_agg['Revenue (SAR)'] = 'sum'
                        rev_col_month = 'Revenue (SAR)'

                    monthly_campaigns = onetime_df.groupby('Month').agg(monthly_agg).reset_index()
                    
                    monthly_campaigns = monthly_campaigns.rename(columns={'Campaign Name': 'Unique Campaigns'})
                    monthly_campaigns = monthly_campaigns.sort_values('Month', ascending=False)
                    
                    # Format for display
                    monthly_display = monthly_campaigns.copy()
                    monthly_display['Sent'] = monthly_display['Sent'].apply(format_metric)
                    monthly_display['Delivered'] = monthly_display['Delivered'].apply(format_metric)
                    monthly_display['Unique Conversions'] = monthly_display['Unique Conversions'].apply(format_metric)
                    monthly_display[rev_col_month] = monthly_display[rev_col_month].apply(lambda x: format_metric(x, "SAR"))
                    
                    # Rename columns to show actual attribution model
                    monthly_display = monthly_display.rename(columns=attribution_rename)
                    st.dataframe(monthly_display, use_container_width=True, hide_index=True)
                    
                    # Optional chart
                    if st.checkbox("Show Monthly Trend Chart", key='monthly_onetime_chart'):
                        fig_monthly = px.bar(monthly_campaigns, x='Month', y='Unique Campaigns',
                                           title="Unique One-Time Campaigns per Month",
                                           color_discrete_sequence=[COLORS['primary']])
                        fig_monthly.update_layout(xaxis_title="Month", yaxis_title="Number of Campaigns")
                        st.plotly_chart(fig_monthly, use_container_width=True)

        # Campaign Drill-Down
        st.subheader("Campaign Drill-Down")
        selected_campaigns = st.multiselect("Select Campaigns for Details", filtered_df['Campaign Name'].unique(), key='drill_camp')
        if selected_campaigns:
            camp_details = filtered_df[filtered_df['Campaign Name'].isin(selected_campaigns)]
            
            # Summary KPIs - Row 1: Volume Metrics
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Total Sent", format_metric(camp_details['Sent'].sum()))
            with col2:
                st.metric("Total Delivered", format_metric(camp_details['Delivered'].sum()))
            with col3:
                st.metric("Total Clicks", format_metric(camp_details['Unique Clicks'].sum()))
            with col4:
                conv_total = camp_details['Selected Conversions'].sum() if 'Selected Conversions' in camp_details.columns else camp_details['Unique Conversions'].sum()
                st.metric(selected_conv_label, format_metric(conv_total))
            with col5:
                rev_total = camp_details['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in camp_details.columns else camp_details['Revenue (SAR)'].sum()
                st.metric(selected_rev_label, format_metric(rev_total, "SAR"))
            with col6:
                st.metric("Click-Through Revenue", format_metric(camp_details['Click-Through Revenue (SAR)'].sum(), "SAR"))
            
            # Row 2: Business Metrics
            st.markdown("#### 💰 Business Intelligence")
            biz_col1, biz_col2, biz_col3, biz_col4 = st.columns(4)
            
            total_revenue = camp_details['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in camp_details.columns else camp_details['Revenue (SAR)'].sum()
            total_conversions = camp_details['Selected Conversions'].sum() if 'Selected Conversions' in camp_details.columns else camp_details['Unique Conversions'].sum()
            total_clicks = camp_details['Unique Clicks'].sum()
            
            with biz_col1:
                aov = (total_revenue / total_conversions) if total_conversions > 0 else 0
                st.metric("Average Order Value", format_metric(aov, "SAR"), help="Revenue per conversion")
            with biz_col2:
                rpc = (total_revenue / total_clicks) if total_clicks > 0 else 0
                st.metric("Revenue Per Click", format_metric(rpc, "SAR"), help="Revenue generated per click")
            with biz_col3:
                avg_ctr = camp_details['CTR'].mean()
                st.metric("Avg CTR", f"{avg_ctr:.2%}", help="Average click-through rate")
            with biz_col4:
                # Calculate conversion rate from raw data
                total_clicks_metric = camp_details['Unique Clicks'].sum()
                conv_col_metric = 'Selected Conversions' if 'Selected Conversions' in camp_details.columns else 'Unique Conversions'
                total_conversions_metric = camp_details[conv_col_metric].sum()
                avg_conv_rate = (total_conversions_metric / total_clicks_metric) if total_clicks_metric > 0 else 0
                st.metric("Avg Conversion Rate", f"{avg_conv_rate:.2%}", help="Average conversion rate")
            
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
            # Add total row
            total_row = {'Channel': 'Total'}
            for col in chan_perf.columns:
                if col != 'Channel':
                    total_row[col] = chan_perf[col].sum()
            chan_perf_with_total = pd.concat([chan_perf, pd.DataFrame([total_row])], ignore_index=True)
            # Format columns for display
            chan_perf_display = chan_perf_with_total.copy()
            chan_perf_display['Sent'] = chan_perf_display['Sent'].apply(format_metric)
            chan_perf_display['Delivered'] = chan_perf_display['Delivered'].apply(format_metric)
            chan_perf_display['Unique Conversions'] = chan_perf_display['Unique Conversions'].apply(format_metric)
            chan_perf_display['Revenue (SAR)'] = chan_perf_display['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            chan_perf_display['Impression-Through Revenue (SAR)'] = chan_perf_display['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            chan_perf_display['Click-Through Revenue (SAR)'] = chan_perf_display['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            st.dataframe(style_total_row(chan_perf_display), use_container_width=True, hide_index=True)
            conv_display_name = get_selected_conversion_display_name(conversion_attribution)
            fig_chan = px.bar(chan_perf, x='Channel', y='Unique Conversions', 
                              title=f"{conv_display_name} by Channel for Selected Campaigns",
                              color='Channel', color_discrete_map=CHANNEL_COLORS,
                              labels={'Unique Conversions': conv_display_name})
            fig_chan.update_layout(showlegend=False)
            st.plotly_chart(fig_chan, use_container_width=True)
            
            # Time Series for Selected Campaigns
            st.subheader("Time Series Performance")
            ts_camp = camp_details.groupby(['Reporting Period Start Date', 'Campaign Name'])[camp_metric].sum().reset_index()
            if not ts_camp.empty:
                fig_ts_camp = px.line(ts_camp, x='Reporting Period Start Date', y=camp_metric, color='Campaign Name',
                                      title=f"{camp_metric} Over Time for Selected Campaigns",
                                      color_discrete_sequence=COLOR_SEQUENCE)
                fig_ts_camp.update_traces(line_width=2.5)
                st.plotly_chart(fig_ts_camp, use_container_width=True)
            
            # Conversion Attribution
            st.subheader("Conversion Attribution")
            attr_camp = {
                'Impression-Through': camp_details['Unique Impression-Through Conversions'].sum(),
                'Click-Through': camp_details['Unique Click-Through Conversions'].sum(),
                'Direct/Open-Through': camp_details['Unique Conversions'].sum() - camp_details['Unique Impression-Through Conversions'].sum() - camp_details['Unique Click-Through Conversions'].sum()
            }
            attr_df_camp = pd.DataFrame(list(attr_camp.items()), columns=['Source', 'Conversions'])
            attr_df_camp['Conversions'] = attr_df_camp['Conversions'].apply(format_metric)
            fig_attr_camp = px.pie(attr_df_camp, names='Source', values='Conversions', title="Attribution for Selected Campaigns",
                                    color_discrete_sequence=COLOR_SEQUENCE)
            st.plotly_chart(fig_attr_camp, use_container_width=True)
            
            # Failed Reasons for Selected Campaigns
            st.subheader("Failed Reasons")
            failed_cols = [col for col in camp_details.columns if 'Failed' in col and col != 'Failed']
            if failed_cols:
                failed_camp = camp_details[failed_cols].sum().reset_index().rename(columns={'index': 'Reason', 0: 'Count'})
                failed_camp['Count'] = failed_camp['Count'].apply(format_metric)
                fig_fail_camp = px.bar(failed_camp, x='Reason', y='Count', title="Failed Reasons for Selected Campaigns",
                                       color_discrete_sequence=[COLORS['danger']])
                st.plotly_chart(fig_fail_camp, use_container_width=True)

        # Campaign Health Score Analysis
        st.subheader("🏥 Campaign Health Dashboard")
        
        # Professional Methodology Explanation for Executives
        with st.expander("📊 Scoring Methodology (Click to View)", expanded=False):
            st.markdown("""
            ### **Health Score Methodology**

            **Method**: Percentile ranking with Empirical Bayes smoothing

            #### **How Scores are Calculated:**
            - **Relative Ranking**: Each campaign is scored against all other campaigns in your portfolio (0-100 scale)
            - **Empirical Bayes Smoothing**: Low-volume campaigns are adjusted toward the portfolio average to avoid misleading scores from small samples
            - **No Fixed Benchmarks**: Scores reflect your actual portfolio distribution, not arbitrary industry numbers

            #### **Component Weights:**
            - 🚀 **Conversion Performance**: 30% - Conversion rate (clicks to conversions)
            - 🎯 **Engagement Performance**: 25% - Click-through rate (impressions to clicks)
            - 💰 **Revenue Efficiency**: 25% - Revenue per conversion (log-scaled to reduce outlier impact)
            - 📧 **Delivery Performance**: 20% - Delivery rate (sent to delivered)

            #### **Performance Tiers:**
            - **Excellent (80-100)**: Top quartile - scale and replicate
            - **Good (60-79)**: Above average - minor optimizations
            - **Fair (40-59)**: Below average - review and improve
            - **Poor (0-39)**: Bottom quartile - immediate action needed

            #### **Data Sufficiency:**
            Campaigns with fewer than 10 sends, 3 conversions, or 3 days of data are marked "Insufficient Data" to avoid misleading scores.
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
                                         title="Distribution of Campaign Health Scores",
                                         color_discrete_sequence=[COLORS['primary']])
            fig_health_dist.add_vline(x=health_df['Health Score'].mean(),
                                    line_dash="dash", line_color=COLORS['danger'],
                                    annotation_text=f"Average: {health_df['Health Score'].mean():.1f}")
            st.plotly_chart(fig_health_dist, use_container_width=True)
            
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
                    line=dict(color=COLORS['success'], width=2, dash='dash'),
                    showlegend=True
                ))
                
                fig_radar.add_trace(go.Scatterpolar(
                    r=good_line,
                    theta=categories,
                    mode='lines',
                    name='Good (60+)',
                    line=dict(color=COLORS['warning'], width=2, dash='dot'),
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
                radar_img = export_chart_image(fig_radar, 'campaign_radar')
                if radar_img:
                    st.download_button("Download Radar Chart", radar_img, "campaign_radar.png", "image/png", key='dl_camp_radar')

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
                total_conversions = breakdown_data['Selected Conversions'].sum() if 'Selected Conversions' in breakdown_data.columns else breakdown_data['Unique Conversions'].sum()
                st.metric(selected_conv_label, format_metric(total_conversions))
                
                conversion_rate = (total_conversions / total_clicks * 100) if total_clicks > 0 else 0
                st.metric("📈 Conversion Rate", f"{conversion_rate:.2f}%")
            
            with col4:
                total_revenue = breakdown_data['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in breakdown_data.columns else breakdown_data['Revenue (SAR)'].sum()
                st.metric(selected_rev_label, format_metric(total_revenue, "SAR"))
                
                rpc = (total_revenue / total_conversions) if total_conversions > 0 else 0
                st.metric("💰 Revenue/Conversion", format_metric(rpc, "SAR"))
            
            # Performance vs Portfolio Analysis
            st.subheader("📊 Performance vs Portfolio")
            
            # Calculate portfolio averages
            portfolio_delivery_rate = (filtered_df['Delivered'].sum() / filtered_df['Sent'].sum() * 100) if filtered_df['Sent'].sum() > 0 else 0
            portfolio_ctr = (filtered_df['Unique Clicks'].sum() / filtered_df['Unique Impressions'].sum() * 100) if filtered_df['Unique Impressions'].sum() > 0 else 0
            portfolio_conversion_rate = (filtered_df['Selected Conversions'].sum() / filtered_df['Unique Clicks'].sum() * 100) if filtered_df['Unique Clicks'].sum() > 0 else 0
            portfolio_rpc = (filtered_df['Selected Revenue (SAR)'].sum() / filtered_df['Selected Conversions'].sum()) if filtered_df['Selected Conversions'].sum() > 0 else 0
            
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
        
        # Show comparison summary if enabled
        if comparison_result:
            st.info(f"📊 Period Comparison Active: {comparison_result['current_label']} vs {comparison_result['comparison_label']}")
            
            # Calculate journey metrics for both periods
            current_metrics = calculate_period_metrics(comparison_result['current_data'], comparison_result['current_days'], conversion_attribution)
            comp_metrics = calculate_period_metrics(comparison_result['comparison_data'], comparison_result['comparison_days'], conversion_attribution)
            metric_changes = calculate_metric_changes(current_metrics, comp_metrics)
            
            # Show quick comparison
            comp_col1, comp_col2, comp_col3, comp_col4 = st.columns(4)
            with comp_col1:
                change_data = metric_changes['selected_revenue']
                st.metric("Revenue", format_metric(change_data['current'], "SAR"), 
                         delta=f"{change_data['pct_change']:+.1f}%")
            with comp_col2:
                change_data = metric_changes['selected_conversions']
                st.metric("Conversions", format_metric(change_data['current']), 
                         delta=f"{change_data['pct_change']:+.1f}%")
            with comp_col3:
                change_data = metric_changes['ctr']
                st.metric("CTR", f"{change_data['current']:.2%}", 
                         delta=f"{change_data['pct_change']:+.1f}%")
            with comp_col4:
                change_data = metric_changes['conversion_rate']
                st.metric("Conv Rate", f"{change_data['current']:.2%}", 
                         delta=f"{change_data['pct_change']:+.1f}%")
            
            st.markdown("---")
        
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
            ### **Health Score Methodology**

            **Method**: Percentile ranking with Empirical Bayes smoothing

            #### **How Scores are Calculated:**
            - **Relative Ranking**: Each journey is scored against all other journeys in your portfolio (0-100 scale)
            - **Empirical Bayes Smoothing**: Low-volume journeys are adjusted toward the portfolio average to avoid misleading scores from small samples
            - **No Fixed Benchmarks**: Scores reflect your actual portfolio distribution, not arbitrary industry numbers

            #### **Component Weights:**
            - 🚀 **Conversion Performance**: 30% - Conversion rate (clicks to conversions)
            - 🎯 **Engagement Performance**: 25% - Click-through rate (impressions to clicks)
            - 💰 **Revenue Efficiency**: 25% - Revenue per conversion (log-scaled to reduce outlier impact)
            - 📧 **Delivery Performance**: 20% - Delivery rate (sent to delivered)

            #### **Performance Tiers:**
            - **Excellent (80-100)**: Top quartile - scale these journeys
            - **Good (60-79)**: Above average - minor optimizations needed
            - **Fair (40-59)**: Below average - moderate improvements required
            - **Poor (0-39)**: Bottom quartile - immediate action required

            #### **Data Sufficiency:**
            Journeys with fewer than 10 sends, 3 conversions, or 3 days of data are marked "Insufficient Data" to prevent unreliable scores.
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
                                         title="Distribution of Journey Health Scores",
                                         color_discrete_sequence=[COLORS['primary']])
            fig_health_dist.add_vline(x=health_df['Health Score'].mean(),
                                    line_dash="dash", line_color=COLORS['danger'],
                                    annotation_text=f"Average: {health_df['Health Score'].mean():.1f}")
            st.plotly_chart(fig_health_dist, use_container_width=True)
            
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
                    line=dict(color=COLORS['success'], width=2, dash='dash'),
                    showlegend=True
                ))
                
                fig_radar.add_trace(go.Scatterpolar(
                    r=good_line,
                    theta=categories,
                    mode='lines',
                    name='Good (60+)',
                    line=dict(color=COLORS['warning'], width=2, dash='dot'),
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
                radar_img = export_chart_image(fig_radar, 'journey_radar')
                if radar_img:
                    st.download_button("Download Radar Chart", radar_img, "journey_radar.png", "image/png", key='dl_jour_radar')

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
                                st.metric("CTR (Click Rate)", f"{engagement_data['ctr']:.2%}",
                                         help="Impressions → Clicks: How many people who saw it clicked it")
                        
                        if 'conversion' in individual_analysis['raw_metrics']:
                            conversion_data = individual_analysis['raw_metrics']['conversion']
                            journey_data = individual_analysis.get('journey_data', filtered_df[filtered_df['Journey Name'] == selected_journey_health])
                            
                            st.markdown("**💰 Conversion Performance:**")
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Clicks", format_metric(conversion_data['total_clicks']))
                            with col2:
                                st.metric("Conversions", format_metric(conversion_data['total_conversions']))
                            with col3:
                                st.metric("Conversion Rate (CVR)", f"{conversion_data['conversion_rate']:.2%}", 
                                         help="Clicks → Conversions: How many people who clicked actually converted")
                            with col4:
                                if 'source' in conversion_data:
                                    st.caption(f"Source: {conversion_data['source']}")
                            
                            # Additional attribution rates
                            st.markdown("**📊 Additional Attribution Metrics:**")
                            attr_col1, attr_col2, attr_col3 = st.columns(3)
                            
                            with attr_col1:
                                # Impression-Through Rate
                                if 'Unique Impression-Through Conversions' in journey_data.columns and 'Unique Impressions' in journey_data.columns:
                                    imp_conv = journey_data['Unique Impression-Through Conversions'].sum()
                                    imp_total = journey_data['Unique Impressions'].sum()
                                    imp_rate = (imp_conv / imp_total * 100) if imp_total > 0 else 0
                                    st.metric("Impression-Through Rate", f"{imp_rate:.2%}",
                                             help="Impressions → Conversions: People who converted after seeing (no click)")
                            
                            with attr_col2:
                                # Click-Through Rate (already shown above, but for completeness)
                                if 'Unique Click-Through Conversions' in journey_data.columns and 'Unique Clicks' in journey_data.columns:
                                    click_conv = journey_data['Unique Click-Through Conversions'].sum()
                                    click_total = journey_data['Unique Clicks'].sum()
                                    click_rate = (click_conv / click_total * 100) if click_total > 0 else 0
                                    st.metric("Click-Through Rate", f"{click_rate:.2%}",
                                             help="Clicks → Conversions: People who converted after clicking (same as CVR above)")
                            
                            with attr_col3:
                                # Overall Rate (Sent)
                                if 'Sent' in journey_data.columns:
                                    sent_total = journey_data['Sent'].sum()
                                    overall_rate = (conversion_data['total_conversions'] / sent_total * 100) if sent_total > 0 else 0
                                    st.metric("Overall Rate (Sent)", f"{overall_rate:.2%}",
                                             help="Sent → Conversions: End-to-end conversion rate from send to conversion")
                        
                        if 'revenue' in individual_analysis['raw_metrics']:
                            revenue_data = individual_analysis['raw_metrics']['revenue']
                            st.markdown("**💵 Revenue Performance:**")
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric(selected_rev_label, format_metric(revenue_data['total_revenue'], "SAR"))
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
                # Proper waterfall chart showing attribution flow
                wf_data = waterfall_result['waterfall_data']
                wf_labels = [d['step'] for d in wf_data if d['step'] != 'Starting Point']
                wf_values = []
                wf_measures = []
                for d in wf_data:
                    if d['step'] == 'Starting Point':
                        continue
                    if d['step'] == 'Total Revenue':
                        wf_measures.append('total')
                        wf_values.append(d['cumulative'])
                    else:
                        wf_measures.append('relative')
                        wf_values.append(d['value'])

                fig_waterfall = go.Figure(go.Waterfall(
                    x=wf_labels,
                    y=wf_values,
                    measure=wf_measures,
                    text=[format_metric(v, "SAR") for v in wf_values],
                    textposition='outside',
                    connector=dict(line=dict(color='#E5E7EB', width=1)),
                    increasing=dict(marker=dict(color=COLORS['primary'])),
                    decreasing=dict(marker=dict(color=COLORS['danger'])),
                    totals=dict(marker=dict(color=COLORS['success'])),
                ))
                fig_waterfall.update_layout(
                    title=f"Revenue Attribution Breakdown: {waterfall_journey}",
                    yaxis_title="Revenue (SAR)",
                    showlegend=False,
                )
                st.plotly_chart(fig_waterfall, use_container_width=True)
                
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
            
            if lifecycle_data and not isinstance(lifecycle_data, dict) and len(lifecycle_data) > 0:
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
            else:
                st.info("No journey lifecycle data available. Journeys need at least 2 data points over time for lifecycle analysis.")
        
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
                                go.Bar(name='Period 1', x=['Daily Average Revenue'], y=[rev_data['period1_daily_avg']], marker_color=COLORS['info']),
                                go.Bar(name='Period 2', x=['Daily Average Revenue'], y=[rev_data['period2_daily_avg']], marker_color=COLORS['primary'])
                            ])
                            fig_rev.update_layout(title="Revenue Comparison", yaxis_title="Revenue (SAR)")
                            st.plotly_chart(fig_rev, use_container_width=True)
                    
                    with chart_col2:
                        # Conversion comparison
                        if 'Unique Conversions' in comparison_result['metrics']:
                            conv_data = comparison_result['metrics']['Unique Conversions']
                            fig_conv = go.Figure(data=[
                                go.Bar(name='Period 1', x=['Daily Average Conversions'], y=[conv_data['period1_daily_avg']], marker_color=COLORS['info']),
                                go.Bar(name='Period 2', x=['Daily Average Conversions'], y=[conv_data['period2_daily_avg']], marker_color=COLORS['success'])
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
        jour_metric_options = ['Delivered Rate', 'Unique Clicks', 'Unique Conversions', 'Selected Revenue (SAR)', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
        if 'Selected Revenue (SAR)' not in filtered_df.columns:
            jour_metric_options = [m for m in jour_metric_options if m != 'Selected Revenue (SAR)']
        # Add conversion attribution options if they exist
        if 'Unique Click-Through Conversions' in filtered_df.columns:
            jour_metric_options.insert(3, 'Unique Click-Through Conversions')
        if 'Unique Impression-Through Conversions' in filtered_df.columns:
            jour_metric_options.insert(3, 'Unique Impression-Through Conversions')
        jour_metric = st.selectbox("Metric", jour_metric_options, key='jour_metric', format_func=_attribution_display)
        top_jour = get_top_journeys(filtered_df, jour_metric)
        
        # Create display version for table
        top_jour_display = top_jour.copy()
        
        # Store original numeric values for sorting
        original_values = top_jour_display[jour_metric].copy()
        
        # Format the metric column for display
        if 'Revenue' in jour_metric:
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(lambda x: format_metric(x, "SAR"))
        elif jour_metric in ['Unique Clicks', 'Unique Conversions', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions']:
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(format_metric)
        elif 'Rate' in jour_metric:
            # For rates, convert to percentage
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(lambda x: f"{x*100:.1f}%")
        
        # Display table with proper sorting
        st.dataframe(top_jour_display.rename(columns=attribution_rename))

        # Create chart with original numeric values
        fig2 = px.bar(top_jour, x='Journey Name', y=jour_metric, title=f"Top Journeys by {_attribution_display(jour_metric)}",
                      color_discrete_sequence=COLOR_SEQUENCE)
        st.plotly_chart(fig2, use_container_width=True)
        
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
                st.metric(selected_conv_label, format_metric(jour_details['Unique Conversions'].sum()))
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
            # Add total row
            total_row_jour = {'Channel': 'Total'}
            for col in chan_perf_jour.columns:
                if col != 'Channel':
                    total_row_jour[col] = chan_perf_jour[col].sum()
            chan_perf_jour_with_total = pd.concat([chan_perf_jour, pd.DataFrame([total_row_jour])], ignore_index=True)
            # Format columns for display
            chan_perf_jour_display = chan_perf_jour_with_total.copy()
            chan_perf_jour_display['Sent'] = chan_perf_jour_display['Sent'].apply(format_metric)
            chan_perf_jour_display['Delivered'] = chan_perf_jour_display['Delivered'].apply(format_metric)
            chan_perf_jour_display['Unique Conversions'] = chan_perf_jour_display['Unique Conversions'].apply(format_metric)
            chan_perf_jour_display['Revenue (SAR)'] = chan_perf_jour_display['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            chan_perf_jour_display['Impression-Through Revenue (SAR)'] = chan_perf_jour_display['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            chan_perf_jour_display['Click-Through Revenue (SAR)'] = chan_perf_jour_display['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))

            # Display table with formatted values
            st.dataframe(style_total_row(chan_perf_jour_display), use_container_width=True, hide_index=True)
            
            # Chart data - chan_perf_jour is already numeric, no parsing needed
            conv_display_name = get_selected_conversion_display_name(conversion_attribution)
            fig_chan_jour = px.bar(chan_perf_jour, x='Channel', y='Unique Conversions',
                                   title=f"{conv_display_name} by Channel for Selected Journeys",
                                   color='Channel', color_discrete_map=CHANNEL_COLORS,
                                   labels={'Unique Conversions': conv_display_name})
            fig_chan_jour.update_layout(showlegend=False)
            st.plotly_chart(fig_chan_jour, use_container_width=True)
            
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
                    fig_ts_jour = px.line(ts_jour, x='Reporting Period Start Date', y=jour_metric, color='Journey Name',
                                           title=f"{jour_metric} Over Time for Selected Journeys",
                                           color_discrete_sequence=COLOR_SEQUENCE)
                    fig_ts_jour.update_yaxes(tickformat=".1f", title=f"{jour_metric} (%)")
                else:
                    fig_ts_jour = px.line(ts_jour, x='Reporting Period Start Date', y=jour_metric, color='Journey Name',
                                           title=f"{jour_metric} Over Time for Selected Journeys",
                                           color_discrete_sequence=COLOR_SEQUENCE)
                fig_ts_jour.update_traces(line_width=2.5)
                st.plotly_chart(fig_ts_jour, use_container_width=True)
                
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
            fig_attr_jour = px.pie(attr_df_jour, names='Source', values='Conversions', title="Attribution for Selected Journeys",
                                    color_discrete_sequence=COLOR_SEQUENCE)
            st.plotly_chart(fig_attr_jour, use_container_width=True)
            
            # Failed Reasons for Selected Journeys
            st.subheader("Failed Reasons")
            failed_cols = [col for col in jour_details.columns if 'Failed' in col and col != 'Failed']
            if failed_cols:
                failed_jour = jour_details[failed_cols].sum().reset_index().rename(columns={'index': 'Reason', 0: 'Count'})
                failed_jour['Count'] = failed_jour['Count'].apply(format_metric)
                fig_fail_jour = px.bar(failed_jour, x='Reason', y='Count', title="Failed Reasons for Selected Journeys",
                                       color_discrete_sequence=[COLORS['danger']])
                st.plotly_chart(fig_fail_jour, use_container_width=True)

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
                        
                        # Check for journeys that were never active
                        never_active_count = 0
                        for journey in stopped_journeys:
                            for period in journey['stopped_periods']['periods']:
                                if not period.get('was_active_before', True):
                                    never_active_count += 1
                                    break  # Count journey only once
                        
                        if never_active_count > 0:
                            st.warning(f"⚠️ **Note:** {never_active_count} journey(s) had zero delivery periods but were never active before. These might be journeys that haven't launched yet rather than journeys that stopped.")

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
                                    
                                    # Show model quality indicator
                                    model_quality = loss_data.get('model_quality', 'medium')
                                    if model_quality == 'high':
                                        quality_icon = "✅"
                                        quality_label = "High Reliability"
                                        quality_color = "green"
                                    elif model_quality == 'medium':
                                        quality_icon = "⚠️"
                                        quality_label = "Moderate Reliability"
                                        quality_color = "orange"
                                    else:
                                        quality_icon = "ℹ️"
                                        quality_label = "Directional Estimate"
                                        quality_color = "gray"
                                    
                                    st.markdown(f"<div style='padding: 10px; border-left: 4px solid {quality_color};'>"
                                              f"{quality_icon} <b>{quality_label}</b></div>", 
                                              unsafe_allow_html=True)

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
                                            line=dict(color=COLORS['danger'], width=4),
                                            marker=dict(size=8, color=COLORS['danger']),
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
                                    
                                    # Calculate expected days from dates for verification
                                    periods_display['calculated_days'] = (
                                        (periods_display['end_date'] - periods_display['start_date']).dt.days + 1
                                    )
                                    
                                    # Format dates
                                    periods_display['start_date'] = periods_display['start_date'].dt.strftime('%Y-%m-%d')
                                    periods_display['end_date'] = periods_display['end_date'].dt.strftime('%Y-%m-%d')
                                    
                                    # Add verification indicator
                                    periods_display['days_match'] = periods_display.apply(
                                        lambda row: '✓' if row['days_stopped'] == row['calculated_days'] else f'⚠️ Mismatch!',
                                        axis=1
                                    )
                                    
                                    periods_display['days_stopped'] = periods_display['days_stopped'].apply(format_metric)
                                    periods_display['calculated_days'] = periods_display['calculated_days'].apply(format_metric)
                                    
                                    # Add activity information
                                    if 'was_active_before' in periods_display.columns:
                                        periods_display['Status'] = periods_display.apply(
                                            lambda row: f"✅ Was Active ({format_metric(row['active_days_before_stop'])} days, avg: {format_metric(row['avg_delivery_before_stop'])} delivered)" 
                                            if row.get('was_active_before', False) 
                                            else "⚠️ Never Active", 
                                            axis=1
                                        )
                                        display_cols = ['start_date', 'end_date', 'days_stopped', 'calculated_days', 'days_match', 'Status']
                                    else:
                                        display_cols = ['start_date', 'end_date', 'days_stopped', 'calculated_days', 'days_match']
                                    
                                    # Add estimated_daily_loss if available
                                    if 'estimated_daily_loss' in periods_display.columns:
                                        periods_display['estimated_daily_loss'] = periods_display['estimated_daily_loss'].apply(lambda x: format_metric(x, "SAR"))
                                        display_cols.append('estimated_daily_loss')
                                    else:
                                        # Add placeholder if missing
                                        periods_display['estimated_daily_loss'] = 'N/A'
                                        display_cols.append('estimated_daily_loss')
                                    
                                    st.dataframe(periods_display[display_cols], use_container_width=True)

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
        if 'Selected Revenue (SAR)' in filtered_df.columns:
            safe_revenue_cols.insert(0, 'Selected Revenue (SAR)')
        safe_conversion_cols = ['Unique Conversions', 'Unique Clicks']

        # Add conversion attribution options if they exist
        if 'Unique Click-Through Conversions' in filtered_df.columns:
            safe_conversion_cols.append('Unique Click-Through Conversions')
        if 'Unique Impression-Through Conversions' in filtered_df.columns:
            safe_conversion_cols.append('Unique Impression-Through Conversions')

        # Add Total columns if they exist (Monthly report)
        if 'Total Conversions' in filtered_df.columns:
            safe_conversion_cols.append('Total Conversions')

        all_metrics = safe_conversion_cols + safe_revenue_cols
        seg_metric = st.selectbox("Metric", all_metrics, key='seg_metric', format_func=_attribution_display)
        top_seg = top_segments(filtered_df, seg_metric)

        # Create display version for table
        top_seg_display = top_seg.copy().rename(columns=attribution_rename)
        seg_metric_display = _attribution_display(seg_metric)
        # Format the metric column for display
        if 'Revenue' in seg_metric:
            top_seg_display[seg_metric_display] = top_seg_display[seg_metric_display].apply(lambda x: format_metric(x, "SAR"))
        elif seg_metric in ['Unique Conversions', 'Total Conversions', 'Unique Clicks', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions']:
            top_seg_display[seg_metric_display] = top_seg_display[seg_metric_display].apply(format_metric)
        st.dataframe(top_seg_display)

        # Create chart with original numeric values
        fig3 = px.bar(top_seg, x='Segment Name', y=seg_metric, title=f"Top Segments by {seg_metric_display}",
                       color_discrete_sequence=COLOR_SEQUENCE)
        st.plotly_chart(fig3, use_container_width=True)

    elif page == "Channels":
        st.header("Channel Analysis")
        chan_df = channel_analysis(filtered_df)

        # Create display version for table - keep conversions visible with labeled columns
        chan_df_display = chan_df.copy()
        for drop_col in ['Selected Revenue (SAR)']:
            if drop_col in chan_df_display.columns:
                chan_df_display = chan_df_display.drop(columns=[drop_col])

        # Rename selected attribution columns in display table only
        chan_df_display = chan_df_display.rename(columns=attribution_rename)
        
        # If comparison mode is active, calculate comparison metrics and add percentage changes
        if comparison_result:
            # Calculate channel metrics for comparison period
            chan_df_comparison = channel_analysis(comparison_result['comparison_data'])
            
            # Create a new display dataframe with values and percentage changes
            chan_df_with_changes = chan_df_display.copy()

            # Compare metric values for each channel
            display_metric_cols = [c for c in chan_df_display.columns if c != 'Channel']

            for display_col in display_metric_cols:
                source_col = resolve_source_column(display_col, revenue_attribution, conversion_attribution)

                if source_col not in chan_df.columns:
                    continue

                new_col_data = []
                for channel in chan_df_display['Channel']:
                    if source_col == 'AOV (SAR)':
                        curr_rev = chan_df.loc[chan_df['Channel'] == channel, 'Selected Revenue (SAR)'] if 'Selected Revenue (SAR)' in chan_df.columns else chan_df.loc[chan_df['Channel'] == channel, 'Revenue (SAR)']
                        curr_conv = chan_df.loc[chan_df['Channel'] == channel, 'Selected Conversions'] if 'Selected Conversions' in chan_df.columns else chan_df.loc[chan_df['Channel'] == channel, 'Unique Conversions']
                        current_val = curr_rev.sum() / curr_conv.sum() if curr_conv.sum() > 0 else 0

                        comp_val = 0
                        if 'Selected Revenue (SAR)' in chan_df_comparison.columns and 'Selected Conversions' in chan_df_comparison.columns:
                            comp_rev = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, 'Selected Revenue (SAR)']
                            comp_conv = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, 'Selected Conversions']
                            comp_val = comp_rev.sum() / comp_conv.sum() if comp_conv.sum() > 0 else 0
                    else:
                        current_val = chan_df.loc[chan_df['Channel'] == channel, source_col].values
                        current_val = current_val[0] if len(current_val) > 0 else 0

                        comp_val = 0
                        if source_col in chan_df_comparison.columns:
                            comp_val = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, source_col].values
                            comp_val = comp_val[0] if len(comp_val) > 0 else 0

                    if comp_val > 0:
                        pct_change = ((current_val - comp_val) / comp_val) * 100
                        if pct_change > 0:
                            pct_str = f" <span style='color: #28a745; font-weight: 600; white-space: nowrap; display: inline-block;'>▲&nbsp;{pct_change:.1f}%</span>"
                        elif pct_change < 0:
                            pct_str = f" <span style='color: #dc3545; font-weight: 600; white-space: nowrap; display: inline-block;'>▼&nbsp;{abs(pct_change):.1f}%</span>"
                        else:
                            pct_str = " <span style='color: #6c757d; white-space: nowrap; display: inline-block;'>→&nbsp;0%</span>"
                    elif current_val > 0 and comp_val == 0:
                        pct_str = " <span style='color: #17a2b8; font-weight: 600; white-space: nowrap; display: inline-block;'>🆕</span>"
                    else:
                        pct_str = ""

                    if 'Revenue' in source_col or 'AOV' in source_col:
                        formatted_val = format_metric(current_val, "SAR", abbreviate=True)
                    else:
                        formatted_val = format_metric(current_val, "", abbreviate=True)

                    new_col_data.append(formatted_val + pct_str)

                chan_df_with_changes[display_col] = new_col_data

            # Add total row with comparisons
            total_row_chan = {'Channel': 'Total'}
            for display_col in display_metric_cols:
                source_col = resolve_source_column(display_col, revenue_attribution, conversion_attribution)

                if source_col not in chan_df.columns:
                    continue

                current_total = chan_df[source_col].sum()
                comp_total = chan_df_comparison[source_col].sum() if source_col in chan_df_comparison.columns else 0

                if source_col == 'AOV (SAR)':
                    total_rev = chan_df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in chan_df.columns else chan_df['Revenue (SAR)'].sum()
                    total_conv = chan_df['Selected Conversions'].sum() if 'Selected Conversions' in chan_df.columns else chan_df['Unique Conversions'].sum()
                    current_total = total_rev / total_conv if total_conv > 0 else 0
                    comp_total = 0
                    if 'Selected Revenue (SAR)' in chan_df_comparison.columns and 'Selected Conversions' in chan_df_comparison.columns:
                        comp_rev = chan_df_comparison['Selected Revenue (SAR)'].sum()
                        comp_conv = chan_df_comparison['Selected Conversions'].sum()
                        comp_total = comp_rev / comp_conv if comp_conv > 0 else 0
                else:
                    current_total = chan_df[source_col].sum()
                    comp_total = chan_df_comparison[source_col].sum() if source_col in chan_df_comparison.columns else 0

                if comp_total > 0:
                    pct_change = ((current_total - comp_total) / comp_total) * 100
                    if pct_change > 0:
                        pct_str = f" <span style='color: #28a745; font-weight: 600; white-space: nowrap; display: inline-block;'>▲&nbsp;{pct_change:.1f}%</span>"
                    elif pct_change < 0:
                        pct_str = f" <span style='color: #dc3545; font-weight: 600; white-space: nowrap; display: inline-block;'>▼&nbsp;{abs(pct_change):.1f}%</span>"
                    else:
                        pct_str = " <span style='color: #6c757d; white-space: nowrap; display: inline-block;'>→&nbsp;0%</span>"
                elif current_total > 0:
                    pct_str = " <span style='color: #17a2b8; font-weight: 600; white-space: nowrap; display: inline-block;'>🆕</span>"
                else:
                    pct_str = ""

                if 'Revenue' in source_col or 'AOV' in source_col:
                    formatted_total = format_metric(current_total, "SAR", abbreviate=True)
                else:
                    formatted_total = format_metric(current_total, "", abbreviate=True)

                total_row_chan[display_col] = formatted_total + pct_str

            chan_df_with_changes = pd.concat([chan_df_with_changes, pd.DataFrame([total_row_chan])], ignore_index=True)
            chan_df_display = chan_df_with_changes
        else:
            # No comparison - use regular formatting
            # Add total row
            total_row_chan = {'Channel': 'Total'}
            for col in chan_df_display.columns:
                if col == 'Channel':
                    continue
                if 'AOV' in col:
                    continue
                total_row_chan[col] = chan_df_display[col].sum()

            # Compute total AOV from total revenue/total conversions
            if 'Selected Revenue (SAR)' in chan_df.columns and 'Selected Conversions' in chan_df.columns:
                total_conv = chan_df['Selected Conversions'].sum()
                total_rev = chan_df['Selected Revenue (SAR)'].sum()
            elif 'Revenue (SAR)' in chan_df.columns and 'Unique Conversions' in chan_df.columns:
                total_conv = chan_df['Unique Conversions'].sum()
                total_rev = chan_df['Revenue (SAR)'].sum()
            else:
                total_conv = 0
                total_rev = 0

            total_aov = (total_rev / total_conv) if total_conv > 0 else 0
            for col in [c for c in chan_df_display.columns if 'AOV' in c]:
                total_row_chan[col] = total_aov

            chan_df_display = pd.concat([chan_df_display, pd.DataFrame([total_row_chan])], ignore_index=True)
            # Format columns
            conversion_col = None
            for col in [selected_conv_label, 'Selected Conversions', 'Unique Conversions', 'Total Conversions']:
                if col in chan_df_display.columns:
                    conversion_col = col
                    break

            numeric_cols = ['Sent', 'Delivered', 'Unique Impressions', 'Unique Clicks']
            if conversion_col:
                numeric_cols.append(conversion_col)
            if 'Total Conversions' in chan_df_display.columns and 'Total Conversions' not in numeric_cols:
                numeric_cols.append('Total Conversions')

            for col in numeric_cols:
                if col in chan_df_display.columns:
                    chan_df_display[col] = chan_df_display[col].apply(format_metric)
            revenue_cols = [col for col in chan_df_display.columns if 'Revenue' in col]
            for col in revenue_cols:
                chan_df_display[col] = chan_df_display[col].apply(lambda x: format_metric(x, "SAR"))
            # Format AOV columns
            aov_cols = [col for col in chan_df_display.columns if 'AOV' in col]
            for col in aov_cols:
                chan_df_display[col] = chan_df_display[col].apply(lambda x: format_metric(x, "SAR"))
        
        # Display table with HTML rendering if comparison is active
        if comparison_result:
            table_html = chan_df_display.to_html(escape=False, index=False)
            components.html(
                """
                <style>
                @media (prefers-color-scheme: dark) {
                    .channel-compare-table {
                        color: rgba(250, 250, 250, 0.95);
                    }
                    .channel-compare-table table {
                        background: #0e1117;
                        border: 1px solid rgba(250, 250, 250, 0.2);
                    }
                    .channel-compare-table th {
                        background: rgba(38, 39, 48, 0.8);
                        border-bottom: 1px solid rgba(250, 250, 250, 0.2);
                    }
                    .channel-compare-table td {
                        border-bottom: 1px solid rgba(250, 250, 250, 0.1);
                    }
                    .channel-compare-table tr:nth-child(even) td {
                        background: rgba(250, 250, 250, 0.03);
                    }
                    .channel-compare-table tr:hover td {
                        background: rgba(250, 250, 250, 0.08);
                    }
                    .channel-compare-table tbody tr:last-child td {
                        background: rgba(100, 150, 255, 0.15);
                        border-top: 2px solid rgba(100, 150, 255, 0.5);
                    }
                }
                @media (prefers-color-scheme: light) {
                    .channel-compare-table {
                        color: #262730;
                    }
                    .channel-compare-table table {
                        background: #ffffff;
                        border: 1px solid #e6e6e6;
                    }
                    .channel-compare-table th {
                        background: #f6f7f9;
                        border-bottom: 1px solid #e6e6e6;
                    }
                    .channel-compare-table td {
                        border-bottom: 1px solid #f0f0f0;
                    }
                    .channel-compare-table tr:nth-child(even) td {
                        background: #fafafa;
                    }
                    .channel-compare-table tr:hover td {
                        background: #f0f7ff;
                    }
                    .channel-compare-table tbody tr:last-child td {
                        background: #e8f4ff;
                        border-top: 2px solid #4a90e2;
                    }
                }
                .channel-compare-table {
                    font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    font-size: 14px;
                }
                .channel-compare-table table {
                    width: 100%;
                    border-collapse: collapse;
                }
                .channel-compare-table th,
                .channel-compare-table td {
                    white-space: nowrap;
                    padding: 8px 10px;
                    text-align: left;
                    vertical-align: middle;
                }
                .channel-compare-table th {
                    font-weight: 600;
                    position: sticky;
                    top: 0;
                    z-index: 1;
                }
                .channel-compare-table tbody tr:last-child td {
                    font-weight: 700;
                }
                </style>
                """ + f"<div class='channel-compare-table'>{table_html}</div>",
                height=360,
                scrolling=True
            )
        else:
            st.dataframe(style_total_row(chan_df_display), use_container_width=True, hide_index=True)

        # Revenue Distribution (Donut Chart)
        rev_display_name = get_selected_revenue_display_name(revenue_attribution)
        st.subheader(f"Revenue Distribution Across Channels - {rev_display_name}")
        if 'Selected Revenue (SAR)' in chan_df.columns:
            # Calculate total revenue for center annotation
            total_revenue = chan_df['Selected Revenue (SAR)'].sum()

            # Create donut chart for revenue share
            fig_donut = px.pie(
                chan_df,
                values='Selected Revenue (SAR)',
                names='Channel',
                title=f"Channel Revenue Share<br><sub>Using: {rev_display_name}</sub>",
                color='Channel',
                color_discrete_map=CHANNEL_COLORS,
                hole=0.4  # Makes it a donut chart
            )
            fig_donut.update_traces(
                textposition='inside',
                textinfo='percent+label',
                hovertemplate='<b>%{label}</b><br>' +
                              'Revenue: %{value:,.0f} SAR<br>' +
                              'Share: %{percent}<br>' +
                              '<extra></extra>'
            )
            fig_donut.update_layout(
                showlegend=True,
                legend=dict(orientation='h', yanchor='bottom', y=-0.2, xanchor='center', x=0.5),
                annotations=[dict(
                    text=f'<b>Total</b><br>{format_metric(total_revenue, "SAR", abbreviate=True)}',
                    x=0.5, y=0.5,
                    font_size=16,
                    showarrow=False
                )]
            )
            st.plotly_chart(fig_donut, use_container_width=True)

        # Revenue + Conversions by Channel (using selected attribution)
        st.subheader("Revenue & Conversions Comparison")
        rev_conv_col1, rev_conv_col2 = st.columns(2)
        with rev_conv_col1:
            if 'Selected Revenue (SAR)' in chan_df.columns:
                rev_display_name = get_selected_revenue_display_name(revenue_attribution)
                fig_rev_chan = px.bar(
                    chan_df, x='Channel', y='Selected Revenue (SAR)',
                    title=f"{rev_display_name} by Channel",
                    color='Channel', color_discrete_map=CHANNEL_COLORS,
                    labels={'Selected Revenue (SAR)': rev_display_name}
                )
                fig_rev_chan.update_layout(showlegend=False)
                st.plotly_chart(fig_rev_chan, use_container_width=True)
        with rev_conv_col2:
            conv_col = 'Selected Conversions' if 'Selected Conversions' in chan_df.columns else 'Unique Conversions'
            conv_display_name = get_selected_conversion_display_name(conversion_attribution) if conv_col == 'Selected Conversions' else 'Unique Conversions'
            fig_conv_chan = px.bar(
                chan_df, x='Channel', y=conv_col,
                title=f"{conv_display_name} by Channel",
                color='Channel', color_discrete_map=CHANNEL_COLORS,
                labels={conv_col: conv_display_name}
            )
            fig_conv_chan.update_layout(showlegend=False)
            st.plotly_chart(fig_conv_chan, use_container_width=True)

        # Compute derived rates for deeper channel analysis
        chan_rates = chan_df.copy()
        chan_rates['Delivery Rate'] = np.where(
            chan_rates['Sent'] > 0,
            (chan_rates['Delivered'] / chan_rates['Sent']) * 100, 0
        )
        chan_rates['CTR'] = np.where(
            chan_rates['Unique Impressions'] > 0,
            (chan_rates['Unique Clicks'] / chan_rates['Unique Impressions']) * 100, 0
        )

        # Charts: Delivery Rate + CTR
        st.subheader("Engagement & Delivery Rates")
        ch_col1, ch_col2 = st.columns(2)
        with ch_col1:
            fig_dr = px.bar(
                chan_rates, x='Channel', y='Delivery Rate',
                title="Delivery Rate by Channel (%)",
                color='Channel', color_discrete_map=CHANNEL_COLORS,
            )
            fig_dr.update_layout(showlegend=False, yaxis_title="Delivery Rate (%)")
            fig_dr.add_hline(y=95, line_dash="dash", line_color=COLORS['muted'],
                             annotation_text="95% target", annotation_position="top right")
            st.plotly_chart(fig_dr, use_container_width=True)
        with ch_col2:
            fig_ctr = px.bar(
                chan_rates, x='Channel', y='CTR',
                title="Click-Through Rate by Channel (%)",
                color='Channel', color_discrete_map=CHANNEL_COLORS,
            )
            fig_ctr.update_layout(showlegend=False, yaxis_title="CTR (%)")
            st.plotly_chart(fig_ctr, use_container_width=True)

        # Volume comparison (Sent vs Delivered side-by-side)
        st.subheader("Send Volume & Delivery")
        volume_melt = chan_df[['Channel', 'Sent', 'Delivered']].melt(
            id_vars='Channel', var_name='Metric', value_name='Count'
        )
        fig_vol = px.bar(
            volume_melt, x='Channel', y='Count', color='Metric',
            barmode='group', title="Sent vs Delivered by Channel",
            color_discrete_map={'Sent': COLORS['primary'], 'Delivered': COLORS['success']},
        )
        st.plotly_chart(fig_vol, use_container_width=True)

        # Revenue Attribution Comparison (all three side-by-side)
        rev_compare_cols = [c for c in ['Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Impression-Through Revenue (SAR)'] if c in chan_df.columns]
        if len(rev_compare_cols) > 1:
            st.subheader("Revenue Attribution Comparison")
            rev_melt = chan_df[['Channel'] + rev_compare_cols].melt(
                id_vars='Channel', var_name='Attribution Model', value_name='Revenue'
            )
            # Shorten labels for readability
            rev_melt['Attribution Model'] = rev_melt['Attribution Model'].str.replace(' (SAR)', '', regex=False).str.replace('Revenue', '').str.strip()
            fig_rev_compare = px.bar(
                rev_melt, x='Channel', y='Revenue', color='Attribution Model',
                barmode='group', title="Revenue by Channel & Attribution Model",
                color_discrete_sequence=COLOR_SEQUENCE,
            )
            st.plotly_chart(fig_rev_compare, use_container_width=True)

        # Campaign Type Performance by Channel (One-Time vs Journey)
        if 'Type of Campaign' in filtered_df.columns and 'Channel' in filtered_df.columns:
            type_vals = filtered_df['Type of Campaign'].dropna().unique()
            if len(type_vals) > 0:
                st.subheader("One-Time vs Journey Performance by Channel")
                rev_col_type = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
                conv_col_type = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'

                # Aggregate all available revenue and conversion columns
                type_chan_agg = {'Sent': 'sum', 'Delivered': 'sum'}
                # Always include selected attribution columns
                if conv_col_type in filtered_df.columns:
                    type_chan_agg[conv_col_type] = 'sum'
                if rev_col_type in filtered_df.columns:
                    type_chan_agg[rev_col_type] = 'sum'
                # Also aggregate all other revenue/conversion columns for detail view
                extra_rev_cols = [c for c in ['Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Impression-Through Revenue (SAR)'] if c in filtered_df.columns and c != rev_col_type]
                extra_conv_cols = [c for c in ['Unique Conversions', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions'] if c in filtered_df.columns and c != conv_col_type]
                for c in extra_rev_cols + extra_conv_cols:
                    type_chan_agg[c] = 'sum'
                type_chan_df = filtered_df.groupby(['Channel', 'Type of Campaign']).agg(type_chan_agg).reset_index()

                # Toggle for showing all revenue/conversion types
                show_all_attrs = st.checkbox("Show all revenue & conversion types", value=False, key='chan_type_show_all')

                # Build display columns
                default_cols = ['Channel', 'Type of Campaign', 'Sent', 'Delivered', conv_col_type, rev_col_type]
                default_cols = [c for c in default_cols if c in type_chan_df.columns]
                if show_all_attrs:
                    display_cols = default_cols + [c for c in extra_rev_cols + extra_conv_cols if c not in default_cols]
                else:
                    display_cols = default_cols

                type_chan_display = type_chan_df[display_cols].copy()
                # Format numeric columns
                for col in ['Sent', 'Delivered'] + extra_conv_cols + ([conv_col_type] if conv_col_type in type_chan_display.columns else []):
                    if col in type_chan_display.columns:
                        type_chan_display[col] = type_chan_display[col].apply(format_metric)
                for col in [rev_col_type] + extra_rev_cols:
                    if col in type_chan_display.columns:
                        type_chan_display[col] = type_chan_display[col].apply(lambda x: format_metric(x, "SAR"))
                # Rename Selected columns to show actual attribution model
                type_chan_display = type_chan_display.rename(columns=attribution_rename)
                st.dataframe(type_chan_display, use_container_width=True, hide_index=True)

                # Stacked bar: Revenue by Channel, stacked by Campaign Type
                type_chan_col1, type_chan_col2 = st.columns(2)
                with type_chan_col1:
                    if rev_col_type in type_chan_df.columns:
                        rev_display_name = get_selected_revenue_display_name(revenue_attribution)
                        fig_type_chan_rev = px.bar(
                            type_chan_df, x='Channel', y=rev_col_type, color='Type of Campaign',
                            barmode='stack', title=f"{rev_display_name} by Channel & Campaign Type",
                            color_discrete_sequence=COLOR_SEQUENCE,
                            labels={rev_col_type: rev_display_name}
                        )
                        fig_type_chan_rev.update_layout(legend=dict(orientation='h', y=-0.2))
                        st.plotly_chart(fig_type_chan_rev, use_container_width=True)
                with type_chan_col2:
                    conv_display_name = get_selected_conversion_display_name(conversion_attribution)
                    fig_type_chan_conv = px.bar(
                        type_chan_df, x='Channel', y=conv_col_type, color='Type of Campaign',
                        barmode='stack', title=f"{conv_display_name} by Channel & Campaign Type",
                        color_discrete_sequence=COLOR_SEQUENCE,
                        labels={conv_col_type: conv_display_name}
                    )
                    fig_type_chan_conv.update_layout(legend=dict(orientation='h', y=-0.2))
                    st.plotly_chart(fig_type_chan_conv, use_container_width=True)

                # Share breakdown: what % of each channel's revenue comes from journeys vs one-time
                if rev_col_type in type_chan_df.columns:
                    channel_totals = type_chan_df.groupby('Channel')[rev_col_type].sum().reset_index()
                    channel_totals.columns = ['Channel', 'Total']
                    type_share = type_chan_df.merge(channel_totals, on='Channel')
                    type_share['Revenue Share'] = np.where(
                        type_share['Total'] > 0,
                        type_share[rev_col_type] / type_share['Total'] * 100, 0
                    )
                    fig_share = px.bar(
                        type_share, x='Channel', y='Revenue Share', color='Type of Campaign',
                        barmode='stack', title="Revenue Share by Campaign Type per Channel (%)",
                        color_discrete_sequence=COLOR_SEQUENCE,
                        custom_data=['Type of Campaign']
                    )
                    fig_share.update_traces(
                        hovertemplate='<b>%{x}</b><br>' +
                                      'Campaign Type: %{customdata[0]}<br>' +
                                      'Revenue Share: %{y:.1f}%<br>' +
                                      '<extra></extra>'
                    )
                    fig_share.update_layout(
                        yaxis_title="Revenue Share (%)", yaxis_range=[0, 100],
                        legend=dict(orientation='h', y=-0.2)
                    )
                    st.plotly_chart(fig_share, use_container_width=True)

        # ESP Analysis
        esp_df = esp_analysis(filtered_df)
        if not esp_df.empty:
            st.subheader("ESP/SSP Analysis")
            esp_df_display = esp_df.copy()
            numeric_cols = ['Sent', 'Delivered', 'Unique Conversions']
            for col in numeric_cols:
                if col in esp_df_display.columns:
                    esp_df_display[col] = esp_df_display[col].apply(format_metric)
            revenue_cols = [col for col in esp_df_display.columns if 'Revenue' in col]
            for col in revenue_cols:
                esp_df_display[col] = esp_df_display[col].apply(lambda x: format_metric(x, "SAR"))
            st.dataframe(esp_df_display)

            esp_col1, esp_col2 = st.columns(2)
            with esp_col1:
                fig_esp = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Delivered',
                                 title="Delivered by ESP", color_discrete_sequence=COLOR_SEQUENCE)
                st.plotly_chart(fig_esp, use_container_width=True)
            with esp_col2:
                if 'Revenue (SAR)' in esp_df.columns:
                    fig_esp_rev = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Revenue (SAR)',
                                         title="Send-Through Revenue by ESP", color_discrete_sequence=COLOR_SEQUENCE,
                                         labels={'Revenue (SAR)': 'Send-Through Revenue (SAR)'})
                    st.plotly_chart(fig_esp_rev, use_container_width=True)

    elif page == "Time Series":
        st.header("Time Series Analysis")
        # Safe column selection - only use columns that exist in both reports
        safe_revenue_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
        if 'Selected Revenue (SAR)' in filtered_df.columns:
            safe_revenue_cols.insert(0, 'Selected Revenue (SAR)')
        safe_conversion_cols = ['Unique Conversions', 'Unique Clicks']

        # Add Total columns if they exist (Monthly report)
        if 'Total Conversions' in filtered_df.columns:
            safe_conversion_cols.append('Total Conversions')

        all_metrics = safe_conversion_cols + safe_revenue_cols
        ts_metric = st.selectbox("Metric", all_metrics, key='ts_metric', format_func=_attribution_display)
        ts_df = time_series_analysis(filtered_df, ts_metric)
        if not ts_df.empty:
            fig_ts = px.line(ts_df, x='Reporting Period Start Date', y=ts_metric, title=f"{_attribution_display(ts_metric)} Over Time",
                             color_discrete_sequence=[COLORS['primary']])
            fig_ts.update_traces(line_width=2.5)
            st.plotly_chart(fig_ts, use_container_width=True)
        else:
            st.write("No time series data available.")

    elif page == "Correlations":
        st.header("Correlations")
        # Focus on key business metrics for a readable correlation matrix
        key_metric_cols = [c for c in [
            'Sent', 'Delivered', 'Unique Impressions', 'Unique Clicks',
            'Unique Conversions', 'Selected Conversions', 'Selected Revenue (SAR)',
            'Revenue (SAR)', 'CTR', 'Conversion Rate', 'Delivery Rate',
            'AOV', 'Revenue Per Click', 'Revenue Per Send', 'ROAS',
            'Campaign Cost', 'Engagement Rate',
        ] if c in filtered_df.columns]

        if key_metric_cols:
            corr = filtered_df[key_metric_cols].corr()
            fig_corr = px.imshow(corr, text_auto='.2f', title="Key Metrics Correlation Matrix",
                                 color_continuous_scale='RdBu_r', aspect='auto',
                                 zmin=-1, zmax=1)
            fig_corr.update_layout(width=900, height=700)
            st.plotly_chart(fig_corr, use_container_width=True)

            # Highlight strongest correlations
            st.subheader("Strongest Correlations")
            corr_pairs = []
            for i in range(len(corr.columns)):
                for j in range(i + 1, len(corr.columns)):
                    val = corr.iloc[i, j]
                    if abs(val) >= 0.5 and abs(val) < 1.0:
                        corr_pairs.append({
                            'Metric 1': corr.columns[i],
                            'Metric 2': corr.columns[j],
                            'Correlation': val,
                            'Strength': 'Strong' if abs(val) >= 0.7 else 'Moderate'
                        })
            if corr_pairs:
                corr_pairs_df = pd.DataFrame(corr_pairs).sort_values('Correlation', key=abs, ascending=False)
                corr_pairs_df['Correlation'] = corr_pairs_df['Correlation'].apply(lambda x: f"{x:+.3f}")
                st.dataframe(corr_pairs_df, use_container_width=True)
            else:
                st.info("No strong correlations (|r| >= 0.5) found between key metrics.")
        else:
            st.write("No numeric data for correlation.")

    elif page == "A/B Testing":
        st.header("A/B Testing Analysis")
        ab_df = ab_testing_analysis(filtered_df)
        if not ab_df.empty:
            st.dataframe(ab_df)
            fig_ab = px.bar(ab_df, x='Campaign Name', y='Lift', title="Conversion Lift by Campaign",
                            color='Lift', color_continuous_scale=[[0, COLORS['danger']], [0.5, COLORS['warning']], [1, COLORS['success']]])
            st.plotly_chart(fig_ab, use_container_width=True)
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
        fig_attr = px.pie(attr_df, names='Source', values='Conversions', title="Conversions by Attribution Source",
                          color_discrete_sequence=COLOR_SEQUENCE)
        st.plotly_chart(fig_attr, use_container_width=True)

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
            fig_fail = px.bar(failed_df, x='Reason', y='Count', title="Failed Reasons Breakdown",
                              color_discrete_sequence=[COLORS['danger']])
            st.plotly_chart(fig_fail, use_container_width=True)

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
                fig_fail_chan = px.bar(failed_melt, x='Channel', y='Count', color='Reason',
                                      title="Failed Reasons by Channel",
                                      color_discrete_sequence=COLOR_SEQUENCE)
                st.plotly_chart(fig_fail_chan, use_container_width=True)
        else:
            st.write("No failed reasons data available.")

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
        st.header("📊 Period-over-Period Comparisons")
        st.markdown("*Analyze performance trends across different time periods with detailed metrics*")
        
        # Check if comparison is enabled
        if comparison_result:
            st.success(f"✅ Comparison Mode Active: **{comparison_result['current_label']}** vs **{comparison_result['comparison_label']}**")
            
            # Calculate comprehensive metrics
            current_metrics = calculate_period_metrics(comparison_result['current_data'], comparison_result['current_days'], conversion_attribution)
            comp_metrics = calculate_period_metrics(comparison_result['comparison_data'], comparison_result['comparison_days'], conversion_attribution)
            metric_changes = calculate_metric_changes(current_metrics, comp_metrics)
            
            # === EXECUTIVE SUMMARY ===
            st.markdown("---")
            st.subheader("📈 Executive Summary")
            
            # Key highlights
            revenue_trend = metric_changes['selected_revenue']
            conv_trend = metric_changes['selected_conversions']
            ctr_trend = metric_changes['ctr']
            delivery_trend = metric_changes['delivery_rate']
            
            # Determine overall trend
            positive_trends = sum([
                revenue_trend['pct_change'] > 0,
                conv_trend['pct_change'] > 0,
                ctr_trend['pct_change'] > 0,
                delivery_trend['pct_change'] > 0
            ])
            
            if positive_trends >= 3:
                st.success("🎯 **Overall Trend: POSITIVE** - Most metrics are improving")
            elif positive_trends >= 2:
                st.info("➡️ **Overall Trend: MIXED** - Some metrics improving, others declining")
            else:
                st.warning("⚠️ **Overall Trend: NEEDS ATTENTION** - Most metrics are declining")
            
            # Key metrics comparison
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Revenue Change",
                    f"{revenue_trend['pct_change']:+.1f}%",
                    delta=format_metric(revenue_trend['absolute_change'], "SAR")
                )
            
            with col2:
                st.metric(
                    "Conversion Change",
                    f"{conv_trend['pct_change']:+.1f}%",
                    delta=format_metric(conv_trend['absolute_change'])
                )
            
            with col3:
                st.metric(
                    "CTR Change",
                    f"{ctr_trend['pct_change']:+.1f}%",
                    delta=f"{ctr_trend['absolute_change']:+.2%}"
                )
            
            with col4:
                st.metric(
                    "Delivery Rate Change",
                    f"{delivery_trend['pct_change']:+.1f}%",
                    delta=f"{delivery_trend['absolute_change']:+.2%}"
                )
            
            # Business Intelligence Metrics
            st.markdown("#### 💰 Business Intelligence")
            biz_col1, biz_col2, biz_col3 = st.columns(3)
            
            aov_trend = metric_changes['aov']
            rpc_trend = metric_changes['revenue_per_click']
            eng_trend = metric_changes['engagement_rate']
            
            with biz_col1:
                st.metric(
                    "AOV Change",
                    f"{aov_trend['pct_change']:+.1f}%",
                    delta=format_metric(aov_trend['absolute_change'], "SAR"),
                    help="Average Order Value - Revenue per conversion"
                )
            
            with biz_col2:
                st.metric(
                    "RPC Change",
                    f"{rpc_trend['pct_change']:+.1f}%",
                    delta=format_metric(rpc_trend['absolute_change'], "SAR"),
                    help="Revenue Per Click - Measures click quality"
                )
            
            with biz_col3:
                st.metric(
                    "Engagement Rate Change",
                    f"{eng_trend['pct_change']:+.1f}%",
                    delta=f"{eng_trend['absolute_change']:+.2%}",
                    help="Combined engagement (clicks + opens) / impressions"
                )
            
            # ROI & Cost Efficiency
            st.markdown("#### 💵 ROI & Cost Efficiency")
            cost_col1, cost_col2, cost_col3, cost_col4 = st.columns(4)
            
            roas_trend = metric_changes['roas']
            rps_trend = metric_changes['revenue_per_send']
            cpc_trend = metric_changes['cost_per_conversion']
            profit_trend = metric_changes['profit']
            
            with cost_col1:
                current_roas = roas_trend['current']
                if current_roas >= 4:
                    roas_status = "🟢"
                elif current_roas >= 2:
                    roas_status = "🟡"
                else:
                    roas_status = "🔴"
                
                st.metric(
                    f"ROAS Change {roas_status}",
                    f"{roas_trend['pct_change']:+.1f}%",
                    delta=f"{roas_trend['current']:.2f}x now",
                    help=f"Return on Ad Spend: {roas_trend['current']:.2f}x (was {roas_trend['comparison']:.2f}x)"
                )
            
            with cost_col2:
                st.metric(
                    "Revenue Per Send Change",
                    f"{rps_trend['pct_change']:+.1f}%",
                    delta=f"{rps_trend['absolute_change']:.4f} SAR",
                    help="KEY efficiency metric - answers your 'doubled sends, less revenue' question"
                )
            
            with cost_col3:
                st.metric(
                    "Cost Per Conversion",
                    f"{cpc_trend['pct_change']:+.1f}%",
                    delta=format_metric(cpc_trend['absolute_change'], "SAR"),
                    delta_color="inverse" if cpc_trend['pct_change'] >= 0 else "normal",
                    help="Lower is better"
                )
            
            with cost_col4:
                st.metric(
                    "Profit Change",
                    f"{profit_trend['pct_change']:+.1f}%",
                    delta=format_metric(profit_trend['absolute_change'], "SAR"),
                    help="Revenue - Cost"
                )
            
            # === DETAILED METRICS TABLE ===
            st.markdown("---")
            st.subheader("📊 Detailed Metrics Comparison")
            
            # Create comparison dataframe
            comparison_data = []
            metric_names = {
                'selected_revenue': ('Total Revenue (SAR)', 'SAR'),
                'selected_conversions': ('Total Conversions', ''),
                'total_clicks': ('Total Clicks', ''),
                'total_impressions': ('Total Impressions', ''),
                'total_sent': ('Total Sent', ''),
                'total_delivered': ('Total Delivered', ''),
                'total_cost': ('Total Campaign Cost', 'SAR'),
                'profit': ('Profit (Revenue - Cost)', 'SAR'),
                'ctr': ('Click-Through Rate', '%'),
                'conversion_rate': ('Conversion Rate', '%'),
                'delivery_rate': ('Delivery Rate', '%'),
                'aov': ('Average Order Value (AOV)', 'SAR'),
                'revenue_per_click': ('Revenue Per Click (RPC)', 'SAR'),
                'revenue_per_send': ('Revenue Per Send (RPS)', 'SAR'),
                'engagement_rate': ('Engagement Rate', '%'),
                'roas': ('ROAS (Return on Ad Spend)', 'ratio'),
                'cost_per_conversion': ('Cost Per Conversion', 'SAR'),
                'cost_per_click': ('Cost Per Click', 'SAR'),
                'profit_margin': ('Profit Margin', '%'),
                'revenue_per_conversion': ('Revenue per Conversion', 'SAR'),
                'daily_revenue': ('Daily Avg Revenue', 'SAR'),
                'daily_conversions': ('Daily Avg Conversions', ''),
                'daily_cost': ('Daily Avg Cost', 'SAR'),
            }
            
            for metric_key, (metric_label, unit) in metric_names.items():
                if metric_key in metric_changes:
                    change_data = metric_changes[metric_key]
                    
                    if unit == '%':
                        current_val = f"{change_data['current']:.2%}"
                        comp_val = f"{change_data['comparison']:.2%}"
                    elif unit == 'SAR':
                        current_val = format_metric(change_data['current'], 'SAR')
                        comp_val = format_metric(change_data['comparison'], 'SAR')
                    elif unit == 'ratio':
                        current_val = f"{change_data['current']:.2f}x"
                        comp_val = f"{change_data['comparison']:.2f}x"
                    else:
                        current_val = format_metric(change_data['current'])
                        comp_val = format_metric(change_data['comparison'])
                    
                    comparison_data.append({
                        'Metric': metric_label,
                        'Current Period': current_val,
                        'Comparison Period': comp_val,
                        'Change %': f"{change_data['pct_change']:+.1f}%",
                        'Trend': change_data['trend']
                    })
            
            comparison_df = pd.DataFrame(comparison_data)
            st.dataframe(comparison_df, use_container_width=True)
            
            # === VISUALIZATION ===
            st.markdown("---")
            st.subheader("📈 Visual Comparison")
            
            # Select metric to visualize
            viz_metric = st.selectbox(
                "Select Metric to Visualize",
                ["Revenue (SAR)", "Conversions", "Clicks", "CTR", "Conversion Rate", "Delivery Rate"],
                key="comparison_viz_metric"
            )
            
            # Map selection to data keys
            viz_mapping = {
                "Revenue (SAR)": 'selected_revenue',
                "Conversions": 'selected_conversions',
                "Clicks": 'total_clicks',
                "CTR": 'ctr',
                "Conversion Rate": 'conversion_rate',
                "Delivery Rate": 'delivery_rate'
            }
            
            selected_key = viz_mapping[viz_metric]
            change_data = metric_changes[selected_key]
            
            # Create comparison bar chart
            fig_comparison = go.Figure()
            
            fig_comparison.add_trace(go.Bar(
                name='Comparison Period',
                x=[comparison_result['comparison_label']],
                y=[change_data['comparison']],
                marker_color=COLORS['info'],
                text=[format_metric(change_data['comparison'], 'SAR' if 'Revenue' in viz_metric else '')],
                textposition='auto'
            ))
            
            fig_comparison.add_trace(go.Bar(
                name='Current Period',
                x=[comparison_result['current_label']],
                y=[change_data['current']],
                marker_color=COLORS['success'] if change_data['pct_change'] > 0 else COLORS['danger'],
                text=[format_metric(change_data['current'], 'SAR' if 'Revenue' in viz_metric else '')],
                textposition='auto'
            ))
            
            fig_comparison.update_layout(
                title=f"{viz_metric} Comparison",
                xaxis_title="Period",
                yaxis_title=viz_metric,
                barmode='group',
                height=400
            )
            
            st.plotly_chart(fig_comparison, use_container_width=True)
            comp_img = export_chart_image(fig_comparison, 'period_comparison')
            if comp_img:
                st.download_button("Download Comparison Chart", comp_img, "period_comparison.png", "image/png", key='dl_comparison')

            # === CHANNEL-LEVEL COMPARISON ===
            if 'Channel' in comparison_result['current_data'].columns:
                st.markdown("---")
                st.subheader("📡 Channel-Level Comparison")
                
                # Aggregate by channel for both periods
                current_by_channel = comparison_result['current_data'].groupby('Channel').agg({
                    'Selected Revenue (SAR)': 'sum',
                    'Selected Conversions': 'sum',
                    'Unique Clicks': 'sum'
                }).reset_index()
                
                comp_by_channel = comparison_result['comparison_data'].groupby('Channel').agg({
                    'Selected Revenue (SAR)': 'sum',
                    'Selected Conversions': 'sum',
                    'Unique Clicks': 'sum'
                }).reset_index()
                
                # Merge and calculate changes
                channel_comparison = current_by_channel.merge(
                    comp_by_channel, 
                    on='Channel', 
                    how='outer',
                    suffixes=('_current', '_comp')
                ).fillna(0)
                
                channel_comparison['Revenue Change %'] = ((channel_comparison['Selected Revenue (SAR)_current'] - channel_comparison['Selected Revenue (SAR)_comp']) / 
                                                          channel_comparison['Selected Revenue (SAR)_comp'].replace(0, 1) * 100)
                
                channel_comparison['Conversion Change %'] = ((channel_comparison['Selected Conversions_current'] - channel_comparison['Selected Conversions_comp']) / 
                                                             channel_comparison['Selected Conversions_comp'].replace(0, 1) * 100)
                
                # Display
                channel_display = channel_comparison[['Channel', 'Revenue Change %', 'Conversion Change %']].copy()
                st.dataframe(channel_display, use_container_width=True)
                
                # Channel comparison chart
                fig_channel = go.Figure()
                
                fig_channel.add_trace(go.Bar(
                    name='Revenue Change %',
                    x=channel_comparison['Channel'],
                    y=channel_comparison['Revenue Change %'],
                    marker_color=[COLORS['success'] if x > 0 else COLORS['danger'] for x in channel_comparison['Revenue Change %']]
                ))
                
                fig_channel.update_layout(
                    title="Revenue Change % by Channel",
                    xaxis_title="Channel",
                    yaxis_title="Change %",
                    height=400
                )
                
                st.plotly_chart(fig_channel, use_container_width=True)
            
            # === INSIGHTS & RECOMMENDATIONS ===
            st.markdown("---")
            st.subheader("💡 Insights & Recommendations")
            
            insights = []
            
            # Revenue insights
            if revenue_trend['pct_change'] > 10:
                insights.append(f"✅ **Strong Revenue Growth**: Revenue increased by {revenue_trend['pct_change']:.1f}%. Consider scaling successful campaigns.")
            elif revenue_trend['pct_change'] < -10:
                insights.append(f"⚠️ **Revenue Decline**: Revenue decreased by {abs(revenue_trend['pct_change']):.1f}%. Investigate underperforming channels and campaigns.")
            
            # Conversion insights
            if conv_trend['pct_change'] > 10:
                insights.append(f"✅ **Conversion Improvement**: Conversions up {conv_trend['pct_change']:.1f}%. Current strategies are working well.")
            elif conv_trend['pct_change'] < -10:
                insights.append(f"⚠️ **Conversion Drop**: Conversions down {abs(conv_trend['pct_change']):.1f}%. Review landing pages and offers.")
            
            # CTR insights
            if ctr_trend['pct_change'] > 10:
                insights.append(f"✅ **Engagement Increase**: CTR improved by {ctr_trend['pct_change']:.1f}%. Content resonates with audience.")
            elif ctr_trend['pct_change'] < -10:
                insights.append(f"⚠️ **Engagement Decline**: CTR down {abs(ctr_trend['pct_change']):.1f}%. Consider refreshing creative assets.")
            
            # Delivery insights
            if delivery_trend['pct_change'] < -5:
                insights.append(f"🚨 **Delivery Issue**: Delivery rate dropped {abs(delivery_trend['pct_change']):.1f}%. Check ESP settings and sender reputation.")
            
            # Display insights
            if insights:
                for insight in insights:
                    st.markdown(f"- {insight}")
            else:
                st.info("Performance is relatively stable with no significant changes to highlight.")
        
        else:
            st.info("🔍 **No Comparison Selected** - Enable comparison mode in the sidebar to analyze period-over-period trends")
            st.markdown("---")
            
            # Show month-over-month trend analysis as fallback
            st.subheader("📅 Monthly Trend Analysis")
            
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
            
            if not monthly_agg.empty and len(monthly_agg) > 1:
                st.subheader("Monthly Summary")
                # Add total row
                total_row_monthly = {'Month': 'Total'}
                for col in monthly_agg.columns:
                    if col != 'Month':
                        total_row_monthly[col] = monthly_agg[col].sum()
                monthly_agg_with_total = pd.concat([monthly_agg, pd.DataFrame([total_row_monthly])], ignore_index=True)
                # Format columns for display
                monthly_agg_display = monthly_agg_with_total.copy()
                monthly_agg_display['Revenue (SAR)'] = monthly_agg_display['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                monthly_agg_display['Unique Conversions'] = monthly_agg_display['Unique Conversions'].apply(format_metric)
                monthly_agg_display['Unique Clicks'] = monthly_agg_display['Unique Clicks'].apply(format_metric)
                monthly_agg_display['Sent'] = monthly_agg_display['Sent'].apply(format_metric)
                monthly_agg_display['Delivered'] = monthly_agg_display['Delivered'].apply(format_metric)
                st.dataframe(style_total_row(monthly_agg_display), use_container_width=True, hide_index=True)
                
                # Chart
                fig_comp = px.line(monthly_agg, x='Month', y='Revenue (SAR)', title="Revenue Over Months", markers=True)
                st.plotly_chart(fig_comp, use_container_width=True)
            else:
                st.write("Not enough monthly data for trend analysis.")

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
                    # Build Plotly figure from Prophet forecast data
                    fig_forecast = go.Figure()
                    fig_forecast.add_trace(go.Scatter(
                        x=df_prophet['ds'], y=df_prophet['y'],
                        mode='markers', name='Actual', marker=dict(color=COLORS['primary'], size=8)
                    ))
                    fig_forecast.add_trace(go.Scatter(
                        x=forecast['ds'], y=forecast['yhat'],
                        mode='lines', name='Forecast', line=dict(color=COLORS['success'], width=2)
                    ))
                    fig_forecast.add_trace(go.Scatter(
                        x=pd.concat([forecast['ds'], forecast['ds'][::-1]]),
                        y=pd.concat([forecast['yhat_upper'], forecast['yhat_lower'][::-1]]),
                        fill='toself', fillcolor='rgba(5,150,105,0.15)', line=dict(width=0),
                        name='Confidence Interval'
                    ))
                    fig_forecast.update_layout(title="Revenue Forecast (Next 3 Months)", xaxis_title="Date", yaxis_title="Revenue (SAR)")
                    st.plotly_chart(fig_forecast, use_container_width=True)
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
        top_camp = top_campaigns(filtered_df, 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)')
        if not top_camp.empty:
            best_camp = top_camp.iloc[0]['Campaign Name']
            st.success(f"🚀 **Top Performer:** {best_camp} - Allocate more budget here!")
            underperformers = top_camp.tail(3)['Campaign Name'].tolist()
            st.warning(f"⚠️ **Underperformers:** {', '.join(underperformers)} - Consider pausing or optimizing.")
        
        # ROI Analysis
        st.subheader("💰 ROI Analysis")
        rev_col_roi = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
        roi_df = filtered_df.groupby('Channel').agg({
            rev_col_roi: 'sum',
            'Sent': 'sum',
            'Campaign Cost': 'sum',
        }).reset_index()
        roi_df = roi_df.rename(columns={'Campaign Cost': 'Cost (SAR)', rev_col_roi: 'Revenue (SAR)'})
        roi_df['Profit (SAR)'] = roi_df['Revenue (SAR)'] - roi_df['Cost (SAR)']
        roi_df['ROAS'] = np.where(roi_df['Cost (SAR)'] > 0, roi_df['Revenue (SAR)'] / roi_df['Cost (SAR)'], 0)
        roi_df['Revenue Per Send'] = np.where(roi_df['Sent'] > 0, roi_df['Revenue (SAR)'] / roi_df['Sent'], 0)

        # Format for display
        roi_display = roi_df.copy()
        for col in ['Revenue (SAR)', 'Cost (SAR)', 'Profit (SAR)']:
            roi_display[col] = roi_display[col].apply(lambda x: format_metric(x, "SAR"))
        roi_display['Sent'] = roi_display['Sent'].apply(format_metric)
        roi_display['ROAS'] = roi_display['ROAS'].apply(lambda x: f"{x:.2f}x")
        roi_display['Revenue Per Send'] = roi_display['Revenue Per Send'].apply(lambda x: f"{x:.4f} SAR")
        st.dataframe(roi_display, use_container_width=True)

        # ROI chart
        fig_roi = px.bar(roi_df, x='Channel', y=['Revenue (SAR)', 'Cost (SAR)'], barmode='group',
                         title="Revenue vs Cost by Channel", color_discrete_sequence=[COLORS['success'], COLORS['danger']])
        st.plotly_chart(fig_roi, use_container_width=True)

        # Dynamic Actionable Recommendations
        st.subheader("📋 Actionable Recommendations")
        # Generate recommendations based on actual data
        _recs = []
        if not roi_df.empty:
            best_roas_ch = roi_df.loc[roi_df['ROAS'].idxmax(), 'Channel'] if roi_df['ROAS'].max() > 0 else None
            best_rps_ch = roi_df.loc[roi_df['Revenue Per Send'].idxmax(), 'Channel'] if roi_df['Revenue Per Send'].max() > 0 else None
            highest_cost_ch = roi_df.loc[roi_df['Cost (SAR)'].idxmax(), 'Channel'] if roi_df['Cost (SAR)'].max() > 0 else None

            if best_roas_ch:
                _recs.append(f"- **Scale {best_roas_ch}:** Highest ROAS ({roi_df.loc[roi_df['Channel']==best_roas_ch, 'ROAS'].values[0]:.1f}x) - consider increasing budget")
            if best_rps_ch and best_rps_ch != best_roas_ch:
                _recs.append(f"- **Leverage {best_rps_ch}:** Best revenue per send - efficient at converting messages to revenue")
            if highest_cost_ch:
                cost_ch_roas = roi_df.loc[roi_df['Channel']==highest_cost_ch, 'ROAS'].values[0]
                if cost_ch_roas < 2:
                    _recs.append(f"- **Optimize {highest_cost_ch}:** Highest cost channel with ROAS of only {cost_ch_roas:.1f}x - review targeting and content")

        # Add data-driven segment and campaign recommendations
        if 'Selected Conversions' in filtered_df.columns:
            ch_conv = filtered_df.groupby('Channel')['Selected Conversions'].sum()
            low_conv_channels = ch_conv[ch_conv > 0].nsmallest(2).index.tolist()
            if low_conv_channels:
                _recs.append(f"- **Improve conversion on {', '.join(low_conv_channels)}:** Low conversion volume - test different CTAs and offers")

        _recs.append("- **A/B test creatives:** For campaigns with below-average CTR")
        _recs.append("- **Monitor forecasts:** Use revenue predictions above for budget planning")

        st.markdown("\n".join(_recs))

else:
    st.write("Please upload a CSV file.")