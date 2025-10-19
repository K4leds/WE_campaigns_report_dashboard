"""
Test stopped journey detection logic
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Simulate a journey with stopped periods
dates = pd.date_range('2025-07-01', '2025-09-10', freq='D')
delivered = []

# Pattern: Active, then stopped 35 days, then active, then stopped 30 days, then active, then stopped 3 days
for i, date in enumerate(dates):
    if i < 5:
        # Active first 5 days (July 1-5)
        delivered.append(1000 + i*100)
    elif i < 40:  # July 6 - Aug 14 (35 days stopped)
        delivered.append(0)
    elif i < 45:  # Aug 15-19 (5 days active)
        delivered.append(1000 + i*100)
    elif i < 75:  # Aug 20 - Sep 18 (30 days stopped)
        delivered.append(0)
    elif i < 80:  # Sep 19-23 (5 days active)
        delivered.append(1000 + i*100)
    else:  # Sep 24+ (3 days stopped)
        delivered.append(0)

test_df = pd.DataFrame({
    'date': dates,
    'Delivered': delivered
})

print("Test Data:")
print(test_df.head(10))
print("\n...")
print(test_df.tail(10))

# Now simulate the detection logic
complete_journey_data = test_df.copy()
complete_journey_data['is_stopped'] = (complete_journey_data['Delivered'] == 0)

stopped_threshold_days = 3
stopped_periods = []
current_stopped_start = None
current_stopped_start_idx = None
consecutive_stopped = 0
had_activity_before = False

print("\n" + "="*80)
print("DETECTION PROCESS:")
print("="*80)

for idx in range(len(complete_journey_data)):
    row = complete_journey_data.iloc[idx]
    
    if row['is_stopped']:
        if current_stopped_start is None:
            current_stopped_start = row['date']
            current_stopped_start_idx = idx
            print(f"\n🔴 Stopped period started at idx={idx}, date={row['date'].date()}")
        consecutive_stopped += 1
    else:
        # Journey is active
        if consecutive_stopped >= stopped_threshold_days and current_stopped_start is not None and had_activity_before:
            prev_date = complete_journey_data.iloc[idx - 1]['date']
            actual_calendar_days = (prev_date - current_stopped_start).days + 1
            
            print(f"✅ Stopped period ended at idx={idx-1}, date={prev_date.date()}")
            print(f"   Start: {current_stopped_start.date()}")
            print(f"   End: {prev_date.date()}")
            print(f"   Consecutive rows: {consecutive_stopped}")
            print(f"   Actual calendar days: {actual_calendar_days}")
            print(f"   Match: {'✓' if consecutive_stopped == actual_calendar_days else '✗ MISMATCH!'}")
            
            stopped_periods.append({
                'start_date': current_stopped_start,
                'end_date': prev_date,
                'days_stopped': actual_calendar_days,
                'consecutive_rows': consecutive_stopped
            })
        
        if not had_activity_before:
            print(f"🟢 First activity detected at idx={idx}, date={row['date'].date()}")
        
        had_activity_before = True
        current_stopped_start = None
        current_stopped_start_idx = None
        consecutive_stopped = 0

# Check for stopped period at the end
if consecutive_stopped >= stopped_threshold_days and current_stopped_start is not None and had_activity_before:
    last_date = complete_journey_data.iloc[-1]['date']
    actual_calendar_days = (last_date - current_stopped_start).days + 1
    
    print(f"✅ Stopped period at end, date={last_date.date()}")
    print(f"   Start: {current_stopped_start.date()}")
    print(f"   End: {last_date.date()}")
    print(f"   Consecutive rows: {consecutive_stopped}")
    print(f"   Actual calendar days: {actual_calendar_days}")
    print(f"   Match: {'✓' if consecutive_stopped == actual_calendar_days else '✗ MISMATCH!'}")
    
    stopped_periods.append({
        'start_date': current_stopped_start,
        'end_date': last_date,
        'days_stopped': actual_calendar_days,
        'consecutive_rows': consecutive_stopped
    })

print("\n" + "="*80)
print("RESULTS:")
print("="*80)
print(f"\nDetected {len(stopped_periods)} stopped period(s):\n")

for i, period in enumerate(stopped_periods, 1):
    print(f"Period {i}:")
    print(f"  Start Date: {period['start_date'].date()}")
    print(f"  End Date: {period['end_date'].date()}")
    print(f"  Days Stopped: {period['days_stopped']}")
    print(f"  Consecutive Rows: {period['consecutive_rows']}")
    
    # Verify
    expected_days = (period['end_date'] - period['start_date']).days + 1
    print(f"  Verification: {period['days_stopped']} days_stopped == {expected_days} calculated → {'✓ CORRECT' if period['days_stopped'] == expected_days else '✗ ERROR!'}")
    print()
