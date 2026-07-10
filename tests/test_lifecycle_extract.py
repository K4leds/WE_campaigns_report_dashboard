from dashboard.lifecycle import (
    analyze_journey_lifecycle, analyze_stopped_journeys,
    estimate_revenue_loss_ml, create_cohort_analysis,
    create_revenue_attribution_waterfall, get_lifecycle_recommendation,
    generate_stopped_journey_recommendations,
)
def test_lifecycle_importable():
    assert callable(analyze_stopped_journeys)
    assert callable(estimate_revenue_loss_ml)
