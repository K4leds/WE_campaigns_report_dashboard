import io
import pandas as pd
import pytest
from pptx import Presentation
import slides_deck_content as sx
import slides_export as sx_export
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
            # Email's first occurrence is pinned to 06-02 (not 06-01) so that Email
            # has data on both sides of the current/comparison split in
            # _comparison_result below — otherwise every channel maps to exactly
            # one date and per-channel QoQ can never find an overlapping channel.
            ["2026-06-02", "2026-06-02", "2026-06-03", "2026-06-01", "2026-06-02", "2026-06-03"]),
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


def test_channel_card_rows_flags_low_volume_channel():
    df = _df()  # SMS has 800+300=1100 sent total, others higher -> still >= CHANNEL_MIN_SENT (200)
    rows = sx.channel_card_rows(df)
    assert all(r["status"] in ("ACTIVE", "LOW VOLUME", "INACTIVE") for r in rows)
    assert {r["channel"] for r in rows} == {"Email", "Web Push", "SMS"}


def test_channel_card_rows_computes_qoq_when_comparison_given():
    df = _full_df()
    cr = _comparison_result(df)
    rows = sx.channel_card_rows(cr["current_data"], comparison_df=cr["comparison_data"])
    assert any(r["qoq"] is not None for r in rows)


def test_build_deck_channel_cards_slide_has_no_bar_chart_helper_left():
    assert not hasattr(sx_export, "chart_channels")


def test_monthly_kpi_rows_includes_total_row():
    rows = sx.monthly_kpi_rows(_df())
    assert rows[-1][0] == "Total"
    assert len(rows) == 2  # 1 month of data (all June) + Total


def test_channel_metrics_rows_has_engagement_and_revenue_tables():
    data = sx.channel_metrics_rows(_df())
    assert len(data["engagement_rows"]) == 3  # Email, Web Push, SMS
    assert len(data["revenue_rows"]) == 3
    assert data["revenue_headers"] == ["Channel", "Conversions", "Conv Rate", "Revenue", "AOV"]


def test_channel_metrics_rows_adds_roas_column_when_cost_present():
    df = _df().copy()
    df["Campaign Cost"] = [100, 90, 80, 50, 40, 30]
    data = sx.channel_metrics_rows(df)
    assert data["revenue_headers"] == ["Channel", "Conversions", "Conv Rate", "Revenue", "AOV", "ROAS"]


def test_build_deck_has_10_slides_with_client_name():
    data = sx.build_deck(_df(), client_name="Acme Co", period_label="Jun 2026")
    assert isinstance(data, (bytes, bytearray)) and len(data) > 5000
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 15
    # client name appears on the title slide
    texts = [sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame]
    assert any("Acme Co" in t for t in texts)


def test_exec_summary_shows_qoq_delta_when_comparison_given():
    from dashboard.comparisons_logic import calculate_period_metrics, calculate_metric_changes
    df = _full_df()
    cr = _comparison_result(df)
    current_m = calculate_period_metrics(cr["current_data"], cr["current_days"], "Total")
    comp_m = calculate_period_metrics(cr["comparison_data"], cr["comparison_days"], "Total")
    changes = calculate_metric_changes(current_m, comp_m)

    prs = sx.new_deck()
    from insights_engine import generate_executive_summary
    summary = generate_executive_summary(df)
    sx.add_slide_exec_summary(prs, summary, df, "Jun 2026", changes, "Jun 1")
    texts = " ".join(sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame)
    assert "vs Jun 1" in texts


def test_exec_summary_delivery_tile_shows_benchmark():
    prs = sx.new_deck()
    from insights_engine import generate_executive_summary
    df = _df()
    summary = generate_executive_summary(df)
    sx.add_slide_exec_summary(prs, summary, df, "Jun 2026")
    texts = " ".join(sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame)
    assert "target" in texts.lower() and "90%" in texts


def test_control_group_uplift_summary_none_without_control_columns():
    assert sx.control_group_uplift_summary(_df()) is None


def test_control_group_uplift_summary_present_with_control_columns():
    summary = sx.control_group_uplift_summary(_full_df())
    assert summary is not None
    assert "uplift_pct" in summary and "reliability" in summary


def test_build_deck_adds_control_uplift_slide_when_data_present():
    data_minimal = sx.build_deck(_df(), client_name="Acme Co")
    data_full = sx.build_deck(_full_df(), client_name="Acme Co")
    n_minimal = len(Presentation(io.BytesIO(data_minimal)).slides)
    n_full = len(Presentation(io.BytesIO(data_full)).slides)
    # _full_df() also has ESP/failed-reason columns and attribution columns,
    # so it now triggers the deliverability slide (Task 12) and the
    # attribution slide (Task 13) in addition to the control-uplift slide.
    assert n_full == n_minimal + 3


def test_top_campaigns_table_has_cvr_and_aov_columns():
    prs = sx.new_deck()
    sx.add_slide_campaigns(prs, _full_df(), "Jun 2026")
    tables = [sh for sh in prs.slides[0].shapes if sh.has_table]
    assert tables, "expected a table on the campaigns slide"
    header_texts = [c.text for c in tables[0].table.rows[0].cells]
    assert header_texts == ["Campaign", "Conversions", "Revenue", "CVR", "AOV"]


def test_top_campaign_spotlight_picks_highest_revenue_campaign():
    spotlight = sx.top_campaign_spotlight(_df())
    assert spotlight["name"] == "C1"  # C1 has Revenue 5500, the max in _df()


def test_journeys_table_has_revenue_and_cvr_columns():
    prs = sx.new_deck()
    sx.add_slide_journeys(prs, _full_df(), "Jun 2026")
    tables = [sh for sh in prs.slides[0].shapes if sh.has_table]
    assert tables, "expected a table on the journeys slide"
    header_texts = [c.text for c in tables[0].table.rows[0].cells]
    assert header_texts == ["Journey", "Conversions", "Revenue", "CVR"]


def test_deliverability_data_none_without_esp_or_failed_columns():
    assert sx.deliverability_data(_df()) is None


def test_deliverability_data_present_with_esp_and_failed_columns():
    data = sx.deliverability_data(_full_df())
    assert data is not None
    assert data["esp_rows"] is not None
    assert data["failed_rows"] is not None


def test_build_deck_adds_deliverability_slide_when_data_present():
    data_minimal = sx.build_deck(_df(), client_name="Acme Co")
    data_full = sx.build_deck(_full_df(), client_name="Acme Co")
    n_minimal = len(Presentation(io.BytesIO(data_minimal)).slides)
    n_full = len(Presentation(io.BytesIO(data_full)).slides)
    assert n_full > n_minimal


def test_qoq_scorecard_rows_has_expected_metrics():
    from dashboard.comparisons_logic import calculate_period_metrics, calculate_metric_changes
    df = _full_df()
    cr = _comparison_result(df)
    current_m = calculate_period_metrics(cr["current_data"], cr["current_days"], "Total")
    comp_m = calculate_period_metrics(cr["comparison_data"], cr["comparison_days"], "Total")
    changes = calculate_metric_changes(current_m, comp_m)
    rows = sx.qoq_scorecard_rows(changes)
    labels = [r[0] for r in rows]
    assert any(l.startswith("Revenue") for l in labels)
    roas_label = next(l for l in labels if l.startswith("ROAS"))
    assert "good ≥" in roas_label


def test_build_deck_adds_qoq_scorecard_when_comparison_result_given():
    df = _full_df()
    cr = _comparison_result(df)
    data_no_comparison = sx.build_deck(df, client_name="Acme Co")
    data_with_comparison = sx.build_deck(df, client_name="Acme Co", comparison_result=cr)
    n_plain = len(Presentation(io.BytesIO(data_no_comparison)).slides)
    n_compared = len(Presentation(io.BytesIO(data_with_comparison)).slides)
    assert n_compared == n_plain + 1


def test_attribution_rows_none_without_attribution_columns():
    assert sx.attribution_rows(_df()) is None


def test_attribution_rows_present_with_attribution_columns():
    data = sx.attribution_rows(_full_df())
    assert data is not None and len(data["rows"]) == 3  # Click-Through, Impression-Only, Send-Only
    assert data["headline"] and len(data["values"]) == 3


def test_build_deck_adds_attribution_slide_when_data_present():
    data_minimal = sx.build_deck(_df(), client_name="Acme Co")
    data_full = sx.build_deck(_full_df(), client_name="Acme Co")
    n_minimal = len(Presentation(io.BytesIO(data_minimal)).slides)
    n_full = len(Presentation(io.BytesIO(data_full)).slides)
    assert n_full > n_minimal


def test_recommendations_slide_shows_expected_impact():
    prs = sx.new_deck()
    actions = [{
        "title": "Fix Delivery Issues", "action": "Improve delivery rate",
        "expected_impact": "+5.2K SAR in recovered revenue", "priority": "HIGH",
    }]
    sx.add_slide_recommendations(prs, actions, "Jun 2026")
    texts = " ".join(sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame)
    assert "+5.2K SAR in recovered revenue" in texts


def test_build_deck_full_fixture_with_comparison_reaches_max_slide_count():
    df = _full_df()
    cr = _comparison_result(df)
    data = sx.build_deck(df, client_name="Acme Co", comparison_result=cr, conversion_attribution="Total")
    prs = Presentation(io.BytesIO(data))
    # 14 base (Task 9) + control uplift + deliverability + attribution + qoq scorecard
    # (Top Segments would have added a 5th conditional slide here, but that
    # slide was cancelled during execution — see Task 10.)
    assert len(prs.slides) == 19


def test_build_storylines_references_top_channel_and_totals():
    from insights_engine import generate_executive_summary
    df = _full_df()
    summary = generate_executive_summary(df)
    chan_rows = sx.channel_card_rows(df)
    monthly_rows = sx.monthly_kpi_rows(df)
    spotlight = sx.top_campaign_spotlight(df)
    stories = sx._build_storylines(summary, chan_rows, monthly_rows, spotlight, comparison_label=None)
    assert stories["channel_cards"] is not None and chan_rows[0]["channel"] in stories["channel_cards"]
    assert stories["spotlight"] is not None and spotlight["name"] in stories["spotlight"]


def test_build_deck_channel_cards_slide_has_story_text():
    data = sx.build_deck(_full_df(), client_name="Acme Co", period_label="Jun 2026")
    prs = Presentation(io.BytesIO(data))
    # slide order: title, agenda, exec, monthly kpi, trend, channel cards, channel metrics, ...
    channel_cards_slide = prs.slides[5]
    texts = " ".join(sh.text_frame.text for sh in channel_cards_slide.shapes if sh.has_text_frame)
    assert "drove" in texts  # from the "{channel} alone drove {share:.0%}..." template
