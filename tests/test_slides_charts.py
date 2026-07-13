import pandas as pd
import plotly.graph_objects as go
import slides_export as sx


def _df():
    return pd.DataFrame({
        "Journey Name": ["Cart Recovery"] * 3 + ["Winback"] * 2,
        "Channel": ["Email", "Web Push", "SMS", "Email", "Web Push"],
        "Reporting Period Start Date": pd.to_datetime(
            ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-01", "2026-06-02"]),
        "Sent": [1000, 900, 800, 500, 400],
        "Delivered": [960, 880, 700, 480, 390],
        "Unique Impressions": [400, 500, 200, 150, 120],
        "Unique Clicks": [120, 200, 40, 30, 25],
        "Unique Conversions": [30, 55, 8, 6, 5],
    })


def test_funnel_stages_monotonic_and_labeled():
    stages = sx.journey_funnel_stages(_df(), "Cart Recovery")
    labels = [s[0] for s in stages]
    assert labels == ["Sent", "Delivered", "Opened", "Clicked", "Converted"]
    vals = [s[1] for s in stages]
    assert vals[0] == 2700 and all(v >= 0 for v in vals)


def test_chart_builders_return_figures():
    df = _df()
    from analysis import time_series_analysis
    assert isinstance(sx.chart_trend(time_series_analysis(df), "Unique Conversions"), go.Figure)
    stages = sx.journey_funnel_stages(df, "Cart Recovery")
    assert isinstance(sx.chart_journey_sankey(stages), go.Figure)
