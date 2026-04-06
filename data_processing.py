"""
Data processing and cleaning functions.
Handles data type conversion, metric calculation, and data validation.
"""

import pandas as pd
import numpy as np
from config import CHANNEL_COSTS


def clean_data(df):
    """
    Clean and prepare raw data for analysis.
    
    Performs:
    - Date column conversion
    - Numeric type conversion
    - Percentage handling
    - Revenue column parsing
    - Calculated metric generation
    - Cost-based metric calculation
    
    Args:
        df: Raw DataFrame from CSV
    
    Returns:
        Cleaned DataFrame with calculated metrics
    """
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
            # Values without '%' - check if they're already decimals (< 1) or raw percentages (>= 1)
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
    
    # NOTE: Revenue columns represent different attribution models - NOT additive!
    # Revenue (SAR) = Send-through (total attribution)
    # Impression-Through Revenue (SAR) = Impression attribution only  
    # Click-Through Revenue (SAR) = Click attribution only
    # These are hierarchical/overlapping, not meant to be summed
    
    # === ENGAGEMENT METRICS ===
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
    
    # === REVENUE METRICS ===
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
