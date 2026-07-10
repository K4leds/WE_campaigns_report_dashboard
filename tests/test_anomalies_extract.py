from dashboard.anomalies import (
    detect_campaign_anomalies, detect_journey_anomalies, get_anomaly_recommendation,
)
def test_anomaly_recommendation_returns_str():
    assert isinstance(get_anomaly_recommendation("CTR", -25.0), str)
