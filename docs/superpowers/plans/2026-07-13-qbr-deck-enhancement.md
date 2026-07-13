# QBR Deck Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Grow the WebEngage client review deck (`slides_export.build_deck` today) from 10 generic slides to an 18-ish-slide analyst-grade QBR deck — QoQ comparisons, per-channel status cards, control-group uplift, ESP/deliverability, attribution, and dollar-quantified recommendations — reusing analysis code that already exists in this repo.

**Architecture:** Split the current monolithic `slides_export.py` into a primitives/toolkit module (`slides_export.py` — theme, shapes, text, tables, charts, font embedding) and a content module (`slides_deck_content.py` — every `add_slide_*` function plus the pure-data helpers that compute what goes on each slide, and `build_deck()` itself). The content module is the only one that imports `analysis.py`, `insights_engine.py`, `dashboard/comparisons_logic.py`, and `slides_narrative.py`; the primitives module has no dependency on any of those, so there is no circular import. `pages/13_export.py` calls `slides_deck_content.build_deck(...)`, passing the dashboard's existing `ctx.comparison_result` and `ctx.conversion_attribution` through.

**Tech Stack:** python-pptx, plotly/kaleido (existing), pandas/numpy, pytest. No new dependencies.

## Global Constraints

- Never invent numbers: every figure on every slide must trace to a column in the input DataFrame or a value returned by `analysis.py` / `insights_engine.py` / `dashboard/comparisons_logic.py`.
- Conditional slides (data not always present in every client's CSV) must degrade silently — skip the slide, never render a broken/empty one. This mirrors the existing `_put_chart` try/except pattern in `slides_export.py`.
- `slides_export.build_deck` is being *removed* (moved to `slides_deck_content.build_deck`) — every caller and every test that references `slides_export.build_deck` must be updated in the same task that moves it (Task 1), so the test suite is never red between tasks.
- Repo `.gitignore` excludes `*.md`; this plan file and the spec were committed with `git add -f` — no action needed here, just don't expect `git add -A` to pick up future `.md` edits automatically.
- Run the full test file after every task with `python -m pytest tests/test_build_deck.py tests/test_slides_helpers.py -v` from the repo root.

---

### Task 1: Extract slide-content module (pure refactor, no behavior change)

**Files:**
- Modify: `slides_export.py` (remove lines 240–411: the `insights_engine`/`analysis`/`slides_narrative` imports, `_header`... no — `_header`/`_put_chart` stay; remove only `add_slide_title` through `build_deck`, i.e. current lines 267–411, plus the three import lines at 240–243)
- Create: `slides_deck_content.py`
- Modify: `pages/13_export.py:8,35`
- Modify: `tests/test_build_deck.py:1,5`

**Interfaces:**
- Produces: `slides_deck_content.build_deck(df, client_name="", period_label=None, comparison_result=None, conversion_attribution="Total") -> bytes` — the same signature `slides_export.build_deck` had, plus two new optional kwargs consumed starting in Task 14/16 (accepted now, unused until then).
- Consumes from `slides_export.py`: `new_deck, blank_slide, rect, text, stat_tile, styled_table, insight_box, recommendation_strip, add_morph, _header, _put_chart, journey_funnel_stages, chart_trend, chart_channels, chart_journey_sankey, embed_fonts, BRAND, BRAND_D, TBL_HDR, INK, MUTED, LINE, WHITE, INSIGHT, GREEN, RED, PILL_LBL, F_REG, F_MED, F_BOLD`.

- [ ] **Step 1: Create `slides_deck_content.py` with the moved content**

```python
"""Slide-builder functions and the QBR-deck orchestrator. Depends on
slides_export.py for drawing primitives and on analysis/insights_engine/
comparisons_logic for the numbers each slide shows."""
import io

from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE

from slides_export import (
    new_deck, blank_slide, rect, text, stat_tile, styled_table, insight_box,
    recommendation_strip, add_morph, _header, _put_chart, journey_funnel_stages,
    chart_trend, chart_channels, chart_journey_sankey, embed_fonts,
    BRAND, BRAND_D, TBL_HDR, INK, MUTED, LINE, WHITE, INSIGHT, GREEN, RED,
    PILL_LBL, F_REG, F_MED, F_BOLD,
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


def add_slide_exec_summary(prs, summary, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "EXECUTIVE SUMMARY", "Performance at a Glance", period_label)
    m = summary.get("headline_metrics", {})
    tiles = [
        ("REVENUE", f"SAR {m.get('total_revenue', 0):,.0f}"),
        ("CONVERSIONS", f"{m.get('total_conversions', 0):,.0f}"),
        ("DELIVERY RATE", f"{m.get('avg_delivery_rate', 0):.1%}"),
        ("CONV. RATE", f"{m.get('avg_conversion_rate', 0):.1%}"),
    ]
    tx, tw, gap = 0.55, 2.92, 0.15
    for i, (lab, val) in enumerate(tiles):
        stat_tile(slide, tx + i * (tw + gap), 1.52, tw, 1.18, lab, val, "", MUTED)
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


def build_deck(df, client_name="", period_label=None, comparison_result=None, conversion_attribution="Total") -> bytes:
    summary = generate_executive_summary(df)
    period_label = period_label or summary.get("period")
    actions = summary.get("top_actions") or generate_top_actions(df, max_actions=5)
    ni = summary.get("narrative_insights", {}) or {}
    prs = new_deck()
    add_slide_title(prs, client_name, period_label)
    add_slide_exec_summary(prs, summary, period_label)
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
    buf = io.BytesIO()
    prs.save(buf)
    return embed_fonts(buf.getvalue())
```

- [ ] **Step 2: Remove the moved code from `slides_export.py`**

Delete current lines 240–411 of `slides_export.py` (the block starting at
`from insights_engine import generate_executive_summary, generate_top_actions`
and ending at the `return embed_fonts(buf.getvalue())` of the old `build_deck`).
Everything before line 240 (theme, primitives, chart builders through
`chart_journey_sankey`) and everything from the old line 414 onward
(`_FONT_DIR` through `embed_fonts`) stays untouched and unmoved.

- [ ] **Step 3: Update `pages/13_export.py`**

```python
# line 8, was: import slides_export
import slides_deck_content
```

```python
# inside the button handler, was: slides_export.build_deck(filtered_df, client_name=client_name)
st.session_state["deck_bytes"] = slides_deck_content.build_deck(filtered_df, client_name=client_name)
```

- [ ] **Step 4: Update `tests/test_build_deck.py` imports**

```python
# was: import slides_export as sx
import slides_deck_content as sx
```

Also add the enriched fixture used by later tasks (Tasks 7, 10, 12, 13, 14,
16 all reuse this — defining it now keeps those tasks' diffs to "add one
test function"):

```python
def _full_df():
    n = 6
    return pd.DataFrame({
        "Campaign Name": [f"C{i}" for i in range(n)],
        "Journey Name": ["Cart Recovery"] * 3 + ["Winback"] * 3,
        "Segment Name": ["VIP", "VIP", "New", "New", "Churn Risk", "Churn Risk"],
        "Channel": ["Email", "Web Push", "SMS"] * 2,
        "ESP/SSP/WSP/RSP name": ["SES", "FCM", "Twilio"] * 2,
        "Reporting Period Start Date": pd.to_datetime(
            ["2026-06-01", "2026-06-02", "2026-06-03"] * 2),
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
```

- [ ] **Step 5: Run the full test suite to verify the refactor is behavior-preserving**

Run: `python -m pytest tests/test_build_deck.py tests/test_slides_helpers.py -v`
Expected: All existing tests PASS unchanged (still 10 slides — no slide
content changed in this task, only its file location).

- [ ] **Step 6: Commit**

```bash
git add slides_export.py slides_deck_content.py pages/13_export.py tests/test_build_deck.py
git commit -m "refactor: split slide-builder functions into slides_deck_content.py"
```

---

### Task 2: Add shared QBR primitives to `slides_export.py`

**Files:**
- Modify: `slides_export.py` (add near the `GREEN`/`RED` theme constants and near `add_morph`)
- Test: `tests/test_slides_helpers.py`

**Interfaces:**
- Produces: `AMBER: RGBColor`, `BENCHMARK_DELIVERY_RATE: float`, `BENCHMARK_ROAS_GOOD: float`, `BENCHMARK_ROAS_OK: float`, `status_pill(slide, x, y, label, color) -> float` (returns pill width), `qoq_delta_text(change: dict, suffix: str = "") -> tuple[str, RGBColor]`, `channel_status(sent: float) -> tuple[str, RGBColor]`.
- Consumes: `insights_engine.CHANNEL_MIN_SENT` (existing constant, already used by `insights_engine.py`'s own per-channel alert logic — see `insights_engine.py:21`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_slides_helpers.py`:

```python
def test_channel_status_thresholds():
    assert sx.channel_status(0)[0] == "INACTIVE"
    assert sx.channel_status(50)[0] == "LOW VOLUME"
    assert sx.channel_status(500)[0] == "ACTIVE"


def test_qoq_delta_text_direction():
    up_text, up_color = sx.qoq_delta_text({"pct_change": 12.5}, "prior period")
    assert "12.5%" in up_text and up_color == sx.GREEN
    down_text, down_color = sx.qoq_delta_text({"pct_change": -8.0}, "prior period")
    assert "-8.0%" in down_text and down_color == sx.RED


def test_status_pill_draws_without_error():
    prs = sx.new_deck()
    slide = sx.blank_slide(prs)
    width = sx.status_pill(slide, 0.5, 0.5, "ACTIVE", sx.GREEN)
    assert width > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_slides_helpers.py -v`
Expected: FAIL with `AttributeError: module 'slides_export' has no attribute 'channel_status'` (and similarly for the other two).

- [ ] **Step 3: Implement in `slides_export.py`**

Add after the existing `PILL_LBL = RGBColor(...)` theme-constants block (current
line 31):

```python
AMBER   = RGBColor(0xC9, 0x7A, 0x1E)

# Mirrors insights_engine.detect_performance_alerts (delivery <0.85 is
# critical, target is >0.90) and the ROAS tiering already used in
# pages/14_comparisons.py's channel-efficiency display.
BENCHMARK_DELIVERY_RATE = 0.90
BENCHMARK_ROAS_GOOD = 4.0
BENCHMARK_ROAS_OK = 2.0
```

Add after `add_morph` (current line 148):

```python
from insights_engine import CHANNEL_MIN_SENT


def channel_status(sent):
    """Classify a channel's activity level for the QBR deck's channel cards.
    Mirrors the volume floor insights_engine.py already uses to decide
    whether a channel is eligible for its own alerts/opportunities."""
    if sent <= 0:
        return "INACTIVE", MUTED
    if sent < CHANNEL_MIN_SENT:
        return "LOW VOLUME", AMBER
    return "ACTIVE", GREEN


def qoq_delta_text(change, suffix=""):
    """change: one entry from dashboard.comparisons_logic.calculate_metric_changes()
    (a dict with a 'pct_change' key). Returns (label text, RGBColor)."""
    pct = change["pct_change"]
    arrow = "▲" if pct > 0 else ("▼" if pct < 0 else "→")
    color = GREEN if pct > 0 else (RED if pct < 0 else MUTED)
    label = f"vs {suffix}" if suffix else ""
    return f"{arrow} {pct:+.1f}% {label}".strip(), color


def status_pill(slide, x, y, label, color):
    w = 0.14 + 0.09 * len(label)
    rect(slide, x, y, w, 0.26, fill=color, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
    text(slide, x, y + 0.02, w, 0.22, (label, 8.5, WHITE, F_MED, True, 0.6),
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    return w
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_slides_helpers.py -v`
Expected: PASS (5 passed — 2 pre-existing + 3 new).

- [ ] **Step 5: Commit**

```bash
git add slides_export.py tests/test_slides_helpers.py
git commit -m "feat: add channel status, QoQ delta, and status-pill primitives"
```

---

### Task 3: Add Agenda and Closing slides

**Files:**
- Modify: `slides_deck_content.py` (add two functions, wire into `build_deck`)
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Produces: `add_slide_agenda(prs, period_label) -> None`, `add_slide_closing(prs) -> None`.
- Consumes: `slides_export.MSO_SHAPE` is already imported at module top (Task 1).

- [ ] **Step 1: Write the failing test**

```python
def test_build_deck_has_14_slides_minimal_fixture():
    data = sx.build_deck(_df(), client_name="Acme Co", period_label="Jun 2026")
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 14
```

Replace the old `test_build_deck_has_10_slides_with_client_name` assertion
`assert len(prs.slides) == 10` with `assert len(prs.slides) == 14` (this
count is reached incrementally as Tasks 3–9 land; for this task alone the
count after adding agenda+closing is 12 — write the test for 12 now and it
will be bumped again in Tasks 4 and 9):

```python
def test_build_deck_has_10_slides_with_client_name():
    data = sx.build_deck(_df(), client_name="Acme Co", period_label="Jun 2026")
    assert isinstance(data, (bytes, bytearray)) and len(data) > 5000
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 12
    texts = [sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame]
    assert any("Acme Co" in t for t in texts)
```

Delete the `test_build_deck_has_14_slides_minimal_fixture` stub added above —
it was scaffolding to show the target; the real running total lives in
`test_build_deck_has_10_slides_with_client_name` and gets bumped in place by
each later task (Tasks 4 and 9 change `== 12` to `== 13` then `== 14`).

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: FAIL — `assert 10 == 12`.

- [ ] **Step 3: Implement**

Add to `slides_deck_content.py`, after `add_slide_title`:

```python
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
```

Add at the end of `slides_deck_content.py`, before `build_deck`:

```python
def add_slide_closing(prs):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=BRAND)
    text(slide, 0.9, 3.1, 11.5, 1.3, ("Measure. Analyze. Optimize.", 34, WHITE, F_BOLD, True, None))
    add_morph(slide)
```

In `build_deck`, insert `add_slide_agenda(prs, period_label)` right after
`add_slide_title(prs, client_name, period_label)`, and add
`add_slide_closing(prs)` as the last call before `buf = io.BytesIO()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add agenda and closing slides to QBR deck"
```

---

### Task 4: Add Monthly KPI table slide

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Produces: `monthly_kpi_rows(df) -> list[tuple]`, `add_slide_monthly_kpi(prs, df, period_label) -> None`.
- Consumes: `pandas as pd` (new import needed in `slides_deck_content.py`).

- [ ] **Step 1: Write the failing tests**

```python
def test_monthly_kpi_rows_includes_total_row():
    rows = sx.monthly_kpi_rows(_df())
    assert rows[-1][0] == "Total"
    assert len(rows) == 2  # 1 month of data (all June) + Total


def test_build_deck_slide_count_after_monthly_kpi():
    data = sx.build_deck(_df(), client_name="Acme Co", period_label="Jun 2026")
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 13
```

Update `test_build_deck_has_10_slides_with_client_name`'s assertion from
`== 12` to `== 13`, and delete the now-redundant
`test_build_deck_slide_count_after_monthly_kpi` (same pattern as Task 3 —
the running-total assertion lives in one place).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: FAIL — `AttributeError: module 'slides_deck_content' has no attribute 'monthly_kpi_rows'`.

- [ ] **Step 3: Implement**

Add `import pandas as pd` to the top of `slides_deck_content.py`.

Add after `add_slide_agenda`:

```python
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
```

In `build_deck`, insert `add_slide_monthly_kpi(prs, df, period_label)` right
after `add_slide_exec_summary(...)` and before `add_slide_trend(...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add monthly KPI table slide"
```

---

### Task 5: Executive Summary gains QoQ deltas

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Modifies signature: `add_slide_exec_summary(prs, summary, period_label, metric_changes=None, comparison_label=None)` — the two new params are keyword-optional so this is backward compatible for callers not yet passing comparison data.
- Consumes: `slides_export.qoq_delta_text`, `slides_export.BENCHMARK_DELIVERY_RATE` (Task 2).

- [ ] **Step 1: Write the failing test**

```python
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
    sx.add_slide_exec_summary(prs, summary, "Jun 2026", changes, "Jun 1")
    texts = " ".join(sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame)
    assert "vs Jun 1" in texts


def test_exec_summary_delivery_tile_shows_benchmark():
    prs = sx.new_deck()
    from insights_engine import generate_executive_summary
    summary = generate_executive_summary(_df())
    sx.add_slide_exec_summary(prs, summary, "Jun 2026")
    texts = " ".join(sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame)
    assert "target" in texts.lower() and "90%" in texts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_build_deck.py::test_exec_summary_shows_qoq_delta_when_comparison_given tests/test_build_deck.py::test_exec_summary_delivery_tile_shows_benchmark -v`
Expected: FAIL — the first with `TypeError: add_slide_exec_summary() takes 3 positional arguments but 5 were given`, the second because no benchmark text exists yet.

- [ ] **Step 3: Implement**

Replace `add_slide_exec_summary` in `slides_deck_content.py`:

```python
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
```

Add `qoq_delta_text, BENCHMARK_DELIVERY_RATE` to the
`from slides_export import (...)` block at the top of `slides_deck_content.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS (all tests, including the pre-existing ones — `add_slide_exec_summary` is still called from `build_deck` with just `(prs, summary, period_label)`, which is valid since the new params default to `None`).

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: show QoQ delta on executive summary tiles when comparison data is available"
```

---

### Task 6: Replace channel bar chart + table with a channel-cards grid

**Files:**
- Modify: `slides_deck_content.py`
- Modify: `slides_export.py` (delete now-unused `chart_channels`)
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Produces: `channel_card_rows(df, comparison_df=None) -> list[dict]` (each dict: `channel, status, status_color, revenue, delivery, insight, qoq`), replaces `add_slide_channels(prs, df, period_label)` with `add_slide_channel_cards(prs, df, period_label, comparison_df=None)`.
- Removes: `slides_export.chart_channels` (only caller was the function being replaced).

- [ ] **Step 1: Write the failing tests**

```python
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
```

Add `import slides_export as sx_export` near the top of `tests/test_build_deck.py`
(alongside `import slides_deck_content as sx`) for that last assertion.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: FAIL — `AttributeError: module 'slides_deck_content' has no attribute 'channel_card_rows'`.

- [ ] **Step 3: Implement**

Delete `chart_channels` from `slides_export.py` (the function defined between
`chart_trend` and `chart_journey_sankey`).

Replace `add_slide_channels` in `slides_deck_content.py` with:

```python
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


def add_slide_channel_cards(prs, df, period_label, comparison_df=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "CHANNEL PERFORMANCE", "Where Revenue Comes From", period_label)
    rows = channel_card_rows(df, comparison_df)[:6]
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
    add_morph(slide)
```

Add `channel_status, status_pill` to the `from slides_export import (...)`
block at the top of `slides_deck_content.py`.

In `build_deck`, replace `add_slide_channels(prs, df, period_label)` with:

```python
    add_slide_channel_cards(
        prs, df, period_label,
        comparison_df=comparison_result["comparison_data"] if comparison_result else None,
    )
```

(`comparison_result` is not yet a parameter used elsewhere in `build_deck` at
this point in the plan — it is already accepted as a kwarg since Task 1; this
is its first real use.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_deck.py tests/test_slides_helpers.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py slides_export.py tests/test_build_deck.py
git commit -m "feat: replace channel bar chart with per-channel status cards"
```

---

### Task 7: Add Control Group Uplift conditional slide

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Produces: `control_group_uplift_summary(df, conversion_attribution="Total") -> dict | None` (keys: `uplift_pct, reliability, is_significant`), `add_slide_control_uplift(prs, summary, period_label) -> None`.
- Consumes: `dashboard.comparisons_logic.calculate_period_metrics`, `dashboard.comparisons_logic.calculate_uplift_significance` (both already exist and are used by `pages/14_comparisons.py`).

- [ ] **Step 1: Write the failing tests**

```python
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
    assert n_full == n_minimal + 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: FAIL — `AttributeError: module 'slides_deck_content' has no attribute 'control_group_uplift_summary'`.

- [ ] **Step 3: Implement**

Add `from dashboard.comparisons_logic import calculate_period_metrics, calculate_uplift_significance`
to the imports at the top of `slides_deck_content.py`.

Add after `add_slide_channel_cards`:

```python
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


def add_slide_control_uplift(prs, summary, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "CAMPAIGN EFFICIENCY", "Control Group vs. Target Group Uplift", period_label)
    text(slide, 0.55, 2.0, 8, 0.6,
         ("The control group measures how much WebEngage-targeted campaigns "
          "outperform an untouched baseline audience.", 13, INK, F_REG, False, None))
    color = GREEN if summary["uplift_pct"] > 0 else RED
    stat_tile(slide, 0.55, 2.8, 3.4, 1.6, "CONVERSION UPLIFT",
              f"{summary['uplift_pct']:+.1f}%", summary["reliability"], color)
    add_morph(slide)
```

In `build_deck`, after `add_slide_channel_cards(...)`, add:

```python
    uplift_summary = control_group_uplift_summary(df, conversion_attribution)
    if uplift_summary:
        add_slide_control_uplift(prs, uplift_summary, period_label)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add conditional control-group uplift slide"
```

---

### Task 8: Top Campaigns table gains CVR and AOV columns

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Modifies: `add_slide_campaigns(prs, df, period_label)` body only — signature unchanged.

- [ ] **Step 1: Write the failing test**

```python
def test_top_campaigns_table_has_cvr_and_aov_columns():
    prs = sx.new_deck()
    sx.add_slide_campaigns(prs, _full_df(), "Jun 2026")
    tables = [sh for sh in prs.slides[0].shapes if sh.has_table]
    assert tables, "expected a table on the campaigns slide"
    header_texts = [c.text for c in tables[0].table.rows[0].cells]
    assert header_texts == ["Campaign", "Conversions", "Revenue", "CVR", "AOV"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_build_deck.py::test_top_campaigns_table_has_cvr_and_aov_columns -v`
Expected: FAIL — `assert ['Campaign', 'Conversions'] == ['Campaign', 'Conversions', 'Revenue', 'CVR', 'AOV']`.

- [ ] **Step 3: Implement**

Add `import numpy as np` to the top of `slides_deck_content.py`.

Replace `add_slide_campaigns` in `slides_deck_content.py`:

```python
def add_slide_campaigns(prs, df, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "TOP CAMPAIGNS", "Highest-Converting Campaigns", period_label)
    conv_col = "Selected Conversions" if "Selected Conversions" in df.columns else "Unique Conversions"
    rev_col = "Selected Revenue (SAR)" if "Selected Revenue (SAR)" in df.columns else "Revenue (SAR)"
    agg = df.groupby("Campaign Name").agg(
        Conversions=(conv_col, "sum"), Revenue=(rev_col, "sum"), Clicks=("Unique Clicks", "sum")
    ).reset_index().nlargest(8, "Conversions")
    agg["CVR"] = np.where(agg["Clicks"] > 0, agg["Conversions"] / agg["Clicks"], 0)
    agg["AOV"] = np.where(agg["Conversions"] > 0, agg["Revenue"] / agg["Conversions"], 0)
    rows = [(r["Campaign Name"], f"{r['Conversions']:,.0f}", f"SAR {r['Revenue']:,.0f}",
             f"{r['CVR']:.1%}", f"SAR {r['AOV']:,.0f}") for _, r in agg.iterrows()]
    styled_table(slide, 0.55, 1.7, 11.4, ["Campaign", "Conversions", "Revenue", "CVR", "AOV"], rows,
                 [4.6, 1.6, 2.0, 1.5, 1.7])
    add_morph(slide)
```

`top_campaigns` from `analysis.py` is no longer called by this function; leave
the import in place only if another function in the file still uses it (it
does not after this change) — remove `top_campaigns` from the
`from analysis import (...)` line at the top of `slides_deck_content.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add CVR and AOV columns to top campaigns table"
```

---

### Task 9: Add Campaign Spotlight slide

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Produces: `top_campaign_spotlight(df) -> dict | None` (keys: `name, channel, revenue, conversions, cvr, audience`), `add_slide_campaign_spotlight(prs, spotlight, period_label) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
def test_top_campaign_spotlight_picks_highest_revenue_campaign():
    spotlight = sx.top_campaign_spotlight(_df())
    assert spotlight["name"] == "C1"  # C1 has Revenue 5500, the max in _df()


def test_build_deck_has_14_slides_minimal_fixture_final():
    data = sx.build_deck(_df(), client_name="Acme Co", period_label="Jun 2026")
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 14
```

Update `test_build_deck_has_10_slides_with_client_name`'s assertion from
`== 13` to `== 14` and delete the temporary
`test_build_deck_has_14_slides_minimal_fixture_final` (same running-total
convention as Tasks 3 and 4).

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: FAIL — `AttributeError: module 'slides_deck_content' has no attribute 'top_campaign_spotlight'`.

- [ ] **Step 3: Implement**

Add after `add_slide_campaigns`:

```python
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


def add_slide_campaign_spotlight(prs, spotlight, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "CAMPAIGN SPOTLIGHT", spotlight["name"], period_label)
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
```

In `build_deck`, after `add_slide_campaigns(prs, df, period_label)`, add:

```python
    spotlight = top_campaign_spotlight(df)
    if spotlight:
        add_slide_campaign_spotlight(prs, spotlight, period_label)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add campaign spotlight slide for the top-revenue campaign"
```

---

### Task 10: Add Top Segments conditional slide

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Produces: `top_segment_rows(df) -> list[tuple] | None`, `add_slide_segments(prs, rows, period_label) -> None`.
- Consumes: `analysis.top_segments` (already imported by `slides_deck_content.py` since Task 1).

- [ ] **Step 1: Write the failing tests**

```python
def test_top_segment_rows_none_without_segment_column():
    assert sx.top_segment_rows(_df()) is None


def test_top_segment_rows_present_with_segment_column():
    rows = sx.top_segment_rows(_full_df())
    assert rows is not None and len(rows) > 0


def test_build_deck_adds_segments_slide_when_data_present():
    data_minimal = sx.build_deck(_df(), client_name="Acme Co")
    data_full = sx.build_deck(_full_df(), client_name="Acme Co")
    n_minimal = len(Presentation(io.BytesIO(data_minimal)).slides)
    n_full = len(Presentation(io.BytesIO(data_full)).slides)
    assert n_full > n_minimal
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: FAIL — `AttributeError: module 'slides_deck_content' has no attribute 'top_segment_rows'`.

- [ ] **Step 3: Implement**

Add `top_segments` to the `from analysis import (...)` line at the top of
`slides_deck_content.py` if it isn't already there (it was removed from that
import in Task 8 alongside `top_campaigns`, so re-add just `top_segments`).

Add after `add_slide_campaign_spotlight`:

```python
def top_segment_rows(df):
    conv_col = "Selected Conversions" if "Selected Conversions" in df.columns else "Unique Conversions"
    seg = top_segments(df, conv_col, top_n=8)
    if seg.empty:
        return None
    return [(str(r.iloc[0]), f"{r.iloc[1]:,.0f}") for _, r in seg.iterrows()]


def add_slide_segments(prs, rows, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "AUDIENCE SEGMENTS", "Top-Converting Segments", period_label)
    styled_table(slide, 0.55, 1.7, 7.0, ["Segment", "Conversions"], rows, [5.2, 1.8])
    add_morph(slide)
```

In `build_deck`, after the campaign spotlight block, add:

```python
    seg_rows = top_segment_rows(df)
    if seg_rows:
        add_slide_segments(prs, seg_rows, period_label)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add conditional top-segments slide"
```

---

### Task 11: Journeys table gains Revenue and CVR columns

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Modifies: `add_slide_journeys(prs, df, period_label)` body only — signature unchanged.

- [ ] **Step 1: Write the failing test**

```python
def test_journeys_table_has_revenue_and_cvr_columns():
    prs = sx.new_deck()
    sx.add_slide_journeys(prs, _full_df(), "Jun 2026")
    tables = [sh for sh in prs.slides[0].shapes if sh.has_table]
    assert tables, "expected a table on the journeys slide"
    header_texts = [c.text for c in tables[0].table.rows[0].cells]
    assert header_texts == ["Journey", "Conversions", "Revenue", "CVR"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_build_deck.py::test_journeys_table_has_revenue_and_cvr_columns -v`
Expected: FAIL — `assert ['Journey', 'Conversions'] == ['Journey', 'Conversions', 'Revenue', 'CVR']`.

- [ ] **Step 3: Implement**

Replace `add_slide_journeys` in `slides_deck_content.py`:

```python
def add_slide_journeys(prs, df, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "JOURNEY HEALTH", "Top Journey & Its Flow", period_label)
    conv_col = "Selected Conversions" if "Selected Conversions" in df.columns else "Unique Conversions"
    rev_col = "Selected Revenue (SAR)" if "Selected Revenue (SAR)" in df.columns else "Revenue (SAR)"
    jdf = df[df["Journey Name"].notna() & (df["Journey Name"] != "nan") & (df["Journey Name"] != "")]
    if not jdf.empty:
        agg = jdf.groupby("Journey Name").agg(
            Conversions=(conv_col, "sum"), Revenue=(rev_col, "sum"), Clicks=("Unique Clicks", "sum")
        ).reset_index().nlargest(6, "Conversions")
        agg["CVR"] = np.where(agg["Clicks"] > 0, agg["Conversions"] / agg["Clicks"], 0)
        rows = [(r["Journey Name"], f"{r['Conversions']:,.0f}", f"SAR {r['Revenue']:,.0f}", f"{r['CVR']:.1%}")
                for _, r in agg.iterrows()]
        styled_table(slide, 7.85, 1.9, 4.95, ["Journey", "Conversions", "Revenue", "CVR"], rows,
                     [2.05, 0.95, 1.15, 0.8])
        top_journey_name = str(agg.iloc[0]["Journey Name"])
        stages = journey_funnel_stages(df, top_journey_name)
        _put_chart(slide, chart_journey_sankey(stages), 0.3, 2.6, 2.9)
    add_morph(slide)
```

`get_top_journeys` from `analysis.py` is no longer called by this function —
remove it from the `from analysis import (...)` line at the top of
`slides_deck_content.py`.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add revenue and CVR columns to journeys table"
```

---

### Task 12: Add Deliverability/ESP conditional slide

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Produces: `deliverability_data(df) -> dict | None` (keys: `esp_rows, failed_rows`, either may be `None` independently but not both), `add_slide_deliverability(prs, data, period_label) -> None`.
- Consumes: `analysis.esp_analysis`, `analysis.failed_reasons_analysis` (add both to the `from analysis import (...)` line).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: FAIL — `AttributeError: module 'slides_deck_content' has no attribute 'deliverability_data'`.

- [ ] **Step 3: Implement**

Add `esp_analysis, failed_reasons_analysis` to the `from analysis import (...)`
line at the top of `slides_deck_content.py`.

Add after `add_slide_segments`:

```python
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
    return {"esp_rows": esp_rows, "failed_rows": failed_rows}


def add_slide_deliverability(prs, data, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "DELIVERABILITY", "ESP Performance & Failure Reasons", period_label)
    if data["esp_rows"]:
        styled_table(slide, 0.55, 1.7, 7.0, ["ESP / Provider", "Sent", "Delivery Rate"],
                     data["esp_rows"], [3.4, 1.8, 1.8])
    if data["failed_rows"]:
        styled_table(slide, 7.85, 1.7, 4.95, ["Failure Reason", "Count"], data["failed_rows"], [3.4, 1.55])
    add_morph(slide)
```

In `build_deck`, after the segments block, add:

```python
    deliverability = deliverability_data(df)
    if deliverability:
        add_slide_deliverability(prs, deliverability, period_label)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add conditional deliverability/ESP slide"
```

---

### Task 13: Add Attribution conditional slide

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Produces: `attribution_rows(df) -> list[tuple] | None`, `add_slide_attribution(prs, rows, period_label) -> None`.
- Consumes: `analysis.attribution_analysis` (add to the `from analysis import (...)` line).

- [ ] **Step 1: Write the failing tests**

```python
def test_attribution_rows_none_without_attribution_columns():
    assert sx.attribution_rows(_df()) is None


def test_attribution_rows_present_with_attribution_columns():
    rows = sx.attribution_rows(_full_df())
    assert rows is not None and len(rows) == 3  # Click-Through, Impression-Only, Send-Only


def test_build_deck_adds_attribution_slide_when_data_present():
    data_minimal = sx.build_deck(_df(), client_name="Acme Co")
    data_full = sx.build_deck(_full_df(), client_name="Acme Co")
    n_minimal = len(Presentation(io.BytesIO(data_minimal)).slides)
    n_full = len(Presentation(io.BytesIO(data_full)).slides)
    assert n_full > n_minimal
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: FAIL — `AttributeError: module 'slides_deck_content' has no attribute 'attribution_rows'`.

- [ ] **Step 3: Implement**

Add `attribution_analysis` to the `from analysis import (...)` line at the
top of `slides_deck_content.py`.

Add after `add_slide_deliverability`:

```python
def attribution_rows(df):
    required = {"Unique Conversions", "Unique Impression-Through Conversions", "Unique Click-Through Conversions"}
    if not required.issubset(df.columns):
        return None
    attr = attribution_analysis(df)
    total = attr["Conversions"].sum()
    if attr.empty or total <= 0:
        return None
    return [(r["Source"], f"{r['Conversions']:,.0f}", f"{(r['Conversions'] / total):.1%}")
            for _, r in attr.iterrows()]


def add_slide_attribution(prs, rows, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "ATTRIBUTION", "How Conversions Were Won", period_label)
    styled_table(slide, 0.55, 1.9, 7.0, ["Source", "Conversions", "Share"], rows, [3.4, 1.8, 1.8])
    add_morph(slide)
```

In `build_deck`, after the deliverability block, add:

```python
    attr_rows = attribution_rows(df)
    if attr_rows:
        add_slide_attribution(prs, attr_rows, period_label)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add conditional attribution breakdown slide"
```

---

### Task 14: Add QoQ Scorecard conditional slide

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Produces: `qoq_scorecard_rows(metric_changes) -> list[tuple]`, `add_slide_qoq_scorecard(prs, rows, current_label, comparison_label, period_label) -> None`.
- Modifies: `build_deck` now computes `metric_changes`/`current_label`/`comparison_label` from `comparison_result` (accepted as a parameter since Task 1, unused until now) and threads `metric_changes`/`comparison_label` into `add_slide_exec_summary` (Task 5's params) and into this new slide.
- Consumes: `dashboard.comparisons_logic.calculate_period_metrics`, `calculate_metric_changes` (already imported per Task 7); `slides_export.BENCHMARK_ROAS_GOOD` (add to the `from slides_export import (...)` block — `BENCHMARK_DELIVERY_RATE` is already imported there since Task 5).

- [ ] **Step 1: Write the failing tests**

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: FAIL — `AttributeError: module 'slides_deck_content' has no attribute 'qoq_scorecard_rows'`.

- [ ] **Step 3: Implement**

Add after `add_slide_attribution`:

```python
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


def add_slide_qoq_scorecard(prs, rows, current_label, comparison_label, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "QUARTER OVER QUARTER", "Performance Scorecard", period_label)
    headers = ["Metric", comparison_label or "Prior Period", current_label or "This Period", "Change %"]
    styled_table(slide, 0.55, 1.9, 11.4, headers, rows, [3.4, 2.6, 2.6, 2.8])
    add_morph(slide)
```

Replace `build_deck` in `slides_deck_content.py`:

```python
def build_deck(df, client_name="", period_label=None, comparison_result=None, conversion_attribution="Total") -> bytes:
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

    prs = new_deck()
    add_slide_title(prs, client_name, period_label)
    add_slide_agenda(prs, period_label)
    add_slide_exec_summary(prs, summary, period_label, metric_changes, comparison_label)
    add_slide_monthly_kpi(prs, df, period_label)
    add_slide_trend(prs, df, period_label)
    add_slide_channel_cards(
        prs, df, period_label,
        comparison_df=comparison_result["comparison_data"] if comparison_result else None,
    )

    uplift_summary = control_group_uplift_summary(df, conversion_attribution)
    if uplift_summary:
        add_slide_control_uplift(prs, uplift_summary, period_label)

    add_slide_campaigns(prs, df, period_label)

    spotlight = top_campaign_spotlight(df)
    if spotlight:
        add_slide_campaign_spotlight(prs, spotlight, period_label)

    seg_rows = top_segment_rows(df)
    if seg_rows:
        add_slide_segments(prs, seg_rows, period_label)

    add_slide_journeys(prs, df, period_label)

    deliverability = deliverability_data(df)
    if deliverability:
        add_slide_deliverability(prs, deliverability, period_label)

    attr_rows = attribution_rows(df)
    if attr_rows:
        add_slide_attribution(prs, attr_rows, period_label)

    if metric_changes:
        qoq_rows = qoq_scorecard_rows(metric_changes)
        if qoq_rows:
            add_slide_qoq_scorecard(prs, qoq_rows, current_label, comparison_label, period_label)

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add conditional QoQ scorecard slide, wire comparison_result end-to-end in build_deck"
```

---

### Task 15: Recommendations show expected dollar/percentage impact

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Modifies: `add_slide_recommendations(prs, actions, period_label)` body only — signature unchanged.

- [ ] **Step 1: Write the failing test**

```python
def test_recommendations_slide_shows_expected_impact():
    prs = sx.new_deck()
    actions = [{
        "title": "Fix Delivery Issues", "action": "Improve delivery rate",
        "expected_impact": "+5.2K SAR in recovered revenue", "priority": "HIGH",
    }]
    sx.add_slide_recommendations(prs, actions, "Jun 2026")
    texts = " ".join(sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame)
    assert "+5.2K SAR in recovered revenue" in texts
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_build_deck.py::test_recommendations_slide_shows_expected_impact -v`
Expected: FAIL — impact text not found in slide text.

- [ ] **Step 3: Implement**

Replace `add_slide_recommendations` in `slides_deck_content.py`:

```python
def add_slide_recommendations(prs, actions, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "RECOMMENDATIONS", "What To Do & Which Feature", period_label)
    y = 1.7
    for action in actions[:3]:
        sentence, feature = sn.narrate_recommendation(action)
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: show expected dollar/percentage impact on recommendation slides"
```

---

### Task 16: Wire `pages/13_export.py` end-to-end and add a full-fixture integration test

**Files:**
- Modify: `pages/13_export.py:19-38`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Consumes: `ctx.comparison_result`, `ctx.conversion_attribution` (both already exist on the `DashboardState` returned by `dashboard.state.get_ctx()` — see `dashboard/state.py:12,14`).

- [ ] **Step 1: Write the failing integration test**

```python
def test_build_deck_full_fixture_with_comparison_reaches_max_slide_count():
    df = _full_df()
    cr = _comparison_result(df)
    data = sx.build_deck(df, client_name="Acme Co", comparison_result=cr, conversion_attribution="Total")
    prs = Presentation(io.BytesIO(data))
    # 14 base (Task 9) + control uplift + segments + deliverability + attribution + qoq scorecard
    # NOTE: Task 17 (added after this task in the plan) inserts one more
    # unconditional slide and bumps this assertion to 20 — see Task 17 Step 1.
    assert len(prs.slides) == 19
```

- [ ] **Step 2: Run test to verify it fails or passes**

Run: `python -m pytest tests/test_build_deck.py::test_build_deck_full_fixture_with_comparison_reaches_max_slide_count -v`
Expected: this should already PASS given Tasks 7–14 are complete — it is a
regression-lock test for the full pipeline, not new behavior. If it fails,
recheck the slide count arithmetic against which conditional slides actually
fired (add a temporary `print(len(prs.slides))` to debug, then remove it).

- [ ] **Step 3: Update `pages/13_export.py`**

Replace the button handler body (current lines 33–38):

```python
def _deck_signature(df, name, comparison_result):
    # Cheap fingerprint of the inputs so a previously-generated deck isn't offered
    # for download after the user changes filters, the client name, or the
    # comparison-mode selection (any of which would otherwise silently serve a
    # deck built from stale data).
    if df is None or df.empty:
        return None
    comp_sig = None
    if comparison_result:
        comp_sig = (comparison_result.get("comparison_label"), comparison_result.get("current_label"))
    return (df.shape, float(df.select_dtypes("number").fillna(0).to_numpy().sum()), name, comp_sig)


cur_sig = _deck_signature(filtered_df, client_name, ctx.comparison_result)
if st.button("Generate Client Review Deck"):
    if filtered_df is None or filtered_df.empty:
        st.warning("No data for the current filters — adjust filters and try again.")
    else:
        with st.spinner("Building deck (rendering charts)…"):
            try:
                st.session_state["deck_bytes"] = slides_deck_content.build_deck(
                    filtered_df, client_name=client_name,
                    comparison_result=ctx.comparison_result,
                    conversion_attribution=ctx.conversion_attribution,
                )
                st.session_state["deck_sig"] = cur_sig
            except Exception as e:
                st.error(f"Could not build the deck: {e}")
```

This replaces the existing `_deck_signature(df, name)` (2-arg) and its call
site at lines 19–29 of `pages/13_export.py` — the function gains a third
parameter and every call site passes the new argument.

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest tests/test_build_deck.py tests/test_slides_helpers.py -v`
Expected: All PASS.

- [ ] **Step 5: Manual verification against the real CSV**

Per this repo's existing convention for running the dashboard headlessly
(`DASHBOARD_TEST_CSV` env var + `tests/Daily Q2_Q3.csv`), run the app and
generate a deck from the Export page to visually confirm the new slides
render correctly and the file opens in PowerPoint without repair prompts.
This is a manual check — there is no automated PowerPoint-rendering
assertion beyond what `python-pptx` already validates by successfully
parsing the file in the tests above.

- [ ] **Step 6: Commit**

```bash
git add pages/13_export.py tests/test_build_deck.py
git commit -m "feat: wire comparison_result/conversion_attribution into deck export, invalidate cached deck on comparison-mode change"
```

---

### Task 17: Add a dense Channel Metrics table slide (separate from the channel cards)

The channel cards (Task 6) stay exactly as they are — this adds a *second*,
data-dense channel slide alongside them: one row per channel across two
stacked tables covering delivery, engagement, and revenue efficiency, closer
to the UPC sample's "Channels Performance" table than the cards are.

**Files:**
- Modify: `slides_deck_content.py`
- Test: `tests/test_build_deck.py`

**Interfaces:**
- Produces: `channel_metrics_rows(df) -> dict` (keys: `engagement_rows`, `revenue_rows`, `revenue_headers`), `add_slide_channel_metrics(prs, data, period_label) -> None`.
- Consumes: `analysis.channel_analysis` (already imported), `numpy as np` (already imported per Task 8).
- This task does not touch `_header`'s `story` kwarg (it doesn't exist yet) — `add_slide_channel_metrics` is written using only the parameters `_header` supports today. Task 18 retrofits storyline support onto this function along with every other slide function, in the same mechanical pass.

- [ ] **Step 1: Write the failing tests**

```python
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


def test_build_deck_has_15_slides_minimal_fixture():
    data = sx.build_deck(_df(), client_name="Acme Co", period_label="Jun 2026")
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 15
```

Update `test_build_deck_has_10_slides_with_client_name`'s assertion from
`== 14` to `== 15` and delete the temporary
`test_build_deck_has_15_slides_minimal_fixture` (same running-total
convention as Tasks 3, 4, and 9). Also update
`test_build_deck_full_fixture_with_comparison_reaches_max_slide_count`
(Task 16) from `== 19` to `== 20`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: FAIL — `AttributeError: module 'slides_deck_content' has no attribute 'channel_metrics_rows'`.

- [ ] **Step 3: Implement**

Add after `add_slide_channel_cards`:

```python
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
        revenue_headers = ["Channel", "Conversions", "Conv Rate", "Revenue", "AOV", "ROAS"]
        revenue_rows = [
            (r["Channel"], f"{r[conv_col]:,.0f}", f"{r['Conv Rate']:.1%}",
             f"SAR {r[rev_col]:,.0f}", f"SAR {r['AOV']:,.0f}", f"{r['ROAS']:.2f}x")
            for _, r in chan.iterrows()
        ]
    else:
        revenue_headers = ["Channel", "Conversions", "Conv Rate", "Revenue", "AOV"]
        revenue_rows = [
            (r["Channel"], f"{r[conv_col]:,.0f}", f"{r['Conv Rate']:.1%}",
             f"SAR {r[rev_col]:,.0f}", f"SAR {r['AOV']:,.0f}")
            for _, r in chan.iterrows()
        ]

    return {"engagement_rows": engagement_rows, "revenue_rows": revenue_rows, "revenue_headers": revenue_headers}


def add_slide_channel_metrics(prs, data, period_label):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "CHANNEL PERFORMANCE", "Full Channel Metrics", period_label)
    styled_table(slide, 0.55, 1.85, 11.4,
                 ["Channel", "Sent", "Delivered", "Delivery Rate", "Clicks", "CTR"],
                 data["engagement_rows"], [2.2, 1.9, 1.9, 1.9, 1.7, 1.8])
    revenue_widths = [2.2, 1.9, 1.9, 2.3, 1.7, 1.4] if len(data["revenue_headers"]) == 6 else [2.5, 2.5, 2.5, 2.5, 2.4]
    styled_table(slide, 0.55, 4.35, 11.4, data["revenue_headers"], data["revenue_rows"], revenue_widths)
    add_morph(slide)
```

In `build_deck`, immediately after the `add_slide_channel_cards(...)` call,
add:

```python
    add_slide_channel_metrics(prs, channel_metrics_rows(df), period_label)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_build_deck.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_deck_content.py tests/test_build_deck.py
git commit -m "feat: add dense channel metrics table slide alongside the channel cards"
```

---

### Task 18: Add storyline captions connecting each slide to the next

**Files:**
- Modify: `slides_export.py` (`_header` gains a `story` parameter)
- Modify: `slides_deck_content.py` (every `add_slide_*` function gains a `story=None` parameter that it forwards to `_header`; `build_deck` computes the storyline sentences once and passes the right one to each call)
- Test: `tests/test_slides_helpers.py`, `tests/test_build_deck.py`

**Interfaces:**
- Modifies: `_header(slide, eyebrow, title, period_label, story=None)` — new trailing optional kwarg, backward compatible with every existing call site that doesn't pass it.
- Produces: `_build_storylines(summary, chan_rows, monthly_rows, spotlight, comparison_label) -> dict[str, str | None]` in `slides_deck_content.py`, keyed by slide name (`monthly_kpi`, `trend`, `channel_cards`, `channel_metrics`, `campaigns`, `spotlight`, `journeys`, `segments`, `deliverability`, `attribution`, `qoq_scorecard`, `recommendations`, `action_plan`).

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_slides_helpers.py
def test_header_renders_story_line_when_given():
    prs = sx.new_deck()
    slide = sx.blank_slide(prs)
    sx._header(slide, "TREND", "Conversions Over Time", "Jun 2026", story="Here's the shape behind that total.")
    texts = " ".join(sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame) if False else \
            " ".join(sh.text_frame.text for sh in slide.shapes if sh.has_text_frame)
    assert "Here's the shape behind that total." in texts
```

```python
# tests/test_build_deck.py
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_slides_helpers.py tests/test_build_deck.py -v`
Expected: FAIL — `TypeError: _header() got an unexpected keyword argument 'story'` and `AttributeError: module 'slides_deck_content' has no attribute '_build_storylines'`.

- [ ] **Step 3: Implement `_header`'s story line in `slides_export.py`**

Replace `_header`:

```python
def _header(slide, eyebrow, title, period_label, story=None):
    rect(slide, 0.55, 0.42, 0.10, 0.62, fill=BRAND)
    text(slide, 0.78, 0.40, 8.5, 0.3, (eyebrow, 10.5, BRAND, F_MED, True, 2.2))
    text(slide, 0.76, 0.62, 9.5, 0.5, (title, 24, INK, F_BOLD, True, None))
    if story:
        text(slide, 0.78, 1.06, 9.5, 0.25, (story, 11, MUTED, F_REG, False, None))
    if period_label:
        text(slide, 9.2, 0.52, 3.6, 0.5,
             [[("Reporting period  ", 10.5, MUTED, F_REG, False, None)],
              [(period_label, 13, INK, F_MED, True, None)]], align=PP_ALIGN.RIGHT)
    rect(slide, 0.55, 1.28, 12.23, 0.02, fill=LINE)
```

- [ ] **Step 4: Thread `story=None` through every slide-builder function**

For each function below in `slides_deck_content.py`, add a trailing
`story=None` parameter and pass it through to that function's `_header(...)`
call by appending `, story=story)` in place of the call's closing `)`.
Functions to change (all in `slides_deck_content.py`):
`add_slide_agenda`, `add_slide_exec_summary`, `add_slide_monthly_kpi`,
`add_slide_trend`, `add_slide_channel_cards`, `add_slide_control_uplift`,
`add_slide_campaigns`, `add_slide_campaign_spotlight`, `add_slide_segments`,
`add_slide_journeys`, `add_slide_deliverability`, `add_slide_attribution`,
`add_slide_qoq_scorecard`, `_add_findings_slide`, `add_slide_recommendations`,
`add_slide_action_plan`, and `add_slide_channel_metrics` (added in Task 17
without a `story` parameter — add it here along with the rest).
(`add_slide_title` and `add_slide_closing` don't call `_header` — skip them.)

Example for `add_slide_trend` (apply the same pattern — add the parameter,
add `story=story` to the `_header` call — to every function in the list
above):

```python
def add_slide_trend(prs, df, period_label, story=None):
    slide = blank_slide(prs)
    rect(slide, 0, 0, 13.333, 7.5, fill=WHITE)
    _header(slide, "PERFORMANCE TREND", "Conversions Over Time", period_label, story=story)
    ts = time_series_analysis(df, "Unique Conversions")
    if not _put_chart(slide, chart_trend(ts, "Unique Conversions"), 0.7, 1.7, 4.9):
        text(slide, 0.76, 3.0, 11, 0.5, ("Trend chart unavailable.", 14, MUTED, F_REG, False, None))
    add_morph(slide)
```

- [ ] **Step 5: Implement `_build_storylines` and wire it into `build_deck`**

Add near the top of `slides_deck_content.py`, after the imports:

```python
def _build_storylines(summary, chan_rows, monthly_rows, spotlight, comparison_label):
    """One computed sentence per slide, so the deck reads as a chain of
    findings rather than a stack of independent reports. Every sentence is
    built from numbers the caller already computed for that slide (or the
    slide immediately before it) -- no new analysis, just narrative framing."""
    m = summary.get("headline_metrics", {})
    total_revenue = m.get("total_revenue", 0)
    total_conversions = m.get("total_conversions", 0)
    n_months = max(len(monthly_rows) - 1, 0)  # exclude the synthetic Total row

    channel_cards_story = None
    if chan_rows and total_revenue:
        top = chan_rows[0]
        share = top["revenue"] / total_revenue
        channel_cards_story = f"{top['channel']} alone drove {share:.0%} of the SAR {total_revenue:,.0f} total below."

    spotlight_story = None
    if spotlight:
        spotlight_story = f"'{spotlight['name']}' was the single best-performing campaign this period."

    return {
        "monthly_kpi": f"SAR {total_revenue:,.0f} came in across {n_months} month(s) — here's the monthly split.",
        "trend": "Here's the day-by-day shape behind that total.",
        "channel_cards": channel_cards_story,
        "channel_metrics": "The full metric set behind those channels.",
        "campaigns": "Here's which individual campaigns drove those channel numbers.",
        "spotlight": spotlight_story,
        "journeys": "Beyond one-off campaigns, here's how automated journeys performed.",
        "segments": "Here's which audience segments converted best.",
        "deliverability": "None of this works if messages don't land — a deliverability check.",
        "attribution": f"How the {total_conversions:,.0f} conversions above split between click-driven and impression-driven.",
        "qoq_scorecard": f"Compared to {comparison_label or 'the prior period'}, here's what moved.",
        "recommendations": "Turning those findings into next steps.",
        "action_plan": "Prioritized and ready to execute.",
    }
```

In `build_deck`, after `ni = summary.get("narrative_insights", {}) or {}` and
before `metric_changes, current_label, comparison_label = None, None, None`,
compute the pieces `_build_storylines` needs and call it once
`comparison_label` is known — move the call to just before
`prs = new_deck()`:

```python
    chan_rows_for_story = channel_card_rows(df)
    monthly_rows_for_story = monthly_kpi_rows(df)
    spotlight_for_story = top_campaign_spotlight(df)
    stories = _build_storylines(summary, chan_rows_for_story, monthly_rows_for_story,
                                 spotlight_for_story, comparison_label)
```

Then update every `add_slide_*` call inside `build_deck` to pass its
matching `story=stories.get("<key>")` argument, e.g.:

```python
    add_slide_monthly_kpi(prs, df, period_label, story=stories.get("monthly_kpi"))
    add_slide_trend(prs, df, period_label, story=stories.get("trend"))
    add_slide_channel_cards(
        prs, df, period_label,
        comparison_df=comparison_result["comparison_data"] if comparison_result else None,
        story=stories.get("channel_cards"),
    )
    add_slide_channel_metrics(prs, channel_metrics_rows(df), period_label, story=stories.get("channel_metrics"))
    # (this replaces Task 17's call, which did not pass `story`)
```

Apply the same `story=stories.get("<key>")` pattern to the remaining calls:
`add_slide_control_uplift(..., story=stories.get("control_uplift"))` — note
`"control_uplift"` is not a key `_build_storylines` returns (it's
conditional and has no natural "connects to next slide" framing); pass
`story=None` for it explicitly instead. Do the same for `add_slide_campaigns`
(`story=stories.get("campaigns")`), `add_slide_campaign_spotlight`
(`story=stories.get("spotlight")`), `add_slide_segments`
(`story=stories.get("segments")`), `add_slide_journeys`
(`story=stories.get("journeys")`), `add_slide_deliverability`
(`story=stories.get("deliverability")`), `add_slide_attribution`
(`story=stories.get("attribution")`), `add_slide_qoq_scorecard`
(`story=stories.get("qoq_scorecard")`), `add_slide_recommendations`
(`story=stories.get("recommendations")`), `add_slide_action_plan`
(`story=stories.get("action_plan")`). Leave `add_slide_agenda`,
`add_slide_exec_summary`, and the two `_add_findings_slide` calls with no
`story` argument (they default to `None` — the agenda and exec summary open
the story rather than continue it, and findings slides already carry their
own narrated bullets).

- [ ] **Step 6: Run the full test suite**

Run: `python -m pytest tests/test_build_deck.py tests/test_slides_helpers.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add slides_export.py slides_deck_content.py tests/test_slides_helpers.py tests/test_build_deck.py
git commit -m "feat: add computed storyline captions connecting each slide to the next"
```

---

## Self-Review Notes

- **Spec coverage:** All 18 slide-lineup rows from the spec map to a task:
  agenda/closing → Task 3; monthly KPI → Task 4; exec summary QoQ → Task 5;
  channel cards → Task 6; control uplift → Task 7; campaigns CVR/AOV → Task 8;
  campaign spotlight → Task 9; segments → Task 10; journeys → Task 11;
  deliverability → Task 12; attribution → Task 13; QoQ scorecard → Task 14;
  recommendations impact figures → Task 15; plumbing → Task 16. Benchmark
  thresholds (`BENCHMARK_DELIVERY_RATE`, `BENCHMARK_ROAS_GOOD/OK`, added in
  Task 2) are rendered on the exec-summary delivery-rate tile (Task 5) and
  the QoQ scorecard's Delivery Rate / ROAS rows (Task 14) — the two places
  in the deck that show those metrics as standalone figures a manager reads
  without other context. `BENCHMARK_ROAS_OK` (the amber/"workable" tier) is
  defined but not surfaced anywhere; only the single "good" threshold is
  shown per metric to keep tiles/table cells short — acceptable since the
  spec asked for "a target reference," not a full three-tier legend.
  Post-approval feedback added two more requirements, both covered: "the
  channels table should have a lot of metrics" → Task 17 (a dense two-table
  channel metrics slide, separate from and additive to the Task 6 cards,
  covering Sent/Delivered/Delivery Rate/Clicks/CTR/Conversions/Conv
  Rate/Revenue/AOV/ROAS); "the whole slides should tell a story" → Task 18
  (`_header` gains a `story` line, `_build_storylines` computes one
  connecting sentence per slide from numbers already computed for that
  slide or the one before it, threaded through every `add_slide_*` call in
  `build_deck`).
- **Placeholder scan:** No TBD/TODO markers; every step has runnable code.
- **Type consistency:** `channel_status`, `qoq_delta_text`, `status_pill`
  (Task 2) are used with identical signatures in Task 6 and Task 5. All
  `*_rows`/`*_data`/`*_summary` helpers consistently return `None` when their
  slide should be skipped, and `build_deck` consistently checks truthiness
  before calling the matching `add_slide_*` — verified across Tasks 7, 10,
  12, 13, 14. `add_slide_channel_metrics` is defined in Task 17 without a
  `story` parameter (matching `_header`'s signature at that point in the
  plan) and Task 18 retrofits it identically to every other slide function —
  verified the Task 17 Interfaces line and Step 3 code agree with each other
  (both omit `story`) and that Task 18 explicitly lists it among the
  functions to update, including the `build_deck` call site.
- **Task-ordering fix:** an earlier draft had Task 18 (storylines) depend on
  Task 17 (channel metrics) for a parameter, while also being numbered to
  execute after it — a forward reference that would have broken Task 17's
  own tests. Resolved by keeping Task 17 free of the `story` kwarg entirely
  (it's simply not part of `_header`'s signature yet) and having Task 18 add
  `story` to *every* slide function, including the one Task 17 just wrote —
  the same "later tasks extend earlier ones" pattern already used
  throughout this plan (e.g. Task 8 modifies Task 1's `add_slide_campaigns`,
  Task 14 modifies Task 1's `build_deck`).
