"""
Temporal Intelligence Engine - Automated Period Analysis and Insights
Automatically detects time periods in data and generates comparative insights
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date as _date_cls
import calendar


def _approx_ramadan_month(year):
    """
    Approximate the Gregorian month in which Ramadan starts for a given year.
    Ramadan shifts ~11 days earlier each Gregorian year.
    Reference point: Ramadan 2025 starts ~March 1 (month 3).
    """
    ref_start = _date_cls(2025, 3, 1)
    years_diff = year - 2025
    shift_days = int(round(years_diff * 10.63))
    try:
        approx_start = ref_start - timedelta(days=shift_days)
        approx_start = approx_start.replace(year=year)
    except ValueError:
        approx_start = ref_start.replace(year=year, day=min(ref_start.day, 28))
        approx_start = approx_start - timedelta(days=shift_days % 365)
    return approx_start.month

def detect_time_periods(df):
    """
    Automatically detect what time periods are present in the data
    Returns: period_type, periods_list, date_range
    """
    df = df.copy()  # Avoid mutating caller's DataFrame

    if 'Reporting Period Start Date' in df.columns:
        date_col = 'Reporting Period Start Date'
    elif 'Day' in df.columns:
        date_col = 'Day'
    else:
        return None

    df['_date'] = pd.to_datetime(df[date_col])
    min_date = df['_date'].min()
    max_date = df['_date'].max()
    
    total_days = (max_date - min_date).days + 1
    
    # Determine appropriate period granularity
    if total_days <= 14:
        period_type = 'daily'
        df['_period'] = df['_date'].dt.date
    elif total_days <= 60:
        period_type = 'weekly'
        df['_period'] = df['_date'].dt.to_period('W').astype(str)
    elif total_days <= 180:
        period_type = 'monthly'
        df['_period'] = df['_date'].dt.to_period('M').astype(str)
    else:
        period_type = 'quarterly'
        df['_period'] = df['_date'].dt.to_period('Q').astype(str)
    
    periods = sorted(df['_period'].unique())
    
    return {
        'period_type': period_type,
        'periods': periods,
        'min_date': min_date,
        'max_date': max_date,
        'total_days': total_days,
        'num_periods': len(periods)
    }


def compare_periods(df, period_info):
    """
    Compare metrics across all detected periods
    Returns: DataFrame with period-over-period comparisons
    """
    if period_info is None:
        return None
    
    # Group by period and calculate key metrics
    period_metrics = df.groupby('_period').agg({
        'Revenue (SAR)': 'sum',
        'Unique Conversions': 'sum',
        'Unique Clicks': 'sum',
        'Unique Impressions': 'sum',
        'Sent': 'sum',
        'Delivered': 'sum'
    }).reset_index()
    
    # Calculate period-over-period changes
    for col in ['Revenue (SAR)', 'Unique Conversions', 'Unique Clicks']:
        period_metrics[f'{col}_change'] = period_metrics[col].pct_change() * 100
        period_metrics[f'{col}_change_abs'] = period_metrics[col].diff()
    
    # Calculate rates
    period_metrics['Conversion_Rate'] = (
        period_metrics['Unique Conversions'] / period_metrics['Unique Clicks']
    ).fillna(0) * 100
    
    period_metrics['CTR'] = (
        period_metrics['Unique Clicks'] / period_metrics['Unique Impressions']
    ).fillna(0) * 100
    
    period_metrics['Delivery_Rate'] = (
        period_metrics['Delivered'] / period_metrics['Sent']
    ).fillna(0) * 100
    
    return period_metrics


def generate_temporal_insights(df, period_metrics, period_info):
    """
    Generate automated narrative insights about period-over-period performance
    """
    insights = []
    period_type = period_info['period_type']
    periods = period_info['periods']
    
    if len(periods) < 2:
        return ["Insufficient data for period comparison. Need at least 2 periods."]
    
    # Get latest and previous periods
    latest_period = periods[-1]
    prev_period = periods[-2]
    
    latest_data = period_metrics[period_metrics['_period'] == latest_period].iloc[0]
    prev_data = period_metrics[period_metrics['_period'] == prev_period].iloc[0]
    
    # Revenue Analysis
    revenue_change = latest_data['Revenue (SAR)_change']
    revenue_latest = latest_data['Revenue (SAR)']
    revenue_prev = prev_data['Revenue (SAR)']
    
    if pd.notna(revenue_change):
        if revenue_change > 10:
            insights.append(
                f"📈 **Strong Revenue Growth**: Revenue increased {revenue_change:.1f}% "
                f"from {format_sar(revenue_prev)} to {format_sar(revenue_latest)} "
                f"in {latest_period} vs {prev_period}. This indicates successful optimization "
                f"or expanded audience reach."
            )
        elif revenue_change < -10:
            insights.append(
                f"📉 **Revenue Decline Alert**: Revenue dropped {abs(revenue_change):.1f}% "
                f"from {format_sar(revenue_prev)} to {format_sar(revenue_latest)} "
                f"in {latest_period} vs {prev_period}. Investigate: delivery issues, "
                f"audience fatigue, or seasonal factors (holidays, events)."
            )
        else:
            insights.append(
                f"➡️ **Stable Revenue**: Revenue changed {revenue_change:+.1f}% "
                f"({format_sar(revenue_latest)}) - performance remains consistent "
                f"period-over-period."
            )
    
    # Conversion Analysis
    conv_change = latest_data['Unique Conversions_change']
    conv_latest = latest_data['Unique Conversions']
    conv_prev = prev_data['Unique Conversions']
    
    if pd.notna(conv_change):
        if conv_change > 15:
            insights.append(
                f"🎯 **Conversion Surge**: Conversions jumped {conv_change:.1f}% "
                f"({int(conv_prev):,} → {int(conv_latest):,}). Strong signal that "
                f"recent optimizations or campaigns are resonating with audience."
            )
        elif conv_change < -15:
            insights.append(
                f"⚠️ **Conversion Drop**: Conversions fell {abs(conv_change):.1f}% "
                f"({int(conv_prev):,} → {int(conv_latest):,}). Review landing pages, "
                f"offer relevance, and customer journey friction points."
            )
    
    # Multi-period trend analysis (if we have 3+ periods)
    if len(periods) >= 3:
        # Look at last 3 periods
        last_3_periods = periods[-3:]
        last_3_data = period_metrics[period_metrics['_period'].isin(last_3_periods)]
        
        # Calculate trend
        revenue_values = last_3_data['Revenue (SAR)'].values
        if len(revenue_values) == 3:
            if revenue_values[0] < revenue_values[1] < revenue_values[2]:
                growth = ((revenue_values[2] - revenue_values[0]) / revenue_values[0]) * 100
                insights.append(
                    f"🚀 **Consistent Growth Trajectory**: Revenue has grown steadily "
                    f"for 3 consecutive {period_type} periods (+{growth:.1f}% total). "
                    f"Current strategy is working - consider scaling budget allocation."
                )
            elif revenue_values[0] > revenue_values[1] > revenue_values[2]:
                decline = ((revenue_values[0] - revenue_values[2]) / revenue_values[0]) * 100
                insights.append(
                    f"📉 **Declining Trend**: Revenue has declined for 3 consecutive "
                    f"periods (-{decline:.1f}% total). This suggests systematic issues: "
                    f"market saturation, creative fatigue, or competitive pressure. "
                    f"Immediate strategic review recommended."
                )
            elif revenue_values[1] < revenue_values[0] and revenue_values[2] > revenue_values[1]:
                insights.append(
                    f"🔄 **Recovery Pattern**: After a dip in {last_3_periods[1]}, revenue "
                    f"is recovering in {last_3_periods[2]} ({format_sar(revenue_values[2])}). "
                    f"This suggests the issue was temporary - monitor to confirm sustained recovery."
                )
    
    # Compare first period vs last period (overall journey)
    first_period = periods[0]
    first_data = period_metrics[period_metrics['_period'] == first_period].iloc[0]
    
    first_rev = first_data['Revenue (SAR)']
    first_conv = first_data['Unique Conversions']
    overall_revenue_change = (
        ((latest_data['Revenue (SAR)'] - first_rev) / first_rev) * 100
    ) if first_rev > 0 else 0

    overall_conv_change = (
        ((latest_data['Unique Conversions'] - first_conv) / first_conv) * 100
    ) if first_conv > 0 else 0
    
    insights.append(
        f"📊 **Overall Period Performance** ({first_period} to {latest_period}): "
        f"Revenue {overall_revenue_change:+.1f}% "
        f"({format_sar(first_data['Revenue (SAR)'])} → {format_sar(latest_data['Revenue (SAR)'])}), "
        f"Conversions {overall_conv_change:+.1f}% "
        f"({int(first_data['Unique Conversions']):,} → {int(latest_data['Unique Conversions']):,})"
    )
    
    # Efficiency Analysis
    conv_rate_latest = latest_data['Conversion_Rate']
    conv_rate_prev = prev_data['Conversion_Rate']
    conv_rate_change = conv_rate_latest - conv_rate_prev
    
    if abs(conv_rate_change) > 0.5:  # More than 0.5 percentage point change
        if conv_rate_change > 0:
            insights.append(
                f"⚡ **Efficiency Improvement**: Conversion rate increased from "
                f"{conv_rate_prev:.2f}% to {conv_rate_latest:.2f}% - you're converting "
                f"more customers with similar traffic."
            )
        else:
            insights.append(
                f"⚠️ **Efficiency Decline**: Conversion rate dropped from "
                f"{conv_rate_prev:.2f}% to {conv_rate_latest:.2f}% - traffic quality "
                f"or landing page experience may need attention."
            )
    
    return insights


def generate_quarterly_insights(df, period_metrics):
    """
    Generate insights specific to quarterly data (3+ months)
    """
    insights = []
    
    if len(period_metrics) < 3:
        return []
    
    # Add month labels
    period_metrics['month_name'] = period_metrics['_period'].apply(
        lambda x: pd.Period(x).strftime('%B %Y') if isinstance(x, str) else str(x)
    )
    
    # Find best and worst performing months
    best_month = period_metrics.loc[period_metrics['Revenue (SAR)'].idxmax()]
    worst_month = period_metrics.loc[period_metrics['Revenue (SAR)'].idxmin()]
    
    best_revenue = best_month['Revenue (SAR)']
    worst_revenue = worst_month['Revenue (SAR)']
    performance_gap = ((best_revenue - worst_revenue) / worst_revenue) * 100 if worst_revenue > 0 else 0
    
    insights.append(
        f"🏆 **Best Performing Period**: {best_month['_period']} with "
        f"{format_sar(best_revenue)} revenue ({int(best_month['Unique Conversions']):,} conversions)"
    )
    
    insights.append(
        f"📊 **Performance Variation**: {performance_gap:.1f}% difference between "
        f"best ({best_month['_period']}) and worst ({worst_month['_period']}) periods. "
        f"{'High variation suggests seasonality or campaign inconsistency.' if performance_gap > 50 else 'Relatively stable performance across periods.'}"
    )
    
    # Calculate monthly average
    avg_revenue = period_metrics['Revenue (SAR)'].mean()
    above_avg_count = (period_metrics['Revenue (SAR)'] > avg_revenue).sum()
    
    insights.append(
        f"📈 **Consistency**: {above_avg_count}/{len(period_metrics)} periods performed "
        f"above average revenue ({format_sar(avg_revenue)})"
    )
    
    # Identify momentum
    recent_3 = period_metrics.tail(3)['Revenue (SAR)'].mean()
    early_3 = period_metrics.head(3)['Revenue (SAR)'].mean()
    momentum = ((recent_3 - early_3) / early_3) * 100 if early_3 > 0 else 0
    
    if momentum > 20:
        insights.append(
            f"🚀 **Strong Momentum**: Recent periods averaging {format_sar(recent_3)} "
            f"vs early periods {format_sar(early_3)} (+{momentum:.1f}%). "
            f"Business is accelerating - capitalize on this momentum."
        )
    elif momentum < -20:
        insights.append(
            f"⚠️ **Losing Momentum**: Recent period average {format_sar(recent_3)} "
            f"is {abs(momentum):.1f}% below early periods ({format_sar(early_3)}). "
            f"Strategic intervention needed to reverse this trend."
        )
    
    return insights


def generate_seasonality_insights(df, period_metrics):
    """
    Detect seasonal patterns in the data
    """
    insights = []
    
    if len(period_metrics) < 4:
        return []
    
    # Add month numbers for pattern detection
    period_metrics['month_num'] = period_metrics['_period'].apply(
        lambda x: pd.Period(x).month if isinstance(x, str) and '-' in str(x) else None
    )
    
    # Check for Ramadan effect (dynamically calculated per year in the data)
    if period_metrics['month_num'].notna().any():
        # Determine approximate Ramadan month from data's year range
        data_years = period_metrics['_period'].apply(
            lambda x: pd.Period(x).year if isinstance(x, str) and '-' in str(x) else None
        ).dropna().unique()
        ramadan_months = set()
        post_ramadan_months = set()
        for yr in data_years:
            rm = _approx_ramadan_month(int(yr))
            ramadan_months.add(rm)
            post_ramadan_months.add(rm + 1 if rm < 12 else 1)

        ramadan_data = period_metrics[period_metrics['month_num'].isin(ramadan_months)]
        post_ramadan_data = period_metrics[period_metrics['month_num'].isin(post_ramadan_months)]

        if not ramadan_data.empty and not post_ramadan_data.empty:
            ramadan_revenue = ramadan_data['Revenue (SAR)'].mean()
            post_ramadan_revenue = post_ramadan_data['Revenue (SAR)'].mean()

            if ramadan_revenue > 0 and post_ramadan_revenue < ramadan_revenue * 0.8:
                post_month_names = ", ".join(calendar.month_name[m] for m in sorted(post_ramadan_months))
                ram_month_names = ", ".join(calendar.month_name[m] for m in sorted(ramadan_months))
                insights.append(
                    f"🌙 **Post-Ramadan Effect Detected**: Revenue in {post_month_names} "
                    f"({format_sar(post_ramadan_revenue)}) dropped significantly from "
                    f"Ramadan period in {ram_month_names} ({format_sar(ramadan_revenue)}). "
                    f"This drastic drop suggests lack of sustained engagement after the month of Ramadan. "
                    f"Consider implementing reminder campaigns and special post-Ramadan offers."
                )
    
    # Check for quarter-end patterns
    period_metrics['quarter_month'] = period_metrics['month_num'].apply(
        lambda x: 'Q-end' if x in [3, 6, 9, 12] else 'Q-mid' if pd.notna(x) else None
    )
    
    if period_metrics['quarter_month'].notna().any():
        q_end = period_metrics[period_metrics['quarter_month'] == 'Q-end']['Revenue (SAR)'].mean()
        q_mid = period_metrics[period_metrics['quarter_month'] == 'Q-mid']['Revenue (SAR)'].mean()
        
        if q_mid > 0 and q_end > q_mid * 1.2:
            insights.append(
                f"📅 **Quarter-End Spike Pattern**: Revenue is {((q_end/q_mid - 1)*100):.1f}% "
                f"higher in quarter-end months. Consider increasing marketing investment "
                f"during these high-performance periods."
            )
    
    return insights


def generate_journey_temporal_insights(df, journey_name, period_info):
    """
    Generate temporal insights for a specific journey
    """
    journey_df = df[df['Journey Name'] == journey_name].copy()
    
    if len(journey_df) < 2:
        return []
    
    period_metrics = journey_df.groupby('_period').agg({
        'Revenue (SAR)': 'sum',
        'Unique Conversions': 'sum',
        'Delivered': 'sum',
        'Sent': 'sum'
    }).reset_index()
    
    insights = []
    periods = sorted(period_metrics['_period'].unique())
    
    if len(periods) >= 2:
        latest = period_metrics[period_metrics['_period'] == periods[-1]].iloc[0]
        prev = period_metrics[period_metrics['_period'] == periods[-2]].iloc[0]
        
        rev_change = ((latest['Revenue (SAR)'] - prev['Revenue (SAR)']) / 
                      prev['Revenue (SAR)']) * 100 if prev['Revenue (SAR)'] > 0 else 0
        
        insights.append(
            f"📊 **Journey {journey_name}**: "
            f"Revenue {rev_change:+.1f}% period-over-period "
            f"({format_sar(prev['Revenue (SAR)'])} → {format_sar(latest['Revenue (SAR)'])})"
        )
        
        # Check for declining delivery
        delivery_prev = (prev['Delivered'] / prev['Sent']) * 100 if prev['Sent'] > 0 else 0
        delivery_latest = (latest['Delivered'] / latest['Sent']) * 100 if latest['Sent'] > 0 else 0
        
        if delivery_latest < delivery_prev - 5:
            insights.append(
                f"⚠️ **Delivery Issue Detected**: Delivery rate dropped from {delivery_prev:.1f}% "
                f"to {delivery_latest:.1f}% - investigate sender reputation and list quality."
            )
    
    return insights


def format_sar(value):
    """Format currency values"""
    if value >= 1e6:
        return f"{value/1e6:.1f}M SAR"
    elif value >= 1e3:
        return f"{value/1e3:.1f}K SAR"
    else:
        return f"{value:,.0f} SAR"


def create_executive_summary(df):
    """
    Create an executive summary with automated insights for any time period
    """
    period_info = detect_time_periods(df)
    
    if period_info is None:
        return {
            'error': 'Unable to detect time periods in data',
            'recommendations': ['Ensure data has Reporting Period Start Date or Day column']
        }
    
    period_metrics = compare_periods(df, period_info)
    
    # Generate all insights
    temporal_insights = generate_temporal_insights(df, period_metrics, period_info)
    quarterly_insights = generate_quarterly_insights(df, period_metrics)
    seasonality_insights = generate_seasonality_insights(df, period_metrics)
    
    # Get top journeys performance
    journey_insights = []
    top_journeys = df.groupby('Journey Name')['Revenue (SAR)'].sum().nlargest(5).index
    for journey in top_journeys:
        journey_insights.extend(generate_journey_temporal_insights(df, journey, period_info))
    
    # Compile recommendations
    recommendations = []
    
    # Check latest period performance
    if len(period_metrics) >= 2:
        latest = period_metrics.iloc[-1]
        prev = period_metrics.iloc[-2]
        
        if latest['Revenue (SAR)'] < prev['Revenue (SAR)'] * 0.9:
            recommendations.append(
                "🚨 **URGENT**: Revenue declined >10% in latest period. "
                "Implement recovery plan: refresh creative, expand audience, increase frequency."
            )
        
        if latest['Conversion_Rate'] < prev['Conversion_Rate'] * 0.9:
            recommendations.append(
                "🎯 **ACTION**: Conversion rate declining. "
                "A/B test landing pages, review offer relevance, optimize checkout flow."
            )
        
        if latest['Revenue (SAR)'] > prev['Revenue (SAR)'] * 1.2:
            recommendations.append(
                "🚀 **OPPORTUNITY**: Strong revenue growth detected. "
                "Scale winning campaigns, increase budget allocation, document success factors."
            )
    
    # Add generic best practices
    if len(period_info['periods']) >= 3:
        recommendations.append(
            "📊 **OPTIMIZE**: With multi-period data, focus on: "
            "1) Scaling top-performing journeys, 2) Pausing bottom 20% performers, "
            "3) A/B testing creative on mid-tier campaigns."
        )
    
    return {
        'period_info': period_info,
        'period_metrics': period_metrics,
        'temporal_insights': temporal_insights,
        'quarterly_insights': quarterly_insights,
        'seasonality_insights': seasonality_insights,
        'journey_insights': journey_insights[:5],  # Top 5
        'recommendations': recommendations,
        'summary': {
            'total_periods_analyzed': period_info['num_periods'],
            'period_type': period_info['period_type'],
            'date_range': f"{period_info['min_date'].strftime('%Y-%m-%d')} to {period_info['max_date'].strftime('%Y-%m-%d')}",
            'total_revenue': df['Revenue (SAR)'].sum(),
            'total_conversions': df['Unique Conversions'].sum(),
            'avg_period_revenue': period_metrics['Revenue (SAR)'].mean(),
        }
    }
