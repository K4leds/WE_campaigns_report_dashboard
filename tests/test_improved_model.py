"""
Quick test of the improved revenue loss estimation using actual app function
"""
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '.')

# Import the actual function from app
from app import estimate_revenue_loss_ml, analyze_stopped_journeys

# Load test data
df = pd.read_csv('tests/Daily Q2_Q3.csv')
if 'Day' in df.columns:
    df['date'] = pd.to_datetime(df['Day'])
elif 'Reporting Period Start Date' in df.columns:
    df['date'] = pd.to_datetime(df['Reporting Period Start Date'])

# Test on a journey with stopped periods
journey_name = 'Cart Abandonment - Cosmetics [w/o Recommendations]'
journey_data = df[df['Journey Name'] == journey_name].copy()

print(f"Testing: {journey_name}")
print(f"Data points: {len(journey_data)}")
print(f"Date range: {journey_data['date'].min()} to {journey_data['date'].max()}")

# Aggregate by date
daily = journey_data.groupby('date', as_index=False).agg({
    'Delivered': 'sum',
    'Revenue (SAR)': 'sum',
    'Impression-Through Revenue (SAR)': 'sum',
    'Click-Through Revenue (SAR)': 'sum'
})

print(f"\nDaily aggregated: {len(daily)} days")
print(f"Days with revenue: {(daily['Revenue (SAR)'] > 0).sum()}")
print(f"Revenue stats:")
print(f"  Mean: {daily['Revenue (SAR)'].mean():,.2f} SAR")
print(f"  Median: {daily['Revenue (SAR)'].median():,.2f} SAR")
print(f"  Std: {daily['Revenue (SAR)'].std():,.2f} SAR")
print(f"  CV: {daily['Revenue (SAR)'].std() / daily['Revenue (SAR)'].mean() * 100:.1f}%")

# Detect stopped periods (simplified)
daily = daily.sort_values('date').reset_index(drop=True)
daily['is_stopped'] = (daily['Delivered'] == 0)

stopped_periods = []
current_start = None
consecutive = 0

for idx in range(len(daily)):
    if daily.iloc[idx]['is_stopped']:
        if current_start is None:
            current_start = daily.iloc[idx]['date']
        consecutive += 1
    else:
        if consecutive >= 3 and current_start is not None:
            stopped_periods.append({
                'start_date': current_start,
                'end_date': daily.iloc[idx-1]['date'],
                'days_stopped': consecutive
            })
        current_start = None
        consecutive = 0

if consecutive >= 3 and current_start is not None:
    stopped_periods.append({
        'start_date': current_start,
        'end_date': daily.iloc[-1]['date'],
        'days_stopped': consecutive
    })

print(f"\n Found {len(stopped_periods)} stopped periods")
for i, period in enumerate(stopped_periods, 1):
    print(f"  {i}. {period['start_date'].date()} to {period['end_date'].date()}: {period['days_stopped']} days")

if stopped_periods:
    print("\n🧪 Testing improved loss estimation...")
    
    # Use the actual app function
    result = estimate_revenue_loss_ml(journey_data, stopped_periods, confidence_level=0.95)
    
    print(f"\n✅ Results:")
    print(f"  Total Loss: {result['total_loss']:,.2f} SAR")
    print(f"  Avg Daily Loss: {result['avg_daily_loss']:,.2f} SAR")
    print(f"  Confidence Interval: {result['confidence_interval'][0]:,.2f} - {result['confidence_interval'][1]:,.2f} SAR")
    print(f"  Model Quality: {result.get('model_quality', 'unknown')}")
    print(f"  Method: {result.get('method', 'unknown')}")
    
    print(f"\n  Attribution Breakdown:")
    for model, loss in result['attribution_breakdown'].items():
        print(f"    {model}: {loss:,.2f} SAR")
    
    # Validate reasonableness
    total_stopped_days = sum(p['days_stopped'] for p in stopped_periods)
    recent_avg = daily[daily['Revenue (SAR)'] > 0].tail(30)['Revenue (SAR)'].mean()
    expected_range = (recent_avg * 0.5, recent_avg * 2.0)
    
    print(f"\n📊 Validation:")
    print(f"  Total stopped days: {total_stopped_days}")
    print(f"  Recent 30-day avg: {recent_avg:,.2f} SAR/day")
    print(f"  Expected daily loss range: {expected_range[0]:,.2f} - {expected_range[1]:,.2f} SAR")
    print(f"  Actual daily loss: {result['avg_daily_loss']:,.2f} SAR")
    
    if expected_range[0] <= result['avg_daily_loss'] <= expected_range[1]:
        print(f"  ✅ PASS: Estimate is within reasonable range")
    elif result['avg_daily_loss'] < expected_range[0]:
        print(f"  ⚠️  CAUTION: Estimate is conservative (lower than expected)")
    else:
        print(f"  ⚠️  CAUTION: Estimate is high (check for issues)")
    
    # Check if model succeeded
    model_quality = result.get('model_quality', 'unknown')
    if model_quality == 'high':
        print(f"\n✅ HIGH RELIABILITY - Suitable for CEO/CMO reports")
        print(f"   Present with confidence, include confidence intervals")
    elif model_quality == 'medium':
        print(f"\n⚠️  MODERATE RELIABILITY - Use with caveats in reports")
        print(f"   Present as estimated range, emphasize directional guidance")
    else:
        print(f"\nℹ️  DIRECTIONAL ESTIMATE - Use qualitatively")
        print(f"   Focus on operational impact, not specific numbers")

else:
    print("\n❌ No stopped periods found")
