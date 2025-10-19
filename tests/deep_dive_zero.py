"""
Deep dive into Product View Abandonment - Cosmetics to see why it predicted 0
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

journey_name = 'Product View Abandonment - Cosmetics'
journey_data = df[df['Journey Name'] == journey_name].copy()

print(f"🔍 Deep Dive: {journey_name}\n")
print(f"Total rows: {len(journey_data)}")
print(f"Date range: {journey_data['date'].min()} to {journey_data['date'].max()}")

# Aggregate by date
daily = journey_data.groupby('date', as_index=False).agg({
    'Delivered': 'sum',
    'Revenue (SAR)': 'sum',
    'Impression-Through Revenue (SAR)': 'sum',
    'Click-Through Revenue (SAR)': 'sum'
})
daily = daily.sort_values('date').reset_index(drop=True)

print(f"\nDaily aggregated: {len(daily)} days")
print(f"Days with delivery: {(daily['Delivered'] > 0).sum()}")
print(f"Days with revenue: {(daily['Revenue (SAR)'] > 0).sum()}")

# Find stopped periods
daily['is_stopped'] = (daily['Delivered'] == 0)
stopped_periods = []
current_start = None
consecutive = 0
had_activity = False

for idx in range(len(daily)):
    if daily.iloc[idx]['is_stopped']:
        if current_start is None:
            current_start = daily.iloc[idx]['date']
        consecutive += 1
    else:
        if consecutive >= 3 and current_start is not None and had_activity:
            stopped_periods.append({
                'start_date': current_start,
                'end_date': daily.iloc[idx-1]['date'],
                'days_stopped': consecutive
            })
        had_activity = True
        current_start = None
        consecutive = 0

if consecutive >= 3 and current_start is not None and had_activity:
    stopped_periods.append({
        'start_date': current_start,
        'end_date': daily.iloc[-1]['date'],
        'days_stopped': consecutive
    })

print(f"\n📅 Stopped Periods: {len(stopped_periods)}")
for i, p in enumerate(stopped_periods, 1):
    print(f"  {i}. {p['start_date'].date()} to {p['end_date'].date()}: {p['days_stopped']} days")

# Check revenue distribution
print(f"\n💰 Revenue Distribution:")
for col in ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']:
    if col in daily.columns:
        values = daily[col]
        positive_values = values[values > 0]
        print(f"\n{col}:")
        print(f"  Total: {values.sum():,.0f} SAR")
        print(f"  Days with revenue: {len(positive_values)}")
        if len(positive_values) > 0:
            print(f"  Mean (when >0): {positive_values.mean():,.0f} SAR")
            print(f"  Median (when >0): {positive_values.median():,.0f} SAR")
            print(f"  Std: {positive_values.std():,.0f} SAR")
            print(f"  CV: {positive_values.std() / positive_values.mean():.2f}")
        else:
            print(f"  ⚠️  NO POSITIVE VALUES!")

# Check what Prophet would see (after filtering)
print(f"\n🤖 What Prophet Sees:")
for col in ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']:
    if col in daily.columns:
        model_data = daily[['date', col]].copy()
        model_data = model_data.rename(columns={'date': 'ds', col: 'y'})
        model_data = model_data.dropna()
        model_data = model_data[model_data['y'] >= 0]
        
        print(f"\n{col}:")
        print(f"  Data points after filtering: {len(model_data)}")
        if len(model_data) >= 14:
            print(f"  ✅ Enough data for Prophet")
            print(f"  Sum of all y values: {model_data['y'].sum():,.0f}")
            print(f"  Non-zero values: {(model_data['y'] > 0).sum()}")
            
            # IQR capping
            Q1 = model_data['y'].quantile(0.25)
            Q3 = model_data['y'].quantile(0.75)
            IQR = Q3 - Q1
            upper_bound = Q3 + 3 * IQR
            
            print(f"  Q1: {Q1:,.0f}, Q3: {Q3:,.0f}, IQR: {IQR:,.0f}")
            print(f"  Upper bound (Q3 + 3*IQR): {upper_bound:,.0f}")
            
            capped_data = model_data['y'].clip(lower=0, upper=upper_bound)
            print(f"  Sum after capping: {capped_data.sum():,.0f}")
            print(f"  Values capped: {(model_data['y'] != capped_data).sum()}")
        else:
            print(f"  ❌ Insufficient data (<14 needed)")

# Show recent revenue trend before/during/after stopped periods
print(f"\n📊 Revenue Around Stopped Periods:")
for i, p in enumerate(stopped_periods, 1):
    print(f"\nPeriod {i}: {p['start_date'].date()} to {p['end_date'].date()}")
    
    # Before
    before = daily[daily['date'] < p['start_date']].tail(7)
    print(f"  7 days before: {before['Revenue (SAR)'].mean():,.0f} SAR/day")
    
    # During (should be 0 or very low)
    during = daily[(daily['date'] >= p['start_date']) & (daily['date'] <= p['end_date'])]
    print(f"  During stop: {during['Revenue (SAR)'].mean():,.0f} SAR/day (should be low/0)")
    
    # After
    after = daily[daily['date'] > p['end_date']].head(7)
    if len(after) > 0:
        print(f"  7 days after: {after['Revenue (SAR)'].mean():,.0f} SAR/day")
