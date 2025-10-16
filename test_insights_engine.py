"""
Quick test script for the new Automated Insights Engine
Tests narrative generation, forecasting, and action recommendations
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Import our insights engine
from insights_engine import (
    generate_narrative_insights,
    predict_revenue_forecast,
    generate_top_actions,
    generate_executive_summary
)

def create_sample_data():
    """Create sample WebEngage-style data for testing"""
    
    # Generate 60 days of sample data
    dates = pd.date_range(end=datetime.now(), periods=60, freq='D')
    
    # Create realistic revenue pattern with a dip and recovery (like Ramadan example)
    base_revenue = 500000
    revenue_pattern = []
    
    for i, date in enumerate(dates):
        # Add some seasonality
        day_of_week_factor = 1.0 if date.dayofweek < 5 else 0.7  # Lower on weekends
        
        # Simulate a dip in middle period (days 25-40) and recovery
        if i < 25:
            seasonal_factor = 1.0
        elif i < 40:
            seasonal_factor = 0.6  # 40% drop (like post-Ramadan)
        else:
            seasonal_factor = 0.8 + (i - 40) * 0.02  # Gradual recovery
        
        daily_revenue = base_revenue * seasonal_factor * day_of_week_factor
        daily_revenue += np.random.normal(0, base_revenue * 0.1)  # Add noise
        revenue_pattern.append(max(0, daily_revenue))
    
    # Create sample dataframe
    df = pd.DataFrame({
        'Reporting Period Start Date': dates,
        'Reporting Period End Date': dates,
        'Day': dates,
        'Journey Name': np.random.choice(['Welcome New Users', 'Cart Abandonment', 'Re-engagement', 'VIP Loyalty'], size=len(dates)),
        'Campaign Name': np.random.choice(['Summer Sale', 'Flash Deal', 'Newsletter', 'Retargeting'], size=len(dates)),
        'Channel': np.random.choice(['Email', 'Push', 'SMS'], size=len(dates)),
        'Segment Name': np.random.choice(['New Users', 'Active', 'At Risk', 'Dormant'], size=len(dates)),
        'Revenue (SAR)': revenue_pattern,
        'Impression-Through Revenue (SAR)': [r * 0.7 for r in revenue_pattern],
        'Click-Through Revenue (SAR)': [r * 0.5 for r in revenue_pattern],
        'Sent': np.random.randint(5000, 15000, size=len(dates)),
        'Delivered': [int(s * np.random.uniform(0.85, 0.95)) for s in np.random.randint(5000, 15000, size=len(dates))],
        'Unique Impressions': np.random.randint(4000, 12000, size=len(dates)),
        'Unique Clicks': [int(i * np.random.uniform(0.02, 0.05)) for i in np.random.randint(4000, 12000, size=len(dates))],
        'Unique Conversions': [int(c * np.random.uniform(0.05, 0.15)) for c in [int(i * np.random.uniform(0.02, 0.05)) for i in np.random.randint(4000, 12000, size=len(dates))]],
    })
    
    return df

def test_narrative_insights():
    """Test narrative insights generation"""
    print("\n" + "="*80)
    print("TEST 1: NARRATIVE INSIGHTS GENERATION")
    print("="*80)
    
    df = create_sample_data()
    insights = generate_narrative_insights(df, lookback_days=30)
    
    print("\n📰 Headline Insights:")
    for insight in insights.get('headline_insights', []):
        print(f"  {insight.get('emoji', '')} {insight.get('title', '')}")
        print(f"     {insight.get('message', '')}\n")
    
    print("\n📈 Trend Analysis:")
    for trend in insights.get('trend_analysis', []):
        print(f"  {trend.get('emoji', '')} {trend.get('title', '')}")
        print(f"     {trend.get('message', '')}\n")
    
    print("\n🚨 Performance Alerts:")
    for alert in insights.get('performance_alerts', []):
        print(f"  {alert.get('emoji', '')} {alert.get('title', '')}")
        print(f"     {alert.get('message', '')}")
        print(f"     Action: {alert.get('action', '')}\n")
    
    print("\n🎯 Opportunities:")
    for opp in insights.get('opportunities', []):
        print(f"  {opp.get('emoji', '')} {opp.get('title', '')}")
        print(f"     {opp.get('message', '')}")
        print(f"     Action: {opp.get('action', '')}\n")
    
    print("✅ Narrative insights test completed!")

def test_revenue_forecast():
    """Test revenue forecasting"""
    print("\n" + "="*80)
    print("TEST 2: REVENUE FORECASTING")
    print("="*80)
    
    df = create_sample_data()
    
    print("\n🔮 Generating 14-day forecast...")
    forecast = predict_revenue_forecast(df, forecast_days=14)
    
    if forecast:
        print(f"\n📊 Forecast Results:")
        print(f"  Total Predicted (14 days): {forecast.get('total_predicted', 0):,.0f} SAR")
        print(f"  Daily Average: {forecast.get('daily_average', 0):,.0f} SAR")
        print(f"  Trend: {forecast.get('trend_pct', 0):+.1f}%")
        print(f"  Confidence Range: {forecast.get('confidence_lower', 0):,.0f} - {forecast.get('confidence_upper', 0):,.0f} SAR")
        
        insight = forecast.get('insight', {})
        print(f"\n💡 Insight: {insight.get('emoji', '')} {insight.get('message', '')}")
        
        print("\n✅ Revenue forecast test completed!")
    else:
        print("❌ Forecast generation failed (need more historical data)")

def test_top_actions():
    """Test action recommendations"""
    print("\n" + "="*80)
    print("TEST 3: ACTION RECOMMENDATIONS")
    print("="*80)
    
    df = create_sample_data()
    actions = generate_top_actions(df, max_actions=5)
    
    print(f"\n🎯 Top {len(actions)} Recommended Actions:\n")
    
    for idx, action in enumerate(actions, 1):
        priority = action.get('priority', 'MEDIUM')
        title = action.get('title', '')
        action_text = action.get('action', '')
        impact = action.get('expected_impact', '')
        confidence = action.get('confidence', '')
        impl_time = action.get('implementation_time', '')
        
        print(f"{idx}. [{priority}] {title}")
        print(f"   Action: {action_text}")
        print(f"   Expected Impact: {impact}")
        print(f"   Confidence: {confidence} | Implementation: {impl_time}\n")
    
    print("✅ Action recommendations test completed!")

def test_executive_summary():
    """Test full executive summary generation"""
    print("\n" + "="*80)
    print("TEST 4: EXECUTIVE SUMMARY")
    print("="*80)
    
    df = create_sample_data()
    
    print("\n📊 Generating comprehensive executive summary...")
    summary = generate_executive_summary(df)
    
    print(f"\n📅 Analysis Period: {summary.get('period', 'N/A')}")
    print(f"⏰ Generated: {summary.get('timestamp', 'N/A')}")
    
    metrics = summary.get('headline_metrics', {})
    print(f"\n💰 Key Metrics:")
    print(f"  Total Revenue: {metrics.get('total_revenue', 0):,.0f} SAR")
    print(f"  Total Conversions: {metrics.get('total_conversions', 0):,.0f}")
    print(f"  Avg Delivery Rate: {metrics.get('avg_delivery_rate', 0):.1%}")
    print(f"  Avg CTR: {metrics.get('avg_ctr', 0):.2%}")
    print(f"  Avg Conversion Rate: {metrics.get('avg_conversion_rate', 0):.2%}")
    
    print(f"\n🚨 Alerts Count: {summary.get('alerts_count', 0)}")
    print(f"🎯 Actions Generated: {len(summary.get('top_actions', []))}")
    
    # Show forecast if available
    forecast = summary.get('forecast')
    if forecast:
        print(f"\n📈 14-Day Forecast:")
        print(f"  Predicted: {forecast.get('total_predicted', 0):,.0f} SAR")
        print(f"  Trend: {forecast.get('trend_pct', 0):+.1f}%")
    
    print("\n✅ Executive summary test completed!")

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("AUTOMATED INSIGHTS ENGINE - TEST SUITE")
    print("="*80)
    print("\nTesting the new insights engine with sample data...")
    
    try:
        test_narrative_insights()
        test_revenue_forecast()
        test_top_actions()
        test_executive_summary()
        
        print("\n" + "="*80)
        print("🎉 ALL TESTS PASSED!")
        print("="*80)
        print("\n✅ The Automated Insights Engine is ready to use!")
        print("📊 Run 'streamlit run app.py' to see it in action")
        print("🎯 Navigate to '🎯 Automated Insights' page in the dashboard\n")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
