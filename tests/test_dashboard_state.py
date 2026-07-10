import pandas as pd
from dashboard.state import DashboardState

def test_dashboard_state_holds_frames():
    df = pd.DataFrame({"a": [1, 2]})
    ctx = DashboardState(
        df=df, filtered_df=df, comparison_result=None,
        revenue_attribution="Total", conversion_attribution="Total",
        selected_rev_label="Revenue (SAR)", selected_conv_label="Unique Conversions",
        date_range=None, comparison_mode="None", filter_options={},
        channels=[], campaign_types=[], campaigns=[], segments=[],
        journeys=[], conversion_events=[],
    )
    assert ctx.revenue_attribution == "Total"
    assert len(ctx.df) == 2
    assert ctx.comparison_result is None
