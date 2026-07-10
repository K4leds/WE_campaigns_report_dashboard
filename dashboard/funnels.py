"""Funnel-analysis calculations for campaigns and journeys.

Extracted verbatim from app.py (Task 5 of the app.py modularization refactor).
"""
import numpy as np
import pandas as pd


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
