"""Anomaly detection for campaigns and journeys.

Extracted verbatim from app.py (Task 6 of the app.py modularization refactor).
"""
import pandas as pd
import numpy as np


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
