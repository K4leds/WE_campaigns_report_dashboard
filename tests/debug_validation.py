"""
Debug the validation logic
"""
import pandas as pd
import sys
sys.path.insert(0, '.')

# Load test data
df = pd.read_csv('tests/Daily Q2_Q3.csv')
if 'Day' in df.columns:
    df['date'] = pd.to_datetime(df['Day'])
elif 'Reporting Period Start Date' in df.columns:
    df['date'] = pd.to_datetime(df['Reporting Period Start Date'])

journey_name = 'Product View Abandonment - Cosmetics'
journey_data = df[df['Journey Name'] == journey_name].copy()

# Aggregate by date
daily = journey_data.groupby('date', as_index=False).agg({
    'Delivered': 'sum',
    'Revenue (SAR)': 'sum'
})
daily = daily.sort_values('date').reset_index(drop=True)

# Find stopped period
stopped_start = pd.to_datetime('2025-07-17')
stopped_end = pd.to_datetime('2025-09-30')
actual_calendar_days = (stopped_end - stopped_start).days + 1

print(f"🔍 Validating stopped period: {stopped_start.date()} to {stopped_end.date()}")
print(f"   Duration: {actual_calendar_days} days\n")

# Get activity before
activity_before = daily[daily['date'] < stopped_start]
revenue_before_stop = activity_before['Revenue (SAR)'].mean()

print(f"📊 Activity Before Stop:")
print(f"   Days: {len(activity_before)}")
print(f"   Avg Revenue/day: {revenue_before_stop:,.2f} SAR\n")

# Check revenue beyond conversion window
conversion_window_days = 7
revenue_after_window_start = stopped_start + pd.Timedelta(days=conversion_window_days)
stopped_period_data = daily[(daily['date'] >= revenue_after_window_start) & (daily['date'] <= stopped_end)]

revenue_beyond_window = stopped_period_data['Revenue (SAR)'].sum()
days_beyond_window = max(1, actual_calendar_days - conversion_window_days)
avg_revenue_during_stop = revenue_beyond_window / days_beyond_window

print(f"📊 Revenue Beyond Conversion Window:")
print(f"   Window starts: {revenue_after_window_start.date()}")
print(f"   Days beyond window: {days_beyond_window}")
print(f"   Total revenue beyond window: {revenue_beyond_window:,.2f} SAR")
print(f"   Avg revenue/day during stop: {avg_revenue_during_stop:,.2f} SAR\n")

# Check validation
threshold = revenue_before_stop * 0.1
print(f"🔍 Validation Check:")
print(f"   Threshold (10% of pre-stop avg): {threshold:,.2f} SAR/day")
print(f"   Avg revenue during stop: {avg_revenue_during_stop:,.2f} SAR/day")
print(f"   avg_revenue_during_stop > threshold: {avg_revenue_during_stop > threshold}")

if revenue_before_stop > 0 and avg_revenue_during_stop > threshold:
    print(f"   ❌ WOULD BE FILTERED OUT (revenue continues at {avg_revenue_during_stop/revenue_before_stop:.1%} of pre-stop level)")
else:
    print(f"   ✅ WOULD BE INCLUDED (truly stopped)")
