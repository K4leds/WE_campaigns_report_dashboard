"""Slide-builder functions and the QBR-deck orchestrator. Depends on
slides_export.py for drawing primitives and on analysis/insights_engine/
comparisons_logic for the numbers each slide shows."""
import io
import pandas as pd

from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

from slides_export import (
    new_deck, blank_slide, rect, text, stat_tile, styled_table, insight_box,
    recommendation_strip, add_morph, _header, _put_chart, journey_funnel_stages,
    chart_trend, chart_channels, chart_journey_sankey, embed_fonts,
    BRAND, BRAND_D, TBL_HDR, INK, MUTED, LINE, WHITE, INSIGHT, GREEN, RED,
    PILL_LBL, F_REG, F_MED, F_BOLD, qoq_delta_text, BENCHMARK_DELIVERY_RATE,
)
from insights_engine import generate_executive_summary, generate_top_actions
from analysis import (top_campaigns, get_top_journeys, channel_analysis,
                      time_series_analysis)
import slides_narrative as sn


def add_slide_title(prs, client_name, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=BRAND)
    rect(slide, 0, 5.0, 13.333, 0.06, fill=WHITE)
    text(slide, 0.9, 2.4, 11.5, 0.5, ("WEBENGAGE PERFORMANCE REVIEW", 14, PILL_LBL, F_MED, True, 3.0))
    text(slide, 0.85, 2.9, 11.5, 1.2, (client_name or "Marketing Performance", 40, WHITE, F_BOLD, True, None))
    if period_label:
        text(slide, 0.9, 4.2, 11.5, 0.5, (period_label, 18, PILL_LBL, F_REG, False, None))
    add_morph(slide)


def add_slide_agenda(prs, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "AGENDA", "What's in This Review", period_label)
    items = [
        "Performance Snapshot & Executive Summary",
        "Monthly KPI Trend",
        "Channel Performance",
        "Campaigns, Journeys & Segments",
        "Deliverability & Attribution",
        "Quarter-over-Quarter Scorecard",
        "Findings, Recommendations & Action Plan",
    ]
    y = 1.9
    for i, item in enumerate(items, start=1):
        rect(slide, 0.6, y, 0.5, 0.5, fill=BRAND, shape=MSO_SHAPE.OVAL)
        text(slide, 0.6, y, 0.5, 0.5, (str(i), 15, WHITE, F_BOLD, True, None),
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, 1.3, y + 0.08, 10.8, 0.4, (item, 15, INK, F_MED, True, None))
        y += 0.68
    add_morph(slide)


def monthly_kpi_rows(df):
    d = df.copy()
    d["_month"] = pd.to_datetime(d["Reporting Period Start Date"]).dt.to_period("M")
    rev_col = "Selected Revenue (SAR)" if "Selected Revenue (SAR)" in d.columns else "Revenue (SAR)"
    conv_col = "Selected Conversions" if "Selected Conversions" in d.columns else "Unique Conversions"
    agg = d.groupby("_month").agg(
        Revenue=(rev_col, "sum"), Conversions=(conv_col, "sum"), Sent=("Sent", "sum")
    ).reset_index().sort_values("_month")
    rows = [(r["_month"].strftime("%B %Y"), f"{r['Revenue']:,.0f}", f"{r['Conversions']:,.0f}", f"{r['Sent']:,.0f}")
            for _, r in agg.iterrows()]
    rows.append(("Total", f"{agg['Revenue'].sum():,.0f}", f"{agg['Conversions'].sum():,.0f}", f"{agg['Sent'].sum():,.0f}"))
    return rows


def add_slide_monthly_kpi(prs, df, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "KPI OVERVIEW", "Revenue & Conversions by Month", period_label)
    rows = monthly_kpi_rows(df)
    styled_table(slide, 0.55, 1.9, 8.5, ["Month", "Revenue (SAR)", "Conversions", "Sent"],
                 rows, [2.6, 2.2, 1.9, 1.8])
    add_morph(slide)


def add_slide_exec_summary(prs, summary, period_label, metric_changes=None, comparison_label=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "EXECUTIVE SUMMARY", "Performance at a Glance", period_label)
    m = summary.get("headline_metrics", {})
    tile_specs = [
        ("REVENUE", f"SAR {m.get('total_revenue', 0):,.0f}", "selected_revenue", None),
        ("CONVERSIONS", f"{m.get('total_conversions', 0):,.0f}", "selected_conversions", None),
        ("DELIVERY RATE", f"{m.get('avg_delivery_rate', 0):.1%}", "delivery_rate",
         f"target ≥{BENCHMARK_DELIVERY_RATE:.0%}"),
        ("CONV. RATE", f"{m.get('avg_conversion_rate', 0):.1%}", "conversion_rate", None),
    ]
    tx, tw, gap = 0.55, 2.92, 0.15
    for i, (lab, val, key, benchmark) in enumerate(tile_specs):
        delta, delta_color = benchmark or "", MUTED
        if metric_changes and key in metric_changes:
            qoq_text, delta_color = qoq_delta_text(metric_changes[key], comparison_label or "prior period")
            delta = f"{qoq_text} · {benchmark}" if benchmark else qoq_text
        stat_tile(slide, tx + i * (tw + gap), 1.52, tw, 1.18, lab, val, delta, delta_color)
    prose = sn.narrate_summary(summary)
    insight_box(slide, 0.55, 3.05, 12.23, 1.7, "THE READ", prose)
    add_morph(slide)


def add_slide_trend(prs, df, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "PERFORMANCE TREND", "Conversions Over Time", period_label)
    ts = time_series_analysis(df, "Unique Conversions")
    if not _put_chart(slide, chart_trend(ts, "Unique Conversions"), 0.7, 1.7, 4.9):
        text(slide, 0.76, 3.0, 11, 0.5, ("Trend chart unavailable.", 14, MUTED, F_REG, False, None))
    add_morph(slide)


def add_slide_channels(prs, df, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "CHANNEL PERFORMANCE", "Where Conversions Come From", period_label)
    chan = channel_analysis(df)
    _put_chart(slide, chart_channels(chan), 0.5, 1.9, 4.0)
    conv_col = "Selected Conversions" if "Selected Conversions" in chan.columns else "Unique Conversions"
    top = chan.sort_values(conv_col, ascending=False).head(6)
    rows = [(r["Channel"], f"{r[conv_col]:,.0f}") for _, r in top.iterrows()]
    styled_table(slide, 7.85, 1.9, 4.95, ["Channel", "Conversions"], rows, [3.2, 1.75])
    add_morph(slide)


def add_slide_campaigns(prs, df, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "TOP CAMPAIGNS", "Highest-Converting Campaigns", period_label)
    tc = top_campaigns(df, "Unique Conversions", top_n=8)
    rows = [(str(r.iloc[0]), f"{r.iloc[1]:,.0f}") for _, r in tc.iterrows()]
    styled_table(slide, 0.55, 1.7, 7.0, ["Campaign", "Conversions"], rows, [5.2, 1.8])
    add_morph(slide)


def add_slide_journeys(prs, df, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "JOURNEY HEALTH", "Top Journey & Its Flow", period_label)
    tj = get_top_journeys(df, "Unique Conversions", top_n=6)
    if not tj.empty:
        rows = [(str(r.iloc[0]), f"{r.iloc[1]:,.0f}") for _, r in tj.iterrows()]
        styled_table(slide, 7.85, 1.9, 4.95, ["Journey", "Conversions"], rows, [3.2, 1.75])
        stages = journey_funnel_stages(df, str(tj.iloc[0, 0]))
        _put_chart(slide, chart_journey_sankey(stages), 0.3, 2.6, 2.9)
    add_morph(slide)


def _add_findings_slide(prs, eyebrow, title, items, kind, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, eyebrow, title, period_label)
    lines = sn.narrate_findings(items, kind)
    y = 1.7
    for line in lines[:4]:
        rect(slide, 0.6, y + 0.06, 0.12, 0.12, fill=BRAND)
        text(slide, 0.95, y, 11.6, 0.9, (line, 14, INK, F_REG, False, None))
        y += 1.05
    if not lines:
        text(slide, 0.76, 3.0, 11, 0.5, ("No notable items this period.", 14, MUTED, F_REG, False, None))
    add_morph(slide)


def add_slide_recommendations(prs, actions, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "RECOMMENDATIONS", "What To Do & Which Feature", period_label)
    y = 1.7
    for action in actions[:3]:
        sentence, feature = sn.narrate_recommendation(action)
        insight_box(slide, 0.55, y, 9.0, 1.5, action.get("title", "Recommendation").upper(), sentence)
        rect(slide, 9.8, y + 0.5, 2.9, 0.5, fill=BRAND, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, 9.8, y + 0.5, 2.9, 0.5,
             [[("WEBENGAGE", 8.5, PILL_LBL, F_MED, True, 1.0)],
              [(feature, 11, WHITE, F_BOLD, True, None)]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        y += 1.7
    add_morph(slide)


def add_slide_action_plan(prs, actions, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "ACTION PLAN", "Priorities for Next Period", period_label)
    y = 1.7
    for i, action in enumerate(actions[:5], start=1):
        rect(slide, 0.6, y, 0.5, 0.5, fill=BRAND, shape=MSO_SHAPE.OVAL)
        text(slide, 0.6, y, 0.5, 0.5, (str(i), 16, WHITE, F_BOLD, True, None),
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        text(slide, 1.3, y + 0.02, 11.3, 0.5,
             [[(action.get("title", ""), 15, INK, F_BOLD, True, None)],
              [(action.get("action") or action.get("message", ""), 12, MUTED, F_REG, False, None)]])
        y += 1.0
    add_morph(slide)


def add_slide_closing(prs):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=BRAND)
    text(slide, 0.9, 3.1, 11.5, 1.3, ("Measure. Analyze. Optimize.", 34, WHITE, F_BOLD, True, None))
    add_morph(slide)


def build_deck(df, client_name="", period_label=None, comparison_result=None, conversion_attribution="Total") -> bytes:
    summary = generate_executive_summary(df)
    period_label = period_label or summary.get("period")
    actions = summary.get("top_actions") or generate_top_actions(df, max_actions=5)
    ni = summary.get("narrative_insights", {}) or {}
    prs = new_deck()
    add_slide_title(prs, client_name, period_label)
    add_slide_agenda(prs, period_label)
    add_slide_exec_summary(prs, summary, period_label)
    add_slide_monthly_kpi(prs, df, period_label)
    add_slide_trend(prs, df, period_label)
    add_slide_channels(prs, df, period_label)
    add_slide_campaigns(prs, df, period_label)
    add_slide_journeys(prs, df, period_label)
    _add_findings_slide(prs, "WHAT'S WORKING", "Opportunities",
                        ni.get("opportunities", []), "opportunity", period_label)
    _add_findings_slide(prs, "WHAT'S AT RISK", "Performance Alerts",
                        ni.get("performance_alerts", []), "alert", period_label)
    add_slide_recommendations(prs, actions, period_label)
    add_slide_action_plan(prs, actions, period_label)
    add_slide_closing(prs)
    buf = io.BytesIO()
    prs.save(buf)
    return embed_fonts(buf.getvalue())
