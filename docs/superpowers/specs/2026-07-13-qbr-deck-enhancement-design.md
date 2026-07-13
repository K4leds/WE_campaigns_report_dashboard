# QBR Deck Enhancement Design

## Problem
`slides_export.build_deck()` produces a 10-slide client deck that's too thin for a
quarterly business review shown to a client: no QoQ comparison, no per-channel
detail, no deliverability/ESP data, no control-group uplift, and tables carry only
one metric each. Reference: a manually-built UPC QBR deck
(`C:\Users\54led\Downloads\UPC - QBR (JFM 2026).pdf`) shows the target density —
per-channel status cards, QoQ funnel/uplift comparisons, coupon/segment tables,
campaign spotlight slides, and a structured recommendations section.

The dashboard already computes most of what's missing:
- `dashboard/comparisons_logic.py` — `calculate_period_metrics`,
  `calculate_metric_changes`, `calculate_uplift_significance` — used by
  `pages/14_comparisons.py`'s period-over-period comparison feature.
- `analysis.py` — `esp_analysis`, `failed_reasons_analysis`, `ab_testing_analysis`,
  `attribution_analysis`, `top_segments` — none currently used by `slides_export.py`.
- `insights_engine.py` — `CHANNEL_MIN_SENT` volume threshold, per-channel
  alert/opportunity detection already scoped to individual channels.

This design wires that existing analysis into new/enhanced slides. No new data
pipelines are introduced.

## Slide lineup (10 → 18 slides)

1. Title — unchanged.
2. **Agenda** *(new)* — static section list.
3. Executive Summary — tiles gain a QoQ delta (▲/▼ %) next to each metric when
   comparison mode is active (via `calculate_metric_changes`); unchanged otherwise.
4. **Monthly KPI table** *(new)* — Revenue / Conversions / Sent by month with a
   Total row (same groupby-by-month pattern already used in
   `pages/14_comparisons.py::_cached_monthly_trend`).
5. Trend — unchanged chart.
6. **Channel cards grid** *(replaces the bar chart + table)* — one card per
   channel: status pill (Active / Low Volume / Inactive, from
   `CHANNEL_MIN_SENT`), revenue, delivery rate, one computed insight sentence,
   QoQ arrow when comparison data exists. Source: `channel_analysis`.
7. **Control Group Uplift** *(new, conditional)* — uplift % and reliability tier.
   Emitted only if `Total in Control Group` has nonzero data.
   Source: `calculate_uplift_significance`, `control_group_uplift` metric.
8. Top Campaigns — table gains CVR and AOV columns (not just conversions).
9. **Campaign Spotlight** *(new)* — large stat-card slide for the single
   #1-ranked campaign: revenue, CVR, audience size, one-line computed insight.
   No creative image (not in the source data).
10. **Top Segments** *(new, conditional)* — table, only if `Segment Name` is
    populated. Source: `top_segments`.
11. Journeys — table gains Revenue and CVR columns.
12. **Deliverability / ESP** *(new, conditional)* — ESP performance table +
    top failure reasons. Only if `ESP/SSP/WSP/RSP name` or failure-reason
    columns exist. Source: `esp_analysis`, `failed_reasons_analysis`.
13. **Attribution breakdown** *(new, conditional)* — Click-Through /
    Impression-Only / Send-Only split. Source: `attribution_analysis`.
14. **QoQ Scorecard** *(new, conditional on comparison mode)* — table:
    Revenue / Conversions / CTR / Delivery Rate / AOV / ROAS, current vs.
    previous period, % change, trend arrow. Source: `calculate_metric_changes`,
    fed by `ctx.comparison_result` (the dashboard's existing comparison state).
15. What's Working (opportunities) — unchanged.
16. What's At Risk (alerts) — unchanged.
17. Recommendations — unchanged.
18. Action Plan — unchanged, followed by a static closing brand slide
    ("Measure. Analyze. Optimize.").

Conditional slides (7, 10, 12, 13, 14) are silently skipped when their
underlying data isn't present — no broken/empty slides for a client CSV that
lacks that column, matching the existing `_put_chart` degrade-gracefully
pattern already in `slides_export.py`.

## Plumbing change
`pages/13_export.py` passes one new optional argument,
`comparison_result=ctx.comparison_result`, into `build_deck()`. Everything else
(fingerprinting, download button, spinner) is unchanged. When comparison mode
is off, `comparison_result` is `None` and slides 3's deltas / slide 14 are
skipped — same conditional-skip mechanism as the other new slides.

## Visual style
Channel cards, the campaign spotlight, and the QoQ scorecard reuse the
existing primitives in `slides_export.py` (`rect`, `text`, `stat_tile`,
`styled_table`) — colored status pills and bold percentage deltas, matching
the UPC sample's visual language, without introducing a new charting library
or layout engine.

## Testing
`tests/test_build_deck.py` slide-count assertion updates from 10 to 18 (plus
a variant asserting conditional slides are skipped when their source columns
are absent, and a variant asserting they appear when `comparison_result` is
supplied). `tests/test_slides_helpers.py` gets a smoke test per new helper
(channel card builder, QoQ scorecard builder).

## Out of scope
- No manual per-channel commentary field (computed-only, per user decision).
- No creative/phone-mockup images (not present in source data).
