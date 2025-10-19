"""
Debug test to see what Prophet is actually predicting
"""
import pandas as pd
import numpy as np
import sys
sys.path.insert(0, '.')

# Load test data
df = pd.read_csv('tests/Daily Q2_Q3.csv')
if 'Day' in df.columns:
    df['date'] = pd.to_datetime(df['Day'])
elif 'Reporting Period Start Date' in df.columns:
    df['date'] = pd.to_datetime(df['Reporting Period Start Date'])

# Test on Cart Abandonment - Cosmetics
journey_name = 'Cart Abandonment - Cosmetics [w/o Recommendations]'
journey_data = df[df['Journey Name'] == journey_name].copy()

# Aggregate by date
daily = journey_data.groupby('date', as_index=False).agg({
    'Delivered': 'sum',
    'Revenue (SAR)': 'sum',
    'Impression-Through Revenue (SAR)': 'sum',
    'Click-Through Revenue (SAR)': 'sum'
})
daily = daily.sort_values('date').reset_index(drop=True)

print("Revenue Distribution:")
print(f"  Full period mean: {daily['Revenue (SAR)'].mean():,.0f} SAR")
print(f"  Full period median: {daily['Revenue (SAR)'].median():,.0f} SAR")
print(f"  Last 30 days mean: {daily.tail(30)['Revenue (SAR)'].mean():,.0f} SAR")
print(f"  Last 30 days median: {daily.tail(30)['Revenue (SAR)'].median():,.0f} SAR")
print(f"  Last 14 days mean: {daily.tail(14)['Revenue (SAR)'].mean():,.0f} SAR")
print(f"  CV: {daily['Revenue (SAR)'].std() / daily['Revenue (SAR)'].mean():.2f}")

# Show revenue over time
print("\nRecent revenue trend (last 20 days):")
for _, row in daily.tail(20).iterrows():
    stopped = "❌" if row['Delivered'] == 0 else "  "
    print(f"{stopped} {row['date'].date()}: {row['Revenue (SAR)']:>8,.0f} SAR")

# Check stopped periods
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

print(f"\n{len(stopped_periods)} stopped periods found:")
for period in stopped_periods:
    # What was revenue BEFORE this stop?
    days_before = daily[daily['date'] < period['start_date']].tail(7)
    avg_before = days_before['Revenue (SAR)'].mean()
    
    # What was revenue AFTER this stop (if any)?
    days_after = daily[daily['date'] > period['end_date']].head(7)
    avg_after = days_after['Revenue (SAR)'].mean() if len(days_after) > 0 else 0
    
    print(f"\n  {period['start_date'].date()} to {period['end_date'].date()}: {period['days_stopped']} days")
    print(f"    7 days before: {avg_before:,.0f} SAR/day")
    print(f"    7 days after: {avg_after:,.0f} SAR/day")
    print(f"    Estimated loss: {avg_before * period['days_stopped']:,.0f} SAR (based on before)")

# Calculate what makes sense
total_days = sum(p['days_stopped'] for p in stopped_periods)
recent_baseline = daily[daily['Revenue (SAR)'] > 0].tail(30)['Revenue (SAR)'].mean()
reasonable_estimate = total_days * recent_baseline

print(f"\n💡 Reasonable estimate check:")
print(f"  Total stopped days: {total_days}")
print(f"  Recent 30-day baseline: {recent_baseline:,.0f} SAR/day")
print(f"  Conservative estimate: {reasonable_estimate:,.0f} SAR")
