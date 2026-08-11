"""
Automated Insights Engine for WebEngage Dashboard
Generates narrative insights, predictions, and actionable recommendations
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
try:
    from prophet import Prophet
except ImportError:
    Prophet = None
import logging
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

# Minimum Sent volume for a channel to be eligible for its own alerts/opportunities/
# actions -- avoids flagging noise on a client's low-volume test channel.
CHANNEL_MIN_SENT = 200

# A channel returning more than this many SAR per SAR spent almost certainly has
# missing/partial cost data (e.g. a token default cost), not a real result.
# Above this we treat ROAS as unreliable rather than print an absurd figure on a
# client slide.
ROAS_SANITY_CEILING = 50.0


def _approx_ramadan_month(year):
    """
    Approximate the Gregorian month in which Ramadan starts for a given year.
    Ramadan shifts ~11 days earlier each Gregorian year.
    Reference point: Ramadan 2025 starts ~March 1 (month 3).
    """
    from datetime import date
    # Approximate start date of Ramadan 2025: March 1
    ref_year = 2025
    ref_start = date(2025, 3, 1)
    years_diff = year - ref_year
    # Shift ~10.63 days earlier per year (average Hijri drift)
    approx_start = date(ref_start.year, ref_start.month, ref_start.day)
    shift_days = int(round(years_diff * 10.63))
    try:
        approx_start = ref_start - timedelta(days=shift_days)
        # Adjust year if it wraps
        approx_start = approx_start.replace(year=year)
    except ValueError:
        # Handle edge cases (e.g., Feb 29)
        approx_start = ref_start.replace(year=year, day=min(ref_start.day, 28))
        approx_start = approx_start - timedelta(days=shift_days % 365)
    return approx_start.month


def generate_narrative_insights(df, journey_name=None, lookback_days=30):
    """
    Generate human-readable narrative insights automatically
    Mimics the style from user's example presentation slides
    
    Args:
        df: Cleaned WebEngage dataframe
        journey_name: Specific journey to analyze (None for overall)
        lookback_days: Number of days to look back for analysis
        
    Returns:
        dict with narrative insights, trends, and context
    """
    insights = {
        'headline_insights': [],
        'trend_analysis': [],
        'performance_alerts': [],
        'opportunities': [],
        'context_notes': []
    }
    
    try:
        df = df.copy()  # Avoid mutating caller's DataFrame

        # Ensure date column exists
        if 'Reporting Period Start Date' in df.columns:
            df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
        elif 'Day' in df.columns:
            df['date'] = pd.to_datetime(df['Day'])
        else:
            return insights

        # Filter by journey if specified
        if journey_name:
            df = df[df['Journey Name'] == journey_name]
            context = f"Journey: {journey_name}"
        else:
            context = "Overall Portfolio"
        
        # Get recent data
        cutoff_date = df['date'].max() - pd.Timedelta(days=lookback_days)
        recent_df = df[df['date'] >= cutoff_date]
        older_df = df[df['date'] < cutoff_date]
        
        if recent_df.empty or older_df.empty:
            return insights
        
        # Calculate key metrics
        recent_revenue = recent_df['Revenue (SAR)'].sum() if 'Revenue (SAR)' in recent_df.columns else 0
        older_revenue = older_df['Revenue (SAR)'].sum() if 'Revenue (SAR)' in older_df.columns else 0
        
        recent_conversions = recent_df['Unique Conversions'].sum() if 'Unique Conversions' in recent_df.columns else 0
        older_conversions = older_df['Unique Conversions'].sum() if 'Unique Conversions' in older_df.columns else 0
        
        # Normalize for time period differences
        recent_days = (recent_df['date'].max() - recent_df['date'].min()).days + 1
        older_days = (older_df['date'].max() - older_df['date'].min()).days + 1
        
        recent_daily_revenue = recent_revenue / recent_days if recent_days > 0 else 0
        older_daily_revenue = older_revenue / older_days if older_days > 0 else 0
        
        # === HEADLINE INSIGHTS ===
        if recent_daily_revenue > 0 and older_daily_revenue > 0:
            revenue_change_pct = ((recent_daily_revenue - older_daily_revenue) / older_daily_revenue) * 100
            
            if revenue_change_pct > 20:
                insights['headline_insights'].append({
                    'emoji': '🚀',
                    'title': 'Strong Revenue Growth',
                    'message': f"Revenue up {revenue_change_pct:+.1f}% vs previous period, averaging {format_sar(recent_daily_revenue)}/day",
                    'severity': 'positive'
                })
            elif revenue_change_pct < -20:
                insights['headline_insights'].append({
                    'emoji': '⚠️',
                    'title': 'Revenue Decline Detected',
                    'message': f"Revenue down {revenue_change_pct:.1f}% vs previous period. This decline may suggest {detect_decline_reason(df, recent_df)}",
                    'severity': 'critical'
                })
            elif abs(revenue_change_pct) <= 10:
                insights['headline_insights'].append({
                    'emoji': '➡️',
                    'title': 'Stable Performance',
                    'message': f"Revenue stable at {format_sar(recent_daily_revenue)}/day (±{abs(revenue_change_pct):.1f}%)",
                    'severity': 'neutral'
                })
        
        # === TREND ANALYSIS (Like the image: "Gradual Recovery") ===
        trend_insight = analyze_recovery_or_decline_pattern(df)
        if trend_insight:
            insights['trend_analysis'].append(trend_insight)
        
        # === PERFORMANCE ALERTS ===
        alerts = detect_performance_alerts(df, recent_df)
        insights['performance_alerts'].extend(alerts)
        insights['performance_alerts'].extend(detect_channel_performance_alerts(df, recent_df))

        # === OPPORTUNITIES ===
        opportunities = identify_optimization_opportunities(df, recent_df)
        insights['opportunities'].extend(opportunities)
        insights['opportunities'].extend(identify_channel_optimization_opportunities(df, recent_df))
        
        # === CONTEXT NOTES (Seasonality, Events) ===
        context_notes = add_business_context(df)
        insights['context_notes'].extend(context_notes)
        
    except Exception as e:
        insights['headline_insights'].append({
            'emoji': 'ℹ️',
            'title': 'Analysis Note',
            'message': f"Partial insights generated: {str(e)}",
            'severity': 'info'
        })
    
    return insights


def analyze_recovery_or_decline_pattern(df):
    """
    Detect recovery or decline patterns in time series
    Similar to: "Gradual Recovery: In May and April revenue is now above February level"
    """
    try:
        if 'date' not in df.columns or 'Revenue (SAR)' not in df.columns:
            return None

        df = df.copy()  # Avoid mutating caller's DataFrame
        # Get monthly aggregates
        df['month'] = pd.to_datetime(df['date']).dt.to_period('M')
        monthly_revenue = df.groupby('month')['Revenue (SAR)'].sum().sort_index()
        
        if len(monthly_revenue) < 3:
            return None
        
        # Get last 3 months
        recent_months = monthly_revenue.tail(3)
        month_names = [m.strftime('%B') for m in recent_months.index.to_timestamp()]
        revenues = recent_months.values
        
        # Check for recovery pattern (increasing trend)
        if revenues[-1] > revenues[-2] > revenues[-3]:
            return {
                'emoji': '📈',
                'title': 'Gradual Recovery Detected',
                'message': f"Revenue is recovering: {month_names[-1]} ({format_sar(revenues[-1])}) > {month_names[-2]} ({format_sar(revenues[-2])}) > {month_names[-3]} ({format_sar(revenues[-3])})",
                'severity': 'positive',
                'detail': f"Current trajectory shows sustained improvement over the past 3 months"
            }
        
        # Check for decline pattern
        elif revenues[-1] < revenues[-2] < revenues[-3]:
            return {
                'emoji': '📉',
                'title': 'Progressive Decline',
                'message': f"Revenue declining across {month_names[-3]}-{month_names[-1]}: {format_sar(revenues[-3])} → {format_sar(revenues[-2])} → {format_sar(revenues[-1])}",
                'severity': 'warning',
                'detail': f"Sustained downward trend requires immediate investigation"
            }
        
        # Check for V-shaped recovery (drop then recovery)
        elif revenues[-1] > revenues[-2] and revenues[-2] < revenues[-3]:
            recovery_pct = ((revenues[-1] - revenues[-2]) / revenues[-2]) * 100
            
            # Check if fully recovered vs initial level
            if revenues[-1] > revenues[-3]:
                vs_initial = ((revenues[-1] - revenues[-3]) / revenues[-3]) * 100
                level_text = f"now {vs_initial:.1f}% above {month_names[-3]} levels"
            elif revenues[-1] >= revenues[-3] * 0.95:  # Within 5% of initial
                level_text = f"now back to {month_names[-3]} levels"
            else:
                gap = ((revenues[-3] - revenues[-1]) / revenues[-3]) * 100
                level_text = f"now approaching {month_names[-3]} levels (still {gap:.1f}% below)"
            
            return {
                'emoji': '↗️',
                'title': 'V-Shaped Recovery',
                'message': f"{month_names[-1]} revenue recovered {recovery_pct:+.1f}% after {month_names[-2]} dip, {level_text}",
                'severity': 'positive',
                'detail': f"Quick recovery from temporary decline is a positive signal"
            }
        
    except Exception as e:
        return None
    
    return None


def detect_decline_reason(df, recent_df):
    """
    Automatically detect potential reasons for revenue decline
    Similar to: "lack of sustained engagement after the month of Ramadan"
    """
    reasons = []
    
    try:
        # Check engagement metrics
        if 'Unique Clicks' in recent_df.columns and 'Unique Impressions' in recent_df.columns:
            recent_ctr = recent_df['Unique Clicks'].sum() / max(recent_df['Unique Impressions'].sum(), 1)
            overall_ctr = df['Unique Clicks'].sum() / max(df['Unique Impressions'].sum(), 1)
            
            if recent_ctr < overall_ctr * 0.8:
                reasons.append("lack of sustained engagement")
        
        # Check delivery issues
        if 'Delivered' in recent_df.columns and 'Sent' in recent_df.columns:
            recent_delivery_rate = recent_df['Delivered'].sum() / max(recent_df['Sent'].sum(), 1)
            overall_delivery_rate = df['Delivered'].sum() / max(df['Sent'].sum(), 1)
            
            if recent_delivery_rate < overall_delivery_rate * 0.9:
                reasons.append("delivery rate deterioration")
        
        # Check for volume decline
        recent_sent = recent_df['Sent'].sum() if 'Sent' in recent_df.columns else 0
        overall_avg_sent = df['Sent'].sum() / max(len(df), 1)
        
        if recent_sent < overall_avg_sent * 0.7:
            reasons.append("reduced campaign activity")
        
        # Check seasonality - approximate Ramadan month for the data year
        # Ramadan shifts ~11 days earlier each Gregorian year
        # Reference: Ramadan 2025 starts ~Feb 28. Adjust by -11 days/year from there.
        current_date = recent_df['date'].max()
        ramadan_month = _approx_ramadan_month(current_date.year)
        post_ramadan_month = ramadan_month + 1 if ramadan_month < 12 else 1
        if current_date.month in [post_ramadan_month]:
            reasons.append("post-Ramadan seasonal effect")
        
    except Exception as e:
        logger.warning(f"detect_decline_reason failed: {e}")

    return reasons[0] if reasons else "various performance factors"


def detect_performance_alerts(df, recent_df):
    """
    Detect critical performance issues requiring immediate attention
    """
    alerts = []
    
    try:
        # Delivery rate alert
        if 'Delivered' in recent_df.columns and 'Sent' in recent_df.columns:
            recent_delivery = recent_df['Delivered'].sum() / max(recent_df['Sent'].sum(), 1)
            if recent_delivery < 0.85:
                alerts.append({
                    'emoji': '🚨',
                    'title': 'Delivery Issue Detected',
                    'message': f"Delivery rate dropped to {recent_delivery:.1%} (target: >90%). Investigate sender reputation and authentication.",
                    'severity': 'critical',
                    'action': 'Review ESP settings, check blocklists, verify DKIM/SPF'
                })
        
        # Conversion rate alert
        if 'Unique Conversions' in recent_df.columns and 'Unique Clicks' in recent_df.columns:
            recent_conv_rate = recent_df['Unique Conversions'].sum() / max(recent_df['Unique Clicks'].sum(), 1)
            overall_conv_rate = df['Unique Conversions'].sum() / max(df['Unique Clicks'].sum(), 1)
            
            if recent_conv_rate < overall_conv_rate * 0.7:
                decline_pct = ((recent_conv_rate - overall_conv_rate) / overall_conv_rate) * 100
                alerts.append({
                    'emoji': '⚠️',
                    'title': 'Conversion Rate Decline',
                    'message': f"Conversion rate down {abs(decline_pct):.1f}% vs historical average. Landing page or offer may need optimization.",
                    'severity': 'warning',
                    'action': 'A/B test landing page elements, review offer relevance'
                })
        
        # Engagement alert. Guard on actual impressions (not maxed to 1): channels
        # without impression tracking (e.g. SMS) would otherwise divide clicks by a
        # floored denominator of 1, producing nonsense rates like "94900%".
        if ('Unique Clicks' in recent_df.columns and 'Unique Impressions' in recent_df.columns
                and recent_df['Unique Impressions'].sum() > 0 and df['Unique Impressions'].sum() > 0):
            recent_ctr = recent_df['Unique Clicks'].sum() / recent_df['Unique Impressions'].sum()
            overall_ctr = df['Unique Clicks'].sum() / df['Unique Impressions'].sum()

            if recent_ctr < overall_ctr * 0.6:
                alerts.append({
                    'emoji': '📉',
                    'title': 'Engagement Fatigue',
                    'message': f"CTR significantly below normal ({recent_ctr:.2%} vs {overall_ctr:.2%}). Audience may be experiencing creative fatigue.",
                    'severity': 'warning',
                    'action': 'Refresh creative assets, test new messaging, expand audience'
                })
        
    except Exception as e:
        logger.warning(f"detect_performance_alerts failed: {e}")

    return alerts


def detect_channel_performance_alerts(df, recent_df):
    """
    Per-channel version of detect_performance_alerts -- same thresholds, scoped to
    each channel present in the data (with enough volume to be meaningful), so a
    client-specific channel mix surfaces client-specific alerts instead of only
    portfolio-wide ones.
    """
    alerts = []

    if 'Channel' not in recent_df.columns:
        return alerts

    try:
        channel_volumes = recent_df.groupby('Channel')['Sent'].sum() if 'Sent' in recent_df.columns else pd.Series(dtype=float)
        eligible_channels = channel_volumes[channel_volumes >= CHANNEL_MIN_SENT].index

        for channel in eligible_channels:
            chan_recent = recent_df[recent_df['Channel'] == channel]
            chan_all = df[df['Channel'] == channel]

            # Delivery rate alert
            if 'Delivered' in chan_recent.columns and 'Sent' in chan_recent.columns:
                recent_delivery = chan_recent['Delivered'].sum() / max(chan_recent['Sent'].sum(), 1)
                if recent_delivery < 0.85:
                    alerts.append({
                        'emoji': '🚨',
                        'title': f'{channel} Delivery Issue',
                        'message': f"{channel} delivery rate dropped to {recent_delivery:.1%} (target: >90%). Investigate sender reputation and authentication.",
                        'severity': 'critical',
                        'action': f'Review {channel} ESP settings, check blocklists, verify authentication',
                        'scope': 'channel',
                        'channel': channel,
                    })

            # Conversion rate alert
            if 'Unique Conversions' in chan_recent.columns and 'Unique Clicks' in chan_recent.columns:
                recent_conv_rate = chan_recent['Unique Conversions'].sum() / max(chan_recent['Unique Clicks'].sum(), 1)
                overall_conv_rate = chan_all['Unique Conversions'].sum() / max(chan_all['Unique Clicks'].sum(), 1)

                if overall_conv_rate > 0 and recent_conv_rate < overall_conv_rate * 0.7:
                    decline_pct = ((recent_conv_rate - overall_conv_rate) / overall_conv_rate) * 100
                    alerts.append({
                        'emoji': '⚠️',
                        'title': f'{channel} Conversion Rate Decline',
                        'message': f"{channel} conversion rate down {abs(decline_pct):.1f}% vs its historical average. Landing page or offer may need optimization.",
                        'severity': 'warning',
                        'action': f'A/B test {channel} landing page elements, review offer relevance',
                        'scope': 'channel',
                        'channel': channel,
                    })

            # Engagement alert. Guard on actual impressions (not maxed to 1): channels
            # without impression tracking (e.g. SMS) would otherwise divide clicks by a
            # floored denominator of 1, producing nonsense rates like "94900%".
            if ('Unique Clicks' in chan_recent.columns and 'Unique Impressions' in chan_recent.columns
                    and chan_recent['Unique Impressions'].sum() > 0 and chan_all['Unique Impressions'].sum() > 0):
                recent_ctr = chan_recent['Unique Clicks'].sum() / chan_recent['Unique Impressions'].sum()
                overall_ctr = chan_all['Unique Clicks'].sum() / chan_all['Unique Impressions'].sum()

                if overall_ctr > 0 and recent_ctr < overall_ctr * 0.6:
                    alerts.append({
                        'emoji': '📉',
                        'title': f'{channel} Engagement Fatigue',
                        'message': f"{channel} CTR significantly below its normal ({recent_ctr:.2%} vs {overall_ctr:.2%}). Audience may be experiencing creative fatigue.",
                        'severity': 'warning',
                        'action': f'Refresh {channel} creative assets, test new messaging',
                        'scope': 'channel',
                        'channel': channel,
                    })

    except Exception as e:
        logger.warning(f"detect_channel_performance_alerts failed: {e}")

    return alerts


def identify_optimization_opportunities(df, recent_df):
    """
    Identify specific, actionable optimization opportunities
    Similar to: "Add reminder blocks to the journey to encourage customers to redeem the code"
    """
    opportunities = []
    
    try:
        # Opportunity: High impressions, low clicks
        if 'Unique Impressions' in recent_df.columns and 'Unique Clicks' in recent_df.columns:
            impressions = recent_df['Unique Impressions'].sum()
            clicks = recent_df['Unique Clicks'].sum()
            ctr = clicks / max(impressions, 1)
            
            if impressions > 1000 and ctr < 0.02:  # Less than 2% CTR
                opportunities.append({
                    'emoji': '🎯',
                    'title': 'Creative Optimization Opportunity',
                    'message': f"Strong reach ({impressions:,.0f} impressions) but low engagement (CTR: {ctr:.2%})",
                    'severity': 'opportunity',
                    'action': 'Test new subject lines, preheaders, and visual elements',
                    'expected_impact': f"+{((0.03 - ctr) * impressions):,.0f} additional clicks at 3% CTR"
                })
        
        # Opportunity: High clicks, low conversions
        if 'Unique Clicks' in recent_df.columns and 'Unique Conversions' in recent_df.columns:
            clicks = recent_df['Unique Clicks'].sum()
            conversions = recent_df['Unique Conversions'].sum()
            conv_rate = conversions / max(clicks, 1)
            
            if clicks > 500 and conv_rate < 0.05:  # Less than 5% conversion
                opportunities.append({
                    'emoji': '🛒',
                    'title': 'Conversion Funnel Optimization',
                    'message': f"Good traffic ({clicks:,.0f} clicks) but low conversion (CR: {conv_rate:.2%})",
                    'severity': 'opportunity',
                    'action': 'Add reminder blocks, optimize landing page, reduce friction points',
                    'expected_impact': f"+{((0.08 - conv_rate) * clicks):,.0f} conversions at 8% CR"
                })
        
        # Opportunity: Stopped or low-activity journeys
        if 'Journey Name' in df.columns:
            journeys = df['Journey Name'].unique()
            for journey in journeys:
                if pd.isna(journey) or str(journey) == 'nan':
                    continue
                    
                journey_recent = recent_df[recent_df['Journey Name'] == journey]
                if len(journey_recent) == 0 or journey_recent['Sent'].sum() < 100:
                    journey_historical = df[df['Journey Name'] == journey]
                    if len(journey_historical) > 0 and journey_historical['Revenue (SAR)'].sum() > 10000:
                        opportunities.append({
                            'emoji': '💤',
                            'title': f'Inactive High-Value Journey',
                            'message': f"Journey '{journey}' was historically valuable but shows minimal recent activity",
                            'severity': 'opportunity',
                            'action': f"Reactivate or investigate why journey stopped",
                            'expected_impact': f"Potential recovery of previous revenue levels"
                        })
        
    except Exception as e:
        logger.warning(f"identify_optimization_opportunities failed: {e}")

    return opportunities


def identify_channel_optimization_opportunities(df, recent_df):
    """
    Per-channel version of identify_optimization_opportunities -- same thresholds,
    scoped to each channel present in the data (with enough volume to be
    meaningful).
    """
    opportunities = []

    if 'Channel' not in recent_df.columns:
        return opportunities

    try:
        channel_volumes = recent_df.groupby('Channel')['Sent'].sum() if 'Sent' in recent_df.columns else pd.Series(dtype=float)
        eligible_channels = channel_volumes[channel_volumes >= CHANNEL_MIN_SENT].index

        for channel in eligible_channels:
            chan_recent = recent_df[recent_df['Channel'] == channel]

            # High impressions, low clicks
            if 'Unique Impressions' in chan_recent.columns and 'Unique Clicks' in chan_recent.columns:
                impressions = chan_recent['Unique Impressions'].sum()
                clicks = chan_recent['Unique Clicks'].sum()
                ctr = clicks / max(impressions, 1)

                if impressions > 1000 and ctr < 0.02:
                    opportunities.append({
                        'emoji': '🎯',
                        'title': f'{channel} Creative Optimization Opportunity',
                        'message': f"{channel} has strong reach ({impressions:,.0f} impressions) but low engagement (CTR: {ctr:.2%})",
                        'severity': 'opportunity',
                        'action': f'Test new {channel} subject lines/creative and visual elements',
                        'expected_impact': f"+{((0.03 - ctr) * impressions):,.0f} additional clicks at 3% CTR",
                        'scope': 'channel',
                        'channel': channel,
                    })

            # High clicks, low conversions
            if 'Unique Clicks' in chan_recent.columns and 'Unique Conversions' in chan_recent.columns:
                clicks = chan_recent['Unique Clicks'].sum()
                conversions = chan_recent['Unique Conversions'].sum()
                conv_rate = conversions / max(clicks, 1)

                if clicks > 500 and conv_rate < 0.05:
                    opportunities.append({
                        'emoji': '🛒',
                        'title': f'{channel} Conversion Funnel Optimization',
                        'message': f"{channel} has good traffic ({clicks:,.0f} clicks) but low conversion (CR: {conv_rate:.2%})",
                        'severity': 'opportunity',
                        'action': f'Review the {channel} landing page/offer, reduce friction points',
                        'expected_impact': f"+{((0.08 - conv_rate) * clicks):,.0f} conversions at 8% CR",
                        'scope': 'channel',
                        'channel': channel,
                    })

    except Exception as e:
        logger.warning(f"identify_channel_optimization_opportunities failed: {e}")

    return opportunities


def add_business_context(df):
    """
    Add business context like seasonality, holidays, events
    Similar to noting "after the month of Ramadan"
    """
    context_notes = []
    
    try:
        if 'date' not in df.columns:
            return context_notes
        
        current_date = df['date'].max()
        current_month = current_date.month
        current_year = current_date.year

        # Ramadan context (dynamically calculated per year)
        ramadan_month = _approx_ramadan_month(current_year)
        post_ramadan_month = ramadan_month + 1 if ramadan_month < 12 else 1
        ramadan_adjacent = [ramadan_month, post_ramadan_month]
        if current_month in ramadan_adjacent:
            context_notes.append({
                'emoji': '🌙',
                'title': 'Seasonal Context: Ramadan/Eid Period',
                'message': 'Current period may be influenced by Ramadan/Eid shopping patterns and post-holiday adjustments',
                'severity': 'info'
            })
        
        # Year-end shopping
        elif current_month in [11, 12]:
            context_notes.append({
                'emoji': '🎄',
                'title': 'Seasonal Context: Year-End Shopping',
                'message': 'Peak shopping season - expect higher engagement and conversion rates',
                'severity': 'info'
            })
        
        # Summer slowdown
        elif current_month in [7, 8]:
            context_notes.append({
                'emoji': '☀️',
                'title': 'Seasonal Context: Summer Period',
                'message': 'Summer months typically show lower engagement due to vacation travel',
                'severity': 'info'
            })
        
    except Exception as e:
        logger.warning(f"add_business_context failed: {e}")

    return context_notes


def predict_revenue_forecast(df, journey_name=None, forecast_days=30):
    """
    Generate revenue predictions using Prophet
    
    Args:
        df: Cleaned WebEngage dataframe
        journey_name: Specific journey to forecast (None for overall)
        forecast_days: Number of days to forecast (7, 14, or 30)
        
    Returns:
        dict with forecast data and insights
    """
    try:
        if Prophet is None:
            return None

        df = df.copy()  # Avoid mutating caller's DataFrame

        # Ensure date column exists
        if 'Reporting Period Start Date' in df.columns:
            df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
        elif 'Day' in df.columns:
            df['date'] = pd.to_datetime(df['Day'])
        else:
            return None

        # Filter by journey if specified
        if journey_name:
            df = df[df['Journey Name'] == journey_name]
        
        if df.empty or len(df) < 14:  # Need at least 2 weeks of data
            return None
        
        # Prepare data for Prophet
        prophet_df = df.groupby('date')['Revenue (SAR)'].sum().reset_index()
        prophet_df.columns = ['ds', 'y']
        
        # Train Prophet model
        model = Prophet(
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=False,
            interval_width=0.95,
            changepoint_prior_scale=0.05
        )
        
        model.fit(prophet_df)
        
        # Create future dataframe
        future = model.make_future_dataframe(periods=forecast_days)
        forecast = model.predict(future)
        
        # Get forecast for future dates only
        forecast_future = forecast.tail(forecast_days)
        
        # Calculate summary statistics
        total_predicted_revenue = forecast_future['yhat'].sum()
        avg_daily_revenue = forecast_future['yhat'].mean()
        confidence_lower = forecast_future['yhat_lower'].sum()
        confidence_upper = forecast_future['yhat_upper'].sum()
        
        # Calculate trend
        historical_avg = prophet_df['y'].tail(forecast_days).mean()
        trend_pct = ((avg_daily_revenue - historical_avg) / historical_avg) * 100 if historical_avg > 0 else 0
        
        # Generate insight
        if trend_pct > 10:
            trend_insight = {
                'emoji': '📈',
                'message': f"Revenue projected to grow {trend_pct:+.1f}% over next {forecast_days} days",
                'severity': 'positive'
            }
        elif trend_pct < -10:
            trend_insight = {
                'emoji': '📉',
                'message': f"Revenue projected to decline {abs(trend_pct):.1f}% over next {forecast_days} days - take preemptive action",
                'severity': 'warning'
            }
        else:
            trend_insight = {
                'emoji': '➡️',
                'message': f"Revenue expected to remain stable over next {forecast_days} days",
                'severity': 'neutral'
            }
        
        return {
            'forecast_df': forecast_future[['ds', 'yhat', 'yhat_lower', 'yhat_upper']],
            'total_predicted': total_predicted_revenue,
            'daily_average': avg_daily_revenue,
            'confidence_lower': confidence_lower,
            'confidence_upper': confidence_upper,
            'trend_pct': trend_pct,
            'insight': trend_insight,
            'forecast_days': forecast_days
        }
        
    except Exception as e:
        return None


def generate_top_actions(df, journey_name=None, max_actions=5):
    """
    Generate prioritized, specific action recommendations
    
    Args:
        df: Cleaned WebEngage dataframe
        journey_name: Specific journey to analyze (None for overall)
        max_actions: Maximum number of actions to return
        
    Returns:
        list of prioritized actions with expected impact
    """
    actions = []
    
    try:
        df = df.copy()  # Avoid mutating caller's DataFrame

        # Filter by journey if specified
        if journey_name:
            df = df[df['Journey Name'] == journey_name]

        if df.empty:
            return actions

        # Ensure date column exists
        if 'Reporting Period Start Date' in df.columns:
            df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
        elif 'Day' in df.columns:
            df['date'] = pd.to_datetime(df['Day'])
        
        # Get recent data (last 30 days)
        cutoff_date = df['date'].max() - pd.Timedelta(days=30)
        recent_df = df[df['date'] >= cutoff_date]
        
        # Action 1: Budget reallocation to high-performers
        if 'Journey Name' in df.columns and not journey_name:
            journey_revenue = df.groupby('Journey Name').agg({
                'Revenue (SAR)': 'sum',
                'Sent': 'sum'
            }).reset_index()
            
            journey_revenue['ROI'] = journey_revenue['Revenue (SAR)'] / journey_revenue['Sent'].replace(0, 1)
            top_journey = journey_revenue.nlargest(1, 'ROI')
            
            if not top_journey.empty and top_journey['ROI'].iloc[0] > 0:
                top_name = top_journey['Journey Name'].iloc[0]
                top_revenue = top_journey['Revenue (SAR)'].iloc[0]
                expected_increase = top_revenue * 0.3  # 30% increase assumption
                
                actions.append({
                    'priority': 'HIGH',
                    'title': f'Scale High-ROI Journey',
                    'action': f"Increase budget by 30% on '{top_name}'",
                    'expected_impact': f"+{format_sar(expected_increase)}/month in revenue",
                    'confidence': '85%',
                    'implementation_time': '1-2 days',
                    'score': expected_increase
                })
        
        # Action 2: Delivery optimization
        if 'Delivered' in recent_df.columns and 'Sent' in recent_df.columns:
            recent_delivery_rate = recent_df['Delivered'].sum() / max(recent_df['Sent'].sum(), 1)
            if recent_delivery_rate < 0.9:
                failed_messages = recent_df['Sent'].sum() - recent_df['Delivered'].sum()
                potential_revenue = failed_messages * (recent_df['Revenue (SAR)'].sum() / max(recent_df['Delivered'].sum(), 1))
                
                actions.append({
                    'priority': 'HIGH',
                    'title': 'Fix Delivery Issues',
                    'action': f"Improve delivery rate from {recent_delivery_rate:.1%} to 95%+",
                    'expected_impact': f"+{format_sar(potential_revenue * 0.05)} in recovered revenue",
                    'confidence': '90%',
                    'implementation_time': '3-5 days',
                    'score': potential_revenue * 0.05
                })
        
        # Action 3: Engagement optimization
        if 'Unique Clicks' in recent_df.columns and 'Unique Impressions' in recent_df.columns:
            current_ctr = recent_df['Unique Clicks'].sum() / max(recent_df['Unique Impressions'].sum(), 1)
            if current_ctr < 0.03:
                impressions = recent_df['Unique Impressions'].sum()
                additional_clicks = impressions * (0.03 - current_ctr)
                # Assume some conversion and revenue per conversion
                conv_rate = recent_df['Unique Conversions'].sum() / max(recent_df['Unique Clicks'].sum(), 1) if 'Unique Conversions' in recent_df.columns else 0.05
                revenue_per_conv = recent_df['Revenue (SAR)'].sum() / max(recent_df['Unique Conversions'].sum(), 1) if 'Unique Conversions' in recent_df.columns else 100
                expected_revenue = additional_clicks * conv_rate * revenue_per_conv
                
                actions.append({
                    'priority': 'MEDIUM',
                    'title': 'Boost Engagement',
                    'action': 'A/B test subject lines and creative to improve CTR to 3%+',
                    'expected_impact': f"+{format_sar(expected_revenue)} in revenue from better engagement",
                    'confidence': '75%',
                    'implementation_time': '5-7 days',
                    'score': expected_revenue
                })
        
        # Action 4: Add reminder touchpoints
        if 'Journey Name' in df.columns and 'Unique Conversions' in df.columns:
            # Find journeys with high drop-off
            for journey in df['Journey Name'].unique():
                if pd.isna(journey) or str(journey) == 'nan':
                    continue
                
                journey_df = df[df['Journey Name'] == journey]
                clicks = journey_df['Unique Clicks'].sum() if 'Unique Clicks' in journey_df.columns else 0
                conversions = journey_df['Unique Conversions'].sum()
                
                if clicks > 100 and conversions > 0:
                    conv_rate = conversions / clicks
                    if conv_rate < 0.08:  # Less than 8% conversion
                        # Assume adding reminders could improve by 2-3%
                        expected_additional_conversions = clicks * 0.025
                        revenue_per_conv = journey_df['Revenue (SAR)'].sum() / conversions
                        expected_revenue = expected_additional_conversions * revenue_per_conv
                        
                        actions.append({
                            'priority': 'HIGH',
                            'title': f'Add Reminder Touchpoints',
                            'action': f"Add reminder blocks to '{journey}' journey to reduce drop-off",
                            'expected_impact': f"+{format_sar(expected_revenue)} from improved conversion",
                            'confidence': '80%',
                            'implementation_time': '2-3 days',
                            'score': expected_revenue
                        })
                        break  # Only add one journey-specific action
        
        # Action 5: Reactivate stopped journeys
        if 'Journey Name' in df.columns:
            for journey in df['Journey Name'].unique():
                if pd.isna(journey) or str(journey) == 'nan':
                    continue
                
                journey_df = df[df['Journey Name'] == journey]
                journey_recent = recent_df[recent_df['Journey Name'] == journey]
                
                historical_revenue = journey_df['Revenue (SAR)'].sum()
                recent_revenue = journey_recent['Revenue (SAR)'].sum()
                
                # If historical revenue was significant but recent is low
                if historical_revenue > 50000 and recent_revenue < historical_revenue * 0.1:
                    actions.append({
                        'priority': 'MEDIUM',
                        'title': 'Reactivate Dormant Journey',
                        'action': f"Investigate and reactivate '{journey}' - was previously high-value",
                        'expected_impact': f"Potential recovery of up to {format_sar(historical_revenue * 0.5)}",
                        'confidence': '60%',
                        'implementation_time': '5-10 days',
                        'score': historical_revenue * 0.5
                    })
                    break  # Only suggest one reactivation

        # Action 6: Campaign-type-aware recommendations
        if 'Type of Campaign' in df.columns:
            # One-time campaign specific actions
            onetime_df = recent_df[recent_df['Type of Campaign'].str.lower().str.contains('one-time', na=False)]
            if not onetime_df.empty and 'Revenue (SAR)' in onetime_df.columns:
                campaign_perf = onetime_df.groupby('Campaign Name').agg({
                    'Revenue (SAR)': 'sum',
                    'Sent': 'sum',
                    'Unique Conversions': 'sum'
                }).reset_index()
                campaign_perf['RPS'] = campaign_perf['Revenue (SAR)'] / campaign_perf['Sent'].replace(0, 1)

                # Find top one-time campaign to replicate
                top_onetime = campaign_perf.nlargest(1, 'Revenue (SAR)')
                if not top_onetime.empty and top_onetime['Revenue (SAR)'].iloc[0] > 0:
                    camp_name = top_onetime['Campaign Name'].iloc[0]
                    camp_rev = top_onetime['Revenue (SAR)'].iloc[0]
                    camp_rps = top_onetime['RPS'].iloc[0]
                    actions.append({
                        'priority': 'HIGH',
                        'title': 'Repeat High-Performing One-Time Campaign',
                        'action': (f"Re-send '{camp_name}' to untargeted or new segments. "
                                   f"Original generated {format_sar(camp_rev)} at {camp_rps:.4f} SAR/send."),
                        'expected_impact': f"+{format_sar(camp_rev * 0.5)} from new audience reach",
                        'confidence': '75%',
                        'implementation_time': '1-2 days',
                        'score': camp_rev * 0.5
                    })

                # Find one-time campaigns with high engagement but low conversion
                if 'Unique Clicks' in onetime_df.columns:
                    camp_engage = onetime_df.groupby('Campaign Name').agg({
                        'Unique Clicks': 'sum', 'Unique Conversions': 'sum',
                        'Revenue (SAR)': 'sum', 'Sent': 'sum'
                    }).reset_index()
                    camp_engage['CVR'] = camp_engage['Unique Conversions'] / camp_engage['Unique Clicks'].replace(0, 1)
                    high_click_low_conv = camp_engage[
                        (camp_engage['Unique Clicks'] > 50) & (camp_engage['CVR'] < 0.03)
                    ].nlargest(1, 'Unique Clicks')
                    if not high_click_low_conv.empty:
                        lc_name = high_click_low_conv['Campaign Name'].iloc[0]
                        lc_clicks = int(high_click_low_conv['Unique Clicks'].iloc[0])
                        lc_cvr = high_click_low_conv['CVR'].iloc[0]
                        potential_convs = lc_clicks * 0.03  # target 3% CVR
                        avg_rev_per_conv = recent_df['Revenue (SAR)'].sum() / max(recent_df['Unique Conversions'].sum(), 1) if 'Unique Conversions' in recent_df.columns else 100
                        expected_rev = potential_convs * avg_rev_per_conv
                        actions.append({
                            'priority': 'MEDIUM',
                            'title': 'Fix Landing Page for Clicked-But-Not-Converted Campaign',
                            'action': (f"'{lc_name}' got {lc_clicks:,} clicks but only {lc_cvr:.1%} converted. "
                                       f"Review the landing page, offer, or conversion flow."),
                            'expected_impact': f"+{format_sar(expected_rev)} if CVR reaches 3%",
                            'confidence': '70%',
                            'implementation_time': '3-5 days',
                            'score': expected_rev
                        })

            # Journey-specific: find journeys with low send volume vs. peers
            journey_df = recent_df[recent_df['Type of Campaign'].str.lower().str.contains('journey', na=False)]
            if not journey_df.empty and 'Journey Name' in journey_df.columns:
                journey_perf = journey_df.groupby('Journey Name').agg({
                    'Revenue (SAR)': 'sum', 'Sent': 'sum'
                }).reset_index()
                journey_perf['RPS'] = journey_perf['Revenue (SAR)'] / journey_perf['Sent'].replace(0, 1)
                # Find high-RPS journeys with room to scale
                median_sent = journey_perf['Sent'].median()
                high_rps_low_vol = journey_perf[
                    (journey_perf['RPS'] > journey_perf['RPS'].median()) &
                    (journey_perf['Sent'] < median_sent)
                ].nlargest(1, 'RPS')
                if not high_rps_low_vol.empty:
                    j_name = high_rps_low_vol['Journey Name'].iloc[0]
                    j_rps = high_rps_low_vol['RPS'].iloc[0]
                    j_sent = int(high_rps_low_vol['Sent'].iloc[0])
                    potential_rev = (median_sent - j_sent) * j_rps
                    if potential_rev > 0:
                        actions.append({
                            'priority': 'MEDIUM',
                            'title': 'Expand High-Efficiency Journey Audience',
                            'action': (f"'{j_name}' has above-average RPS ({j_rps:.4f} SAR/send) "
                                       f"but below-average volume ({j_sent:,} sends). "
                                       f"Broaden the trigger criteria or audience segment."),
                            'expected_impact': f"+{format_sar(potential_rev)} from increased reach",
                            'confidence': '70%',
                            'implementation_time': '3-5 days',
                            'score': potential_rev
                        })

        # Action 7: Channel budget reallocation -- shift spend from a low-ROAS paid
        # channel toward a high-ROAS one. Uses 'Campaign Cost', which already reflects
        # this session's per-channel cost overrides (see DashboardState.channel_costs),
        # not just the hardcoded config defaults.
        if 'Channel' in recent_df.columns and 'Campaign Cost' in recent_df.columns and 'Revenue (SAR)' in recent_df.columns:
            chan_perf = recent_df.groupby('Channel').agg({
                'Revenue (SAR)': 'sum', 'Campaign Cost': 'sum', 'Sent': 'sum'
            }).reset_index()
            paid_channels = chan_perf[(chan_perf['Campaign Cost'] > 0) & (chan_perf['Sent'] >= CHANNEL_MIN_SENT)].copy()

            if len(paid_channels) >= 2:
                paid_channels['ROAS'] = paid_channels['Revenue (SAR)'] / paid_channels['Campaign Cost']
                # Drop channels whose ROAS is implausibly high -- that's a cost-data
                # gap, not a real return, and it would otherwise dominate the ranking
                # and inflate the projected impact on a client slide.
                paid_channels = paid_channels[paid_channels['ROAS'] <= ROAS_SANITY_CEILING]

            if len(paid_channels) >= 2:
                best = paid_channels.nlargest(1, 'ROAS').iloc[0]
                worst = paid_channels.nsmallest(1, 'ROAS').iloc[0]

                if worst['ROAS'] > 0 and best['ROAS'] >= worst['ROAS'] * 1.5:
                    reallocated_spend = worst['Campaign Cost'] * 0.2
                    expected_revenue = reallocated_spend * best['ROAS']

                    actions.append({
                        'priority': 'HIGH' if best['ROAS'] >= worst['ROAS'] * 2 else 'MEDIUM',
                        'title': 'Reallocate Channel Budget',
                        'action': (f"Shift budget from {worst['Channel']} (ROAS {worst['ROAS']:.1f}x) "
                                   f"toward {best['Channel']} (ROAS {best['ROAS']:.1f}x)"),
                        'expected_impact': f"+{format_sar(expected_revenue)} by moving 20% of {worst['Channel']}'s spend to {best['Channel']}",
                        'confidence': '65%',
                        'implementation_time': '1-2 days',
                        'score': expected_revenue
                    })

        # Sort by expected impact (score) and take top N
        actions.sort(key=lambda x: x['score'], reverse=True)
        actions = actions[:max_actions]
        
        # Remove internal score field
        for action in actions:
            if 'score' in action:
                del action['score']
        
    except Exception as e:
        logger.warning(f"generate_top_actions failed: {e}")

    return actions


def format_sar(value):
    """Format SAR currency values for display"""
    if value >= 1_000_000:
        return f"{value/1_000_000:.1f}M SAR"
    elif value >= 1_000:
        return f"{value/1_000:.1f}K SAR"
    else:
        return f"{value:.0f} SAR"


def generate_executive_summary(df):
    """
    Generate a comprehensive executive summary for the entire portfolio
    Combines narratives, forecasts, and actions into a cohesive report
    """
    summary = {
        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M'),
        'period': None,
        'headline_metrics': {},
        'narrative_insights': {},
        'forecast': None,
        'top_actions': [],
        'alerts_count': 0
    }
    
    try:
        df = df.copy()  # avoid mutating caller's DataFrame (adds a 'date' column below)

        # Get date range
        if 'Reporting Period Start Date' in df.columns:
            df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
        elif 'Day' in df.columns:
            df['date'] = pd.to_datetime(df['Day'])
        
        if 'date' in df.columns:
            min_date = df['date'].min()
            max_date = df['date'].max()
            summary['period'] = f"{min_date.strftime('%b %d')} - {max_date.strftime('%b %d, %Y')}"
        
        # Headline metrics - use attribution-selected columns when available
        summary['headline_metrics'] = {
            'total_revenue': df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in df.columns else (df['Revenue (SAR)'].sum() if 'Revenue (SAR)' in df.columns else 0),
            'total_conversions': df['Selected Conversions'].sum() if 'Selected Conversions' in df.columns else (df['Unique Conversions'].sum() if 'Unique Conversions' in df.columns else 0),
            'total_sent': df['Sent'].sum() if 'Sent' in df.columns else 0,
            'avg_delivery_rate': (df['Delivered'].sum() / max(df['Sent'].sum(), 1)) if 'Delivered' in df.columns and 'Sent' in df.columns else 0,
            'avg_ctr': (df['Unique Clicks'].sum() / max(df['Unique Impressions'].sum(), 1)) if 'Unique Clicks' in df.columns and 'Unique Impressions' in df.columns else 0,
            'avg_conversion_rate': (df['Unique Conversions'].sum() / max(df['Unique Clicks'].sum(), 1)) if 'Unique Conversions' in df.columns and 'Unique Clicks' in df.columns else 0
        }
        
        # Generate insights
        summary['narrative_insights'] = generate_narrative_insights(df, lookback_days=30)

        # Count alerts
        summary['alerts_count'] = len(summary['narrative_insights'].get('performance_alerts', []))

        # Generate top actions
        summary['top_actions'] = generate_top_actions(df, max_actions=5)
        
    except Exception as e:
        summary['error'] = str(e)
    
    return summary
