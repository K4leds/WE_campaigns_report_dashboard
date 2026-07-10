from dashboard.data_pipeline import (
    load_and_clean_data, apply_filters_and_attribution,
    cached_executive_summary, cached_journey_health_scores,
    cached_journey_lifecycle, cached_comparison,
)


def test_pipeline_callables():
    assert callable(load_and_clean_data)
    assert callable(apply_filters_and_attribution)
    assert callable(cached_comparison)
