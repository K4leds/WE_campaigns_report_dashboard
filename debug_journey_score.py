#!/usr/bin/env python3
"""
Debug script to explain why a specific journey got a particular health score.
Shows raw metrics, smoothed values, percentiles, and component contributions.
"""

import pandas as pd
import numpy as np
import sys
sys.path.append('.')
from app import clean_data, calculate_journey_health_score

def debug_journey_scoring(journey_name="Cart Abandonment - Cosmetics [w/o Recommendations]"):
    # Load data
    df = pd.read_csv('data/report-Daily.csv')
    df_clean = clean_data(df)
    
    print(f"\n🔍 DEBUG: Analyzing '{journey_name}' scoring")
    print("=" * 60)
    
    # Get the specific journey data
    journey_data = df_clean[df_clean['Journey Name'] == journey_name].copy()
    
    if journey_data.empty:
        print(f"❌ Journey '{journey_name}' not found!")
        print("Available journeys:")
        for name in df_clean['Journey Name'].unique():
            print(f"  - {name}")
        return
    
    print(f"📊 Journey has {len(journey_data)} rows of data")
    
    # Calculate the score with detailed breakdown
    score_result = calculate_journey_health_score(journey_data, df_clean)
    
    print(f"\n🎯 FINAL SCORE: {score_result['health_score']} ({score_result['tier']})")
    print(f"Method: {score_result['scoring_method']}")
    
    # Show raw metrics for this journey
    print(f"\n📈 RAW METRICS for '{journey_name}':")
    
    # Delivery metrics
    if 'Sent' in journey_data.columns and 'Delivered' in journey_data.columns:
        total_sent = journey_data['Sent'].sum()
        total_delivered = journey_data['Delivered'].sum()
        delivery_rate = (total_delivered / total_sent) if total_sent > 0 else 0
        print(f"  📤 Delivery: {total_delivered:,}/{total_sent:,} = {delivery_rate:.1%}")
    
    # Engagement metrics
    if 'Unique Clicks' in journey_data.columns and 'Unique Impressions' in journey_data.columns:
        total_clicks = journey_data['Unique Clicks'].sum()
        total_impressions = journey_data['Unique Impressions'].sum()
        ctr = (total_clicks / total_impressions) if total_impressions > 0 else 0
        print(f"  👆 CTR: {total_clicks:,}/{total_impressions:,} = {ctr:.2%}")
    
    # Conversion metrics - Use corrected logic like in the main app
    if 'Conversion Rate' in journey_data.columns and journey_data['Conversion Rate'].notna().any():
        # Use the provided conversion rate column (already calculated correctly by WebEngage)
        conv_rate = journey_data['Conversion Rate'].mean() / 100.0  # Convert percentage to decimal
        total_conversions = journey_data['Unique Conversions'].sum() if 'Unique Conversions' in journey_data.columns else 0
        total_clicks = journey_data['Unique Clicks'].sum() if 'Unique Clicks' in journey_data.columns else 0
        print(f"  💰 Conversion: {total_conversions:,} conv / {total_clicks:,} clicks = {conv_rate:.2%} (from Conversion Rate column)")
    elif 'Unique Conversions' in journey_data.columns and 'Unique Clicks' in journey_data.columns:
        total_conversions = journey_data['Unique Conversions'].sum()
        total_clicks = journey_data['Unique Clicks'].sum()
        conv_rate = (total_conversions / total_clicks) if total_clicks > 0 else 0
        print(f"  💰 Conversion: {total_conversions:,}/{total_clicks:,} = {conv_rate:.2%} (manual calculation - may be unreliable)")
    else:
        conv_rate = 0
    
    # Revenue metrics
    if 'Revenue (SAR)' in journey_data.columns and 'Unique Conversions' in journey_data.columns:
        total_revenue = journey_data['Revenue (SAR)'].sum()
        total_conversions = journey_data['Unique Conversions'].sum()
        rpc = (total_revenue / total_conversions) if total_conversions > 0 else 0
        log_rpc = np.log1p(rpc)
        print(f"  💵 Revenue: {total_revenue:,.0f} SAR / {total_conversions:,} conv = {rpc:.0f} SAR/conv")
        print(f"  📊 Log(RPC): log(1+{rpc:.0f}) = {log_rpc:.2f}")
    
    # Component scores breakdown
    print(f"\n🔢 COMPONENT SCORES:")
    weights = {'delivery': 0.20, 'engagement': 0.25, 'conversion': 0.30, 'revenue': 0.25}
    
    for component, score in score_result['component_scores'].items():
        weight = weights[component]
        contribution = score * weight
        print(f"  {component.capitalize():>12}: {score:5.1f} × {weight:.2f} = {contribution:5.1f} points")
    
    total_weighted = sum(score_result['component_scores'][k] * weights[k] for k in weights)
    print(f"  {'TOTAL':>12}: {total_weighted:5.1f}")
    
    # Population comparison
    print(f"\n📊 POPULATION COMPARISON:")
    
    # Calculate population percentiles for context
    journey_groups = df_clean.groupby('Journey Name')
    
    # Delivery rates across all journeys
    delivery_rates = []
    for name, group in journey_groups:
        if 'Sent' in group.columns and 'Delivered' in group.columns:
            sent = group['Sent'].sum()
            delivered = group['Delivered'].sum()
            if sent > 0:
                delivery_rates.append(delivered / sent)
    
    if delivery_rates and delivery_rate is not None:
        percentile = (np.array(delivery_rates) <= delivery_rate).mean() * 100
        print(f"  📤 Delivery {delivery_rate:.1%} is {percentile:.0f}th percentile")
    
    # CTRs across all journeys
    ctrs = []
    for name, group in journey_groups:
        if 'Unique Clicks' in group.columns and 'Unique Impressions' in group.columns:
            clicks = group['Unique Clicks'].sum()
            impressions = group['Unique Impressions'].sum()
            if impressions > 0:
                ctrs.append(clicks / impressions)
    
    if ctrs and ctr is not None:
        percentile = (np.array(ctrs) <= ctr).mean() * 100
        print(f"  👆 CTR {ctr:.2%} is {percentile:.0f}th percentile")
    
    # Conversion rates across all journeys - Use corrected logic
    conv_rates = []
    for name, group in journey_groups:
        if 'Conversion Rate' in group.columns and group['Conversion Rate'].notna().any():
            # Use the provided conversion rate column
            journey_conv_rate = group['Conversion Rate'].mean() / 100.0
            if not pd.isna(journey_conv_rate):
                conv_rates.append(journey_conv_rate)
        elif 'Unique Conversions' in group.columns and 'Unique Clicks' in group.columns:
            # Fallback to manual calculation
            conversions = group['Unique Conversions'].sum()
            clicks = group['Unique Clicks'].sum()
            if clicks > 0:
                conv_rates.append(conversions / clicks)
    
    if conv_rates and conv_rate is not None:
        percentile = (np.array(conv_rates) <= conv_rate).mean() * 100
        print(f"  💰 Conversion {conv_rate:.2%} is {percentile:.0f}th percentile")
    
    # Revenue per conversion across all journeys
    rpcs = []
    for name, group in journey_groups:
        if 'Revenue (SAR)' in group.columns and 'Unique Conversions' in group.columns:
            revenue = group['Revenue (SAR)'].sum()
            conversions = group['Unique Conversions'].sum()
            if conversions > 0:
                rpcs.append(revenue / conversions)
    
    if rpcs and rpc is not None:
        percentile = (np.array(rpcs) <= rpc).mean() * 100
        print(f"  💵 RPC {rpc:.0f} SAR is {percentile:.0f}th percentile")
    
    # Recommendations
    print(f"\n💡 RECOMMENDATIONS:")
    for rec in score_result['recommendations']:
        print(f"  {rec}")
    
    print(f"\n📋 SUMMARY:")
    print(f"The '{journey_name}' scored {score_result['health_score']:.1f} (Poor) because:")
    
    worst_components = sorted(score_result['component_scores'].items(), key=lambda x: x[1])
    for component, score in worst_components[:2]:  # Show worst 2 components
        if score < 40:
            print(f"  🚨 {component.capitalize()} score ({score:.1f}) is critically low")
        elif score < 60:
            print(f"  ⚠️ {component.capitalize()} score ({score:.1f}) is below average")

if __name__ == "__main__":
    debug_journey_scoring()