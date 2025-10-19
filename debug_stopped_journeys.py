"""
Debug script to analyze stopped journey detection
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def debug_stopped_detection(df, journey_name, stopped_threshold_days=3):
    """Debug stopped journey detection for a specific journey"""
    
    # Ensure date column exists
    if 'Reporting Period Start Date' in df.columns:
        df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
    elif 'Day' in df.columns:
        df['date'] = pd.to_datetime(df['Day'])
    else:
        print("No date column found")
        return
    
    # Filter for specific journey
    journey_data = df[df['Journey Name'] == journey_name].copy()
    journey_data = journey_data.sort_values('date').reset_index(drop=True)
    
    print(f"\n{'='*80}")
    print(f"Analyzing Journey: {journey_name}")
    print(f"{'='*80}")
    print(f"Total rows: {len(journey_data)}")
    print(f"Date range: {journey_data['date'].min()} to {journey_data['date'].max()}")
    print(f"Total calendar days: {(journey_data['date'].max() - journey_data['date'].min()).days + 1}")
    
    # Check for date gaps
    journey_data['date_diff'] = journey_data['date'].diff().dt.days
    gaps = journey_data[journey_data['date_diff'] > 1]
    if len(gaps) > 0:
        print(f"\n⚠️ WARNING: Found {len(gaps)} date gaps in the data!")
        print("Date gaps:")
        for idx, row in gaps.iterrows():
            prev_date = journey_data.iloc[idx-1]['date']
            print(f"  Gap of {row['date_diff']} days: {prev_date.date()} → {row['date'].date()}")
    
    # Check delivery status
    if 'Delivered' not in journey_data.columns:
        print("\n❌ 'Delivered' column not found!")
        return
    
    # Aggregate multiple rows per date (same journey may have multiple campaigns per date)
    daily = journey_data.groupby('date', as_index=False).agg({'Delivered': 'sum'})
    daily['Delivered'] = daily['Delivered'].fillna(0)
    daily['is_stopped'] = (daily['Delivered'] == 0)
    stopped_rows = daily[daily['is_stopped']]
    print(f"\nRows with zero delivery (daily-aggregated): {len(stopped_rows)} out of {len(daily)}")
    
    # Show delivery pattern
    print(f"\nDelivery pattern (last 30 rows):")
    print("-" * 80)
    for idx in range(max(0, len(daily)-30), len(daily)):
        row = daily.iloc[idx]
        status = "🔴 STOPPED" if row['is_stopped'] else "🟢 Active"
        delivered = row['Delivered'] if not pd.isna(row['Delivered']) else 0
        print(f"{row['date'].date()} | Delivered: {delivered:>10,.0f} | {status}")
    
    # CURRENT detection logic (row-based)
    print(f"\n{'='*80}")
    print("CURRENT DETECTION LOGIC (Row-based):")
    print(f"{'='*80}")
    
    stopped_periods_current = []
    current_stopped_start = None
    consecutive_stopped = 0
    
    for idx in range(len(daily)):
        row = daily.iloc[idx]
        
        if row['is_stopped']:
            if current_stopped_start is None:
                current_stopped_start = row['date']
            consecutive_stopped += 1
        else:
            if consecutive_stopped >= stopped_threshold_days and current_stopped_start is not None:
                prev_date = daily.iloc[idx - 1]['date']
                days_stopped = (prev_date - current_stopped_start).days + 1
                
                stopped_periods_current.append({
                    'start_date': current_stopped_start,
                    'end_date': prev_date,
                    'days_stopped': days_stopped,
                    'consecutive_rows': consecutive_stopped
                })
            current_stopped_start = None
            consecutive_stopped = 0
    
    # Check for stopped period at the end
    if consecutive_stopped >= stopped_threshold_days and current_stopped_start is not None:
        last_date = daily.iloc[-1]['date']
        days_stopped = (last_date - current_stopped_start).days + 1
        
        stopped_periods_current.append({
            'start_date': current_stopped_start,
            'end_date': last_date,
            'days_stopped': days_stopped,
            'consecutive_rows': consecutive_stopped
        })
    
    print(f"\nDetected {len(stopped_periods_current)} stopped period(s):")
    for i, period in enumerate(stopped_periods_current, 1):
        print(f"\nPeriod {i}:")
        print(f"  Start: {period['start_date'].date()}")
        print(f"  End: {period['end_date'].date()}")
        print(f"  Calendar days stopped: {period['days_stopped']}")
        print(f"  Consecutive rows: {period['consecutive_rows']}")
    
    # NEW detection logic (calendar-based with gap filling)
    print(f"\n{'='*80}")
    print("IMPROVED DETECTION LOGIC (Calendar-based):")
    print(f"{'='*80}")
    
    # Create a complete date range
    date_range = pd.date_range(
        start=daily['date'].min(),
        end=daily['date'].max(),
        freq='D'
    )
    
    # Create complete dataframe with all dates
    complete_df = pd.DataFrame({'date': date_range})
    complete_df = complete_df.merge(daily[['date', 'Delivered']], on='date', how='left')
    complete_df['Delivered'] = complete_df['Delivered'].fillna(0)
    complete_df['is_stopped'] = (complete_df['Delivered'] == 0)
    
    print(f"\nComplete calendar view:")
    print(f"  Total calendar days: {len(complete_df)}")
    print(f"  Days with data: {len(journey_data)}")
    print(f"  Missing days (filled as stopped): {len(complete_df) - len(journey_data)}")
    
    # Detect stopped periods in complete calendar
    stopped_periods_improved = []
    current_stopped_start = None
    consecutive_stopped = 0
    
    for idx in range(len(complete_df)):
        row = complete_df.iloc[idx]
        
        if row['is_stopped']:
            if current_stopped_start is None:
                current_stopped_start = row['date']
            consecutive_stopped += 1
        else:
            if consecutive_stopped >= stopped_threshold_days and current_stopped_start is not None:
                prev_date = complete_df.iloc[idx - 1]['date']
                
                stopped_periods_improved.append({
                    'start_date': current_stopped_start,
                    'end_date': prev_date,
                    'days_stopped': consecutive_stopped
                })
            current_stopped_start = None
            consecutive_stopped = 0
    
    # Check for stopped period at the end
    if consecutive_stopped >= stopped_threshold_days and current_stopped_start is not None:
        last_date = complete_df.iloc[-1]['date']
        
        stopped_periods_improved.append({
            'start_date': current_stopped_start,
            'end_date': last_date,
            'days_stopped': consecutive_stopped
        })
    
    print(f"\nDetected {len(stopped_periods_improved)} stopped period(s):")
    for i, period in enumerate(stopped_periods_improved, 1):
        print(f"\nPeriod {i}:")
        print(f"  Start: {period['start_date'].date()}")
        print(f"  End: {period['end_date'].date()}")
        print(f"  Days stopped: {period['days_stopped']}")
    
    print(f"\n{'='*80}")
    print("SUMMARY:")
    print(f"{'='*80}")
    print(f"Current logic detected: {len(stopped_periods_current)} period(s)")
    print(f"Improved logic detected: {len(stopped_periods_improved)} period(s)")
    print(f"Difference: {len(stopped_periods_improved) - len(stopped_periods_current)} additional period(s)")
    
    return stopped_periods_current, stopped_periods_improved


if __name__ == "__main__":
    print("Stopped Journey Detection Debugger")
    print("="*80)
    
    # This script should be imported and used with your actual dataframe
    print("\nUsage:")
    print("  import debug_stopped_journeys as dbg")
    print("  dbg.debug_stopped_detection(your_df, 'Journey Name')")
