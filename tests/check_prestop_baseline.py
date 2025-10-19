"""
Check what pre-stop baseline should be for Cart Abandonment
"""
import pandas as pd

df = pd.read_csv('tests/Daily Q2_Q3.csv')
if 'Day' in df.columns:
    df['date'] = pd.to_datetime(df['Day'])
elif 'Reporting Period Start Date' in df.columns:
    df['date'] = pd.to_datetime(df['Reporting Period Start Date'])

journey_name = 'Cart Abandonment - Cosmetics [w/o Recommendations]'
journey_data = df[df['Journey Name'] == journey_name].copy()

# Aggregate by date
daily = journey_data.groupby('date', as_index=False).agg({
    'Delivered': 'sum',
    'Revenue (SAR)': 'sum'
})
daily = daily.sort_values('date').reset_index(drop=True)

# Stopped periods
stop1_start = pd.to_datetime('2025-05-04')
stop1_end = pd.to_datetime('2025-05-18')

stop2_start = pd.to_datetime('2025-08-13')
stop2_end = pd.to_datetime('2025-09-17')

# Pre-stop baselines
before_stop1 = daily[(daily['date'] < stop1_start)].tail(14)
before_stop2 = daily[(daily['date'] < stop2_start) & (daily['date'] > stop1_end)].tail(14)

print(f"🔍 Cart Abandonment - Cosmetics\n")

print(f"Stop 1: {stop1_start.date()} to {stop1_end.date()} (15 days)")
print(f"  14 days before stop: {before_stop1['date'].min().date()} to {before_stop1['date'].max().date()}")
print(f"  Avg Revenue (last 14 days): {before_stop1['Revenue (SAR)'].mean():,.0f} SAR/day")
print(f"  Median Revenue (last 14 days): {before_stop1['Revenue (SAR)'].median():,.0f} SAR/day")
print(f"  Expected loss (15 days): {before_stop1['Revenue (SAR)'].median() * 15:,.0f} SAR\n")

print(f"Stop 2: {stop2_start.date()} to {stop2_end.date()} (36 days)")
print(f"  14 days before stop: {before_stop2['date'].min().date()} to {before_stop2['date'].max().date()}")
print(f"  Avg Revenue (last 14 days): {before_stop2['Revenue (SAR)'].mean():,.0f} SAR/day")
print(f"  Median Revenue (last 14 days): {before_stop2['Revenue (SAR)'].median():,.0f} SAR/day")
print(f"  Expected loss (36 days): {before_stop2['Revenue (SAR)'].median() * 36:,.0f} SAR\n")

total_expected = (before_stop1['Revenue (SAR)'].median() * 15) + (before_stop2['Revenue (SAR)'].median() * 36)
print(f"💰 Total Expected Loss: {total_expected:,.0f} SAR")
print(f"   Avg Daily: {total_expected / 51:,.0f} SAR/day")
