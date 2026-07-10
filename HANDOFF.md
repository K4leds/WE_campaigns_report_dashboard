# Handoff: app.py Multipage Refactor (in progress)

**Repo:** `c:\Users\54led\vs_projects\WE_campaigns_report_dashboard`
**Branch:** `webengage-marketing-analytics-dashboard`
**Current HEAD:** `7c88aa5`
**Progress:** Tasks 1–14 of 28 complete. Foundation phase (1–10) fully done. Page-split phase (11–27) is 4 of 17 pages done (14 done overall, 14 remaining: Tasks 15–28).

This file is self-contained — everything needed to resume is embedded below, not linked. No need to read anything else first, though the full plan and ledger still exist on disk at the paths named in "Where things live" if you want more detail than what's here.

---

## 1. What this refactor is

`app.py` was an 8,896-line Streamlit monolith: one `if page == "..." / elif` chain (17 pages) plus ~40 analytical helper functions, all in one file. Goal: split it into

- `dashboard/` — a logic package (data pipeline, health scores, funnels, anomalies, lifecycle/stopped-journey/cohort analysis, comparison math, chart helpers). **Done, all 8 modules exist.**
- `pages/` — one file per dashboard page, using Streamlit's modern `st.Page` + `st.navigation` API. **4 of 17 done: 01_automated_insights.py, 02_overview.py, 03_marketing_actions.py, 04_campaigns.py.**
- `app.py` — becomes a thin entrypoint (upload, clean, sidebar filters, build `DashboardState`, then `st.navigation([...]).run()`). **Not yet wired — the old `if/elif` routing still exists in app.py for the NOT-yet-split pages (Journeys onward). Task 28 replaces it with real navigation once all 17 pages are split.**

**Hard constraint across every task: ZERO behavior change.** This is a pure structural refactor — no logic edits, only code moves. Every page must render identically to the pre-refactor app.

## 2. Current app.py state (as of HEAD `7c88aa5`)

`app.py` is now 3,367 lines (down from 8,896). The remaining `if/elif` routing chain, with real line numbers as of this commit:

```
434:    if page == "Journeys":
2059:    elif page == "Segments":
2096:    elif page == "Channels":
2675:    elif page == "Time Series":
2698:    elif page == "Correlations":
2739:    elif page == "A/B Testing":
2750:    elif page == "Attribution":
2763:    elif page == "Failed Reasons":
2799:    elif page == "Export":
2831:    elif page == "Comparisons":
3237:    elif page == "AI Insights":
```

**These line numbers WILL shift after every page-split task**, since each task deletes a branch's body from app.py. Always re-grep before trusting a line number:
```bash
grep -nE '^    if page ==|^    elif page ==' app.py
```

## 3. Remaining tasks (15–28)

Task numbers below match the original plan's task numbering (`docs/superpowers/plans/2026-07-10-app-multipage-refactor.md`, section "Tasks 11–27" + "Task 28"), renumbered here for the page each targets:

| Task | Page file | Source branch (name to grep for) | Notes |
|---|---|---|---|
| 15 | `pages/05_journeys.py` | `if page == "Journeys":` | **Only the "Journey Analysis" portion** — stop before the `st.header("📊 Advanced Business Intelligence Analytics")` sub-section (that's Task 16) and before `st.header("🚨 Stopped Journey Analysis...")` (Task 17). Read the full "Journeys" branch first to find those two `st.header(...)` boundaries by string search — do not assume line offsets. |
| 16 | `pages/06_advanced_bi.py` | inside the Journeys branch: `st.header("📊 Advanced Business Intelligence Analytics")` block | Uses `dashboard.comparisons_logic` (create_journey_comparison_analysis, create_custom_date_range_comparison, calculate_period_metrics) and `dashboard.lifecycle.create_cohort_analysis`. |
| 17 | `pages/07_stopped_journeys.py` | inside the Journeys branch: `st.header("🚨 Stopped Journey Analysis & Revenue Loss Estimation")` block | Uses `dashboard.lifecycle` (analyze_stopped_journeys, estimate_revenue_loss_ml, generate_stopped_journey_recommendations). |
| 18 | `pages/08_segments.py` | `elif page == "Segments":` | Uses `analysis.top_segments`. |
| 19 | `pages/09_channels.py` | `elif page == "Channels":` | Uses `analysis.channel_analysis`. |
| 20 | `pages/10_time_series.py` | `elif page == "Time Series":` | Uses `analysis.time_series_analysis`. |
| 21 | `pages/11_correlations.py` | `elif page == "Correlations":` | |
| 22 | `pages/12_ab_testing.py` | `elif page == "A/B Testing":` | Uses `analysis.ab_testing_analysis`. |
| 23 | `pages/13_attribution.py` | `elif page == "Attribution":` | Uses `analysis.attribution_analysis`. |
| 24 | `pages/14_failed_reasons.py` | `elif page == "Failed Reasons":` | Uses `analysis.failed_reasons_analysis`, `analysis.esp_analysis`. |
| 25 | `pages/15_comparisons.py` | `elif page == "Comparisons":` | Uses `dashboard.comparisons_logic` (calculate_comparison_periods, calculate_period_metrics, calculate_metric_changes, calculate_uplift_significance). |
| 26 | `pages/16_ai_insights.py` | `elif page == "AI Insights":` | Uses `insights_engine` and `temporal_intelligence` functions — trace actual names used, don't assume. |
| 27 | `pages/17_export.py` | `elif page == "Export":` | |
| 28 | wire `st.navigation`, delete dead routing, final verify | — | See section 6 below. |

**Journeys (Task 15) is the trickiest remaining task** because it's really 3 pages bundled in one `elif` branch. Locate the 3 sub-boundaries by searching for these exact strings inside the Journeys branch before splitting:
- `st.header("Journey Analysis")` — start of Task 15's content
- `st.header("📊 Advanced Business Intelligence Analytics")` — start of Task 16's content
- `st.header("🚨 Stopped Journey Analysis & Revenue Loss Estimation")` — start of Task 17's content

## 4. The exact page-split pattern to follow (copy this)

Every page task follows this recipe. Use `pages/03_marketing_actions.py` as the cleanest concrete reference (below is its real header, verbatim from the file):

```python
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from utils import format_metric, style_total_row, export_chart_image
from config import CHANNEL_COSTS, REQUIRED_COLUMNS, COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import (
    apply_attribution, apply_dimension_filters, get_attribution_display_label,
    get_selected_revenue_display_name, get_selected_conversion_display_name, resolve_source_column,
)

ctx = get_ctx()
df = ctx.df
filtered_df = ctx.filtered_df
comparison_result = ctx.comparison_result
revenue_attribution = ctx.revenue_attribution
conversion_attribution = ctx.conversion_attribution
selected_rev_label = ctx.selected_rev_label
selected_conv_label = ctx.selected_conv_label
date_range = ctx.date_range
comparison_mode = ctx.comparison_mode

# ... then the page body, pasted verbatim from app.py, de-indented by 8 spaces ...
```

**⚠️ Known erratum, already fixed in every completed page — do not repeat the mistake:** the ORIGINAL plan document's header template said `from dashboard.charts import format_metric, style_total_row, export_chart_image, attribution_display`. That's WRONG — `format_metric`, `style_total_row`, `export_chart_image` live in `utils.py`, not `dashboard/charts.py`. `dashboard/charts.py` only exports `attribution_display(ctx, col_name)`. Only import from `dashboard.charts` if the page body actually calls `attribution_display` or needs the local `_attribution_display(col_name)` closure pattern (see `pages/02_overview.py` for how to reconstruct `attribution_rename` + `_attribution_display` locally when a page needs them — grep the branch body for those two names to decide).

**Rules for every page task:**
1. Read the full branch body first (by name/header string, not trusted line numbers).
2. Copy the header above, but PRUNE unused imports — trace every name the pasted body actually references and only keep what's used. Never remove the `get_ctx()`/ctx-unpacking block.
3. Paste the branch body verbatim, de-indented by 8 spaces (branch body is at 8-space indent under `if`/`elif`; page-file module level is 0-space).
4. In app.py: delete the branch's `if`/`elif` line and its entire body. If you deleted the very first `if page == ...` branch, change the next `elif` to `if`. Otherwise leave the rest of the chain untouched.
5. If any name in the pasted body doesn't resolve to an already-extracted module (`dashboard.health`, `dashboard.funnels`, `dashboard.anomalies`, `dashboard.lifecycle`, `dashboard.comparisons_logic`, `dashboard.data_pipeline`, `dashboard.charts`, `analysis.py`, `utils.py`, `config.py`, `attribution.py`, `insights_engine.py`, `temporal_intelligence.py`, `data_processing.py`) or a standard library/pandas/numpy/plotly/sklearn import, **stop and report the specific missing name** rather than guessing.

## 5. Verification (do this for every task)

`ast.parse` alone is NOT enough — it only checks syntax, not whether names resolve at runtime (page files call `get_ctx()` at module scope, which needs real Streamlit session state). Use this 4-step check every time:

```bash
# 1. Syntax check both files
python -c "import ast; ast.parse(open('pages/NN_name.py', encoding='utf-8').read()); print('page ok')"
python -c "import io,ast; ast.parse(io.open('app.py',encoding='utf-8').read()); print('app.py parses')"

# 2. Existing test suite must stay green (currently 8 tests, should not decrease)
python -m pytest tests/ -q

# 3. REAL behavioral smoke test — actually runs the page with fake seeded data.
#    This is the single most valuable check; it catches NameError/ImportError
#    that ast.parse cannot. Recreate this file if it's missing from
#    .superpowers/sdd/smoke-test-snippet.py — full contents below in section 7.
python .superpowers/sdd/smoke-test-snippet.py pages/NN_name.py
# Expect the LAST line of output to be: PAGE RAN OK
# "missing ScriptRunContext" warnings are expected noise — ignore them.
# If you see "RUNTIME ERROR: ...", read the traceback, fix the missing
# import/name, and re-run until PAGE RAN OK.

# 4. Confirm the routing chain shrank by exactly one branch
grep -n "elif page ==" app.py | wc -l
```

## 6. Task 28 — final wiring (once all 17 pages exist)

Replace the old `page = st.sidebar.selectbox("Navigate to", [...])` block and the now-empty `if/elif` chain with:

```python
pages = [
    st.Page("pages/01_automated_insights.py", title="Automated Insights", icon="🎯", default=True),
    st.Page("pages/02_overview.py", title="Overview"),
    st.Page("pages/03_marketing_actions.py", title="Marketing Actions", icon="📈"),
    st.Page("pages/04_campaigns.py", title="Campaigns"),
    st.Page("pages/05_journeys.py", title="Journeys"),
    st.Page("pages/06_advanced_bi.py", title="Advanced BI", icon="📊"),
    st.Page("pages/07_stopped_journeys.py", title="Stopped Journeys", icon="🚨"),
    st.Page("pages/08_segments.py", title="Segments"),
    st.Page("pages/09_channels.py", title="Channels"),
    st.Page("pages/10_time_series.py", title="Time Series"),
    st.Page("pages/11_correlations.py", title="Correlations"),
    st.Page("pages/12_ab_testing.py", title="A/B Testing"),
    st.Page("pages/13_attribution.py", title="Attribution"),
    st.Page("pages/14_failed_reasons.py", title="Failed Reasons"),
    st.Page("pages/15_comparisons.py", title="Comparisons"),
    st.Page("pages/16_ai_insights.py", title="AI Insights", icon="🤖"),
    st.Page("pages/17_export.py", title="Export"),
]
st.navigation(pages).run()
```

**Important:** the upload widget and sidebar filters must stay in `app.py` ABOVE `st.navigation().run()` so they render on every page (Streamlit's documented entrypoint pattern — common widgets defined in the entrypoint persist across all pages). If upload/filters currently sit entirely inside `if uploaded_file is not None:`, keep the upload widget + `st.navigation().run()` running unconditionally, with filter sidebar + `set_ctx()` populated only when a file is present. Pages already gate on missing data via `get_ctx()` (defined in `dashboard/state.py`), so this is safe.

After wiring: verify `grep -n "page ==" app.py` returns nothing, run the full test suite, and do ONE real `streamlit run app.py` manual walkthrough — upload a CSV, click through all 17 pages, confirm numbers match the pre-refactor baseline. Check final `wc -l app.py` (should be a few hundred lines).

## 7. `smoke-test-snippet.py` — recreate this file if missing

Located at `.superpowers/sdd/smoke-test-snippet.py`. If that path doesn't exist in your environment, recreate it exactly as follows (it must be run from the repo root):

```python
import os
import sys
sys.path.insert(0, os.getcwd())

import pandas as pd
import streamlit as st
from dashboard.state import DashboardState, set_ctx
import runpy

df = pd.DataFrame({
    'Journey Name': ['J1', 'J1'], 'Campaign Name': ['C1', 'C2'],
    'Channel': ['Email', 'SMS'], 'Type of Campaign': ['Journey', 'One-Time'],
    'Segment Name': ['S1', 'S1'], 'Conversion Event': ['Order Completed', 'Order Completed'],
    'Sent': [100, 200], 'Delivered': [95, 190], 'Failed': [5, 10], 'Queued': [0, 0],
    'Reporting Period Start Date': pd.to_datetime(['2025-01-01', '2025-01-02']),
    'Reporting Period End Date': pd.to_datetime(['2025-01-01', '2025-01-02']),
    'Day': pd.to_datetime(['2025-01-01', '2025-01-02']),
    'Unique Impressions': [80, 150], 'Total Impressions': [90, 160],
    'Unique Clicks': [10, 20], 'Total Clicks': [12, 22],
    'Unique Conversions': [2, 4], 'Total Conversions': [3, 5],
    'Unique Opens': [40, 70],
    'Revenue (SAR)': [50.0, 100.0], 'Impression-Through Revenue (SAR)': [10.0, 20.0],
    'Click-Through Revenue (SAR)': [40.0, 80.0],
    'Selected Revenue (SAR)': [50.0, 100.0], 'Selected Conversions': [2, 4],
    'Total in Control Group': [0, 0], 'Unique Control Group Conversions': [0, 0],
    'CTR': [0.125, 0.13], 'Conversion Rate': [0.2, 0.2], 'Delivery Rate': [0.95, 0.95],
})

set_ctx(DashboardState(
    df=df, filtered_df=df, comparison_result=None,
    revenue_attribution='Total', conversion_attribution='Total',
    selected_rev_label='Revenue (SAR)', selected_conv_label='Unique Conversions',
    date_range=None, comparison_mode='None',
    filter_options={'channels': ['Email', 'SMS'], 'campaign_types': ['Journey', 'One-Time'],
                     'campaigns': ['C1', 'C2'], 'segments': ['S1'], 'journeys': ['J1'],
                     'conversion_events': ['Order Completed']},
    channels=[], campaign_types=[], campaigns=[], segments=[], journeys=[], conversion_events=[],
))

page_path = sys.argv[1]
try:
    runpy.run_path(page_path, run_name='__main__')
    print('PAGE RAN OK')
except SystemExit:
    print('PAGE CALLED st.stop() (check if expected)')
except Exception as e:
    print('RUNTIME ERROR:', type(e).__name__, e)
    raise
```

If a later page needs a column this fake DataFrame doesn't have, add the column rather than skipping the smoke test — keep the file at this same path so it stays reusable.

## 8. `dashboard/state.py` — the shared-state contract (already built, do not modify)

```python
"""Shared dashboard state passed from the entrypoint to page modules."""
from dataclasses import dataclass, field
from typing import Any, Optional

import streamlit as st


@dataclass
class DashboardState:
    df: Any
    filtered_df: Any
    comparison_result: Optional[dict]
    revenue_attribution: str
    conversion_attribution: str
    selected_rev_label: str
    selected_conv_label: str
    date_range: Any
    comparison_mode: str
    filter_options: dict = field(default_factory=dict)
    channels: list = field(default_factory=list)
    campaign_types: list = field(default_factory=list)
    campaigns: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    journeys: list = field(default_factory=list)
    conversion_events: list = field(default_factory=list)

    def attribution_display(self, col_name: str) -> str:
        """Map internal 'Selected Revenue/Conversions' names to the selected label."""
        from attribution import get_attribution_display_label
        return get_attribution_display_label(
            col_name, self.revenue_attribution, self.conversion_attribution
        )


def set_ctx(ctx: DashboardState) -> None:
    st.session_state["ctx"] = ctx


def get_ctx() -> DashboardState:
    """Return the current DashboardState, or gate the page if no CSV is loaded yet."""
    ctx = st.session_state.get("ctx")
    if ctx is None:
        st.info("⬆️ Upload a WebEngage CSV on the main page to begin.")
        st.stop()
    return ctx
```

`app.py`'s prelude (lines ~280-433 as of HEAD) already builds and calls `set_ctx(DashboardState(...))` right before the `if page == "Journeys":` line — this is already wired and does not need to change for Tasks 15–27, only for Task 28's navigation swap.

## 9. Lessons learned so far (avoid repeating these)

1. **Don't assert unverified assumptions about a function's dependencies in a dispatch.** One task (extracting `estimate_revenue_loss_ml`) was told to expect sklearn (RandomForestRegressor etc.) based on a wrong guess; the real dependency was `prophet`+`scipy.stats`. The mistake produced dead imports that had to be fixed in a follow-up. Let whoever does the work trace names themselves and report what they find.
2. **Trailing whitespace differences during a "verbatim" code move are not real defects.** One review flagged that a copy wasn't byte-for-byte due to stripped trailing whitespace on ~43 lines. This was correctly waived — Python ignores trailing whitespace outside string literals, and the important invariant is logic preservation, not literal byte match. Don't burn a fix-cycle on this if it recurs.
3. **`ast.parse` cannot catch NameError/ImportError in page files** because `get_ctx()` calls `st.stop()` which needs real Streamlit context — a plain import or `ast.parse` won't exercise the actual body logic that runs after `ctx = get_ctx()`. The `runpy.run_path()` + seeded `set_ctx()` smoke test (section 5/7) actually executes the page and is the strongest available verification short of a live `streamlit run`.
4. **`app.py`'s original page-split plan template had a wrong import path** (see section 4's erratum) — already corrected in all 4 completed pages; just don't reintroduce it.
5. Two earlier duplicate-function reconciliation tasks (Tasks 2–3, already done) found and fixed two real behavioral divergences between app.py's local copies and the canonical `analysis.py` versions (in `top_campaigns` and `channel_analysis`) — these are already merged into `analysis.py` and don't need revisiting.
6. Root-level `test_stopped_detection.py` has zero pytest-collected tests (no `test_*` functions, doesn't import `app`) — confirmed harmless and unaffected by this refactor; don't worry about it.

## 10. Where things live (for reference, not required reading)

- Full original plan (28-task breakdown, all details): `docs/superpowers/plans/2026-07-10-app-multipage-refactor.md`
- Original design spec: `docs/superpowers/specs/2026-07-10-app-multipage-refactor-design.md`
- Task-by-task progress ledger with every review verdict: `.superpowers/sdd/progress.md`
- Per-task briefs/reports (verbose, one file per task so far): `.superpowers/sdd/task-*-brief.md`, `.superpowers/sdd/task-*-report.md`
- **Note:** `.gitignore` excludes `*.md` in this repo (intentional — many local guide docs are untracked). This `HANDOFF.md` and the plan/spec docs above were force-added with `git add -f` to be tracked; keep doing that if you add more `.md` docs you want committed.
- Project-level Claude Code permission allowlist (reduces prompts for pytest/git-add/git-commit/grep/python -c): `.claude/settings.json`

## 11. Suggested first message to the next session/LLM

> "Resume the app.py multipage refactor. Read `HANDOFF.md` at the repo root — it's self-contained. Current HEAD is 7c88aa5 on branch webengage-marketing-analytics-dashboard. Tasks 1-14 of 28 are done (verified, reviewed, committed). Continue with Task 15 (pages/05_journeys.py — Journey Analysis section only, see section 3 for the sub-boundaries). Follow the pattern in section 4, verify with section 5's 4-step check, and keep updating `.superpowers/sdd/progress.md` as you go if you're using the same subagent-driven-development workflow — otherwise just work through the remaining tasks directly, using the 4 completed pages/*.py files as your concrete reference."
