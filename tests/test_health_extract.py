import pandas as pd
from dashboard.health import calculate_journey_health_score, calculate_campaign_health_score

def test_health_functions_importable_and_return_dict():
    df = pd.DataFrame({
        "Journey Name": ["J1", "J1"],
        "Sent": [100, 100], "Delivered": [95, 95],
        "Unique Impressions": [90, 90], "Unique Clicks": [10, 10],
        "Unique Conversions": [2, 2], "Revenue (SAR)": [50.0, 50.0],
        "Delivery Rate": [0.95, 0.95], "CTR": [0.11, 0.11],
        "Conversion Rate": [0.2, 0.2],
    })
    res = calculate_journey_health_score(df, df)
    assert "health_score" in res and "tier" in res
