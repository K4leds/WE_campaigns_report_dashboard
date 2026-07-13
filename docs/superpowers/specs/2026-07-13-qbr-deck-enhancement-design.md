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

**Audience.** This deck is read by experienced analysts and marketing managers
deciding where to act, not a general-audience summary. Two consequences drive
the rest of this design:
- **Recommendations carry numbers, not just narrative.** `insights_engine.
  generate_top_actions()` already computes `expected_impact` (a dollar or
  percentage-point figure) per action; today `slides_narrative.
  narrate_recommendation()` drops it in favor of a prose sentence. The
  Recommendations slide (17) is changed to show the sentence *and* the
  `expected_impact` figure as a stat, so every recommendation is defensible in
  a client ROI conversation.
- **Rate metrics carry a benchmark, not a bare number.** `insights_engine`
  already encodes what "good" looks like for the rates it alerts on (delivery
  rate <85% is critical, conversion-rate/CTR drop >30-40% vs. historical is a
  problem, ROAS ≥4 is strong / ≥2 is workable). Any stat tile or table column
  showing delivery rate, CTR, conversion rate, or ROAS displays that threshold
  as a small reference label (e.g. "target >90%") pulled from the same
  constants `insights_engine` uses, so a manager can judge good vs. bad
  without leaving the slide.

## Slide lineup (10 → 20 slides)

1. Title — unchanged.
2. **Agenda** *(new)* — static section list.
3. Executive Summary — tiles gain a QoQ delta (▲/▼ %) next to each metric when
   comparison mode is active (via `calculate_metric_changes`); the Delivery
   Rate tile always shows its benchmark target.
4. **Monthly KPI table** *(new)* — Revenue / Conversions / Sent by month with a
   Total row (same groupby-by-month pattern already used in
   `pages/14_comparisons.py::_cached_monthly_trend`).
5. Trend — unchanged chart.
6. **Channel cards grid** *(replaces the bar chart + table)* — one card per
   channel: status pill (Active / Low Volume / Inactive, from
   `CHANNEL_MIN_SENT`), revenue, delivery rate, one computed insight sentence,
   QoQ arrow when comparison data exists. Source: `channel_analysis`.
7. **Channel Metrics table** *(new)* — a second, data-dense channel slide
   alongside the cards: two stacked tables (Sent / Delivered / Delivery Rate /
   Clicks / CTR, then Conversions / Conv Rate / Revenue / AOV / ROAS) with one
   row per channel, closer to the UPC sample's "Channels Performance" table
   than the cards are. ROAS column only appears if `Campaign Cost` exists.
8. **Control Group Uplift** *(new, conditional)* — uplift % and reliability tier.
   Emitted only if `Total in Control Group` has nonzero data.
   Source: `calculate_uplift_significance`, `control_group_uplift` metric.
9. Top Campaigns — table gains CVR and AOV columns (not just conversions).
10. **Campaign Spotlight** *(new)* — large stat-card slide for the single
    #1-ranked campaign: revenue, CVR, audience size, one-line computed insight.
    No creative image (not in the source data).
11. **Top Segments** *(new, conditional)* — table, only if `Segment Name` is
    populated. Source: `top_segments`.
12. Journeys — table gains Revenue and CVR columns.
13. **Deliverability / ESP** *(new, conditional)* — ESP performance table +
    top failure reasons. Only if `ESP/SSP/WSP/RSP name` or failure-reason
    columns exist. Source: `esp_analysis`, `failed_reasons_analysis`.
14. **Attribution breakdown** *(new, conditional)* — Click-Through /
    Impression-Only / Send-Only split. Source: `attribution_analysis`.
15. **QoQ Scorecard** *(new, conditional on comparison mode)* — table:
    Revenue / Conversions / CTR / Delivery Rate / AOV / ROAS, current vs.
    previous period, % change, trend arrow, with benchmark labels on the
    Delivery Rate and ROAS rows. Source: `calculate_metric_changes`, fed by
    `ctx.comparison_result` (the dashboard's existing comparison state).
16. What's Working (opportunities) — unchanged.
17. What's At Risk (alerts) — unchanged.
18. Recommendations — each recommendation now shows its `expected_impact`
    figure (from `generate_top_actions`) as a stat alongside the sentence.
19. Action Plan — unchanged.
20. Closing — static brand slide ("Measure. Analyze. Optimize.").

Conditional slides (8, 11, 13, 14, 15) are silently skipped when their
underlying data isn't present — no broken/empty slides for a client CSV that
lacks that column, matching the existing `_put_chart` degrade-gracefully
pattern already in `slides_export.py`.

## Narrative arc (storyline captions)
Every slide's header gains an optional one-line "story" caption — a computed
sentence connecting that slide to the one before it, so the deck reads as a
chain of findings ("this total → broken down by month → shaped like this →
driven by this channel → by these specific campaigns → ...") rather than a
stack of independent reports. Each caption is built from numbers the
corresponding slide-builder function already has in scope (or that its
predecessor computed) — no new analysis, purely narrative framing on top of
existing data. `_header()` renders the caption; a single `_build_storylines()`
function computes all of them once per deck build.

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
