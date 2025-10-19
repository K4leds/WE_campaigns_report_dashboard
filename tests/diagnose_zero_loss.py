"""
Diagnostic script to identify why some journeys show 0 loss estimation
"""
import pandas as pd
import sys
sys.path.insert(0, '.')

from app import analyze_stopped_journeys

# Load test data
df = pd.read_csv('tests/Daily Q2_Q3.csv')
if 'Day' in df.columns:
    df['date'] = pd.to_datetime(df['Day'])
elif 'Reporting Period Start Date' in df.columns:
    df['date'] = pd.to_datetime(df['Reporting Period Start Date'])

print("🔍 Analyzing all stopped journeys for zero loss estimation...\n")

# Run stopped journey analysis
result = analyze_stopped_journeys(df, stopped_threshold_days=3, lookback_period=90)

if 'error' in result:
    print(f"❌ Error: {result['error']}")
    sys.exit(1)

stopped_journeys = result.get('stopped_journeys', [])
print(f"📊 Found {len(stopped_journeys)} stopped journeys\n")

# Analyze each stopped journey
zero_loss_journeys = []
low_loss_journeys = []

for journey in stopped_journeys:
    journey_name = journey['journey_name']
    loss_data = journey['estimated_revenue_loss']
    total_loss = loss_data['total_loss']
    avg_daily_loss = loss_data['avg_daily_loss']
    method = loss_data.get('method', 'unknown')
    quality = loss_data.get('model_quality', 'unknown')
    
    # Get journey data for diagnostics
    journey_df = df[df['Journey Name'] == journey_name].copy()
    
    # Calculate revenue stats
    has_revenue = 'Revenue (SAR)' in journey_df.columns
    if has_revenue:
        total_revenue = journey_df['Revenue (SAR)'].sum()
        days_with_revenue = (journey_df['Revenue (SAR)'] > 0).sum()
        avg_revenue = journey_df[journey_df['Revenue (SAR)'] > 0]['Revenue (SAR)'].mean()
    else:
        total_revenue = 0
        days_with_revenue = 0
        avg_revenue = 0
    
    # Aggregate by date
    if 'date' in journey_df.columns:
        daily = journey_df.groupby('date').agg({'Revenue (SAR)': 'sum'} if has_revenue else {})
        unique_days = len(daily)
    else:
        unique_days = 0
    
    # Check for zero or very low loss
    if total_loss == 0:
        zero_loss_journeys.append({
            'name': journey_name,
            'stopped_days': journey['stopped_periods']['total_stopped_days'],
            'total_revenue': total_revenue,
            'days_with_revenue': days_with_revenue,
            'avg_revenue': avg_revenue,
            'unique_days': unique_days,
            'method': method,
            'quality': quality,
            'attribution': loss_data.get('attribution_breakdown', {})
        })
    elif avg_daily_loss < 100:
        low_loss_journeys.append({
            'name': journey_name,
            'stopped_days': journey['stopped_periods']['total_stopped_days'],
            'total_loss': total_loss,
            'avg_daily_loss': avg_daily_loss,
            'total_revenue': total_revenue,
            'days_with_revenue': days_with_revenue,
            'avg_revenue': avg_revenue,
            'unique_days': unique_days,
            'method': method,
            'quality': quality,
            'attribution': loss_data.get('attribution_breakdown', {})
        })

# Report findings
print("=" * 80)
print("ZERO LOSS JOURNEYS")
print("=" * 80)

if zero_loss_journeys:
    for j in zero_loss_journeys:
        print(f"\n❌ {j['name']}")
        print(f"   Stopped Days: {j['stopped_days']}")
        print(f"   Method: {j['method']}")
        print(f"   Quality: {j['quality']}")
        print(f"   Total Revenue (all time): {j['total_revenue']:,.2f} SAR")
        print(f"   Days with Revenue: {j['days_with_revenue']}")
        print(f"   Avg Revenue (when >0): {j['avg_revenue']:,.2f} SAR")
        print(f"   Unique Days in Data: {j['unique_days']}")
        print(f"   Attribution Breakdown: {j['attribution']}")
        
        # Diagnose the issue
        if j['total_revenue'] == 0:
            print(f"   ⚠️  ISSUE: No revenue data at all")
        elif j['days_with_revenue'] < 14:
            print(f"   ⚠️  ISSUE: Insufficient revenue days (<14 needed for Prophet)")
        elif j['unique_days'] < 14:
            print(f"   ⚠️  ISSUE: Insufficient data points (<14 days)")
        elif not j['attribution']:
            print(f"   ⚠️  ISSUE: All attribution models failed")
        else:
            print(f"   ⚠️  ISSUE: Unknown - model ran but predicted 0")
else:
    print("\n✅ No journeys with zero loss estimation!")

print("\n" + "=" * 80)
print("LOW LOSS JOURNEYS (<100 SAR/day)")
print("=" * 80)

if low_loss_journeys:
    for j in low_loss_journeys:
        print(f"\n⚠️  {j['name']}")
        print(f"   Stopped Days: {j['stopped_days']}")
        print(f"   Total Loss: {j['total_loss']:,.2f} SAR")
        print(f"   Avg Daily Loss: {j['avg_daily_loss']:,.2f} SAR/day")
        print(f"   Method: {j['method']}")
        print(f"   Quality: {j['quality']}")
        print(f"   Total Revenue (all time): {j['total_revenue']:,.2f} SAR")
        print(f"   Avg Revenue (when >0): {j['avg_revenue']:,.2f} SAR/day")
        print(f"   Unique Days: {j['unique_days']}")
        
        # Check reasonableness
        if j['avg_revenue'] > 0:
            ratio = j['avg_daily_loss'] / j['avg_revenue']
            print(f"   Loss vs Avg Ratio: {ratio:.1%}")
            if ratio < 0.2:
                print(f"   ⚠️  Loss estimate is LOW compared to historical average")
            elif ratio > 2.0:
                print(f"   ⚠️  Loss estimate is HIGH compared to historical average")
            else:
                print(f"   ✅ Loss estimate is reasonable")
else:
    print("\n✅ No journeys with suspiciously low loss!")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print(f"Total Stopped Journeys: {len(stopped_journeys)}")
print(f"Zero Loss: {len(zero_loss_journeys)}")
print(f"Low Loss (<100/day): {len(low_loss_journeys)}")
print(f"Normal Loss: {len(stopped_journeys) - len(zero_loss_journeys) - len(low_loss_journeys)}")
