# app.py Multipage Refactor — Design

**Date:** 2026-07-10
**Status:** Approved design, pending spec review

## Problem

`app.py` is a single 8,896-line module (~505 KB). It contains:

- ~40 analytical helper functions (health scores, funnels, anomaly detection,
  lifecycle/stopped-journey analysis, revenue-loss ML, comparison metrics) defined
  inline above the routing.
- A shared prelude (CSV upload → clean → cache → sidebar filters → `filtered_df` /
  `comparison_result`).
- 17 dashboard "pages" implemented as one giant `if page == "…" / elif` chain driven
  by a sidebar `st.selectbox`.

This is a Streamlit monolith. It is hard to read, hard to edit reliably, and mixes
presentation with analytical logic even though dedicated logic modules already exist
(`analysis.py`, `attribution.py`, `insights_engine.py`, `temporal_intelligence.py`,
`data_processing.py`, `utils.py`).

## Goal

Full restructure into:

- A thin `app.py` **entrypoint** (page config, upload, clean, sidebar filters,
  build shared state) that ends in `st.navigation([...]).run()`.
- A `dashboard/` **logic package** holding the analytical helpers, reconciled with
  the existing top-level logic modules.
- A `pages/` **presentation folder** with one file per current page (17 files).

Uses the modern **`st.Page` + `st.navigation`** API (Streamlit 1.36+), confirmed
against current Streamlit docs via context7. No behavior changes — this is a
structural refactor. Every page must render identically to today.

## Target Architecture

```
app.py                    ← entrypoint: page config, upload, clean_data,
                            sidebar filters, build filtered_df / comparison_result,
                            stash DashboardState in session_state, st.navigation(...).run()

dashboard/
  __init__.py
  state.py                ← DashboardState dataclass + get_ctx() accessor/guard
  data_pipeline.py        ← clean_data, load_and_clean_data,
                            apply_filters_and_attribution, cached_* wrappers
  health.py               ← calculate_journey_health_score,
                            calculate_campaign_health_score
  funnels.py              ← analyze_campaign_funnel, analyze_journey_funnel,
                            calculate_funnel_conversion_rates
  anomalies.py            ← detect_campaign_anomalies, detect_journey_anomalies,
                            get_anomaly_recommendation
  lifecycle.py            ← analyze_journey_lifecycle, get_lifecycle_recommendation,
                            analyze_stopped_journeys, estimate_revenue_loss_ml,
                            generate_stopped_journey_recommendations,
                            create_revenue_attribution_waterfall, create_cohort_analysis
  comparisons_logic.py    ← calculate_comparison_periods, calculate_period_metrics,
                            calculate_metric_changes, calculate_uplift_significance,
                            create_journey_comparison_analysis,
                            create_custom_date_range_comparison
  charts.py               ← export_chart_image, style_total_row, format_metric,
                            attribution display helpers, shared viz utilities

pages/
  01_automated_insights.py    (was: "🎯 Automated Insights")
  02_overview.py              (was: "Overview")
  03_marketing_actions.py     (was: "📈 Marketing Actions")
  04_campaigns.py             (was: "Campaigns")
  05_journeys.py              (was: "Journeys")
  06_advanced_bi.py           (was: "Advanced BI" block within Journeys/section)
  07_stopped_journeys.py      (was: "🚨 Stopped Journey Analysis")
  08_segments.py              (was: "Segments")
  09_channels.py              (was: "Channels")
  10_time_series.py           (was: "Time Series")
  11_correlations.py          (was: "Correlations")
  12_ab_testing.py            (was: "A/B Testing")
  13_attribution.py           (was: "Attribution")
  14_failed_reasons.py        (was: "Failed Reasons")
  15_comparisons.py           (was: "Comparisons")
  16_ai_insights.py           (was: "AI Insights")
  17_export.py                (was: "Export")
```

**Note:** during planning, some `dashboard/*` modules may be merged into the existing
top-level modules (`analysis.py`, `insights_engine.py`, `temporal_intelligence.py`)
rather than created new, where the function clearly belongs there. The plan will
reconcile this per-function. The page count and page-file split are fixed.

The exact set of page files will be finalized against the actual `if page ==` branches
(some branches such as "Advanced BI" and "Stopped Journey Analysis" render inside the
Journeys branch today and will be split into their own page files or kept as sections —
decided per-branch during planning based on how they are reached).

## Shared-State Contract

Today `df`, `filtered_df`, `comparison_result`, attribution labels, filter selections,
and helper closures (`_attribution_display`, `_apply_attribution`,
`_apply_dimension_filters`) are **local variables** in one script; page branches read
them by scope.

In the multipage app each page is a **separate module run fresh** after the entrypoint.
The contract:

1. The **entrypoint (`app.py`) runs on every page load** — it rebuilds the sidebar,
   `filtered_df`, and `comparison_result` before the selected page body runs.
   `st.navigation(...).run()` executes the chosen page *after* the entrypoint body.
2. Shared **data** is passed via `st.session_state["ctx"]` as a `DashboardState`.
3. Shared **functions** (former closures) become plain functions in `dashboard/charts.py`
   (and other modules) taking explicit args (`ctx`, or the attribution strings) instead
   of closing over script scope.
4. `@st.cache_data` functions keep **identical signatures** so caching behavior is preserved.

Entrypoint (sketch):

```python
# app.py, after building filtered_df & comparison_result
st.session_state["ctx"] = DashboardState(
    df=df, filtered_df=filtered_df, comparison_result=comparison_result,
    revenue_attribution=revenue_attribution,
    conversion_attribution=conversion_attribution,
    selected_rev_label=selected_rev_label, selected_conv_label=selected_conv_label,
    date_range=date_range, comparison_mode=comparison_mode,
    filter_options=_opts, ...  # filter selections
)
st.navigation(PAGES).run()
```

Page (sketch):

```python
# pages/02_overview.py
import streamlit as st
from dashboard.state import get_ctx
from dashboard import charts, health

ctx = get_ctx()                      # gate: friendly message + st.stop() if no data
df, filtered_df = ctx.df, ctx.filtered_df
st.header("Overview")
# ... existing overview body, logic unchanged
```

## Empty State (no CSV uploaded)

**Gate every page.** `get_ctx()` displays a friendly "Upload a CSV to begin" message and
calls `st.stop()` when no data has been loaded. This matches today's behavior exactly
(today the whole `if uploaded_file is not None:` block is skipped, so pages never render
without data). Landing-page UX polish is explicitly out of scope for this refactor.

## Migration Strategy

Safety comes from **verifying identical behavior at each step**, not new unit tests
(the app is UI-heavy). Steps:

1. **Extract logic modules first, `app.py` still monolithic.** Move the ~40 helpers into
   `dashboard/*` (reconciling with existing modules), replace inline defs with imports.
   Run the app after each module; behavior must be identical. Shrinks `app.py` from
   ~8,900 to ~4,000 lines before any page split.
2. **Introduce `DashboardState` + entrypoint prelude.** Keep pages as the `if page ==`
   chain temporarily, now reading from `ctx`. Verify.
3. **Split pages one at a time** into `pages/NN_*.py`; convert each `elif page ==` branch
   to its own file and wire `st.Page`. Run + click through that page after each move.
   17 small, verifiable steps.
4. **Delete dead routing** and the `selectbox` nav once all pages are files.

## Verification

- No meaningful automated UI tests exist. Verification = run `streamlit run app.py` after
  each step and confirm the page renders and key numbers match the pre-refactor app.
- Existing `tests/` and `test_*.py` stay green throughout, because logic functions keep
  identical signatures.

## Risks

- **Hidden cross-references between page branches** — a variable set in one branch read in
  another, or shared `st.session_state` keys (e.g. `forecast_result`). Before splitting
  each page, grep for cross-branch reads and surface them rather than silently breaking.
- **Cache behavior drift** — mitigated by keeping `@st.cache_data` signatures identical.
- **Closures over script scope** — mitigated by converting them to explicit-arg functions
  in step 1, before any page split.

## Out of Scope

- Any change to analytical logic or output.
- Landing-page / navigation UX redesign.
- New automated test coverage beyond keeping existing tests green.
- Refactoring the existing top-level logic modules beyond what's needed to absorb the
  extracted helpers.
