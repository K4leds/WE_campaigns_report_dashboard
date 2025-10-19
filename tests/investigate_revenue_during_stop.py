"""
Investigate why stopped journey still shows revenue after 7-day conversion window
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

print(f"🔍 Investigating: {journey_name}\n")

# Aggregate by date
daily = journey_data.groupby('date', as_index=False).agg({
    'Delivered': 'sum',
    'Revenue (SAR)': 'sum',
    'Impression-Through Revenue (SAR)': 'sum',
    'Click-Through Revenue (SAR)': 'sum',
    'Unique Conversions': 'sum',
    'Sent': 'sum'
})
daily = daily.sort_values('date').reset_index(drop=True)

# Find the long stopped period (July 17 - Sept 30)
stopped_start = pd.to_datetime('2025-07-17')
stopped_end = pd.to_datetime('2025-09-30')

print(f"📅 Analyzing stopped period: {stopped_start.date()} to {stopped_end.date()}")
print(f"   Duration: {(stopped_end - stopped_start).days + 1} days\n")

# Check last delivery date
last_delivery = daily[daily['Delivered'] > 0]['date'].max()
print(f"🚚 Last Delivery Date: {last_delivery.date()}")
print(f"   Days since last delivery to end of stop: {(stopped_end - last_delivery).days}\n")

# With 7-day conversion window, revenue should stop 7 days after last delivery
conversion_window_end = last_delivery + pd.Timedelta(days=7)
print(f"⏰ 7-Day Conversion Window Ends: {conversion_window_end.date()}")
print(f"   Revenue should be 0 after this date\n")

# Check revenue during stopped period
during_stop = daily[(daily['date'] >= stopped_start) & (daily['date'] <= stopped_end)]
print(f"📊 During Stopped Period ({len(during_stop)} days):")
print(f"   Total Delivered: {during_stop['Delivered'].sum():,.0f}")
print(f"   Total Sent: {during_stop['Sent'].sum():,.0f}")
print(f"   Total Revenue: {during_stop['Revenue (SAR)'].sum():,.0f} SAR")
print(f"   Total Conversions: {during_stop['Unique Conversions'].sum():,.0f}")

# Break down by day - show days with revenue during stop
print(f"\n📅 Days with Revenue During Stop Period:")
revenue_during_stop = during_stop[during_stop['Revenue (SAR)'] > 0].copy()
print(f"   Days with revenue: {len(revenue_during_stop)} out of {len(during_stop)}")

if len(revenue_during_stop) > 0:
    print(f"\n   First 10 days with revenue:")
    for _, row in revenue_during_stop.head(10).iterrows():
        days_since_last_delivery = (row['date'] - last_delivery).days
        print(f"   {row['date'].date()}: {row['Revenue (SAR)']:>8,.0f} SAR | "
              f"Delivered: {row['Delivered']:>4,.0f} | "
              f"Days since last delivery: {days_since_last_delivery}")
    
    # Check if revenue continues after conversion window
    after_window = revenue_during_stop[revenue_during_stop['date'] > conversion_window_end]
    print(f"\n   ⚠️  Days with revenue AFTER 7-day window: {len(after_window)}")
    
    if len(after_window) > 0:
        print(f"   🚨 PROBLEM: Revenue reported {(after_window['date'].max() - conversion_window_end).days} days after conversion window!")
        print(f"\n   Sample days AFTER conversion window:")
        for _, row in after_window.head(5).iterrows():
            print(f"   {row['date'].date()}: {row['Revenue (SAR)']:>8,.0f} SAR | "
                  f"Delivered: {row['Delivered']:>4,.0f} | "
                  f"Conversions: {row['Unique Conversions']:>4,.0f}")

# Check if there are multiple campaigns for this journey
print(f"\n🔍 Campaign Breakdown:")
campaign_counts = journey_data.groupby('Campaign Name').agg({
    'date': ['min', 'max', 'count'],
    'Delivered': 'sum',
    'Revenue (SAR)': 'sum'
}).round(2)
print(campaign_counts)

# Check if different campaigns are active during the "stopped" period
print(f"\n🔍 Activity During Stopped Period by Campaign:")
during_stop_raw = journey_data[(journey_data['date'] >= stopped_start) & (journey_data['date'] <= stopped_end)]
campaign_stop = during_stop_raw.groupby('Campaign Name').agg({
    'Delivered': 'sum',
    'Sent': 'sum',
    'Revenue (SAR)': 'sum',
    'Unique Conversions': 'sum'
}).round(2)
print(campaign_stop)

print(f"\n💡 Analysis:")
if during_stop['Delivered'].sum() == 0 and during_stop['Revenue (SAR)'].sum() > 0:
    days_with_revenue_after_window = len(revenue_during_stop[revenue_during_stop['date'] > conversion_window_end])
    if days_with_revenue_after_window > 0:
        print(f"   🚨 DATA QUALITY ISSUE:")
        print(f"      - Journey stopped delivering on {last_delivery.date()}")
        print(f"      - 7-day conversion window ended on {conversion_window_end.date()}")
        print(f"      - But revenue is reported until {revenue_during_stop['date'].max().date()}")
        print(f"      - This is {(revenue_during_stop['date'].max() - conversion_window_end).days} days BEYOND the conversion window")
        print(f"\n   🤔 Possible Reasons:")
        print(f"      1. Multiple campaigns in same journey with different schedules")
        print(f"      2. Data attribution issue - revenue attributed to wrong journey/date")
        print(f"      3. Conversion window setting in WebEngage is >7 days")
        print(f"      4. Return customers creating new conversions (not from campaign)")
    else:
        print(f"   ✅ Revenue aligns with 7-day conversion window")
else:
    print(f"   Journey still has some delivery activity during 'stopped' period")
