from dashboard.funnels import (
    analyze_campaign_funnel, analyze_journey_funnel, calculate_funnel_conversion_rates,
)
def test_funnels_importable():
    assert callable(analyze_campaign_funnel)
    assert callable(analyze_journey_funnel)
    assert callable(calculate_funnel_conversion_rates)
