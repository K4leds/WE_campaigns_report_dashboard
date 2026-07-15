"""Slide-builder functions and the QBR-deck orchestrator. Depends on
slides_export.py for drawing primitives and on analysis/insights_engine/
comparisons_logic for the numbers each slide shows."""
import io
import pandas as pd
import numpy as np

from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

from slides_export import (
    new_deck, blank_slide, rect, text, stat_tile, styled_table, insight_box,
    recommendation_strip, add_morph, _header, _put_chart, _put_chart_with_callout,
    journey_funnel_stages,
    chart_trend, chart_journey_sankey, chart_bar_horizontal, chart_donut,
    chart_kpi_ring, embed_fonts, channel_status, status_pill,
    BRAND, BRAND_D, TBL_HDR, INK, MUTED, LINE, WHITE, INSIGHT, GREEN, RED,
    PILL_LBL, F_REG, F_MED, F_BOLD, qoq_delta_text, BENCHMARK_DELIVERY_RATE,
    BENCHMARK_ROAS_GOOD,
)
from insights_engine import (generate_executive_summary, generate_top_actions,
                             identify_optimization_opportunities,
                             identify_channel_optimization_opportunities,
                             CHANNEL_MIN_SENT, ROAS_SANITY_CEILING)
from dashboard.comparisons_logic import (
    calculate_period_metrics, calculate_uplift_significance, calculate_metric_changes,
)
from analysis import (channel_analysis,
                      time_series_analysis, esp_analysis, failed_reasons_analysis,
                      attribution_analysis)
import slides_narrative as sn


def _build_storylines(summary, chan_rows, monthly_rows, spotlight,
                     comparison_label, audience="executive", tone="confident"):
    """Generate one narrative bridge sentence per slide so the deck reads as a
    chain of findings rather than a stack of independent reports.

    v2: Each bridge is now AI-generated (via slides_narrative) when DeepSeek is
    available, using pre-computed numeric context. Falls back to template strings
    when the LLM is unavailable — the deck always builds, just with computed
    rather than generated transitions.
    """
    from slides_narrative import _narrate_storyline

    m = summary.get("headline_metrics", {})
    total_revenue = m.get("total_revenue", 0)
    total_conversions = m.get("total_conversions", 0)
    n_months = max(len(monthly_rows) - 1, 0)

    # Build the numeric context dict for each slide position
    ctx = {
        "total_revenue": total_revenue,
        "total_conversions": total_conversions,
        "n_months": n_months,
        "top_channel": chan_rows[0]["channel"] if chan_rows else "",
        "top_channel_revenue": chan_rows[0]["revenue"] if chan_rows else 0,
        "top_channel_share": (chan_rows[0]["revenue"] / total_revenue) if chan_rows and total_revenue else 0,
        "comparison_label": comparison_label or "the prior period",
        "spotlight_name": spotlight["name"] if spotlight else "",
        "spotlight_channel": spotlight["channel"] if spotlight else "",
    }

    # Generate each storyline — LLM if available, template if not
    return {
        "monthly_kpi": _narrate_storyline(
            ctx, "monthly_kpi", audience, tone,
            fallback=f"SAR {total_revenue:,.0f} came in across {n_months} month(s) — here's the monthly split."
        ),
        "trend": _narrate_storyline(
            ctx, "trend", audience, tone,
            fallback="Here's the day-by-day shape behind that total."
        ),
        "channel_cards": _narrate_storyline(
            ctx, "channel_cards", audience, tone,
            fallback=(f"{ctx['top_channel']} alone drove {ctx['top_channel_share']:.0%} "
                      f"of the SAR {total_revenue:,.0f} total below.")
            if ctx["top_channel"] and total_revenue else None
        ),
        "channel_metrics": _narrate_storyline(
            ctx, "channel_metrics", audience, tone,
            fallback="The full metric set behind those channels."
        ),
        "campaigns": _narrate_storyline(
            ctx, "campaigns", audience, tone,
            fallback="Here's which individual campaigns drove those channel numbers."
        ),
        "spotlight": _narrate_storyline(
            ctx, "spotlight", audience, tone,
            fallback=(f"'{ctx['spotlight_name']}' was the single best-performing "
                      f"campaign this period.") if ctx["spotlight_name"] else None
        ),
        "journeys": _narrate_storyline(
            ctx, "journeys", audience, tone,
            fallback="Beyond one-off campaigns, here's how automated journeys performed."
        ),
        "deliverability": _narrate_storyline(
            ctx, "deliverability", audience, tone,
            fallback="None of this works if messages don't land — a deliverability check."
        ),
        "attribution": _narrate_storyline(
            ctx, "attribution", audience, tone,
            fallback=(f"How the {total_conversions:,.0f} conversions above split "
                      f"between click-driven and impression-driven.")
        ),
        "qoq_scorecard": _narrate_storyline(
            ctx, "qoq_scorecard", audience, tone,
            fallback=f"Compared to {comparison_label or 'the prior period'}, here's what moved."
        ),
        "recommendations": _narrate_storyline(
            ctx, "recommendations", audience, tone,
            fallback="Turning those findings into next steps."
        ),
        "action_plan": _narrate_storyline(
            ctx, "action_plan", audience, tone,
            fallback="Prioritized and ready to execute."
        ),
    }


def add_slide_title(prs, client_name, period_label):
    from slides_export import _SLIDE_NUMBER
    _SLIDE_NUMBER[0] = 0  # reset counter for new deck
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=BRAND)
    rect(slide, 0, 5.0, 13.333, 0.06, fill=WHITE)
    text(slide, 0.9, 2.4, 11.5, 0.5, ("WEBENGAGE PERFORMANCE REVIEW", 14, PILL_LBL, F_MED, True, 3.0))
    text(slide, 0.85, 2.9, 11.5, 1.2, (client_name or "Marketing Performance", 40, WHITE, F_BOLD, True, None))
    if period_label:
        text(slide, 0.9, 4.2, 11.5, 0.5, (period_label, 18, PILL_LBL, F_REG, False, None))
    add_morph(slide)


def add_slide_agenda(prs, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "AGENDA", "What's in This Review", period_label, story=story)
    items = [
        "Performance Snapshot & Executive Summary",
        "Monthly KPI Trend",
        "Channel Performance",
        "Campaigns & Journeys",
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


def add_slide_monthly_kpi(prs, df, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    rows = monthly_kpi_rows(df)
    total_rev = rows[-1][1] if rows else "0"
    n_months = len(rows) - 1
    _header(slide, "KPI OVERVIEW", "Revenue & Conversions by Month", period_label,
            story=story,
            action_title=f"SAR {total_rev} TOTAL REVENUE ACROSS {n_months} MONTHS")
    # Data bars on revenue column (col index 1), banded rows
    styled_table(slide, 0.55, 1.9, 8.5,
                 ["Month", "Revenue (SAR)", "Conversions", "Sent"],
                 rows, [2.6, 2.2, 1.9, 1.8],
                 data_bar_col=1, banded=True)

    # Right third is otherwise dead space -- surface the headline numbers there.
    d = df.copy()
    d["_month"] = pd.to_datetime(d["Reporting Period Start Date"]).dt.to_period("M")
    rev_col = "Selected Revenue (SAR)" if "Selected Revenue (SAR)" in d.columns else "Revenue (SAR)"
    conv_col = "Selected Conversions" if "Selected Conversions" in d.columns else "Unique Conversions"
    mrev = d.groupby("_month")[rev_col].sum()
    if not mrev.empty and n_months > 0:
        best_m = mrev.idxmax()
        tiles = [
            ("TOTAL CONVERSIONS", f"{d[conv_col].sum():,.0f}"),
            ("BEST MONTH", f"{best_m.strftime('%b %Y')}"),
            ("AVG REVENUE / MONTH", f"SAR {mrev.mean():,.0f}"),
        ]
        for i, (lab, val) in enumerate(tiles):
            stat_tile(slide, 9.35, 1.9 + i * 1.15, 3.2, 1.0, lab, val, "", MUTED)
    add_morph(slide)


def add_slide_exec_summary(prs, summary, df, period_label, metric_changes=None,
                          comparison_label=None, story=None,
                          audience="executive", tone="confident"):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)

    m = summary.get("headline_metrics", {})
    total_revenue = m.get("total_revenue", 0)
    delivery_rate = m.get("avg_delivery_rate", 0)

    # BCG-style action title: make the header itself tell the story
    action = (f"WEBENGAGE DROVE SAR {total_revenue:,.0f} IN REVENUE "
              f"FROM {m.get('total_conversions', 0):,.0f} CONVERSIONS")
    _header(slide, "EXECUTIVE SUMMARY", "Performance at a Glance", period_label,
            story=story, action_title=action)

    # --- Top row: Stat tiles (revenue, conversions) + KPI rings (delivery, conv rate) ---
    tile_specs = [
        ("REVENUE", f"SAR {total_revenue:,.0f}", "selected_revenue", None),
        ("CONVERSIONS", f"{m.get('total_conversions', 0):,.0f}", "selected_conversions", None),
    ]
    tx, tw, gap = 0.55, 2.92, 0.15
    for i, (lab, val, key, benchmark) in enumerate(tile_specs):
        delta, delta_color = benchmark or "", MUTED
        if metric_changes and key in metric_changes:
            qoq_text, delta_color = qoq_delta_text(metric_changes[key], comparison_label or "prior period")
            delta = f"{qoq_text} · {benchmark}" if benchmark else qoq_text
        stat_tile(slide, tx + i * (tw + gap), 1.55, tw, 1.18, lab, val, delta, delta_color)

    # KPI rings for benchmark metrics — more visual than stat tiles
    # Delivery rate ring
    delivery_fig = chart_kpi_ring(delivery_rate, BENCHMARK_DELIVERY_RATE,
                                  label="Delivery Rate", suffix="%")
    _put_chart(slide, delivery_fig, 7.05, 1.45, 1.35)
    # Add a small label under the ring
    text(slide, 7.05, 2.85, 1.5, 0.2,
         (f"target ≥{BENCHMARK_DELIVERY_RATE:.0%}", 7.5, MUTED, F_REG, False, None),
         align=PP_ALIGN.CENTER)

    # Conversion rate ring
    conv_rate = m.get("avg_conversion_rate", 0)
    conv_benchmark = 0.05  # 5% is a reasonable conversion benchmark
    conv_fig = chart_kpi_ring(conv_rate, conv_benchmark if conv_benchmark > 0 else 0.01,
                              label="Conv. Rate", suffix="%")
    _put_chart(slide, conv_fig, 8.70, 1.45, 1.35)
    text(slide, 8.70, 2.85, 1.5, 0.2,
         (f"target ≥{conv_benchmark:.0%}", 7.5, MUTED, F_REG, False, None),
         align=PP_ALIGN.CENTER)

    # Prose insight box (LLM when available, deterministic fallback otherwise)
    prose = sn.narrate_summary(summary, audience=audience, tone=tone, quality="standard")
    insight_box(slide, 0.55, 3.05, 12.23, 1.55, "THE READ", prose)

    # --- Bottom row: channel revenue-share donut + reach/engagement tiles ---
    # (previously this half of the slide was left empty)
    ch_rows = channel_card_rows(df)[:6]
    if ch_rows:
        labels = [r["channel"] for r in ch_rows]
        vals = [r["revenue"] for r in ch_rows]
        _put_chart(slide, chart_donut(labels, vals, center_text=f"SAR {sum(vals):,.0f}"),
                   0.7, 4.75, 2.15)
        text(slide, 0.7, 6.75, 3.2, 0.2,
             ("Channel revenue share", 9, MUTED, F_MED, True, 1.0))
    stat_tile(slide, 6.9, 4.95, 2.7, 1.25, "MESSAGES SENT",
              f"{m.get('total_sent', 0):,.0f}", "", MUTED)
    stat_tile(slide, 9.75, 4.95, 2.7, 1.25, "AVG CTR",
              f"{m.get('avg_ctr', 0) * 100:.1f}%", "", MUTED)

    add_morph(slide)


def _trend_callout(ts):
    """Computed one-liner for the trend chart: peak plus end-to-end direction."""
    try:
        y = ts["Unique Conversions"] if "Unique Conversions" in ts.columns else ts.iloc[:, 1]
        if len(y) < 2 or y.max() <= 0:
            return "Daily conversions over the period."
        peak = y.max()
        first, last = y.iloc[0], y.iloc[-1]
        if first > 0:
            change = (last - first) / first * 100
            direction = "up" if change >= 0 else "down"
            return f"Peaked at {peak:,.0f} conversions; {direction} {abs(change):.0f}% end-to-end."
        return f"Peaked at {peak:,.0f} conversions over the period."
    except Exception:
        return "Daily conversions over the period."


def add_slide_trend(prs, df, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "PERFORMANCE TREND", "Conversions Over Time", period_label, story=story)
    ts = time_series_analysis(df, "Unique Conversions")
    callout = _trend_callout(ts)
    if not _put_chart_with_callout(slide, chart_trend(ts, "Unique Conversions"),
                                    0.7, 1.7, 4.9, callout_text=callout):
        text(slide, 0.76, 3.0, 11, 0.5, ("Trend chart unavailable.", 14, MUTED, F_REG, False, None))
    add_morph(slide)


def channel_card_rows(df, comparison_df=None):
    chan = channel_analysis(df)
    rev_col = "Selected Revenue (SAR)" if "Selected Revenue (SAR)" in chan.columns else "Revenue (SAR)"
    comp_chan = channel_analysis(comparison_df) if comparison_df is not None and not comparison_df.empty else None
    rows = []
    for _, r in chan.sort_values(rev_col, ascending=False).iterrows():
        sent = r["Sent"]
        status, color = channel_status(sent)
        delivery = (r["Delivered"] / sent) if sent > 0 else 0
        revenue = r[rev_col]
        qoq = None
        if comp_chan is not None:
            match = comp_chan[comp_chan["Channel"] == r["Channel"]]
            if not match.empty and match.iloc[0][rev_col] > 0:
                prev = match.iloc[0][rev_col]
                qoq = ((revenue - prev) / prev) * 100
        rows.append({
            "channel": r["Channel"], "status": status, "status_color": color,
            "revenue": revenue, "delivery": delivery,
            "insight": f"{delivery:.0%} delivery on {sent:,.0f} sends",
            "qoq": qoq,
        })
    return rows


def add_slide_channel_cards(prs, df, period_label, comparison_df=None, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    rows = channel_card_rows(df, comparison_df)[:6]

    # BCG-style action title: make the header the key finding
    top_row = rows[0] if rows else None
    action = (f"{top_row['channel'].upper()} LED WITH SAR {top_row['revenue']:,.0f} — "
              f"HERE'S HOW EACH CHANNEL CONTRIBUTED") if top_row else "CHANNEL REVENUE BREAKDOWN"
    _header(slide, "CHANNEL PERFORMANCE", "Where Revenue Comes From", period_label,
            story=story, action_title=action)

    # Channel cards (left 60% of the slide)
    cols, card_w, card_h, gap_x, gap_y = 3, 3.95, 2.35, 0.19, 0.2
    ox, oy = 0.55, 1.7
    for i, r in enumerate(rows):
        col, row = i % cols, i // cols
        x = ox + col * (card_w + gap_x)
        y = oy + row * (card_h + gap_y)
        rect(slide, x, y, card_w, card_h, fill=WHITE, line=LINE, line_w=1.0)
        rect(slide, x, y, card_w, 0.05, fill=BRAND)
        text(slide, x + 0.22, y + 0.18, card_w - 1.6, 0.3, (r["channel"], 14, INK, F_BOLD, True, None))
        status_pill(slide, x + card_w - 1.35, y + 0.2, r["status"], r["status_color"])
        text(slide, x + 0.22, y + 0.58, card_w - 0.4, 0.35,
             (f"SAR {r['revenue']:,.0f}", 18, BRAND, F_BOLD, True, None))
        if r["qoq"] is not None:
            arrow = "▲" if r["qoq"] > 0 else ("▼" if r["qoq"] < 0 else "→")
            color = GREEN if r["qoq"] > 0 else (RED if r["qoq"] < 0 else MUTED)
            text(slide, x + 0.22, y + 0.95, card_w - 0.4, 0.25,
                 (f"{arrow} {r['qoq']:+.1f}% vs prior period", 10, color, F_MED, True, None))
        text(slide, x + 0.22, y + card_h - 0.55, card_w - 0.4, 0.45,
             (r["insight"], 10.5, MUTED, F_REG, False, None))

    # Channel share donut — right side of the cards
    if rows:
        chan_labels = [r["channel"] for r in rows]
        chan_vals = [r["revenue"] for r in rows]
        donut_fig = chart_donut(chan_labels, chan_vals,
                                center_text=f"SAR{sum(chan_vals):,.0f}")
        _put_chart(slide, donut_fig, 0.55, 4.35, 2.8)

    add_morph(slide)


def channel_metrics_rows(df):
    chan = channel_analysis(df)
    rev_col = "Selected Revenue (SAR)" if "Selected Revenue (SAR)" in chan.columns else "Revenue (SAR)"
    conv_col = "Selected Conversions" if "Selected Conversions" in chan.columns else "Unique Conversions"
    chan = chan.sort_values(rev_col, ascending=False).copy()
    chan["Delivery Rate"] = np.where(chan["Sent"] > 0, chan["Delivered"] / chan["Sent"], 0)
    chan["CTR"] = np.where(chan["Unique Impressions"] > 0, chan["Unique Clicks"] / chan["Unique Impressions"], 0)
    chan["Conv Rate"] = np.where(chan["Unique Clicks"] > 0, chan[conv_col] / chan["Unique Clicks"], 0)
    chan["AOV"] = np.where(chan[conv_col] > 0, chan[rev_col] / chan[conv_col], 0)

    engagement_rows = [
        (r["Channel"], f"{r['Sent']:,.0f}", f"{r['Delivered']:,.0f}",
         f"{r['Delivery Rate']:.1%}", f"{r['Unique Clicks']:,.0f}", f"{r['CTR']:.2%}")
        for _, r in chan.iterrows()
    ]

    has_cost = "Campaign Cost" in df.columns
    if has_cost:
        cost_by_channel = df.groupby("Channel")["Campaign Cost"].sum()
        chan["Cost"] = chan["Channel"].map(cost_by_channel).fillna(0)
        chan["ROAS"] = np.where(chan["Cost"] > 0, chan[rev_col] / chan["Cost"], 0)

        def _roas_cell(cost, roas):
            # Missing cost -> "—" (not a real 0x); implausibly high -> cost-data gap,
            # so we withhold rather than print an absurd figure on a client slide.
            if cost <= 0 or roas > ROAS_SANITY_CEILING:
                return "—"
            return f"{roas:.2f}x"

        revenue_headers = ["Channel", "Conversions", "Conv Rate", "Revenue", "AOV", "ROAS"]
        revenue_rows = [
            (r["Channel"], f"{r[conv_col]:,.0f}", f"{r['Conv Rate']:.1%}",
             f"SAR {r[rev_col]:,.0f}", f"SAR {r['AOV']:,.0f}", _roas_cell(r["Cost"], r["ROAS"]))
            for _, r in chan.iterrows()
        ]
    else:
        revenue_headers = ["Channel", "Conversions", "Conv Rate", "Revenue", "AOV"]
        revenue_rows = [
            (r["Channel"], f"{r[conv_col]:,.0f}", f"{r['Conv Rate']:.1%}",
             f"SAR {r[rev_col]:,.0f}", f"SAR {r['AOV']:,.0f}")
            for _, r in chan.iterrows()
        ]

    return {"engagement_rows": engagement_rows, "revenue_rows": revenue_rows,
            "revenue_headers": revenue_headers, "headline": _channel_metrics_headline(chan, conv_col)}


def _channel_metrics_headline(chan, conv_col):
    """One-line action-title finding for the channel-metrics slide. A delivery
    shortfall (most actionable) wins; otherwise the most click-efficient channel."""
    eligible = chan[chan["Sent"] >= CHANNEL_MIN_SENT]
    if not eligible.empty:
        worst = eligible.nsmallest(1, "Delivery Rate").iloc[0]
        if worst["Delivery Rate"] < BENCHMARK_DELIVERY_RATE:
            return (f"{str(worst['Channel']).upper()} DELIVERY AT {worst['Delivery Rate']:.0%} "
                    f"SITS BELOW THE {BENCHMARK_DELIVERY_RATE:.0%} TARGET")
    conv_pool = chan[chan["Unique Clicks"] > 0]
    if not conv_pool.empty:
        best = conv_pool.nlargest(1, "Conv Rate").iloc[0]
        return (f"{str(best['Channel']).upper()} CONVERTS BEST AT "
                f"{best['Conv Rate']:.1%} OF CLICKS")
    return None


def add_slide_channel_metrics(prs, data, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "CHANNEL PERFORMANCE", "Full Channel Metrics", period_label, story=story,
            action_title=data.get("headline"))
    # Banded rows + conditional formatting on Delivery Rate col (index 3)
    # Red if below 90% benchmark
    delivery_conditional = {3: {"benchmark": 0.90, "below": RED, "above": GREEN}}
    styled_table(slide, 0.55, 1.85, 11.4,
                 ["Channel", "Sent", "Delivered", "Delivery Rate", "Clicks", "CTR"],
                 data["engagement_rows"], [2.2, 1.9, 1.9, 1.9, 1.7, 1.8],
                 conditional_cols=delivery_conditional, banded=True)
    revenue_widths = [2.2, 1.9, 1.9, 2.3, 1.7, 1.4] if len(data["revenue_headers"]) == 6 else [2.5, 2.5, 2.5, 2.5, 2.4]
    styled_table(slide, 0.55, 4.35, 11.4, data["revenue_headers"], data["revenue_rows"],
                 revenue_widths, banded=True)
    add_morph(slide)


def control_group_uplift_summary(df, conversion_attribution="Total"):
    if "Total in Control Group" not in df.columns or "Unique Control Group Conversions" not in df.columns:
        return None
    control = df[df["Total in Control Group"] > 0]
    if control.empty:
        return None
    dates = pd.to_datetime(df["Reporting Period Start Date"]) if "Reporting Period Start Date" in df.columns else None
    period_days = (dates.max() - dates.min()).days + 1 if dates is not None else 1
    metrics = calculate_period_metrics(df, period_days, conversion_attribution)
    uplift = metrics.get("control_group_uplift")
    if uplift is None:
        return None
    total_control_group = control["Total in Control Group"].sum()
    total_control_conversions = control["Unique Control Group Conversions"].sum()
    conv_col = "Selected Conversions" if "Selected Conversions" in control.columns else "Unique Conversions"
    test_conversions = control[conv_col].sum()
    test_total = control["Sent"].sum()
    _, is_significant, reliability = calculate_uplift_significance(
        test_conversions, test_total, total_control_conversions, total_control_group)
    return {"uplift_pct": uplift, "reliability": reliability, "is_significant": is_significant}


def add_slide_control_uplift(prs, summary, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "CAMPAIGN EFFICIENCY", "Control Group vs. Target Group Uplift", period_label, story=story)
    text(slide, 0.55, 2.0, 8, 0.6,
         ("The control group measures how much WebEngage-targeted campaigns "
          "outperform an untouched baseline audience.", 13, INK, F_REG, False, None))
    color = GREEN if summary["uplift_pct"] > 0 else RED
    stat_tile(slide, 0.55, 2.8, 3.4, 1.6, "CONVERSION UPLIFT",
              f"{summary['uplift_pct']:+.1f}%", summary["reliability"], color)
    add_morph(slide)


def add_slide_campaigns(prs, df, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    conv_col = "Selected Conversions" if "Selected Conversions" in df.columns else "Unique Conversions"
    rev_col = "Selected Revenue (SAR)" if "Selected Revenue (SAR)" in df.columns else "Revenue (SAR)"
    agg = df.groupby("Campaign Name").agg(
        Conversions=(conv_col, "sum"), Revenue=(rev_col, "sum"), Clicks=("Unique Clicks", "sum")
    ).reset_index().nlargest(12, "Conversions")
    agg["CVR"] = np.where(agg["Clicks"] > 0, agg["Conversions"] / agg["Clicks"], 0)
    agg["AOV"] = np.where(agg["Conversions"] > 0, agg["Revenue"] / agg["Conversions"], 0)
    top = agg.iloc[0] if not agg.empty else None
    action = (f"'{str(top['Campaign Name'])}' LED WITH {top['Conversions']:,.0f} CONVERSIONS "
              f"AT {top['CVR']:.0%} CVR") if top is not None else None
    _header(slide, "TOP CAMPAIGNS", "Highest-Converting Campaigns", period_label, story=story,
            action_title=action)
    rows = [(r["Campaign Name"], f"{r['Conversions']:,.0f}", f"SAR {r['Revenue']:,.0f}",
             f"{r['CVR']:.1%}", f"SAR {r['AOV']:,.0f}") for _, r in agg.iterrows()]
    styled_table(slide, 0.55, 1.7, 11.4, ["Campaign", "Conversions", "Revenue", "CVR", "AOV"], rows,
                 [4.6, 1.6, 2.0, 1.5, 1.7], data_bar_col=2, banded=True)
    add_morph(slide)


def top_campaign_spotlight(df):
    conv_col = "Selected Conversions" if "Selected Conversions" in df.columns else "Unique Conversions"
    rev_col = "Selected Revenue (SAR)" if "Selected Revenue (SAR)" in df.columns else "Revenue (SAR)"
    agg = df.groupby("Campaign Name").agg(
        Revenue=(rev_col, "sum"), Conversions=(conv_col, "sum"),
        Clicks=("Unique Clicks", "sum"), Sent=("Sent", "sum"),
        Channel=("Channel", lambda s: s.mode().iat[0] if not s.mode().empty else ""),
    ).reset_index()
    if agg.empty or agg["Revenue"].sum() == 0:
        return None
    top = agg.nlargest(1, "Revenue").iloc[0]
    cvr = (top["Conversions"] / top["Clicks"]) if top["Clicks"] > 0 else 0
    return {
        "name": top["Campaign Name"], "channel": top["Channel"], "revenue": top["Revenue"],
        "conversions": top["Conversions"], "cvr": cvr, "audience": top["Sent"],
    }


def add_slide_campaign_spotlight(prs, spotlight, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "CAMPAIGN SPOTLIGHT", spotlight["name"], period_label, story=story)
    rect(slide, 9.55, 0.45, 3.05, 0.5, fill=BRAND, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    text(slide, 9.55, 0.45, 3.05, 0.5, (spotlight["channel"], 12, WHITE, F_BOLD, True, None),
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    tiles = [
        ("REVENUE", f"SAR {spotlight['revenue']:,.0f}"),
        ("CONVERSIONS", f"{spotlight['conversions']:,.0f}"),
        ("CVR", f"{spotlight['cvr']:.1%}"),
        ("AUDIENCE REACHED", f"{spotlight['audience']:,.0f}"),
    ]
    tx, tw, gap = 0.55, 2.92, 0.15
    for i, (lab, val) in enumerate(tiles):
        stat_tile(slide, tx + i * (tw + gap), 1.9, tw, 1.3, lab, val, "", MUTED)
    insight_box(slide, 0.55, 3.6, 12.23, 1.2, "WHY IT WORKED",
                f"'{spotlight['name']}' was this period's highest-revenue campaign on "
                f"{spotlight['channel']}, converting {spotlight['cvr']:.1%} of its clicks.")
    add_morph(slide)


def add_slide_journeys(prs, df, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    conv_col = "Selected Conversions" if "Selected Conversions" in df.columns else "Unique Conversions"
    rev_col = "Selected Revenue (SAR)" if "Selected Revenue (SAR)" in df.columns else "Revenue (SAR)"
    jdf = df[df["Journey Name"].notna() & (df["Journey Name"] != "nan") & (df["Journey Name"] != "")]
    action = None
    if not jdf.empty:
        agg = jdf.groupby("Journey Name").agg(
            Conversions=(conv_col, "sum"), Revenue=(rev_col, "sum"), Clicks=("Unique Clicks", "sum")
        ).reset_index().nlargest(10, "Conversions")
        agg["CVR"] = np.where(agg["Clicks"] > 0, agg["Conversions"] / agg["Clicks"], 0)
        t = agg.iloc[0]
        action = (f"'{str(t['Journey Name'])}' DROVE {t['Conversions']:,.0f} JOURNEY "
                  f"CONVERSIONS AND SAR {t['Revenue']:,.0f}")
    _header(slide, "JOURNEY HEALTH", "Top Journeys & Best Flow", period_label, story=story,
            action_title=action)
    if not jdf.empty:
        rows = [(r["Journey Name"], f"{r['Conversions']:,.0f}", f"SAR {r['Revenue']:,.0f}", f"{r['CVR']:.1%}")
                for _, r in agg.iterrows()]
        styled_table(slide, 7.85, 1.9, 4.95, ["Journey", "Conversions", "Revenue", "CVR"], rows,
                     [2.05, 0.95, 1.15, 0.8], data_bar_col=2, banded=True)
        top_journey_name = str(agg.iloc[0]["Journey Name"])
        stages = journey_funnel_stages(df, top_journey_name)
        _put_chart(slide, chart_journey_sankey(stages), 0.3, 2.6, 2.9)
    add_morph(slide)


def deliverability_data(df):
    esp_df = esp_analysis(df)
    failed_df = failed_reasons_analysis(df)
    esp_rows = None
    if not esp_df.empty:
        esp_df = esp_df.copy()
        esp_df["Delivery Rate"] = np.where(esp_df["Sent"] > 0, esp_df["Delivered"] / esp_df["Sent"], 0)
        top_esp = esp_df.nlargest(5, "Sent")
        esp_rows = [(r["ESP/SSP/WSP/RSP name"], f"{r['Sent']:,.0f}", f"{r['Delivery Rate']:.1%}")
                    for _, r in top_esp.iterrows()]
    failed_rows = None
    if not failed_df.empty and failed_df["Count"].sum() > 0:
        top_failed = failed_df.nlargest(5, "Count")
        failed_rows = [(str(r["Reason"]).replace("Failed ", ""), f"{r['Count']:,.0f}")
                       for _, r in top_failed.iterrows()]
    if esp_rows is None and failed_rows is None:
        return None

    headline = None
    if not esp_df.empty:
        worst = esp_df.nlargest(5, "Sent").nsmallest(1, "Delivery Rate").iloc[0]
        if worst["Delivery Rate"] < BENCHMARK_DELIVERY_RATE:
            headline = (f"{str(worst['ESP/SSP/WSP/RSP name']).upper()} DELIVERED ONLY "
                        f"{worst['Delivery Rate']:.0%} — BELOW THE {BENCHMARK_DELIVERY_RATE:.0%} TARGET")
    if headline is None and not failed_df.empty and failed_df["Count"].sum() > 0:
        tr = failed_df.nlargest(1, "Count").iloc[0]
        headline = (f"{str(tr['Reason']).replace('Failed ', '').upper()} IS THE TOP "
                    f"FAILURE REASON AT {tr['Count']:,.0f} MESSAGES")
    return {"esp_rows": esp_rows, "failed_rows": failed_rows, "headline": headline}


def add_slide_deliverability(prs, data, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "DELIVERABILITY", "ESP Performance & Failure Reasons", period_label, story=story,
            action_title=data.get("headline"))
    if data["esp_rows"]:
        styled_table(slide, 0.55, 1.7, 7.0, ["ESP / Provider", "Sent", "Delivery Rate"],
                     data["esp_rows"], [3.4, 1.8, 1.8], banded=True)
    if data["failed_rows"]:
        styled_table(slide, 7.85, 1.7, 4.95, ["Failure Reason", "Count"], data["failed_rows"],
                     [3.4, 1.55], banded=True)
    add_morph(slide)


def attribution_rows(df):
    required = {"Unique Conversions", "Unique Impression-Through Conversions", "Unique Click-Through Conversions"}
    if not required.issubset(df.columns):
        return None
    attr = attribution_analysis(df)
    total = attr["Conversions"].sum()
    if attr.empty or total <= 0:
        return None
    rows = [(r["Source"], f"{r['Conversions']:,.0f}", f"{(r['Conversions'] / total):.1%}")
            for _, r in attr.iterrows()]
    top = attr.nlargest(1, "Conversions").iloc[0]
    headline = (f"{str(top['Source']).upper()} DROVE {top['Conversions'] / total:.0%} "
                f"OF THE {total:,.0f} CONVERSIONS")
    return {"rows": rows, "labels": list(attr["Source"]),
            "values": [float(v) for v in attr["Conversions"]], "headline": headline}


def add_slide_attribution(prs, data, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "ATTRIBUTION", "How Conversions Were Won", period_label, story=story,
            action_title=data.get("headline"))
    styled_table(slide, 0.55, 2.1, 7.0, ["Source", "Conversions", "Share"], data["rows"], [3.4, 1.8, 1.8],
                 banded=True)
    # Fill the right half: a share donut instead of dead space.
    total = sum(data["values"])
    _put_chart(slide, chart_donut(data["labels"], data["values"],
                                  center_text=f"{total:,.0f}"), 8.0, 1.9, 3.6)
    add_morph(slide)


def qoq_scorecard_rows(metric_changes):
    # Benchmark label appended for the two metrics insights_engine/comparisons
    # already treat as having a fixed target (see slides_export.py's
    # BENCHMARK_* constants) -- None for metrics judged only relative to
    # their own prior period.
    metric_specs = [
        ("selected_revenue", "Revenue", "SAR", None),
        ("selected_conversions", "Conversions", "", None),
        ("ctr", "Click-Through Rate", "%", None),
        ("delivery_rate", "Delivery Rate", "%", f"target ≥{BENCHMARK_DELIVERY_RATE:.0%}"),
        ("aov", "Average Order Value", "SAR", None),
        ("roas", "ROAS", "x", f"good ≥{BENCHMARK_ROAS_GOOD:.0f}x"),
    ]
    rows = []
    for key, label, unit, benchmark in metric_specs:
        if key not in metric_changes:
            continue
        c = metric_changes[key]
        if unit == "%":
            cur, comp = f"{c['current']:.1%}", f"{c['comparison']:.1%}"
        elif unit == "SAR":
            cur, comp = f"SAR {c['current']:,.0f}", f"SAR {c['comparison']:,.0f}"
        elif unit == "x":
            cur, comp = f"{c['current']:.2f}x", f"{c['comparison']:.2f}x"
        else:
            cur, comp = f"{c['current']:,.0f}", f"{c['comparison']:,.0f}"
        label_with_benchmark = f"{label} ({benchmark})" if benchmark else label
        rows.append((label_with_benchmark, comp, cur, f"{c['pct_change']:+.1f}%"))
    return rows


def add_slide_qoq_scorecard(prs, rows, current_label, comparison_label, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    action = None
    if rows:
        def _pct(s):
            try:
                return float(str(s).strip("%").replace("+", ""))
            except ValueError:
                return 0.0
        mover = max(rows, key=lambda r: abs(_pct(r[3])))
        p = _pct(mover[3])
        metric_name = str(mover[0]).split(" (")[0].upper()
        action = f"{metric_name} {'IMPROVED' if p >= 0 else 'DECLINED'} {abs(p):.1f}% VS {(comparison_label or 'PRIOR PERIOD').upper()}"
    _header(slide, "QUARTER OVER QUARTER", "Performance Scorecard", period_label, story=story,
            action_title=action)
    headers = ["Metric", comparison_label or "Prior Period", current_label or "This Period", "Change %"]
    # Conditional formatting: color the Change % column based on positive/negative
    change_conditional = {3: {"benchmark": 0, "below": RED, "above": GREEN}}
    styled_table(slide, 0.55, 1.9, 11.4, headers, rows, [3.4, 2.6, 2.6, 2.8],
                 conditional_cols=change_conditional, banded=True)
    add_morph(slide)


def _add_findings_slide(prs, eyebrow, title, items, kind, period_label,
                       story=None, audience="executive", tone="confident"):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, eyebrow, title, period_label, story=story)
    lines = sn.narrate_findings(items, kind, audience=audience, tone=tone)
    y = 1.7
    for line in lines[:4]:
        rect(slide, 0.6, y + 0.06, 0.12, 0.12, fill=BRAND)
        text(slide, 0.95, y, 11.6, 0.9, (line, 14, INK, F_REG, False, None))
        y += 1.05
    if not lines:
        text(slide, 0.76, 3.0, 11, 0.5, ("No notable items this period.", 14, MUTED, F_REG, False, None))
    add_morph(slide)


def add_slide_recommendations(prs, actions, period_label, story=None,
                             audience="executive", tone="urgent"):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "RECOMMENDATIONS", "What To Do & Which Feature", period_label, story=story)
    y = 1.7
    for action in actions[:3]:
        sentence, feature = sn.narrate_recommendation(action, audience=audience, tone=tone)
        impact = action.get("expected_impact")
        body = f"{sentence}  ({impact})" if impact else sentence
        insight_box(slide, 0.55, y, 9.0, 1.5, action.get("title", "Recommendation").upper(), body)
        rect(slide, 9.8, y + 0.5, 2.9, 0.5, fill=BRAND, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, 9.8, y + 0.5, 2.9, 0.5,
             [[("WEBENGAGE", 8.5, PILL_LBL, F_MED, True, 1.0)],
              [(feature, 11, WHITE, F_BOLD, True, None)]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        y += 1.7
    add_morph(slide)


def add_slide_action_plan(prs, actions, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "ACTION PLAN", "Priorities for Next Period", period_label, story=story)
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


def build_deck(df, client_name="", period_label=None, comparison_result=None,
               conversion_attribution="Total", audience="executive",
               tone="confident", quality="standard") -> bytes:
    """Build the complete QBR PowerPoint deck.

    New in v2:
    - audience: "executive" | "marketing" | "analyst" — calibrates all LLM prose.
    - tone: "confident" | "consultative" | "urgent" | "reassuring" | "analytical".
    - quality: "quick" | "standard" | "premium" — controls reasoning depth & tokens.

    Returns PPTX bytes suitable for st.download_button.
    """
    summary = generate_executive_summary(df)
    period_label = period_label or summary.get("period")
    actions = summary.get("top_actions") or generate_top_actions(df, max_actions=5)
    ni = summary.get("narrative_insights", {}) or {}

    metric_changes, current_label, comparison_label = None, None, None
    if comparison_result:
        current_m = calculate_period_metrics(
            comparison_result["current_data"], comparison_result["current_days"], conversion_attribution)
        comp_m = calculate_period_metrics(
            comparison_result["comparison_data"], comparison_result["comparison_days"], conversion_attribution)
        metric_changes = calculate_metric_changes(current_m, comp_m)
        current_label = comparison_result.get("current_label")
        comparison_label = comparison_result.get("comparison_label")

    chan_rows_for_story = channel_card_rows(df)
    monthly_rows_for_story = monthly_kpi_rows(df)
    spotlight_for_story = top_campaign_spotlight(df)
    stories = _build_storylines(summary, chan_rows_for_story, monthly_rows_for_story,
                                 spotlight_for_story, comparison_label,
                                 audience=audience, tone=tone)

    prs = new_deck()
    add_slide_title(prs, client_name, period_label)
    add_slide_agenda(prs, period_label)
    add_slide_exec_summary(prs, summary, df, period_label, metric_changes, comparison_label,
                           audience=audience, tone=tone)
    add_slide_monthly_kpi(prs, df, period_label, story=stories.get("monthly_kpi"))
    add_slide_trend(prs, df, period_label, story=stories.get("trend"))
    add_slide_channel_cards(
        prs, df, period_label,
        comparison_df=comparison_result["comparison_data"] if comparison_result else None,
        story=stories.get("channel_cards"),
    )
    add_slide_channel_metrics(prs, channel_metrics_rows(df), period_label, story=stories.get("channel_metrics"))

    uplift_summary = control_group_uplift_summary(df, conversion_attribution)
    if uplift_summary:
        add_slide_control_uplift(prs, uplift_summary, period_label, story=None)

    add_slide_campaigns(prs, df, period_label, story=stories.get("campaigns"))

    spotlight = top_campaign_spotlight(df)
    if spotlight:
        add_slide_campaign_spotlight(prs, spotlight, period_label, story=stories.get("spotlight"))

    add_slide_journeys(prs, df, period_label, story=stories.get("journeys"))

    deliverability = deliverability_data(df)
    if deliverability:
        add_slide_deliverability(prs, deliverability, period_label, story=stories.get("deliverability"))

    attr_rows = attribution_rows(df)
    if attr_rows:
        add_slide_attribution(prs, attr_rows, period_label, story=stories.get("attribution"))

    if metric_changes:
        qoq_rows = qoq_scorecard_rows(metric_changes)
        if qoq_rows:
            add_slide_qoq_scorecard(prs, qoq_rows, current_label, comparison_label, period_label,
                                     story=stories.get("qoq_scorecard"))

    # ni["opportunities"] only scans the trailing 30 days, so on a quarterly deck
    # it's usually empty. Fall back to a full-period scan so this slide has content.
    opportunities = ni.get("opportunities", [])
    if not opportunities:
        opportunities = (identify_optimization_opportunities(df, df)
                         + identify_channel_optimization_opportunities(df, df))
    _add_findings_slide(prs, "WHAT'S WORKING", "Opportunities",
                        opportunities, "opportunity", period_label,
                        audience=audience, tone=tone)
    _add_findings_slide(prs, "WHAT'S AT RISK", "Performance Alerts",
                        ni.get("performance_alerts", []), "alert", period_label,
                        audience=audience, tone=tone)
    add_slide_recommendations(prs, actions, period_label, story=stories.get("recommendations"),
                              audience=audience, tone=tone)
    add_slide_action_plan(prs, actions, period_label, story=stories.get("action_plan"))
    add_slide_closing(prs)

    buf = io.BytesIO()
    prs.save(buf)
    return embed_fonts(buf.getvalue())
