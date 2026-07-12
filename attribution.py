"""
Centralized revenue and conversion attribution logic
Ensures consistent attribution application across all charts, tables, and metrics
"""

import pandas as pd
from config import REVENUE_ATTRIBUTION_LABELS, CONVERSION_ATTRIBUTION_LABELS


def apply_attribution(df, revenue_attribution, conversion_attribution):
    """
    Map selected attribution model to 'Selected Revenue/Conversions' columns.
    This is the single source of truth for attribution across the entire dashboard.
    
    Args:
        df: DataFrame to apply attribution to
        revenue_attribution: One of "Total", "Click-Through", "Impression-Through"
        conversion_attribution: One of "Total", "Click-Through", "Impression-Through"
    
    Returns:
        DataFrame with 'Selected Revenue (SAR)' and 'Selected Conversions' columns added
    """
    # Apply revenue attribution
    if 'Revenue (SAR)' in df.columns:
        if revenue_attribution == "Click-Through" and 'Click-Through Revenue (SAR)' in df.columns:
            df['Selected Revenue (SAR)'] = df['Click-Through Revenue (SAR)']
        elif revenue_attribution == "Impression-Through" and 'Impression-Through Revenue (SAR)' in df.columns:
            df['Selected Revenue (SAR)'] = df['Impression-Through Revenue (SAR)']
        else:
            df['Selected Revenue (SAR)'] = df['Revenue (SAR)']
    else:
        df['Selected Revenue (SAR)'] = 0

    # Apply conversion attribution
    if 'Unique Conversions' in df.columns:
        if conversion_attribution == "Click-Through" and 'Unique Click-Through Conversions' in df.columns:
            df['Selected Conversions'] = df['Unique Click-Through Conversions'].fillna(0)
        elif conversion_attribution == "Impression-Through" and 'Unique Impression-Through Conversions' in df.columns:
            df['Selected Conversions'] = df['Unique Impression-Through Conversions'].fillna(0)
        else:
            df['Selected Conversions'] = df['Unique Conversions'].fillna(0)
    else:
        df['Selected Conversions'] = 0

    # Guard: ensure Selected columns are always numeric (never NaN) at the source.
    for _col in ['Selected Revenue (SAR)', 'Selected Conversions']:
        if _col in df.columns:
            df[_col] = pd.to_numeric(df[_col], errors='coerce').fillna(0)

    return df


def apply_dimension_filters(df, channels, campaign_types, campaigns, segments, journeys, conversion_events=None):
    """Apply sidebar dimension filters."""
    if channels:
        df = df[df['Channel'].isin(channels)]
    if campaign_types and 'Type of Campaign' in df.columns:
        df = df[df['Type of Campaign'].isin(campaign_types)]
    if campaigns:
        df = df[df['Campaign Name'].isin(campaigns)]
    if segments:
        df = df[df['Segment Name'].isin(segments)]
    if journeys:
        df = df[df['Journey Name'].isin(journeys)]
    if conversion_events and 'Conversion Event' in df.columns:
        df = df[df['Conversion Event'].isin(conversion_events)]
    return df


def get_attribution_display_label(col_name, revenue_attribution, conversion_attribution):
    """
    Map internal 'Selected Revenue/Conversions' column names to user-selected attribution labels.
    """
    rev_label = REVENUE_ATTRIBUTION_LABELS.get(revenue_attribution, "Selected Revenue (SAR)")
    conv_label = CONVERSION_ATTRIBUTION_LABELS.get(conversion_attribution, "Selected Conversions")
    
    attribution_rename = {
        'Selected Revenue (SAR)': rev_label,
        'Selected Conversions': conv_label
    }
    return attribution_rename.get(col_name, col_name)


def get_selected_revenue_display_name(revenue_attribution):
    """
    Get the display name for the currently selected revenue attribution.
    Returns the actual revenue column name (e.g., 'Click-Through Revenue (SAR)') 
    instead of the generic 'Selected Revenue (SAR)'.
    """
    return REVENUE_ATTRIBUTION_LABELS.get(revenue_attribution, "Revenue (SAR)")


def get_selected_conversion_display_name(conversion_attribution):
    """
    Get the display name for the currently selected conversion attribution.
    Returns the actual conversion column name (e.g., 'Click-Through Conversions')
    instead of the generic 'Selected Conversions'.
    """
    return CONVERSION_ATTRIBUTION_LABELS.get(conversion_attribution, "Unique Conversions")


def resolve_source_column(display_col, revenue_attribution, conversion_attribution):
    """Map display column names back to canonical source columns."""
    selected_rev_display = get_selected_revenue_display_name(revenue_attribution)
    selected_conv_display = get_selected_conversion_display_name(conversion_attribution)

    if display_col == selected_rev_display:
        return 'Selected Revenue (SAR)'
    if display_col == selected_conv_display:
        return 'Selected Conversions'

    return display_col
