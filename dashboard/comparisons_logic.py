import pandas as pd
import numpy as np


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
    # Conversion rate is Click-Through Conversions ÷ Clicks dashboard-wide:
    # total-attribution conversions include non-clickers and push the ratio past 100%.
    _ct_conversions = (period_data['Unique Click-Through Conversions'].sum()
                       if 'Unique Click-Through Conversions' in period_data.columns
                       else metrics['selected_conversions'])
    metrics['conversion_rate'] = (_ct_conversions / metrics['total_clicks']) if metrics['total_clicks'] > 0 else 0
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
