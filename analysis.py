"""
Core analysis functions for campaigns, journeys, channels, and metrics.
Provides data aggregation, ranking, and cross-dimensional analysis.
"""

import pandas as pd
import numpy as np
from utils import metric_aggregation_method


def top_campaigns(df, metric='Unique Conversions', top_n=10):
    """
    Get top campaigns by specified metric.
    
    Args:
        df: DataFrame with campaign data
        metric: Metric column to rank by
        top_n: Number of top campaigns to return
    
    Returns:
        DataFrame with top campaigns
    """
    # Conversion Rate: weighted sum(click-through conversions) / sum(clicks).
    # We use Unique Click-Through Conversions when available because Unique Conversions
    # includes impression-through conversions and can exceed Unique Clicks (causing 100% cap).
    if metric == 'Conversion Rate' and 'Unique Clicks' in df.columns:
        conv_col = 'Unique Click-Through Conversions' if 'Unique Click-Through Conversions' in df.columns else 'Unique Conversions'
        grouped = df.groupby('Campaign Name')[[conv_col, 'Unique Clicks']].sum()
        grouped['Conversion Rate'] = np.where(
            grouped['Unique Clicks'] > 0,
            grouped[conv_col] / grouped['Unique Clicks'],
            0.0,
        )
        return grouped['Conversion Rate'].nlargest(top_n).reset_index()

    agg = metric_aggregation_method(metric)
    return df.groupby('Campaign Name')[metric].agg(agg).nlargest(top_n).reset_index()


def get_top_journeys(df, metric='Delivered Rate', top_n=10):
    """
    Get top journeys by specified metric.

    Args:
        df: DataFrame with journey data
        metric: Metric column to rank by
        top_n: Number of top journeys to return

    Returns:
        DataFrame with top journeys
    """
    agg = metric_aggregation_method(metric)
    df_filtered = df[df['Journey Name'].notna() & (df['Journey Name'] != 'nan') & (df['Journey Name'] != '')]
    if df_filtered.empty:
        return pd.DataFrame(columns=['Journey Name', metric])
    return df_filtered.groupby('Journey Name')[metric].agg(agg).nlargest(top_n).reset_index()


def top_segments(df, metric='Unique Conversions', top_n=10):
    """
    Get top segments by specified metric.

    Args:
        df: DataFrame with segment data
        metric: Metric column to rank by
        top_n: Number of top segments to return

    Returns:
        DataFrame with top segments
    """
    agg = metric_aggregation_method(metric)
    df_filtered = df[df['Segment Name'].notna() & (df['Segment Name'] != 'nan') & (df['Segment Name'] != '')]
    if df_filtered.empty:
        return pd.DataFrame(columns=['Segment Name', metric])
    return df_filtered.groupby('Segment Name')[metric].agg(agg).nlargest(top_n).reset_index()


def channel_analysis(df):
    """
    Perform aggregated analysis across channels.
    
    Args:
        df: DataFrame with channel data
    
    Returns:
        DataFrame with channel-level aggregations
    """
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
    if 'Revenue (SAR)' in df.columns:
        agg_dict['Revenue (SAR)'] = 'sum'
    
    # Keep original columns for reference but they won't be displayed by default
    if 'Click-Through Revenue (SAR)' in df.columns:
        agg_dict['Click-Through Revenue (SAR)'] = 'sum'
    if 'Impression-Through Revenue (SAR)' in df.columns:
        agg_dict['Impression-Through Revenue (SAR)'] = 'sum'
    if 'Unique Click-Through Conversions' in df.columns:
        agg_dict['Unique Click-Through Conversions'] = 'sum'

    result = df.groupby('Channel').agg(agg_dict).reset_index()

    # Safety: fill NaN with 0 for attribution-aware columns. When the user selects
    # Click-Through or Impression-Through conversion attribution and the source CSV
    # has those columns (but with only 0/NaN values), groupby().sum() can produce NaN
    # for per-channel rows, which ag-Grid's JS formatter renders as blank cells while
    # the Total row (computed via the renamed display column's .sum()) still shows
    # a value because pandas .sum(skipna=True) handles NaN differently.
    if 'Selected Conversions' in result.columns:
        result['Selected Conversions'] = result['Selected Conversions'].fillna(0)
    if 'Selected Revenue (SAR)' in result.columns:
        result['Selected Revenue (SAR)'] = result['Selected Revenue (SAR)'].fillna(0)

    # Calculate AOV using selected metrics
    if 'Selected Revenue (SAR)' in result.columns and 'Selected Conversions' in result.columns:
        result['AOV (SAR)'] = np.where(
            result['Selected Conversions'] > 0,
            result['Selected Revenue (SAR)'] / result['Selected Conversions'], 0
        )

    return result


def time_series_analysis(df, metric='Unique Conversions'):
    """
    Generate time series data for a metric.
    
    Args:
        df: DataFrame with time series data
        metric: Metric column to analyze
    
    Returns:
        DataFrame with time series aggregation
    """
    df_ts = df.groupby('Reporting Period Start Date')[metric].sum().reset_index()
    return df_ts


def failed_reasons_analysis(df):
    """
    Analyze reasons for message failures.
    
    Args:
        df: DataFrame with failure reason columns
    
    Returns:
        DataFrame with failure reason counts
    """
    # Exclude 'Failed' and 'Failed Rate' columns - only include specific failure reasons
    failed_cols = [col for col in df.columns if 'Failed' in col and col not in ['Failed', 'Failed Rate']]
    if failed_cols:
        return df[failed_cols].sum().reset_index().rename(columns={'index': 'Reason', 0: 'Count'})
    return pd.DataFrame()


def esp_analysis(df):
    """
    Analyze performance by ESP/SSP/WSP/RSP provider.

    Args:
        df: DataFrame with ESP data

    Returns:
        DataFrame with ESP-level aggregations
    """
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

    if 'Total Conversions' in df_filtered.columns:
        agg_dict['Total Conversions'] = 'sum'
    if 'Selected Revenue (SAR)' in df_filtered.columns:
        agg_dict['Selected Revenue (SAR)'] = 'sum'
    elif 'Revenue (SAR)' in df_filtered.columns:
        agg_dict['Revenue (SAR)'] = 'sum'

    if 'Click-Through Revenue (SAR)' in df_filtered.columns:
        agg_dict['Click-Through Revenue (SAR)'] = 'sum'
    if 'Impression-Through Revenue (SAR)' in df_filtered.columns:
        agg_dict['Impression-Through Revenue (SAR)'] = 'sum'

    result = df_filtered.groupby('ESP/SSP/WSP/RSP name').agg(agg_dict).reset_index()
    # Safety: fill NaN with 0 for attribution-aware columns
    if 'Selected Conversions' in result.columns:
        result['Selected Conversions'] = result['Selected Conversions'].fillna(0)
    if 'Selected Revenue (SAR)' in result.columns:
        result['Selected Revenue (SAR)'] = result['Selected Revenue (SAR)'].fillna(0)
    return result


def ab_testing_analysis(df):
    """
    Calculate lift and statistical significance for A/B tested campaigns.
    
    Args:
        df: DataFrame with campaign data including control group columns
    
    Returns:
        DataFrame with A/B test results including lift and p-values
    """
    df_ab = df[df['Total in Control Group'] > 0].copy()
    if not df_ab.empty:
        # One test per campaign: the daily export repeats each campaign as a row
        # per day, and z-testing single days invites cherry-picking. Summing both
        # arms' daily counts keeps the test and control denominators consistent.
        df_ab = df_ab.groupby('Campaign Name', as_index=False).agg({
            'Sent': 'sum',
            'Unique Conversions': 'sum',
            'Total in Control Group': 'sum',
            'Unique Control Group Conversions': 'sum',
        })
        df_ab['Test Conversion Rate'] = np.where(df_ab['Sent'] > 0, df_ab['Unique Conversions'] / df_ab['Sent'], np.nan)
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
    """
    Summarize conversion attribution by source.

    Click-Through, Impression-Through, and Unique (Total/send-through)
    Conversions are separate, HIERARCHICAL attribution windows over the same
    conversion events -- not independent, additive counts. Every row in the
    underlying data satisfies Click-Through <= Impression-Through <= Unique
    Conversions (a click implies an impression; any attributed conversion
    counts toward the broader send-through total). Subtracting them naively
    (Total - Impression - Click) double-counts the Click-Through slice and
    goes negative whenever a campaign's own IT/CT share is large. This
    mirrors the same hierarchy already handled correctly for revenue in
    dashboard.lifecycle.create_revenue_attribution_waterfall().

    Args:
        df: DataFrame with attribution columns

    Returns:
        DataFrame with attribution breakdown (Click-Through, Impression-Only,
        Send-Only), each mutually exclusive and non-negative by construction.
    """
    total = df['Unique Conversions'].sum()
    impression = df['Unique Impression-Through Conversions'].sum()
    click = df['Unique Click-Through Conversions'].sum()

    attr = {
        'Click-Through': click,
        'Impression-Only': impression - click,
        'Send-Only': total - impression,
    }
    return pd.DataFrame(list(attr.items()), columns=['Source', 'Conversions'])
