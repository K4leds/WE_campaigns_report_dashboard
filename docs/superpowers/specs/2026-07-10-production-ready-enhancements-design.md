# Production-Ready Dashboard: 2026 AI-Era Enhancements

**Date:** 2026-07-10
**Status:** Draft
**Branch:** `webengage-marketing-analytics-dashboard`

## Overview

Transform the existing WebEngage campaigns dashboard from a "metrics display" into a cohesive, production-ready product for 2026. The dashboard serves three concrete use cases: (1) getting actionable insights from campaign data, (2) taking data-driven actions, and (3) generating quarterly/monthly reports and slides.

### Guiding principles

1. **Data trust first** — accuracy and verifiability are prerequisites for every feature
2. **Unified experience** — one design system, one table component, one visual language
3. **Organized navigation** — pages grouped by workflow, not dumped in a flat list
4. **AI-forward but API-key-gated** — local intelligence works out of the box; LLM upgrade path requires user's own key
5. **Export as a first-class feature** — structured data, formatted reports, slide-generator-ready

---

## Section 1: Data Accuracy & Verification Layer

### Problem

- Past bugs (channel revenue summing across channels instead of per-channel) eroded trust
- K/M formatting (`11.5K SAR`) stores display strings in DataFrames, breaking column sorting
- No way to verify that dashboard calculations match source data
- Users manually cross-check numbers against WebEngage UI

### Design

**1a. Calculation Audit Trail**
Every derived metric stores its formula and raw inputs. On hover/tap, a tooltip shows:
`AOV = Revenue ÷ Unique Conversions = 45,000 ÷ 320 = 140.63 SAR`

Affected metrics: Revenue attribution, ROAS, AOV, Revenue Per Click, Revenue Per Send, Channel Revenue, Conversion Rate, CTR, Delivery Rate.

**1b. Inline Validation Checks**
A silent background cross-check runs on data load. For each computed metric, the display component recalculates it from raw columns and compares against the stored value. If difference > 1%, a subtle warning badge appears on that metric.

Validation runs in `dashboard/verification.py` (new module), called from the data pipeline after filtering.

**1c. Unified Numeric Display (K/M Sorting Fix)**
- Underlying DataFrames never store formatted strings — all metrics remain numeric `float64`/`int64`
- Display formatting is a **render-layer-only concern**
- `st.dataframe` uses `st.column_config.NumberColumn(format="%.2f")` — native Streamlit, sort-safe
- Custom tables (tghe `render_table()` component in Section 2) format at render time via `ag-Grid` value formatters, leaving the underlying model numeric

### Files affected
- **New:** `dashboard/verification.py` — audit trail + validation logic
- **Modified:** `utils.py` — `format_metric()` becomes a pure display decorator, no longer aliasing DataFrame columns
- **Modified:** Every page file — table display calls use `column_config` instead of `apply(lambda x: format_metric(x))`

---

## Section 2: Unified Table & Comparison System

### Problem
- Comparison mode generates a completely different table structure with extra delta columns
- Columns are already numerous; adding `vs Prev` per metric makes tables unreadable
- Two divergent table code paths (normal vs comparison) increase bugs and maintenance

### Design

**2a. ag-Grid Integration**
Replace `st.dataframe` with `streamlit-aggrid` for all data tables. ag-Grid provides:
- **Custom cell renderers** — render value + delta badge in one cell: `45.2K ▲12.3%`
- **Sort-safe** — underlying value stays numeric, display is a renderer function
- **Resizable columns, search/filter, export to CSV** from the grid itself
- **Pin columns** — campaign/journey name pinned left, scrollable metric columns

When comparison mode is inactive: cell shows just the value.
When comparison mode is active: cell shows value + inline delta badge.

Delta badge styling (CSS in the cell renderer):
- `▲` in green (`#22C55E`) for positive change
- `▼` in red (`#EF4444`) for negative change
- `—` in gray for no change / N/A
- Badge text smaller (80% of value font size), right-aligned in cell

**2b. `render_table()` Component**
A single function in `utils.py` (or new `components/table.py`):

```python
def render_table(df, key=None, use_comparison=True, column_config=None, 
                 pin_columns=None, height=400):
    """Render a unified ag-Grid table with optional inline comparison deltas."""
```

Params:
- `df`: DataFrame to display
- `key`: Streamlit component key (unique per call site)
- `use_comparison`: if True and `ctx.comparison_result` exists, inject delta badges
- `column_config`: optional overrides for column headers, value formatters, width
- `pin_columns`: list of column names to pin left (default: first 1-2 identifier columns)
- `height`: grid height in px

**2c. Backward Compatibility**
- No table code is deleted — only wrapped. Existing page code that builds DataFrames still works
- ag-Grid replaces `st.dataframe()` calls, but the DataFrame construction logic stays untouched
- All existing filters, sorting, and metric selection flow through unchanged

### Files affected
- **New:** `components/table.py` — `render_table()` wrapper
- **Modified:** `utils.py` — add ag-Grid helper utilities
- **Modified:** All page files — replace `st.dataframe()` / `st.column_config` calls with `render_table()`
- **Added dependency:** `streamlit-aggrid`

---

## Section 3: Navigation & Page Reorganization

### Problem
- 15 pages in a flat list — overwhelming, no workflow guidance
- Mixed concerns: correlations next to segments next to export
- No clear "start here" page

### Design

**3a. Four-zone sidebar navigation**

```
🔍 Overview
   Automated Insights
   Executive Overview
   Marketing Actions

📈 Analysis
   Campaigns
   Journeys
   Channels (tabs: Channels, Failed Reasons)
   Segments
   Attribution
   A/B Testing
   Time Series (tabs: Time Series, Correlations)

🤖 AI & Forecasting
   Revenue Forecast
   Anomaly Detection
   AI Insights Lab

📤 Export
   Export Reports
```

**3b. Page merges (reducing from 15 to 11 pages)**
- **Correlations** → tab inside **Time Series** (they're time-adjacent analyses)
- **Failed Reasons** → tab inside **Channels** (it's channel-specific diagnostics)
- **Executive Overview** = current `Overview` page (renamed, made the default landing page)

**3c. Collapsible sidebar groups**
Streamlit's `st.navigation()` supports `st.Page()` grouping with `section` parameter. Each zone is a collapsible section. The sidebar shows section headers as clickable expanders.

**3d. Default landing page**
`Executive Overview` is the default page. User opens the app → sees KPIs + narrative summary first, then navigates to deeper analysis as needed.

### Files affected
- **Modified:** `app.py` — navigation structure changes to grouped `st.navigation()`
- **Renamed:** No file moves — just URL/display name changes via `st.Page(title=...)`
- **Modified:** `pages/08_time_series.py` — add Correlation tab
- **Modified:** `pages/07_channels.py` — add Failed Reasons tab

---

## Section 4: Visual Design System — 2026 Modern Look

### Problem
- Default Streamlit appearance — no brand identity, no visual hierarchy
- No dark mode
- Metrics scattered as raw text, not in structured cards
- Chart styling inconsistent with page design

### Design

**4a. Dark/Light Mode Toggle**
- Sidebar toggle persisted in `st.session_state["theme"]`
- Dark mode by default
- CSS variables swap on toggle — no page reload needed
- Plotly charts use matching background color (`#0F172A` dark / `#F8FAFC` light)

**4b. KPI Card Component**

```python
def render_kpi_card(label, value, delta=None, delta_description=None, icon=None, 
                    progress=None, color="primary"):
```

Renders a styled `st.container()` with:
- Icon + label on top line (small, muted)
- Large value in the middle (bold, 2rem)
- Optional delta badge (colored `▲`/`▼` with description)
- Optional mini progress bar (e.g., "78% of target")

Three cards per row via `st.columns(3)`.

**4c. Plotly Chart Styling Update**
Extend the existing `we_dashboard` template:
- Remove default grid lines or make them very faint (rgba white 0.08)
- Title inside the plot area (top-left, smaller font)
- Tooltips: consistent number formatting (comma-separated, 2 decimals)
- Chart background matches page theme background
- Hover label: rounded corners, shadow, dark bg on light mode and vice versa

**4d. Color Palette & Typography**

```
Primary:    #0EA5E9  (existing brand blue)
Success:    #22C55E  (green)
Warning:    #F59E0B  (amber)
Danger:     #EF4444  (red)
Info:       #6366F1  (indigo — new)
Background: #0F172A (dark) / #F8FAFC (light)
Surface:    #1E293B (dark) / #FFFFFF (light)
Border:     #334155 (dark) / #E2E8F0 (light)
Text:       #F1F5F9 (dark) / #0F172A (light)
Text Muted: #94A3B8 (dark) / #64748B (light)
```

Font stack: `Inter, -apple-system, BlinkMacSystemFont, sans-serif`

**4e. Implementation approach**
- `app.py` injects `<style>` block with CSS variables on every rerun (Streamlit's standard approach)
- Or use Streamlit's `.streamlit/config.toml` with `theme` section for basic theming
- CSS variables approach gives full control — dark mode toggle swaps `--bg` and `--surface` values

### Files affected
- **Modified:** `app.py` — inject global CSS + theme toggle
- **Modified:** `utils.py` — add `configure_theme()`, `render_kpi_card()`, `inject_global_styles()`
- **Modified:** `config.py` — update `COLORS` dict with extended palette
- **Modified:** `utils.py` — `configure_plotly_template()` updated with new palette

---

## Section 5: Export & Report System

### Problem
- Current export: single page, 2 download buttons (CSV, Excel with 7 raw sheets)
- No structure, no formatting, no narrative in exports
- No report-ready output — user manually copies to Google Slides
- Chart images are not exportable (Kaleido was removed for spawning popups)

### Design

**5a. Executive Report (PDF/HTML-ready Excel)**
A new formatted export option:
- **Cover sheet:** Report title, date range, filters applied, generated timestamp
- **KPI Summary:** 6-8 top metrics in a styled table with comparison deltas
- **Top 10 Campaigns:** Formatted table with inline rank badges
- **Channel Breakdown:** Per-channel metrics with conditional formatting (green/red for ↑/↓)
- **AI Narrative:** Auto-generated executive summary from `insights_engine`
- **Style:** Bold headers, frozen panes, auto-column-width, alternating row colors

**5b. Structured Data Layer (Foundation for Slides)**
All export functions return Python dicts with defined schemas:

```python
report_data = {
    "period": {"start": "2026-01-01", "end": "2026-03-31"},
    "filters": {...},
    "summary_metrics": [{"label": "Total Revenue", "value": 1245678, "delta": 0.123, ...}],
    "tables": {
        "top_campaigns": DataFrame,
        "channel_analysis": DataFrame,
        "journey_performance": DataFrame,
    },
    "chart_images": {
        "revenue_trend": bytes,  # PNG
        "channel_breakdown": bytes,
    },
    "narrative": "Executive summary text..."
}
```

This same data structure feeds future Google Slides generation — no re-computation needed.

**5c. Chart Image Export (Replacing Kaleido)**
- Use `plotly.io.to_image(fig, format='png')` — Plotly's built-in orca-based export
- Or install `kaleido` as a headless-only import (no subprocess popup issue if called correctly)
- Charts exported at 1920x1080 for slide insertion
- User downloads chart as PNG via button in chart toolbar or in the Export page

**5d. Batch Report Generator**
"Generate Monthly Report" button produces a zip:
- `Executive_Summary_2026_Q2.xlsx` (formatted multi-sheet)
- `Raw_Data_2026_Q2.csv`
- `Charts/` folder with individual PNGs
- Ready to share or import into Google Slides

### Files affected
- **Rewritten:** `pages/13_export.py` — new export UI with all options
- **New:** `export/report_builder.py` — structured report data assembly
- **New:** `export/excel_formatter.py` — Excel formatting (openpyxl styling)
- **New:** `export/chart_exporter.py` — Plotly → PNG conversion
- **Modified:** `utils.py` — remove stale `export_chart_image()` Kaleido path

---

## Section 6: AI Layer & API Key Integration

### Problem
- Existing AI features (Prophet, KMeans, narrative insights) are entirely local and rule-based
- No natural language interaction, no deep reasoning about data
- No upgrade path to LLM-powered analysis without rebuilding

### Design

**6a. AI Router (Pluggable Architecture)**

```
User Query / Trigger
       ↓
   AI Router
   (ai_bridge.py)
       ↓
   ┌───┴───┐
   │       │
   No Key  │  API Key Present
   │       │
   ↓       ↓
Rule Engine  LLM + Data Context
(local)     (OpenAI / Anthropic / etc.)
```

- `ai_bridge.py` checks `st.session_state["ai_config"]["api_key"]`
- If no key: falls through to existing local engines (`insights_engine.py`)
- If key present: builds a structured prompt with recent metrics + comparison data → calls LLM → parses structured JSON response

**6b. Settings UI**

A settings panel (in the sidebar or dedicated page):

```
AI Settings
  ─ Provider: [OpenAI ▼ | Anthropic ▼]
  ─ API Key:  [•••••••••••••••••]
  ─ Model:    [GPT-4o ▼ | Claude Sonnet ▼ | etc.]
  ─ Use AI for:
     ☑ Narrative insights
     ☑ Root cause analysis
     ☑ Slide content generation
     ☑ Q&A chatbot
  ─ [Test Connection]  [Save]
```

- API key stored in `st.session_state` only (never written to disk or DataFrame)
- "Test Connection" button validates the key with a minimal API call

**6c. LLM-Powered Upgrades**

| Feature | Local (no key) | LLM (with key) |
|---|---|---|
| Narrative insights | Templated: "Revenue ↑12% driven by Campaign X" | Nuanced: explains why, what changed, what to watch |
| Root cause analysis | N/A (not available) | "Conversions dropped 23% — likely causes: (1) delivery issue on SMS, (2) creative fatigue on Welcome Flow" |
| Slide content gen | N/A | "Generate a 5-slide Q2 summary" → structured content per slide |
| Q&A Chatbot | N/A | Ask questions in natural language, get answers with chart references |
| Anomaly explanation | "Campaign X is 2.3σ below mean" | "Campaign X underperformed because segment A had a 40% delivery drop after the ESP switch on June 15" |

**6d. Prompt & Context Structure**

LLM calls follow a strict structured prompt to ensure accuracy:

1. **System prompt:** "You are a marketing analytics AI assistant. Answer based on the provided data only. Do not make up metrics."
2. **Context:** Always includes:
   - Current period aggregate metrics (revenue, conversions, sends, delivery rate, CTR)
   - Previous period comparison (deltas)
   - Top 5 campaigns / channels / journeys by revenue
   - Recent anomalies detected by local rule engine
3. **Output schema:** JSON with defined fields (structured output parsing)
4. **Caching:** Per session, keyed by prompt hash — repeated questions return cached responses

### Files affected
- **New:** `ai_bridge.py` — router, LLM client, prompt builder, response parser
- **New:** `ai_config.py` — settings UI component, session state management
- **Modified:** `pages/01_automated_insights.py` — wire through AI router for narrative upgrades
- **Modified:** `pages/15_ai_insights.py` — wire AI router for forecast explanations

---

## Implementation Order

| Phase | Sections | Effort | Outcome |
|---|---|---|---|
| **Phase 1: Foundation** | Section 1 (Accuracy) + Section 2 (Tables) | ~1 week | Trustworthy numbers, sortable tables, inline comparison deltas |
| **Phase 2: UX Overhaul** | Section 3 (Nav) + Section 4 (Design System) | ~1 week | Modern look, logical navigation, dark mode |
| **Phase 3: Export** | Section 5 (Reports) | ~3-4 days | Formatted Excel, executive report, chart PNGs, batch zip |
| **Phase 4: AI Bridge** | Section 6 (Router + Settings) | ~3-4 days | API key setup, LLM-powered upgrades for narratives |
| **Phase 5: Polishing** | Google Slides API + Q&A chatbot | Future | Cloud slide generation, conversational analytics |

---

## Self-Review Check

- **Placeholders:** None. All sections specify concrete components, files, and behaviors.
- **Internal consistency:** Section 2 (unified ag-Grid table) assumes `streamlit-aggrid` as a dependency; Section 1c aligns with it (render-layer-only formatting). Section 5's export component feeds the future Slides API (Section 5b). Section 6's AI builds on existing `insights_engine.py`.
- **Scope:** Focused on the dashboard itself. Google Slides integration is explicitly deferred to Phase 5 (future). No database, authentication, or deployment concerns — those would be separate efforts.
- **Ambiguity check:** All feature descriptions are specific about what changes, what files are affected, and what the user sees. "Looks modern" is defined by the palette, card component, dark mode, and chart styling in Section 4.
