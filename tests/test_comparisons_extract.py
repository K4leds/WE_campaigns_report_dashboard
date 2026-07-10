from dashboard.comparisons_logic import (
    calculate_comparison_periods, calculate_period_metrics,
    calculate_metric_changes, calculate_uplift_significance,
    create_journey_comparison_analysis, create_custom_date_range_comparison,
)


def test_metric_changes_shape():
    cur = {"revenue": 100.0}
    prev = {"revenue": 50.0}
    out = calculate_metric_changes(cur, prev)
    assert isinstance(out, dict)
    assert out["revenue"]["current"] == 100.0
    assert out["revenue"]["comparison"] == 50.0
    assert out["revenue"]["pct_change"] == 100.0
