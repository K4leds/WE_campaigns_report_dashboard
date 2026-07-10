import pandas as pd
from data_processing import clean_data


def test_clean_data_adds_rates_and_fills():
    raw = pd.DataFrame({
        "Channel": ["Email", "SMS"],
        "Sent": [1000, 500],
        "Delivered": [900, 480],
        "Unique Impressions": [800, 0],
        "Unique Clicks": [80, 10],
        "Unique Conversions": [8, 1],
        "Revenue (SAR)": [100.0, 20.0],
        "Reporting Period Start Date": ["2025-01-01", "2025-01-02"],
        "Reporting Period End Date": ["2025-01-01", "2025-01-02"],
    })
    out = clean_data(raw.copy())
    assert "Delivery Rate" in out.columns
    assert abs(out.loc[0, "Delivery Rate"] - 0.9) < 1e-9
    assert out["Delivered"].notna().all()
