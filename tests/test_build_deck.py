import io
import pandas as pd
import pytest
from pptx import Presentation
import slides_deck_content as sx
import slides_narrative as sn


@pytest.fixture(autouse=True)
def _no_ai(monkeypatch):
    monkeypatch.setattr(sn, "is_configured", lambda: False)


def _df():
    n = 6
    return pd.DataFrame({
        "Campaign Name": [f"C{i}" for i in range(n)],
        "Journey Name": ["Cart Recovery"] * 3 + ["Winback"] * 3,
        "Channel": ["Email", "Web Push", "SMS"] * 2,
        "Reporting Period Start Date": pd.to_datetime(
            ["2026-06-01", "2026-06-02", "2026-06-03"] * 2),
        "Sent": [1000, 900, 800, 500, 400, 300],
        "Delivered": [960, 880, 700, 480, 390, 280],
        "Unique Impressions": [400, 500, 200, 150, 120, 90],
        "Unique Clicks": [120, 200, 40, 30, 25, 15],
        "Unique Conversions": [30, 55, 8, 6, 5, 3],
        "Revenue (SAR)": [3000, 5500, 800, 600, 500, 300],
    })


def _full_df():
    n = 6
    return pd.DataFrame({
        "Campaign Name": [f"C{i}" for i in range(n)],
        "Journey Name": ["Cart Recovery"] * 3 + ["Winback"] * 3,
        "Segment Name": ["VIP", "VIP", "New", "New", "Churn Risk", "Churn Risk"],
        "Channel": ["Email", "Web Push", "SMS"] * 2,
        "ESP/SSP/WSP/RSP name": ["SES", "FCM", "Twilio"] * 2,
        "Reporting Period Start Date": pd.to_datetime(
            ["2026-06-01", "2026-06-02", "2026-06-03"] * 2),
        "Sent": [1000, 900, 800, 500, 400, 300],
        "Delivered": [960, 880, 700, 480, 390, 280],
        "Failed Invalid Number": [10, 5, 20, 5, 3, 2],
        "Unique Impressions": [400, 500, 200, 150, 120, 90],
        "Unique Clicks": [120, 200, 40, 30, 25, 15],
        "Unique Click-Through Conversions": [20, 40, 5, 4, 3, 2],
        "Unique Impression-Through Conversions": [25, 45, 6, 5, 4, 3],
        "Unique Conversions": [30, 55, 8, 6, 5, 3],
        "Revenue (SAR)": [3000, 5500, 800, 600, 500, 300],
        "Total in Control Group": [200, 150, 100, 80, 60, 40],
        "Unique Control Group Conversions": [10, 8, 5, 4, 3, 2],
    })


def _comparison_result(df):
    current = df[df["Reporting Period Start Date"] >= "2026-06-02"]
    comparison = df[df["Reporting Period Start Date"] < "2026-06-02"]
    return {
        "current_data": current, "comparison_data": comparison,
        "current_days": 2, "comparison_days": 1,
        "current_label": "Jun 2-3", "comparison_label": "Jun 1",
    }


def test_monthly_kpi_rows_includes_total_row():
    rows = sx.monthly_kpi_rows(_df())
    assert rows[-1][0] == "Total"
    assert len(rows) == 2  # 1 month of data (all June) + Total


def test_build_deck_has_10_slides_with_client_name():
    data = sx.build_deck(_df(), client_name="Acme Co", period_label="Jun 2026")
    assert isinstance(data, (bytes, bytearray)) and len(data) > 5000
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 13
    # client name appears on the title slide
    texts = [sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame]
    assert any("Acme Co" in t for t in texts)
