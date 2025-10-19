"""
Validation script to assess reliability of revenue loss estimation for executive reporting.

This script tests:
1. Prophet model accuracy on historical data
2. Confidence interval coverage
3. Fallback method reliability
4. Data quality requirements
5. Edge case handling

Run this before presenting loss estimates to CEO/CMO.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def load_test_data():
    """Load the daily report for testing"""
    df = pd.read_csv('tests/Daily Q2_Q3.csv')
    
    if 'Day' in df.columns:
        df['date'] = pd.to_datetime(df['Day'])
    elif 'Reporting Period Start Date' in df.columns:
        df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
    
    return df


def test_prophet_accuracy(journey_data, test_days=7):
    """
    Test Prophet model accuracy by:
    1. Using historical data to train
    2. Forecasting for a known period
    3. Comparing forecast vs actual
    
    Returns: accuracy metrics
    """
    try:
        from prophet import Prophet
    except ImportError:
        print("❌ Prophet not installed. Install with: pip install prophet")
        return None
    
    # Aggregate by date
    daily = journey_data.groupby('date', as_index=False).agg({
        'Delivered': 'sum',
        'Revenue (SAR)': 'sum'
    })
    daily = daily.sort_values('date').reset_index(drop=True)
    
    if len(daily) < 30:
        return {'error': 'Insufficient data (need 30+ days)'}
    
    # Split: train on all but last test_days, test on last test_days
    train_data = daily.iloc[:-test_days].copy()
    test_data = daily.iloc[-test_days:].copy()
    
    # Prepare for Prophet
    train_prophet = train_data[['date', 'Revenue (SAR)']].rename(columns={'date': 'ds', 'Revenue (SAR)': 'y'})
    train_prophet = train_prophet.dropna()
    
    if len(train_prophet) < 7:
        return {'error': 'Insufficient revenue data'}
    
    # Train model
    model = Prophet(
        yearly_seasonality=False,
        weekly_seasonality=True,
        daily_seasonality=False,
        interval_width=0.95
    )
    model.fit(train_prophet)
    
    # Forecast
    future = test_data[['date']].rename(columns={'date': 'ds'})
    forecast = model.predict(future)
    
    # Compare
    actual = test_data['Revenue (SAR)'].values
    predicted = forecast['yhat'].values
    
    # Calculate metrics
    mae = np.mean(np.abs(actual - predicted))
    mape = np.mean(np.abs((actual - predicted) / (actual + 1))) * 100  # +1 to avoid div by zero
    
    # Check if actuals fall within confidence intervals
    lower = forecast['yhat_lower'].values
    upper = forecast['yhat_upper'].values
    coverage = np.mean((actual >= lower) & (actual <= upper)) * 100
    
    return {
        'mae': mae,
        'mape': mape,
        'coverage': coverage,
        'actual_mean': np.mean(actual),
        'predicted_mean': np.mean(predicted),
        'test_days': test_days
    }


def test_fallback_accuracy(journey_data, test_days=7):
    """
    Test simple average fallback method accuracy
    """
    # Aggregate by date
    daily = journey_data.groupby('date', as_index=False).agg({
        'Revenue (SAR)': 'sum'
    })
    daily = daily.sort_values('date').reset_index(drop=True)
    
    if len(daily) < 37:  # Need 30 days history + 7 test days
        return {'error': 'Insufficient data'}
    
    # Split
    train_data = daily.iloc[:-test_days]
    test_data = daily.iloc[-test_days:]
    
    # Fallback method: use 30-day average before test period
    lookback_data = train_data.iloc[-30:]
    avg_daily = lookback_data['Revenue (SAR)'].mean()
    
    # Predict
    predicted = np.full(test_days, avg_daily)
    actual = test_data['Revenue (SAR)'].values
    
    # Metrics
    mae = np.mean(np.abs(actual - predicted))
    mape = np.mean(np.abs((actual - predicted) / (actual + 1))) * 100
    
    return {
        'mae': mae,
        'mape': mape,
        'actual_mean': np.mean(actual),
        'predicted_mean': avg_daily,
        'test_days': test_days
    }


def assess_data_quality(journey_data):
    """
    Assess data quality for reliable estimation
    """
    daily = journey_data.groupby('date', as_index=False).agg({
        'Delivered': 'sum',
        'Revenue (SAR)': 'sum'
    })
    
    # Check for sufficient history
    total_days = len(daily)
    days_with_revenue = (daily['Revenue (SAR)'] > 0).sum()
    days_with_delivery = (daily['Delivered'] > 0).sum()
    
    # Check for volatility
    revenue_std = daily['Revenue (SAR)'].std()
    revenue_mean = daily['Revenue (SAR)'].mean()
    cv = (revenue_std / revenue_mean * 100) if revenue_mean > 0 else 0
    
    # Check for trends
    if len(daily) >= 30:
        recent_mean = daily['Revenue (SAR)'].iloc[-30:].mean()
        earlier_mean = daily['Revenue (SAR)'].iloc[:-30].mean()
        trend_change = ((recent_mean - earlier_mean) / (earlier_mean + 1)) * 100
    else:
        trend_change = 0
    
    return {
        'total_days': total_days,
        'days_with_revenue': days_with_revenue,
        'days_with_delivery': days_with_delivery,
        'revenue_mean': revenue_mean,
        'revenue_std': revenue_std,
        'coefficient_of_variation': cv,
        'trend_change_pct': trend_change
    }


def generate_reliability_report(journey_name, prophet_metrics, fallback_metrics, data_quality):
    """
    Generate a reliability assessment report
    """
    print(f"\n{'='*80}")
    print(f"REVENUE LOSS ESTIMATION RELIABILITY REPORT")
    print(f"Journey: {journey_name}")
    print(f"{'='*80}\n")
    
    # Data Quality Assessment
    print("📊 DATA QUALITY ASSESSMENT")
    print("-" * 80)
    
    quality_score = 0
    max_score = 5
    
    if data_quality['total_days'] >= 60:
        print(f"✅ Sufficient history: {data_quality['total_days']} days (60+ recommended)")
        quality_score += 1
    else:
        print(f"⚠️  Limited history: {data_quality['total_days']} days (60+ recommended)")
    
    if data_quality['days_with_revenue'] >= 30:
        print(f"✅ Revenue data coverage: {data_quality['days_with_revenue']} days")
        quality_score += 1
    else:
        print(f"⚠️  Limited revenue data: {data_quality['days_with_revenue']} days (30+ recommended)")
    
    cv = data_quality['coefficient_of_variation']
    if cv < 50:
        print(f"✅ Stable revenue pattern: CV={cv:.1f}% (low volatility)")
        quality_score += 1
    elif cv < 100:
        print(f"⚠️  Moderate volatility: CV={cv:.1f}%")
        quality_score += 0.5
    else:
        print(f"❌ High volatility: CV={cv:.1f}% (estimates less reliable)")
    
    trend = data_quality['trend_change_pct']
    if abs(trend) < 20:
        print(f"✅ Stable trend: {trend:+.1f}% change")
        quality_score += 1
    elif abs(trend) < 50:
        print(f"⚠️  Moderate trend: {trend:+.1f}% change")
        quality_score += 0.5
    else:
        print(f"❌ Strong trend: {trend:+.1f}% change (model may underestimate)")
    
    print(f"\n📈 Daily Revenue Stats:")
    print(f"   Mean: {data_quality['revenue_mean']:,.2f} SAR")
    print(f"   Std Dev: {data_quality['revenue_std']:,.2f} SAR")
    
    # Prophet Model Assessment
    print(f"\n🤖 PROPHET ML MODEL ACCURACY")
    print("-" * 80)
    
    if prophet_metrics and 'error' not in prophet_metrics:
        mape = prophet_metrics['mape']
        coverage = prophet_metrics['coverage']
        
        if mape < 20:
            print(f"✅ Excellent accuracy: MAPE={mape:.1f}%")
            quality_score += 1
        elif mape < 40:
            print(f"⚠️  Moderate accuracy: MAPE={mape:.1f}%")
            quality_score += 0.5
        else:
            print(f"❌ Poor accuracy: MAPE={mape:.1f}%")
        
        print(f"   MAE: {prophet_metrics['mae']:,.2f} SAR")
        print(f"   Confidence Interval Coverage: {coverage:.0f}% (target: 95%)")
        print(f"   Actual Mean: {prophet_metrics['actual_mean']:,.2f} SAR")
        print(f"   Predicted Mean: {prophet_metrics['predicted_mean']:,.2f} SAR")
    else:
        print(f"❌ Prophet model could not be tested")
        if prophet_metrics:
            print(f"   Error: {prophet_metrics.get('error', 'Unknown')}")
    
    # Fallback Method Assessment
    print(f"\n📉 FALLBACK (AVERAGE) METHOD ACCURACY")
    print("-" * 80)
    
    if fallback_metrics and 'error' not in fallback_metrics:
        mape = fallback_metrics['mape']
        
        if mape < 30:
            print(f"✅ Acceptable accuracy: MAPE={mape:.1f}%")
        elif mape < 50:
            print(f"⚠️  Moderate accuracy: MAPE={mape:.1f}%")
        else:
            print(f"❌ Poor accuracy: MAPE={mape:.1f}%")
        
        print(f"   MAE: {fallback_metrics['mae']:,.2f} SAR")
        print(f"   Actual Mean: {fallback_metrics['actual_mean']:,.2f} SAR")
        print(f"   Predicted (30-day avg): {fallback_metrics['predicted_mean']:,.2f} SAR")
    else:
        print(f"❌ Fallback method could not be tested")
    
    # Overall Recommendation
    print(f"\n{'='*80}")
    print(f"EXECUTIVE REPORTING RECOMMENDATION")
    print(f"{'='*80}\n")
    
    reliability_score = (quality_score / max_score) * 100
    
    if reliability_score >= 80:
        print(f"✅ HIGH RELIABILITY ({reliability_score:.0f}%)")
        print(f"\n💼 RECOMMENDED FOR CEO/CMO REPORTS:")
        print(f"   • Present loss estimates with confidence")
        print(f"   • Include confidence intervals")
        print(f"   • Note: Based on {data_quality['total_days']} days of historical data")
        print(f"   • Consider this a conservative estimate")
    
    elif reliability_score >= 60:
        print(f"⚠️  MODERATE RELIABILITY ({reliability_score:.0f}%)")
        print(f"\n💼 USE WITH CAVEATS FOR CEO/CMO REPORTS:")
        print(f"   • Present as estimated range rather than specific number")
        print(f"   • Emphasize this is directional guidance")
        print(f"   • Highlight data limitations:")
        if data_quality['total_days'] < 60:
            print(f"     - Limited history ({data_quality['total_days']} days)")
        if cv > 50:
            print(f"     - High revenue volatility (CV={cv:.0f}%)")
        if abs(trend) > 20:
            print(f"     - Strong trend ({trend:+.0f}% change)")
        print(f"   • Suggest collecting more data before making major decisions")
    
    else:
        print(f"❌ LOW RELIABILITY ({reliability_score:.0f}%)")
        print(f"\n💼 NOT RECOMMENDED FOR CEO/CMO REPORTS:")
        print(f"   • Insufficient data or high uncertainty")
        print(f"   • Recommend qualitative analysis instead")
        print(f"   • Collect more historical data before estimating")
        print(f"   • Focus on delivery restoration rather than loss quantification")
    
    print(f"\n💡 RECOMMENDED REPORTING LANGUAGE:")
    print("-" * 80)
    
    if reliability_score >= 80:
        print(f'"Based on {data_quality["total_days"]} days of historical performance data')
        print(f' and ML forecasting models, we estimate the revenue impact of the')
        print(f' stopped delivery period at [X] SAR, with a 95% confidence interval')
        print(f' of [Y] to [Z] SAR. This represents [X/Daily] SAR per day in lost')
        print(f' revenue opportunity."')
    
    elif reliability_score >= 60:
        print(f'"Preliminary analysis suggests the stopped delivery period may have')
        print(f' resulted in approximately [X] SAR in lost revenue opportunity.')
        print(f' This estimate is based on {data_quality["total_days"]} days of historical data')
        print(f' and should be considered directional guidance. Actual impact may')
        print(f' vary by ±50% given revenue variability."')
    
    else:
        print(f'"The journey experienced a stopped delivery period from [Date] to [Date].')
        print(f' While quantifying the exact revenue impact requires more historical data,')
        print(f' restoring delivery is a priority given the journey\'s strategic importance.')
        print(f' We recommend investigating root cause and implementing monitoring alerts."')
    
    return reliability_score


def main():
    """Main validation routine"""
    print("="*80)
    print("REVENUE LOSS ESTIMATION VALIDATION FOR EXECUTIVE REPORTING")
    print("="*80)
    
    # Load data
    print("\n📂 Loading test data...")
    df = load_test_data()
    print(f"✅ Loaded {len(df)} rows")
    
    # Get top journeys by volume
    journeys = df[df['Journey Name'].notna()].groupby('Journey Name').size().sort_values(ascending=False)
    test_journeys = journeys.head(3).index.tolist()
    
    print(f"\n🧪 Testing {len(test_journeys)} sample journeys...")
    
    results = []
    
    for journey_name in test_journeys:
        journey_data = df[df['Journey Name'] == journey_name].copy()
        
        # Run tests
        print(f"\n{'─'*80}")
        print(f"Testing: {journey_name}")
        print(f"{'─'*80}")
        
        prophet_metrics = test_prophet_accuracy(journey_data)
        fallback_metrics = test_fallback_accuracy(journey_data)
        data_quality = assess_data_quality(journey_data)
        
        reliability_score = generate_reliability_report(
            journey_name, 
            prophet_metrics, 
            fallback_metrics, 
            data_quality
        )
        
        results.append({
            'journey': journey_name,
            'reliability_score': reliability_score,
            'data_quality': data_quality
        })
    
    # Summary
    print(f"\n{'='*80}")
    print(f"SUMMARY")
    print(f"{'='*80}\n")
    
    avg_score = np.mean([r['reliability_score'] for r in results])
    
    print(f"Average Reliability Score: {avg_score:.0f}%\n")
    
    for r in results:
        print(f"  {r['journey'][:50]}: {r['reliability_score']:.0f}%")
    
    print(f"\n{'='*80}")
    print(f"FINAL RECOMMENDATION")
    print(f"{'='*80}\n")
    
    if avg_score >= 80:
        print("✅ Loss estimation is RELIABLE for executive reporting")
        print("\nKey Points to Include in CEO/CMO Reports:")
        print("  • Present specific loss figures with confidence intervals")
        print("  • Explain ML forecasting methodology (Prophet)")
        print("  • Provide per-day and total loss estimates")
        print("  • Include attribution breakdown (Send/Impression/Click-Through)")
        print("  • Emphasize these are conservative estimates")
    
    elif avg_score >= 60:
        print("⚠️  Loss estimation is MODERATELY RELIABLE - use with caveats")
        print("\nGuidelines for CEO/CMO Reports:")
        print("  • Present as estimated ranges rather than specific numbers")
        print("  • Emphasize directional guidance")
        print("  • Clearly state assumptions and limitations")
        print("  • Focus on relative impact (% of normal revenue)")
        print("  • Recommend additional data collection")
    
    else:
        print("❌ Loss estimation NOT RECOMMENDED for executive reporting")
        print("\nAlternative Approach for CEO/CMO Reports:")
        print("  • Focus on operational impact (days stopped, delivery gaps)")
        print("  • Provide qualitative assessment")
        print("  • Show historical performance trends")
        print("  • Recommend restoration priority based on journey importance")
        print("  • Wait for more data before quantifying losses")
    
    print(f"\n{'='*80}\n")


if __name__ == "__main__":
    main()
