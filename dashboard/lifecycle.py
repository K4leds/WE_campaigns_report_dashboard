"""Lifecycle, stopped-journey, cohort, and revenue-attribution waterfall analysis.

Extracted verbatim from app.py (Task 7 of the app.py modularization refactor).
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error


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
