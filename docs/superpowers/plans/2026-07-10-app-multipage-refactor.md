# app.py Multipage Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the 8,896-line `app.py` Streamlit monolith into a thin entrypoint, a `dashboard/` logic package, and a `pages/` folder (one file per page) using `st.Page` + `st.navigation`, with zero behavior change.

**Architecture:** `app.py` becomes the entrypoint (page config, upload, clean, sidebar filters, build `filtered_df`/`comparison_result`, stash a `DashboardState` in `st.session_state`, then `st.navigation([...]).run()`). Analytical helpers move into `dashboard/*` modules (or, where a duplicate already exists in `analysis.py`/`utils.py`/`data_processing.py`, the local copy is deleted and the existing module imported). Each of the 17 pages becomes a file under `pages/` that reads shared data via `get_ctx()`.

**Tech Stack:** Python 3.13, Streamlit 1.56.0, pandas, numpy, plotly, scikit-learn, statsmodels.

## Global Constraints

- **Streamlit ≥ 1.36** required for `st.Page`/`st.navigation` (installed: 1.56.0). Do not use the older `pages/`-autodiscovery convention.
- **Zero behavior change.** Every page must render identically to the pre-refactor app. No logic edits — moves only.
- **`@st.cache_data` function signatures must stay byte-for-byte identical** so caching behavior is preserved.
- **Verification is manual + import-smoke**, not new unit tests: after each task run `python -c "import <module>"` for touched modules, run `streamlit run app.py` and confirm the affected page renders and key numbers are unchanged. Existing `tests/` and `test_*.py` must stay green.
- **`.gitignore` excludes `*.md`** — use `git add -f` for any plan/spec docs; source files (`.py`) add normally.
- **Every page file must call `get_ctx()`** at the top, which gates on missing data (`st.info(...); st.stop()`).
- Follow existing code style: functions read `df`/`filtered_df` positionally; attribution handled via `attribution.py` helpers.

---

## File Structure

**Created:**
- `dashboard/__init__.py` — package marker
- `dashboard/state.py` — `DashboardState` dataclass + `get_ctx()`
- `dashboard/data_pipeline.py` — data load/filter/cache wrappers
- `dashboard/health.py` — journey/campaign health scores
- `dashboard/funnels.py` — funnel analysis
- `dashboard/anomalies.py` — anomaly detection
- `dashboard/lifecycle.py` — lifecycle + stopped-journey + revenue-loss ML + cohort + waterfall
- `dashboard/comparisons_logic.py` — comparison period metrics, uplift, journey comparison
- `dashboard/charts.py` — attribution display helper + re-exports of `utils` viz helpers
- `pages/01_automated_insights.py` … `pages/17_export.py` — 17 page files

**Modified:**
- `app.py` — becomes the thin entrypoint

**Unchanged existing modules reused:** `config.py`, `attribution.py`, `insights_engine.py`, `analysis.py`, `utils.py`, `data_processing.py`, `temporal_intelligence.py`.

### Duplicate reconciliation (local copy in app.py vs existing module)

app.py currently re-implements functions that already exist elsewhere. For each, verify the local copy is functionally equivalent, then delete local + import the module version:

| Local in app.py | Canonical module | Task |
|---|---|---|
| `clean_data` (L138) | `data_processing.clean_data` | Task 2 |
| `export_chart_image` (L44), `style_total_row` (L56), `format_metric` (L82) | `utils.*` | Task 2 |
| `top_campaigns`, `get_top_journeys`, `top_segments`, `channel_analysis`, `time_series_analysis`, `failed_reasons_analysis`, `esp_analysis`, `ab_testing_analysis`, `attribution_analysis` | `analysis.*` | Task 3 |

**Genuinely unique helpers (true extraction into `dashboard/`):** health scores (L467, L768), funnels (L1082, L1146, L1210), anomalies (L1235, L1333, L1431), waterfall (L1455), lifecycle (L1501, L1599), journey/date comparison (L1629, L1701), stopped-journey (L1834, L2035, L2343), cohort (L2391), comparison period math (L2434, L2520, L2552, L2665), `analyze_individual_journey` (L2720).

---

## Task 1: Create `dashboard/` package + `DashboardState` + `get_ctx()`

**Files:**
- Create: `dashboard/__init__.py`
- Create: `dashboard/state.py`
- Test: `tests/test_dashboard_state.py`

**Interfaces:**
- Produces: `DashboardState` dataclass with fields `df, filtered_df, comparison_result, revenue_attribution, conversion_attribution, selected_rev_label, selected_conv_label, date_range, comparison_mode, comparison_result, filter_options, channels, campaign_types, campaigns, segments, journeys, conversion_events`. `set_ctx(ctx) -> None` stores it in `st.session_state["ctx"]`. `get_ctx() -> DashboardState` returns it or gates with `st.info(...)` + `st.stop()`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dashboard_state.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dashboard_state.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'dashboard'`

- [ ] **Step 3: Create the package + module**

```python
# dashboard/__init__.py
```
(empty file)

```python
# dashboard/state.py
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

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dashboard_state.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard/__init__.py dashboard/state.py tests/test_dashboard_state.py
git commit -m "feat: add dashboard package with DashboardState and get_ctx"
```

---

## Task 2: Reconcile duplicated `clean_data` + viz helpers with existing modules

**Files:**
- Modify: `app.py` (delete local `export_chart_image` L44-54, `style_total_row` L56-63, `format_metric` L82-104, `clean_data` L138-~295; add imports)
- Test: `tests/test_clean_data_parity.py`

**Interfaces:**
- Consumes: `data_processing.clean_data`, `utils.format_metric`, `utils.style_total_row`, `utils.export_chart_image`.
- Produces: nothing new; app.py now imports these instead of defining them.

- [ ] **Step 1: Write a parity test proving the module `clean_data` matches app's behavior on a sample frame**

```python
# tests/test_clean_data_parity.py
import pandas as pd
from data_processing import clean_data

def test_clean_data_adds_rates_and_fills():
    raw = pd.DataFrame({
        "Channel": ["Email", "SMS"],
        "Sent": [1000, 500],
        "Delivered": [900, 480],
        "Unique Impressions": [800, 0],
        "Unique Clicks": [80, 10],
        "Unique Conversions": [8, 1],
        "Revenue (SAR)": [100.0, 20.0],
        "Reporting Period Start Date": ["2025-01-01", "2025-01-02"],
        "Reporting Period End Date": ["2025-01-01", "2025-01-02"],
    })
    out = clean_data(raw.copy())
    assert "Delivery Rate" in out.columns
    assert abs(out.loc[0, "Delivery Rate"] - 0.9) < 1e-9
    assert out["Delivered"].notna().all()
```

- [ ] **Step 2: Run test to verify current module behavior**

Run: `python -m pytest tests/test_clean_data_parity.py -v`
Expected: PASS (this pins the canonical `data_processing.clean_data`). If it FAILS, STOP — the module copy differs from app's copy; report the diff before deleting anything.

- [ ] **Step 3: Diff the two `clean_data` implementations before deleting**

Run: `python -c "import inspect, data_processing; print(inspect.getsource(data_processing.clean_data))" > /tmp/mod_clean.txt`
Compare against app.py L138-295 (read the range). They must be functionally equivalent (same columns produced, same rate logic). If app.py's copy has diverged (extra columns like `Campaign Cost`, `AOV`, `Engagement Rate`), **the app.py copy is canonical** — instead copy those additions into `data_processing.clean_data` first, re-run Step 2, then proceed. Document any merge in the commit message.

- [ ] **Step 4: Replace local defs with imports in app.py**

Add to the import block near the top of app.py (after line 22):

```python
from data_processing import clean_data
from utils import format_metric, style_total_row, export_chart_image
```

Delete the local `def export_chart_image`, `def style_total_row`, `def format_metric`, and `def clean_data` blocks from app.py.

- [ ] **Step 5: Import-smoke + run**

Run: `python -c "import ast; ast.parse(open('app.py').read()); print('app.py parses')"`
Expected: `app.py parses`
Run: `python -m pytest tests/ -q`
Expected: all pass.
Then `streamlit run app.py`, upload a known CSV, confirm Overview renders and totals match.

- [ ] **Step 6: Commit**

```bash
git add app.py tests/test_clean_data_parity.py data_processing.py
git commit -m "refactor: use data_processing.clean_data and utils viz helpers in app.py"
```

---

## Task 3: Reconcile duplicated analysis helpers with `analysis.py`

**Files:**
- Modify: `app.py` (delete local `top_campaigns` L303, `get_top_journeys` L320, `top_segments` L327, `channel_analysis` L334, `time_series_analysis` L371, `failed_reasons_analysis` L375, `esp_analysis` L382, `ab_testing_analysis` L414, `attribution_analysis` L458; add import)

**Interfaces:**
- Consumes: `analysis.top_campaigns, get_top_journeys, top_segments, channel_analysis, time_series_analysis, failed_reasons_analysis, esp_analysis, ab_testing_analysis, attribution_analysis`.

- [ ] **Step 1: Diff each local copy against `analysis.py`**

For each of the 9 functions, read the app.py definition and the `analysis.py` definition. Confirm identical signatures and logic. If any app.py copy diverges, port the difference into `analysis.py` first (the app.py copy is canonical), then continue.

- [ ] **Step 2: Add the import to app.py**

After the Task 2 imports add:

```python
from analysis import (
    top_campaigns, get_top_journeys, top_segments, channel_analysis,
    time_series_analysis, failed_reasons_analysis, esp_analysis,
    ab_testing_analysis, attribution_analysis,
)
```

- [ ] **Step 3: Delete the 9 local defs from app.py**

- [ ] **Step 4: Import-smoke + run**

Run: `python -c "import ast; ast.parse(open('app.py').read()); print('ok')"`
Expected: `ok`
Run: `python -m pytest tests/ -q` → all pass.
`streamlit run app.py` → confirm Campaigns, Channels, Segments, A/B Testing, Attribution, Failed Reasons pages still render.

- [ ] **Step 5: Commit**

```bash
git add app.py analysis.py
git commit -m "refactor: use analysis.py helpers in app.py, drop duplicate copies"
```

---

## Task 4: Extract health scores → `dashboard/health.py`

**Files:**
- Create: `dashboard/health.py`
- Modify: `app.py` (move `calculate_journey_health_score` L467-767, `calculate_campaign_health_score` L768-1081; add import)
- Test: `tests/test_health_extract.py`

**Interfaces:**
- Produces: `calculate_journey_health_score(df_journey, all_journeys_df=None) -> dict`, `calculate_campaign_health_score(df_campaign, all_campaigns_df=None) -> dict` (same signatures/returns as current).

- [ ] **Step 1: Copy both functions verbatim into `dashboard/health.py`**

Create `dashboard/health.py` with the module docstring, required imports (`import numpy as np`, `import pandas as pd`), and the two functions copied byte-for-byte from app.py L467-1081. Include any module-level constants they reference (check for references to `CHANNEL_COSTS`, `COLORS`; import from `config` if used).

- [ ] **Step 2: Write an import + smoke test**

```python
# tests/test_health_extract.py
import pandas as pd
from dashboard.health import calculate_journey_health_score, calculate_campaign_health_score

def test_health_functions_importable_and_return_dict():
    df = pd.DataFrame({
        "Journey Name": ["J1", "J1"],
        "Sent": [100, 100], "Delivered": [95, 95],
        "Unique Impressions": [90, 90], "Unique Clicks": [10, 10],
        "Unique Conversions": [2, 2], "Revenue (SAR)": [50.0, 50.0],
        "Delivery Rate": [0.95, 0.95], "CTR": [0.11, 0.11],
        "Conversion Rate": [0.2, 0.2],
    })
    res = calculate_journey_health_score(df, df)
    assert "health_score" in res and "tier" in res
```

- [ ] **Step 3: Run test to verify it passes**

Run: `python -m pytest tests/test_health_extract.py -v`
Expected: PASS. If it fails with a missing name (e.g. a helper only defined later in app.py), add that dependency import to `health.py`.

- [ ] **Step 4: Replace in app.py with import, delete local defs**

Add `from dashboard.health import calculate_journey_health_score, calculate_campaign_health_score` to the import block; delete the two local defs.

- [ ] **Step 5: Import-smoke + run**

Run: `python -c "import ast; ast.parse(open('app.py').read()); print('ok')"` → `ok`
Run: `python -m pytest tests/ -q` → pass.
`streamlit run app.py` → Journeys page health dashboard + Campaigns health dashboard render with same scores.

- [ ] **Step 6: Commit**

```bash
git add dashboard/health.py app.py tests/test_health_extract.py
git commit -m "refactor: extract health-score functions to dashboard/health.py"
```

---

## Task 5: Extract funnels → `dashboard/funnels.py`

**Files:**
- Create: `dashboard/funnels.py`
- Modify: `app.py` (move `analyze_campaign_funnel` L1082, `analyze_journey_funnel` L1146, `calculate_funnel_conversion_rates` L1210; add import)
- Test: `tests/test_funnels_extract.py`

**Interfaces:**
- Produces: `analyze_campaign_funnel(df_campaign)`, `analyze_journey_funnel(df_journey)`, `calculate_funnel_conversion_rates(funnel_data)` — same signatures.

- [ ] **Step 1:** Copy the three functions verbatim into `dashboard/funnels.py` with needed imports (`import pandas as pd`, `import numpy as np`).
- [ ] **Step 2:** Write import-smoke test `tests/test_funnels_extract.py`:

```python
from dashboard.funnels import (
    analyze_campaign_funnel, analyze_journey_funnel, calculate_funnel_conversion_rates,
)
def test_funnels_importable():
    assert callable(analyze_campaign_funnel)
    assert callable(calculate_funnel_conversion_rates)
```

- [ ] **Step 3:** Run: `python -m pytest tests/test_funnels_extract.py -v` → PASS.
- [ ] **Step 4:** Add `from dashboard.funnels import analyze_campaign_funnel, analyze_journey_funnel, calculate_funnel_conversion_rates` to app.py; delete local defs.
- [ ] **Step 5:** `python -c "import ast; ast.parse(open('app.py').read()); print('ok')"` → ok; `python -m pytest tests/ -q` → pass; `streamlit run app.py` → Conversion Pipeline / funnel sections render.
- [ ] **Step 6:** Commit:

```bash
git add dashboard/funnels.py app.py tests/test_funnels_extract.py
git commit -m "refactor: extract funnel analysis to dashboard/funnels.py"
```

---

## Task 6: Extract anomalies → `dashboard/anomalies.py`

**Files:**
- Create: `dashboard/anomalies.py`
- Modify: `app.py` (move `detect_campaign_anomalies` L1235, `detect_journey_anomalies` L1333, `get_anomaly_recommendation` L1431; add import)
- Test: `tests/test_anomalies_extract.py`

**Interfaces:**
- Produces: `detect_campaign_anomalies(df, lookback_days=30)`, `detect_journey_anomalies(df, lookback_days=30)`, `get_anomaly_recommendation(metric_name, pct_change)` — same signatures.

- [ ] **Step 1:** Copy the three functions verbatim into `dashboard/anomalies.py` with imports (`import pandas as pd`, `import numpy as np`).
- [ ] **Step 2:** Write `tests/test_anomalies_extract.py`:

```python
from dashboard.anomalies import (
    detect_campaign_anomalies, detect_journey_anomalies, get_anomaly_recommendation,
)
def test_anomaly_recommendation_returns_str():
    assert isinstance(get_anomaly_recommendation("CTR", -25.0), str)
```

- [ ] **Step 3:** Run: `python -m pytest tests/test_anomalies_extract.py -v` → PASS.
- [ ] **Step 4:** Add import to app.py, delete local defs.
- [ ] **Step 5:** `ast.parse` ok; `pytest tests/ -q` pass; `streamlit run app.py` → anomaly callouts render.
- [ ] **Step 6:** Commit:

```bash
git add dashboard/anomalies.py app.py tests/test_anomalies_extract.py
git commit -m "refactor: extract anomaly detection to dashboard/anomalies.py"
```

---

## Task 7: Extract lifecycle + stopped-journey + cohort + waterfall → `dashboard/lifecycle.py`

**Files:**
- Create: `dashboard/lifecycle.py`
- Modify: `app.py` (move `create_revenue_attribution_waterfall` L1455, `analyze_journey_lifecycle` L1501, `get_lifecycle_recommendation` L1599, `analyze_stopped_journeys` L1834, `estimate_revenue_loss_ml` L2035, `generate_stopped_journey_recommendations` L2343, `create_cohort_analysis` L2391; add import)
- Test: `tests/test_lifecycle_extract.py`

**Interfaces:**
- Produces: `create_revenue_attribution_waterfall(df_journey)`, `analyze_journey_lifecycle(df)`, `get_lifecycle_recommendation(maturity_stage, consistency_score, growth_trend, efficiency_score)`, `analyze_stopped_journeys(df, stopped_threshold_days=3, lookback_period=90, confidence_level=0.95)`, `estimate_revenue_loss_ml(journey_data, stopped_periods, confidence_level=0.95)`, `generate_stopped_journey_recommendations(journey_data, stopped_periods, revenue_loss_estimate)`, `create_cohort_analysis(df, cohort_period='week')` — same signatures.

- [ ] **Step 1:** Copy the seven functions verbatim into `dashboard/lifecycle.py`. Include ML imports these use: `from sklearn.model_selection import train_test_split`, `from sklearn.ensemble import RandomForestRegressor`, `from sklearn.metrics import mean_squared_error`, plus `import numpy as np`, `import pandas as pd`, `import plotly.graph_objects as go`. Check whether `estimate_revenue_loss_ml` references module-level names defined elsewhere in app.py; import them.
- [ ] **Step 2:** Write `tests/test_lifecycle_extract.py`:

```python
from dashboard.lifecycle import (
    analyze_journey_lifecycle, analyze_stopped_journeys,
    estimate_revenue_loss_ml, create_cohort_analysis,
    create_revenue_attribution_waterfall, get_lifecycle_recommendation,
    generate_stopped_journey_recommendations,
)
def test_lifecycle_importable():
    assert callable(analyze_stopped_journeys)
    assert callable(estimate_revenue_loss_ml)
```

- [ ] **Step 3:** Run: `python -m pytest tests/test_lifecycle_extract.py -v` → PASS. Also run the existing stopped-journey tests: `python -m pytest tests/ -k stopped -q` and `python -m pytest test_stopped_detection.py -q` → pass. If those import the functions from `app`, update their imports to `dashboard.lifecycle` in this step.
- [ ] **Step 4:** Add import to app.py, delete local defs.
- [ ] **Step 5:** `ast.parse` ok; `pytest tests/ -q` pass; `streamlit run app.py` → Stopped Journey Analysis section renders with same revenue-loss numbers.
- [ ] **Step 6:** Commit:

```bash
git add dashboard/lifecycle.py app.py tests/test_lifecycle_extract.py test_stopped_detection.py
git commit -m "refactor: extract lifecycle/stopped-journey/cohort logic to dashboard/lifecycle.py"
```

---

## Task 8: Extract comparison math → `dashboard/comparisons_logic.py`

**Files:**
- Create: `dashboard/comparisons_logic.py`
- Modify: `app.py` (move `create_journey_comparison_analysis` L1629, `create_custom_date_range_comparison` L1701, `calculate_comparison_periods` L2434, `calculate_uplift_significance` L2520, `calculate_period_metrics` L2552, `calculate_metric_changes` L2665; add import)
- Test: `tests/test_comparisons_extract.py`

**Interfaces:**
- Produces: `create_journey_comparison_analysis(df, journey1, journey2)`, `create_custom_date_range_comparison(df, date_range_1, date_range_2, journeys_filter=None)`, `calculate_comparison_periods(df, current_date_range, comparison_mode, custom_comparison_range=None)`, `calculate_uplift_significance(test_conversions, test_total, control_conversions, control_total)`, `calculate_period_metrics(period_data, period_days, conversion_attribution='Total')`, `calculate_metric_changes(current_metrics, comparison_metrics)` — same signatures.

- [ ] **Step 1:** Copy the six functions verbatim into `dashboard/comparisons_logic.py` with imports (`import pandas as pd`, `import numpy as np`; `from scipy import stats` only if `calculate_uplift_significance` uses it — check).
- [ ] **Step 2:** Write `tests/test_comparisons_extract.py`:

```python
from dashboard.comparisons_logic import (
    calculate_comparison_periods, calculate_period_metrics,
    calculate_metric_changes, calculate_uplift_significance,
    create_journey_comparison_analysis, create_custom_date_range_comparison,
)
def test_metric_changes_shape():
    cur = {"revenue": 100.0}
    prev = {"revenue": 50.0}
    out = calculate_metric_changes(cur, prev)
    assert isinstance(out, dict)
```

- [ ] **Step 3:** Run: `python -m pytest tests/test_comparisons_extract.py -v` → PASS. If `calculate_metric_changes` needs more keys, mirror the keys the function reads (read its body first).
- [ ] **Step 4:** Add import to app.py, delete local defs.
- [ ] **Step 5:** `ast.parse` ok; `pytest tests/ -q` pass; `streamlit run app.py` → Comparisons page + Period Comparison summary render.
- [ ] **Step 6:** Commit:

```bash
git add dashboard/comparisons_logic.py app.py tests/test_comparisons_extract.py
git commit -m "refactor: extract comparison math to dashboard/comparisons_logic.py"
```

---

## Task 9: Create `dashboard/charts.py` + `dashboard/data_pipeline.py` and move remaining shared helpers

**Files:**
- Create: `dashboard/charts.py`
- Create: `dashboard/data_pipeline.py`
- Modify: `app.py` (move `analyze_individual_journey` L2720 into `dashboard/lifecycle.py` OR `charts.py` as appropriate; keep the `@st.cache_data` wrappers `load_and_clean_data`, `apply_filters_and_attribution`, `cached_executive_summary`, `cached_journey_health_scores`, `cached_journey_lifecycle`, `cached_comparison` in `data_pipeline.py`)
- Test: `tests/test_data_pipeline.py`

**Interfaces:**
- Produces (`dashboard/charts.py`): re-export `format_metric, style_total_row, export_chart_image` from `utils`; `attribution_display(ctx, col_name)`.
- Produces (`dashboard/data_pipeline.py`): `load_and_clean_data(uploaded_file)`, `apply_filters_and_attribution(df, revenue_attribution, conversion_attribution, date_range, channels, campaign_types, campaigns, segments, journeys, conversion_events=None)`, `cached_executive_summary(filtered_df)`, `cached_journey_health_scores(filtered_df)`, `cached_journey_lifecycle(filtered_df)`, `cached_comparison(...)` — all with `@st.cache_data`, **signatures identical to current app.py**.

- [ ] **Step 1:** Create `dashboard/charts.py`:

```python
"""Shared presentation helpers for dashboard pages."""
from utils import format_metric, style_total_row, export_chart_image  # noqa: F401
from attribution import get_attribution_display_label


def attribution_display(ctx, col_name):
    """Map 'Selected Revenue/Conversions' column names to the user-selected label."""
    return get_attribution_display_label(
        col_name, ctx.revenue_attribution, ctx.conversion_attribution
    )
```

- [ ] **Step 2:** Create `dashboard/data_pipeline.py` and move the six cached functions from app.py (L2889-3006 region) verbatim, preserving `@st.cache_data` and signatures. They call `clean_data`, `apply_attribution`, `apply_dimension_filters`, `generate_executive_summary`, `calculate_journey_health_score`, `analyze_journey_lifecycle`, `calculate_comparison_periods` — import each from its now-canonical module (`data_processing`, `attribution`, `insights_engine`, `dashboard.health`, `dashboard.lifecycle`, `dashboard.comparisons_logic`).

- [ ] **Step 3:** Write `tests/test_data_pipeline.py`:

```python
from dashboard.data_pipeline import (
    load_and_clean_data, apply_filters_and_attribution,
    cached_executive_summary, cached_journey_health_scores,
    cached_journey_lifecycle, cached_comparison,
)
def test_pipeline_callables():
    assert callable(load_and_clean_data)
    assert callable(apply_filters_and_attribution)
    assert callable(cached_comparison)
```

- [ ] **Step 4:** Run: `python -m pytest tests/test_data_pipeline.py -v` → PASS.
- [ ] **Step 5:** In app.py, replace the inline cached-function defs with `from dashboard.data_pipeline import (...)` and `from dashboard.charts import attribution_display, format_metric, style_total_row, export_chart_image`. Replace the `_attribution_display` closure calls with `attribution_display(ctx, ...)` where `ctx` is available (post-Task 10) — for now keep the local `_attribution_display` closure pointing at `attribution_display` with the current attribution vars.
- [ ] **Step 6:** `ast.parse` ok; `pytest tests/ -q` pass; `streamlit run app.py` → full walkthrough of all pages, numbers unchanged.
- [ ] **Step 7:** Commit:

```bash
git add dashboard/charts.py dashboard/data_pipeline.py app.py tests/test_data_pipeline.py
git commit -m "refactor: extract cached data pipeline and chart helpers to dashboard package"
```

---

## Task 10: Convert app.py prelude to build `DashboardState` + `st.navigation` scaffold (pages still inline)

**Files:**
- Modify: `app.py`

**Interfaces:**
- Consumes: `dashboard.state.DashboardState, set_ctx`.
- Produces: after this task, `st.session_state["ctx"]` is populated whenever a CSV is loaded; the `if page ==` chain temporarily still runs but reads `ctx` fields.

- [ ] **Step 1:** After the prelude computes `filtered_df` and `comparison_result` (around L3077-3091), build and store the state:

```python
from dashboard.state import DashboardState, set_ctx

set_ctx(DashboardState(
    df=df, filtered_df=filtered_df, comparison_result=comparison_result,
    revenue_attribution=revenue_attribution,
    conversion_attribution=conversion_attribution,
    selected_rev_label=selected_rev_label, selected_conv_label=selected_conv_label,
    date_range=date_range, comparison_mode=comparison_mode,
    filter_options=_opts,
    channels=channels, campaign_types=campaign_types, campaigns=campaigns,
    segments=segments, journeys=journeys, conversion_events=conversion_events,
))
```

- [ ] **Step 2:** Leave the `if page == ...` chain intact for now (still driven by the sidebar selectbox). This task only adds state population.
- [ ] **Step 3:** `ast.parse` ok; `pytest tests/ -q` pass; `streamlit run app.py` → every page still works exactly as before (the selectbox nav is unchanged).
- [ ] **Step 4:** Commit:

```bash
git add app.py
git commit -m "refactor: populate DashboardState in app.py prelude"
```

---

## Tasks 11–27: Split each page branch into a `pages/NN_*.py` file

**Pattern (applies to every page task below):** each is the same 6-step cycle. `PAGE_HEADER_SNIPPET` at the top of every new page file is:

```python
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go

from dashboard.state import get_ctx
from dashboard.charts import format_metric, style_total_row, export_chart_image, attribution_display
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

def _attribution_display(col_name):
    return attribution_display(ctx, col_name)
```

Add only the page-specific imports each branch actually uses (import-narrow later; over-importing is fine for correctness). Then paste the branch body **de-indented by 8 spaces** (from `if page ==` block level to module level).

Each page task's steps:
1. Create `pages/NN_name.py` with the header snippet + the de-indented branch body.
2. Register it in the `st.navigation` list in app.py (added in Task 28) — for now, temporarily test by pointing the selectbox at it OR defer runtime test to Task 28. To keep each page independently testable, run: `python -c "import ast; ast.parse(open('pages/NN_name.py').read()); print('ok')"`.
3. Delete the corresponding `elif page == ...` branch body from app.py.
4. `ast.parse` app.py → ok.
5. Commit.

### Task 11: `pages/01_automated_insights.py`
Source branch: app.py `if page == "🎯 Automated Insights":` L3094-3440. Note this branch uses `st.session_state['forecast_result']` — keep those reads/writes as-is (session_state is shared across pages). Imports needed: `from insights_engine import generate_narrative_insights, predict_revenue_forecast, generate_top_actions, generate_executive_summary`; `from dashboard.lifecycle import analyze_individual_journey` if referenced.
Commit: `refactor: extract Automated Insights page`

### Task 12: `pages/02_overview.py`
Source: `elif page == "Overview":` L3441-4293. Commit: `refactor: extract Overview page`

### Task 13: `pages/03_marketing_actions.py`
Source: `elif page == "📈 Marketing Actions":` L4294-4848. Commit: `refactor: extract Marketing Actions page`

### Task 14: `pages/04_campaigns.py`
Source: `elif page == "Campaigns":` L4849-5963. Uses `from analysis import top_campaigns`; `from dashboard.health import calculate_campaign_health_score`; `from dashboard.funnels import analyze_campaign_funnel, calculate_funnel_conversion_rates`; `from dashboard.anomalies import detect_campaign_anomalies, get_anomaly_recommendation`. Commit: `refactor: extract Campaigns page`

### Task 15: `pages/05_journeys.py`
Source: Journeys branch **only the Journey Analysis portion** L5964-6775 (up to just before "Advanced Business Intelligence Analytics" header at L6776). Uses `from dashboard.health import calculate_journey_health_score`; `from dashboard.funnels import analyze_journey_funnel`; `from dashboard.anomalies import detect_journey_anomalies`; `from dashboard.lifecycle import analyze_journey_lifecycle, get_lifecycle_recommendation, create_revenue_attribution_waterfall, analyze_individual_journey`. **Care:** this branch is one `elif`; the split at L6776/L7358 into pages 06/07 means the page-selection logic must route those sub-sections to their own nav entries. Read L5964-7588 fully before splitting to place the boundaries at the `st.header` lines (L6776 Advanced BI, L7358 Stopped Journeys). Commit: `refactor: extract Journeys page`

### Task 16: `pages/06_advanced_bi.py`
Source: "Advanced Business Intelligence Analytics" block L6776-7357. Uses `from dashboard.comparisons_logic import create_journey_comparison_analysis, create_custom_date_range_comparison, calculate_period_metrics`; `from dashboard.lifecycle import create_cohort_analysis`. Commit: `refactor: extract Advanced BI page`

### Task 17: `pages/07_stopped_journeys.py`
Source: "🚨 Stopped Journey Analysis & Revenue Loss Estimation" block L7358-7588. Uses `from dashboard.lifecycle import analyze_stopped_journeys, estimate_revenue_loss_ml, generate_stopped_journey_recommendations`. Commit: `refactor: extract Stopped Journeys page`

### Task 18: `pages/08_segments.py`
Source: `elif page == "Segments":` L7589-7625. Uses `from analysis import top_segments`. Commit: `refactor: extract Segments page`

### Task 19: `pages/09_channels.py`
Source: `elif page == "Channels":` L7626-8204. Uses `from analysis import channel_analysis`. Commit: `refactor: extract Channels page`

### Task 20: `pages/10_time_series.py`
Source: `elif page == "Time Series":` L8205-8227. Uses `from analysis import time_series_analysis`. Commit: `refactor: extract Time Series page`

### Task 21: `pages/11_correlations.py`
Source: `elif page == "Correlations":` L8228-8268. Commit: `refactor: extract Correlations page`

### Task 22: `pages/12_ab_testing.py`
Source: `elif page == "A/B Testing":` L8269-8279. Uses `from analysis import ab_testing_analysis`. Commit: `refactor: extract A/B Testing page`

### Task 23: `pages/13_attribution.py`
Source: `elif page == "Attribution":` L8280-8292. Uses `from analysis import attribution_analysis`. Commit: `refactor: extract Attribution page`

### Task 24: `pages/14_failed_reasons.py`
Source: `elif page == "Failed Reasons":` L8293-8328. Uses `from analysis import failed_reasons_analysis, esp_analysis`. Commit: `refactor: extract Failed Reasons page`

### Task 25: `pages/15_comparisons.py`
Source: `elif page == "Comparisons":` L8361-8766. Uses `from dashboard.comparisons_logic import calculate_comparison_periods, calculate_period_metrics, calculate_metric_changes, calculate_uplift_significance`. Commit: `refactor: extract Comparisons page`

### Task 26: `pages/16_ai_insights.py`
Source: `elif page == "AI Insights":` L8767-end. Uses `from insights_engine import ...` and `from temporal_intelligence import ...` as referenced. Commit: `refactor: extract AI Insights page`

### Task 27: `pages/17_export.py`
Source: `elif page == "Export":` L8329-8360. Commit: `refactor: extract Export page`

---

## Task 28: Wire `st.navigation`, delete dead routing, final verification

**Files:**
- Modify: `app.py` (delete the `page = st.sidebar.selectbox(...)` nav L116-133 and the now-empty `if/elif page ==` chain; add `st.navigation`)

**Interfaces:**
- Consumes: all 17 `pages/*.py` files.

- [ ] **Step 1:** Remove the old `page = st.sidebar.selectbox("Navigate to", [...])` block (L116-133).
- [ ] **Step 2:** At the **end** of the `if uploaded_file is not None:` block (after `set_ctx(...)`), add navigation. Because pages must gate before upload too, define nav at module level but only pages render via `get_ctx()`:

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

**Important:** The upload widget and sidebar filters must stay in `app.py` *above* `st.navigation().run()` so they render on every page (entrypoint pattern per Streamlit docs). If upload/filters currently sit inside `if uploaded_file is not None:`, restructure so the upload widget + `st.navigation().run()` always run, and the filter sidebar + `set_ctx()` run only when a file is present. Pages call `get_ctx()` which gates when no file is loaded.

- [ ] **Step 3:** Verify no `elif page ==` / `if page ==` references remain: `grep -n "page ==" app.py` → no output.
- [ ] **Step 4:** `python -c "import ast; ast.parse(open('app.py').read()); print('ok')"` → ok.
- [ ] **Step 5:** `python -m pytest tests/ -q` → all pass; run root-level tests too: `python -m pytest test_insights_engine.py test_stopped_detection.py -q` → pass.
- [ ] **Step 6:** `streamlit run app.py` → full manual walkthrough: upload CSV, visit **all 17 pages** via the new nav, confirm each renders and key numbers match the pre-refactor baseline. Confirm the "upload first" gate shows before a CSV is loaded.
- [ ] **Step 7:** Check final app.py size: `wc -l app.py` → should be a few hundred lines.
- [ ] **Step 8:** Commit:

```bash
git add app.py
git commit -m "refactor: replace selectbox routing with st.navigation multipage app"
```

---

## Self-Review Notes

- **Spec coverage:** entrypoint (Tasks 9,10,28) ✓; `dashboard/state.py` (Task 1) ✓; data_pipeline (Task 9) ✓; health/funnels/anomalies/lifecycle/comparisons_logic/charts (Tasks 4-9) ✓; 17 page files (Tasks 11-27) ✓; gate every page (Task 1 `get_ctx`, header snippet) ✓; migration order matches spec (logic first, then state, then pages) ✓; verification via run + import-smoke ✓; cross-branch `session_state` risk addressed (only `forecast_result`, kept intact — Task 11) ✓.
- **Duplicate reconciliation** (not in original spec but discovered): Tasks 2-3 handle app.py's inline copies of `clean_data`/`utils`/`analysis` functions — delete-and-import with a parity check. This is within "absorb the extracted helpers" scope.
- **Line numbers** are from the pre-refactor app.py and **shift as tasks delete code** — each task re-locates its target by function name / `st.header` string, not by absolute line. Implementers must grep for the function/branch, not trust the L-numbers blindly.
