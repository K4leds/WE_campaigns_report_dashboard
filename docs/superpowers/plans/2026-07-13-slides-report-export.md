# WebEngage Client Review Deck Export — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a one-click Export-tab button that builds a branded, client-facing PowerPoint deck (10 slides) from the currently-filtered dashboard data.

**Architecture:** Python computes every number/chart (`insights_engine`, `analysis.py`); `python-pptx` builds the `.pptx` with an exact brand theme, embedded DM Sans, and Morph transitions; DeepSeek (via a new `slides_narrative.py`, reusing `llm_narrative`'s discipline) writes only prose/recommendations and never a number. Charts render Plotly→PNG via kaleido. The file is served through `st.download_button` — never rendered server-side.

**Tech Stack:** Python, Streamlit, python-pptx, Plotly + kaleido, pandas, DeepSeek (OpenAI-compatible via `openai`).

## Global Constraints

- Runs server-side on **Streamlit Community Cloud**: build files only, no COM/PowerPoint rendering in shipped code.
- **Anti-hallucination boundary:** the LLM only ever receives pre-computed fact sheets; it never produces a number, table value, or chart. If DeepSeek is unavailable, deterministic fallbacks from `insights_engine` are used and no error is shown.
- **Deck respects the active filter:** always operate on `ctx.filtered_df`.
- **Theme (exact):** slide bg `#FFFFFF`; brand `#006FA2` (dark `#005379`); table header fill `#4472C4` + white text, white cells, hairline `#E3E8EB`; body ink `#1B2A32`; muted `#6C7A82`; insight fill `#EAF3F8`; delta up `#1E9E62`, down `#C03A2B`. Font **DM Sans** (Regular/Medium/Bold), embedded. 16:9 (13.333in × 7.5in).
- **Slides are modular:** one `add_slide_*(prs, ctx_data, narr)` per slide + an ordered list in `build_deck`; adding a slide later = appending a function.
- **WebEngage feature recommendations** must be chosen only from the curated real-feature list; never invent a feature.
- **Latest libraries:** add `python-pptx` at latest stable; keep `kaleido`/`plotly` current. Verify current kaleido-on-Streamlit-Cloud chromium setup with the developing-with-streamlit skill / Context7 / Firecrawl during Task 1.
- **Fonts embedded hard-required for v1.** (Note: Google Slides drops embedded fonts on import but has DM Sans natively — embed still matters for desktop PowerPoint viewers.)

---

### Task 1: Dependencies, fonts, and Streamlit-Cloud chart rendering

**Files:**
- Modify: `requirements.txt`
- Create: `packages.txt`
- Create: `assets/fonts/DMSans-Regular.ttf`, `assets/fonts/DMSans-Medium.ttf`, `assets/fonts/DMSans-Bold.ttf`
- Create: `tests/test_kaleido_export.py`

**Interfaces:**
- Produces: DM Sans TTFs at `assets/fonts/` (consumed by Task 6 embedding + Task 3 chart font), a working Plotly→PNG pipeline.

- [ ] **Step 1: Add python-pptx to requirements.txt**

Append this line to `requirements.txt` (verify latest version first with `pip index versions python-pptx` or Context7; use the current stable, e.g. `python-pptx>=1.0.2`):

```
python-pptx>=1.0.2
```

- [ ] **Step 2: Create packages.txt for kaleido's Chromium**

kaleido 1.x needs a system Chromium on Streamlit Cloud. Create `packages.txt`:

```
chromium
```

Then confirm the *current* correct approach — kaleido-v1 chrome provisioning changes. Use the developing-with-streamlit skill and Context7 (`resolve-library-id` → `kaleido`/`plotly`) and, if needed, Firecrawl search "streamlit cloud kaleido chromium 2026". If the verified guidance differs (e.g. an env var like `BROWSER_PATH`, or `plotly_get_chrome`), record it as a comment in `packages.txt` and in `slides_export.py`'s `_fig_to_png` docstring.

- [ ] **Step 3: Bundle DM Sans TTFs**

Copy the three DM Sans static TTFs into `assets/fonts/`. They already exist locally at `%LOCALAPPDATA%\Microsoft\Windows\Fonts\DMSans-{Regular,Medium,Bold}.ttf` (installed during design), or download from `https://raw.githubusercontent.com/googlefonts/dm-fonts/main/Sans/fonts/ttf/DMSans-{Regular,Medium,Bold}.ttf`.

```bash
mkdir -p assets/fonts
cp "$LOCALAPPDATA/Microsoft/Windows/Fonts/DMSans-Regular.ttf" assets/fonts/
cp "$LOCALAPPDATA/Microsoft/Windows/Fonts/DMSans-Medium.ttf"  assets/fonts/
cp "$LOCALAPPDATA/Microsoft/Windows/Fonts/DMSans-Bold.ttf"    assets/fonts/
```

- [ ] **Step 4: Write the kaleido smoke test**

Create `tests/test_kaleido_export.py`:

```python
def test_plotly_exports_png_bytes():
    import plotly.graph_objects as go
    fig = go.Figure(go.Bar(x=[1, 2, 3], y=[4, 5, 6]))
    png = fig.to_image(format="png", scale=2)
    assert isinstance(png, (bytes, bytearray)) and len(png) > 1000
    assert png[:8] == b"\x89PNG\r\n\x1a\n"  # PNG magic number


def test_dm_sans_fonts_present():
    import os
    for name in ("DMSans-Regular.ttf", "DMSans-Medium.ttf", "DMSans-Bold.ttf"):
        p = os.path.join("assets", "fonts", name)
        assert os.path.exists(p) and os.path.getsize(p) > 10000
```

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_kaleido_export.py -v`
Expected: both PASS (locally Chrome is present; on Streamlit Cloud, Step 2 provides it).

- [ ] **Step 6: Commit**

```bash
git add requirements.txt packages.txt assets/fonts tests/test_kaleido_export.py
git commit -m "chore: add python-pptx, chromium (kaleido), bundle DM Sans; smoke test"
```

---

### Task 2: `slides_export.py` theme + layout helpers

**Files:**
- Create: `slides_export.py`
- Create: `tests/test_slides_helpers.py`

**Interfaces:**
- Produces:
  - Theme `RGBColor` constants: `BRAND, BRAND_D, TBL_HDR, INK, MUTED, LINE, WHITE, INSIGHT, GREEN, RED`; font names `F_REG, F_MED, F_BOLD`.
  - `new_deck() -> Presentation` (16:9, sets core size)
  - `blank_slide(prs) -> slide`
  - `rect(slide, x, y, w, h, fill=None, line=None, line_w=0.75, shape=MSO_SHAPE.RECTANGLE) -> shape`
  - `text(slide, x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, sp_after=0) -> textbox` where `runs` is a single run-tuple `(str, size, color, font, bold, letter_spacing_pt|None)`, a list of run-tuples (one line), or a list of lines.
  - `styled_table(slide, x, y, w, headers, rows, col_widths=None)` — header fill `TBL_HDR`, white cells.
  - `stat_tile(slide, x, y, w, h, label, value, delta, delta_color)`
  - `insight_box(slide, x, y, w, h, title, body)`
  - `recommendation_strip(slide, y, text_body, feature_name)`
  - `add_morph(slide)`
  - `fig_to_png(fig) -> bytes`

- [ ] **Step 1: Write failing tests**

Create `tests/test_slides_helpers.py`:

```python
import slides_export as sx


def test_new_deck_is_16x9():
    prs = sx.new_deck()
    # 13.333in x 7.5in in EMU (914400 EMU/in)
    assert abs(prs.slide_width - 12192000) < 2000
    assert abs(prs.slide_height - 6858000) < 2000


def test_blank_slide_and_helpers_run():
    prs = sx.new_deck()
    slide = sx.blank_slide(prs)
    sx.rect(slide, 0, 0, 13.333, 7.5, fill=sx.WHITE)
    sx.text(slide, 0.5, 0.5, 6, 0.5, ("Hello", 24, sx.INK, sx.F_BOLD, True, None))
    sx.stat_tile(slide, 0.5, 1.5, 2.9, 1.2, "REVENUE", "SAR 1.2K", "▲ 5%", sx.GREEN)
    sx.styled_table(slide, 0.5, 3.0, 5.0, ["A", "B"], [("x", "1"), ("y", "2")])
    sx.insight_box(slide, 7.0, 3.0, 5.0, 1.0, "KEY INSIGHT", "Body text.")
    sx.recommendation_strip(slide, 6.4, "Do the thing.", "Journey Designer")
    sx.add_morph(slide)
    # morph transition present in slide xml
    from pptx.oxml.ns import qn
    assert slide.element.find(qn("p:transition")) is not None


def test_fig_to_png_returns_png_bytes():
    import plotly.graph_objects as go
    png = sx.fig_to_png(go.Figure(go.Bar(x=[1], y=[1])))
    assert png[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_slides_helpers.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'slides_export'`).

- [ ] **Step 3: Implement `slides_export.py` helpers**

Create `slides_export.py` (helpers proven in the approved design sample):

```python
"""Builds the client-facing WebEngage review deck (.pptx). Python owns all
numbers and charts; slides_narrative.py owns prose. Never rendered server-side
— build_deck returns bytes for st.download_button."""
import io

import plotly.graph_objects as go
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.oxml.ns import qn
from pptx.oxml import parse_xml

# ---- Theme ----
BRAND   = RGBColor(0x00, 0x6F, 0xA2)
BRAND_D = RGBColor(0x00, 0x53, 0x79)
TBL_HDR = RGBColor(0x44, 0x72, 0xC4)
INK     = RGBColor(0x1B, 0x2A, 0x32)
MUTED   = RGBColor(0x6C, 0x7A, 0x82)
LINE    = RGBColor(0xE3, 0xE8, 0xEB)
WHITE   = RGBColor(0xFF, 0xFF, 0xFF)
INSIGHT = RGBColor(0xEA, 0xF3, 0xF8)
GREEN   = RGBColor(0x1E, 0x9E, 0x62)
RED     = RGBColor(0xC0, 0x3A, 0x2B)
PILL_LBL = RGBColor(0xBF, 0xE1, 0xEF)
F_REG, F_MED, F_BOLD = "DM Sans", "DM Sans Medium", "DM Sans"


def new_deck() -> Presentation:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    return prs


def blank_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def rect(slide, x, y, w, h, fill=None, line=None, line_w=0.75, shape=MSO_SHAPE.RECTANGLE):
    sp = slide.shapes.add_shape(shape, Inches(x), Inches(y), Inches(w), Inches(h))
    sp.shadow.inherit = False
    if fill is None:
        sp.fill.background()
    else:
        sp.fill.solid(); sp.fill.fore_color.rgb = fill
    if line is None:
        sp.line.fill.background()
    else:
        sp.line.color.rgb = line; sp.line.width = Pt(line_w)
    return sp


def text(slide, x, y, w, h, runs, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, sp_after=0):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame; tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    if isinstance(runs, tuple):
        runs = [[runs]]
    elif isinstance(runs, list) and runs and isinstance(runs[0], tuple):
        runs = [runs]
    for i, line_runs in enumerate(runs):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align; p.space_after = Pt(sp_after); p.space_before = Pt(0)
        for (s, size, color, font, bold, ls) in line_runs:
            r = p.add_run(); r.text = s
            r.font.size = Pt(size); r.font.color.rgb = color
            r.font.name = font; r.font.bold = bold
            if ls is not None:
                r._r.get_or_add_rPr().set('spc', str(int(ls * 100)))
    return tb


def stat_tile(slide, x, y, w, h, label, value, delta, delta_color):
    rect(slide, x, y, w, h, fill=WHITE, line=LINE, line_w=1.0)
    rect(slide, x, y, w, 0.055, fill=BRAND)
    text(slide, x + 0.22, y + 0.16, w - 0.4, 0.25, (label, 9.5, MUTED, F_MED, True, 1.4))
    text(slide, x + 0.20, y + 0.40, w - 0.4, 0.5, (value, 23, INK, F_BOLD, True, None))
    if delta:
        text(slide, x + 0.22, y + h - 0.32, w - 0.4, 0.25,
             (delta, 9.5, delta_color, F_MED, True, None))


def styled_table(slide, x, y, w, headers, rows, col_widths=None):
    n = len(rows) + 1
    tbl = slide.shapes.add_table(n, len(headers), Inches(x), Inches(y),
                                 Inches(w), Inches(0.35 * n)).table
    tbl.first_row = False; tbl.horz_banding = False
    if col_widths:
        for i, cw in enumerate(col_widths):
            tbl.columns[i].width = Inches(cw)

    def _cell(cell, s, color, font, bold, align, fill):
        cell.fill.solid(); cell.fill.fore_color.rgb = fill
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = Inches(0.12); cell.margin_right = Inches(0.12)
        cell.margin_top = Inches(0.04); cell.margin_bottom = Inches(0.04)
        p = cell.text_frame.paragraphs[0]; p.alignment = align
        r = p.add_run(); r.text = str(s)
        r.font.size = Pt(11.5); r.font.color.rgb = color
        r.font.name = font; r.font.bold = bold

    for c, s in enumerate(headers):
        _cell(tbl.cell(0, c), s, WHITE, F_MED, True,
              PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT, TBL_HDR)
    for ri, row in enumerate(rows, start=1):
        for c, s in enumerate(row):
            _cell(tbl.cell(ri, c), s, INK, F_REG, False,
                  PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT, WHITE)
    return tbl


def insight_box(slide, x, y, w, h, title, body):
    rect(slide, x, y, w, h, fill=INSIGHT)
    rect(slide, x, y, 0.07, h, fill=BRAND)
    text(slide, x + 0.28, y + 0.13, w - 0.5, 0.25, (title, 9.5, BRAND, F_MED, True, 1.8))
    text(slide, x + 0.28, y + 0.40, w - 0.5, h - 0.5, (body, 11, INK, F_REG, False, None))


def recommendation_strip(slide, y, text_body, feature_name):
    rect(slide, 0.55, y, 12.23, 0.72, fill=BRAND)
    text(slide, 0.85, y + 0.10, 8.4, 0.5,
         [[("RECOMMENDATION", 9.5, PILL_LBL, F_MED, True, 1.8)],
          [(text_body, 11.5, WHITE, F_MED, False, None)]],
         anchor=MSO_ANCHOR.MIDDLE)
    if feature_name:
        rect(slide, 9.55, y + 0.19, 3.05, 0.34, fill=WHITE, shape=MSO_SHAPE.ROUNDED_RECTANGLE)
        text(slide, 9.55, y + 0.185, 3.05, 0.34,
             [[("WEBENGAGE  ", 9, MUTED, F_MED, True, 1.0),
               (feature_name, 10.5, BRAND, F_BOLD, True, None)]],
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def add_morph(slide):
    xml = (
        '<p:transition xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main" '
        'xmlns:p14="http://schemas.microsoft.com/office/powerpoint/2010/main" '
        'p14:dur="700" spd="med"><p14:morph option="byObject"/></p:transition>'
    )
    cSld = slide.element.find(qn('p:cSld'))
    slide.element.insert(list(slide.element).index(cSld) + 1, parse_xml(xml))


def fig_to_png(fig) -> bytes:
    """Plotly -> PNG at 3x for crisp slides. Needs a system Chromium for kaleido
    (see packages.txt). Raises if Chromium is missing; build_deck degrades per spec."""
    return fig.to_image(format="png", scale=3)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_slides_helpers.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_export.py tests/test_slides_helpers.py
git commit -m "feat: slides_export theme + pptx layout helpers"
```

---

### Task 3: Chart builders (trend, channels, journey Sankey)

**Files:**
- Modify: `slides_export.py`
- Create: `tests/test_slides_charts.py`

**Interfaces:**
- Consumes: theme constants from Task 2; `analysis.channel_analysis`, `analysis.time_series_analysis`, `analysis.get_top_journeys`.
- Produces:
  - `journey_funnel_stages(df, journey_name) -> list[tuple[str, int]]` — ordered stages `[("Sent", n), ("Delivered", n), ("Opened", n), ("Clicked", n), ("Converted", n)]` from summed columns `Sent, Delivered, Unique Impressions, Unique Clicks, (Selected|Unique) Conversions` for that journey.
  - `chart_trend(ts_df, metric) -> go.Figure`
  - `chart_channels(chan_df) -> go.Figure`
  - `chart_journey_sankey(stages) -> go.Figure`

- [ ] **Step 1: Write failing tests**

Create `tests/test_slides_charts.py`:

```python
import pandas as pd
import plotly.graph_objects as go
import slides_export as sx


def _df():
    return pd.DataFrame({
        "Journey Name": ["Cart Recovery"] * 3 + ["Winback"] * 2,
        "Channel": ["Email", "Web Push", "SMS", "Email", "Web Push"],
        "Reporting Period Start Date": pd.to_datetime(
            ["2026-06-01", "2026-06-02", "2026-06-03", "2026-06-01", "2026-06-02"]),
        "Sent": [1000, 900, 800, 500, 400],
        "Delivered": [960, 880, 700, 480, 390],
        "Unique Impressions": [400, 500, 200, 150, 120],
        "Unique Clicks": [120, 200, 40, 30, 25],
        "Unique Conversions": [30, 55, 8, 6, 5],
    })


def test_funnel_stages_monotonic_and_labeled():
    stages = sx.journey_funnel_stages(_df(), "Cart Recovery")
    labels = [s[0] for s in stages]
    assert labels == ["Sent", "Delivered", "Opened", "Clicked", "Converted"]
    vals = [s[1] for s in stages]
    assert vals[0] == 2700 and all(v >= 0 for v in vals)


def test_chart_builders_return_figures():
    df = _df()
    from analysis import time_series_analysis, channel_analysis
    assert isinstance(sx.chart_trend(time_series_analysis(df), "Unique Conversions"), go.Figure)
    assert isinstance(sx.chart_channels(channel_analysis(df)), go.Figure)
    stages = sx.journey_funnel_stages(df, "Cart Recovery")
    assert isinstance(sx.chart_journey_sankey(stages), go.Figure)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_slides_charts.py -v`
Expected: FAIL (`AttributeError: module 'slides_export' has no attribute 'journey_funnel_stages'`).

- [ ] **Step 3: Implement chart builders in `slides_export.py`**

Append to `slides_export.py`:

```python
_PLOTLY_FONT = dict(family="DM Sans", size=15, color="#1B2A32")


def journey_funnel_stages(df, journey_name):
    sub = df[df["Journey Name"] == journey_name]
    conv_col = "Selected Conversions" if "Selected Conversions" in sub.columns else "Unique Conversions"
    spec = [("Sent", "Sent"), ("Delivered", "Delivered"), ("Opened", "Unique Impressions"),
            ("Clicked", "Unique Clicks"), ("Converted", conv_col)]
    return [(label, int(sub[col].sum()) if col in sub.columns else 0) for label, col in spec]


def chart_trend(ts_df, metric):
    x = ts_df.iloc[:, 0]
    y = ts_df[metric] if metric in ts_df.columns else ts_df.iloc[:, 1]
    fig = go.Figure(go.Scatter(
        x=x, y=y, mode="lines", fill="tozeroy",
        line=dict(color="#006FA2", width=3),
        fillcolor="rgba(0,111,162,0.12)"))
    fig.update_layout(
        font=_PLOTLY_FONT, paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(l=48, r=16, t=12, b=36), width=1120, height=430,
        xaxis=dict(showgrid=False, showline=True, linecolor="#E3E8EB"),
        yaxis=dict(showgrid=True, gridcolor="#EEF2F4", zeroline=False))
    return fig


def chart_channels(chan_df):
    conv_col = "Selected Conversions" if "Selected Conversions" in chan_df.columns else "Unique Conversions"
    d = chan_df.sort_values(conv_col, ascending=True)
    fig = go.Figure(go.Bar(
        x=d[conv_col], y=d["Channel"], orientation="h",
        marker_color="#006FA2", text=d[conv_col], textposition="auto"))
    fig.update_layout(
        font=_PLOTLY_FONT, paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(l=8, r=24, t=12, b=24), width=720, height=430,
        xaxis=dict(showgrid=True, gridcolor="#EEF2F4", zeroline=False),
        yaxis=dict(showgrid=False))
    return fig


def chart_journey_sankey(stages):
    # stages: [(label, value), ...] progression; each step also produces a drop-off.
    labels, node_colors, src, tgt, val, link_colors = [], [], [], [], [], []
    prog_blue = ["#006FA2", "#1685B3", "#3FA0C6", "#66B6D6", "#1E9E62"]
    for i, (lab, _) in enumerate(stages):
        labels.append(lab); node_colors.append(prog_blue[min(i, len(prog_blue) - 1)])
    drop_start = len(labels)
    for i in range(len(stages) - 1):
        cur, nxt = stages[i][1], stages[i + 1][1]
        # progression link
        src.append(i); tgt.append(i + 1); val.append(max(nxt, 0))
        link_colors.append("rgba(0,111,162,0.38)")
        # drop-off link to a grey terminal
        drop = max(cur - nxt, 0)
        labels.append(f"Lost at {stages[i][0]}"); node_colors.append("#C9D4DA")
        src.append(i); tgt.append(drop_start + i); val.append(drop)
        link_colors.append("rgba(180,190,196,0.30)")
    fig = go.Figure(go.Sankey(
        arrangement="snap",
        node=dict(label=labels, color=node_colors, pad=18, thickness=16,
                  line=dict(color="white", width=0)),
        link=dict(source=src, target=tgt, value=val, color=link_colors)))
    fig.update_layout(font=dict(family="DM Sans", size=15, color="#1B2A32"),
                      paper_bgcolor="white", plot_bgcolor="white",
                      margin=dict(l=8, r=8, t=10, b=22), width=900, height=380)
    return fig
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_slides_charts.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_export.py tests/test_slides_charts.py
git commit -m "feat: deck chart builders (trend, channels, journey sankey)"
```

---

### Task 4: `slides_narrative.py` — AI prose, recommendations, WebEngage feature map

**Files:**
- Create: `slides_narrative.py`
- Create: `tests/test_slides_narrative.py`

**Interfaces:**
- Consumes: `llm_narrative._get_client`, `llm_narrative.is_configured` (reuse the DeepSeek client + discipline).
- Produces:
  - `WEBENGAGE_FEATURES: dict[str, str]` — finding-type slug → feature name.
  - `recommend_feature(action: dict) -> str` — deterministic pick from the map (never invents), used as pill fallback and default.
  - `narrate_summary(summary_facts: dict) -> str` — prose exec read; falls back to a deterministic sentence from `headline_metrics` if DeepSeek unavailable.
  - `narrate_findings(items: list[dict], kind: str) -> list[str]` — one short line per opportunity/alert; deterministic fallback = each item's `title: message`.
  - `narrate_recommendation(action: dict) -> tuple[str, str]` — returns `(sentence, feature_name)`; deterministic fallback uses `action['action']` + `recommend_feature`.

- [ ] **Step 1: Write failing tests**

Create `tests/test_slides_narrative.py` (DeepSeek stubbed off → exercises deterministic path):

```python
import slides_narrative as sn


def test_feature_lookup_only_returns_real_features(monkeypatch):
    action = {"title": "Low delivery on SMS", "type": "deliverability"}
    feat = sn.recommend_feature(action)
    assert feat in sn.WEBENGAGE_FEATURES.values()


def test_narrate_summary_deterministic_fallback(monkeypatch):
    monkeypatch.setattr(sn, "is_configured", lambda: False)
    facts = {"headline_metrics": {"total_revenue": 412800, "total_conversions": 3410},
             "period": "Jun 01 - Jun 30, 2026"}
    out = sn.narrate_summary(facts)
    assert isinstance(out, str) and "3,410" in out.replace(",", "") or "3410" in out.replace(",", "")


def test_narrate_findings_fallback(monkeypatch):
    monkeypatch.setattr(sn, "is_configured", lambda: False)
    items = [{"title": "Web Push strong", "message": "6.8% conv rate"}]
    lines = sn.narrate_findings(items, "opportunity")
    assert lines and "Web Push" in lines[0]


def test_narrate_recommendation_fallback(monkeypatch):
    monkeypatch.setattr(sn, "is_configured", lambda: False)
    action = {"title": "Fix cart drop", "action": "Add a 2h nudge", "type": "journey"}
    sentence, feature = sn.narrate_recommendation(action)
    assert "nudge" in sentence.lower()
    assert feature in sn.WEBENGAGE_FEATURES.values()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/Scripts/python.exe -m pytest tests/test_slides_narrative.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'slides_narrative'`).

- [ ] **Step 3: Implement `slides_narrative.py`**

```python
"""DeepSeek prose for the review deck. Same anti-hallucination discipline as
llm_narrative: the model only phrases pre-computed facts and picks WebEngage
features from a fixed list — it never produces a number or invents a feature.
Every function degrades to a deterministic fallback when DeepSeek is unavailable."""
from llm_narrative import _get_client, is_configured

# Curated real WebEngage features. Keys are finding-type slugs; values are the
# exact product names allowed to appear on a slide.
WEBENGAGE_FEATURES = {
    "deliverability":  "Send Time Optimization",
    "engagement":      "Personalization",
    "channel":         "Preferred Channel",
    "fatigue":         "Frequency Capping",
    "journey":         "Journey Designer",
    "segmentation":    "RFM Segments",
    "conversion":      "Catalog & Recommendations",
    "testing":         "A/B Testing",
    "retention":       "Predictive Segments",
    "default":         "Journey Designer",
}

_FEATURE_LIST_STR = ", ".join(sorted(set(WEBENGAGE_FEATURES.values())))


def recommend_feature(action: dict) -> str:
    t = (action.get("type") or "").lower()
    if t in WEBENGAGE_FEATURES:
        return WEBENGAGE_FEATURES[t]
    blob = f"{action.get('title','')} {action.get('message','')} {action.get('action','')}".lower()
    for key, feat in WEBENGAGE_FEATURES.items():
        if key != "default" and key in blob:
            return feat
    return WEBENGAGE_FEATURES["default"]


def _fmt_metrics(m: dict) -> str:
    parts = []
    if "total_revenue" in m:
        parts.append(f"SAR {m['total_revenue']:,.0f} revenue")
    if "total_conversions" in m:
        parts.append(f"{m['total_conversions']:,.0f} conversions")
    return ", ".join(parts)


def narrate_summary(summary_facts: dict) -> str:
    metrics = summary_facts.get("headline_metrics", {})
    fallback = f"This period delivered {_fmt_metrics(metrics)}."
    if not is_configured():
        return fallback
    client = _get_client()
    prompt = ("Write 2-3 plain-English sentences summarizing this WebEngage period for a "
              "client. Use ONLY these facts, never invent numbers.\n"
              f"Metrics: {metrics}\nPeriod: {summary_facts.get('period')}")
    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-flash", max_tokens=300,
            messages=[{"role": "system", "content": "You are a marketing analyst. No markdown."},
                      {"role": "user", "content": prompt}])
        return resp.choices[0].message.content.strip() or fallback
    except Exception:
        return fallback


def narrate_findings(items: list, kind: str) -> list:
    fallback = [f"{it.get('title','')}: {it.get('message','')}".strip(": ") for it in items[:4]]
    if not items or not is_configured():
        return fallback
    client = _get_client()
    bullets = "\n".join(f"- {it.get('title','')}: {it.get('message','')}" for it in items[:4])
    prompt = (f"Rewrite each {kind} as one crisp client-facing sentence citing its numbers. "
              f"Return one per line, no bullets, no markdown.\n{bullets}")
    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-flash", max_tokens=400,
            messages=[{"role": "system", "content": "Marketing analyst. Keep each line under 22 words."},
                      {"role": "user", "content": prompt}])
        lines = [l.strip("-• ").strip() for l in resp.choices[0].message.content.splitlines() if l.strip()]
        return lines or fallback
    except Exception:
        return fallback


def narrate_recommendation(action: dict) -> tuple:
    feature = recommend_feature(action)
    fallback = (action.get("action") or action.get("message") or action.get("title", "")).strip()
    if not is_configured():
        return fallback, feature
    client = _get_client()
    prompt = ("Turn this finding into ONE actionable client-facing recommendation sentence. "
              f"You may reference this WebEngage feature if relevant: {feature}. "
              f"Allowed features only: {_FEATURE_LIST_STR}. No markdown.\n"
              f"Finding: {action.get('title','')} — {action.get('action') or action.get('message','')}")
    try:
        resp = client.chat.completions.create(
            model="deepseek-v4-flash", max_tokens=160,
            messages=[{"role": "system", "content": "Marketing analyst. One sentence, under 26 words."},
                      {"role": "user", "content": prompt}])
        return (resp.choices[0].message.content.strip() or fallback), feature
    except Exception:
        return fallback, feature
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/test_slides_narrative.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add slides_narrative.py tests/test_slides_narrative.py
git commit -m "feat: slides_narrative DeepSeek prose + curated WebEngage feature map"
```

---

### Task 5: Slide builders + `build_deck` orchestration

**Files:**
- Modify: `slides_export.py`
- Create: `tests/test_build_deck.py`

**Interfaces:**
- Consumes: all Task 2/3 helpers; `slides_narrative`; `insights_engine.generate_executive_summary`, `insights_engine.generate_top_actions`; `analysis.{top_campaigns,get_top_journeys,channel_analysis,time_series_analysis}`.
- Produces: `build_deck(df, client_name="", period_label=None) -> bytes` — a 10-slide `.pptx` as bytes. Charts that fail to render are skipped (slide still built); DeepSeek failures fall back to deterministic text.

- [ ] **Step 1: Write failing test**

Create `tests/test_build_deck.py`:

```python
import io
import pandas as pd
import pytest
from pptx import Presentation
import slides_export as sx
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


def test_build_deck_has_10_slides_with_client_name():
    data = sx.build_deck(_df(), client_name="Acme Co", period_label="Jun 2026")
    assert isinstance(data, (bytes, bytearray)) and len(data) > 5000
    prs = Presentation(io.BytesIO(data))
    assert len(prs.slides) == 10
    # client name appears on the title slide
    texts = [sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame]
    assert any("Acme Co" in t for t in texts)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_build_deck.py -v`
Expected: FAIL (`AttributeError: module 'slides_export' has no attribute 'build_deck'`).

- [ ] **Step 3: Implement slide builders + `build_deck`**

Append to `slides_export.py`:

```python
import pandas as pd
from insights_engine import generate_executive_summary, generate_top_actions, format_sar
from analysis import (top_campaigns, get_top_journeys, channel_analysis,
                      time_series_analysis)
import slides_narrative as sn


def _header(slide, eyebrow, title, period_label):
    rect(slide, 0.55, 0.42, 0.10, 0.62, fill=BRAND)
    text(slide, 0.78, 0.40, 8.5, 0.3, (eyebrow, 10.5, BRAND, F_MED, True, 2.2))
    text(slide, 0.76, 0.62, 9.5, 0.5, (title, 24, INK, F_BOLD, True, None))
    if period_label:
        text(slide, 9.2, 0.52, 3.6, 0.5,
             [[("Reporting period  ", 10.5, MUTED, F_REG, False, None)],
              [(period_label, 13, INK, F_MED, True, None)]], align=PP_ALIGN.RIGHT)
    rect(slide, 0.55, 1.28, 12.23, 0.02, fill=LINE)


def _put_chart(slide, fig, x, y, height):
    """Render + place a chart; skip silently if Chromium/kaleido unavailable."""
    try:
        png = fig_to_png(fig)
    except Exception:
        return False
    slide.shapes.add_picture(io.BytesIO(png), Inches(x), Inches(y), height=Inches(height))
    return True


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
    insight_box(slide, 0.55, 3.05, 12.23, 3.2, "THE READ", prose)
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
    _put_chart(slide, chart_channels(chan), 0.5, 1.7, 4.7)
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
        _put_chart(slide, chart_journey_sankey(stages), 0.45, 2.4, 3.6)
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


def build_deck(df, client_name="", period_label=None) -> bytes:
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
    return buf.getvalue()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_build_deck.py -v`
Expected: PASS (10 slides, client name present).

- [ ] **Step 5: Commit**

```bash
git add slides_export.py tests/test_build_deck.py
git commit -m "feat: 10-slide build_deck orchestration + slide builders"
```

---

### Task 6: Embed DM Sans into the deck

**Files:**
- Modify: `slides_export.py`
- Create: `tests/test_font_embed.py`

**Interfaces:**
- Consumes: TTFs at `assets/fonts/`; `build_deck` output bytes.
- Produces: `embed_fonts(pptx_bytes: bytes) -> bytes` — returns a new `.pptx` with DM Sans embedded (adds `/ppt/fonts/fontN.fntdata` parts + `<p:embeddedFontLst>` in `presentation.xml`). `build_deck` calls it before returning.

- [ ] **Step 1: Write failing test**

Create `tests/test_font_embed.py`:

```python
import io
import zipfile
import pandas as pd
import pytest
import slides_export as sx
import slides_narrative as sn


@pytest.fixture(autouse=True)
def _no_ai(monkeypatch):
    monkeypatch.setattr(sn, "is_configured", lambda: False)


def _df():
    return pd.DataFrame({
        "Campaign Name": ["C1", "C2"], "Journey Name": ["J", "J"],
        "Channel": ["Email", "SMS"],
        "Reporting Period Start Date": pd.to_datetime(["2026-06-01", "2026-06-02"]),
        "Sent": [100, 80], "Delivered": [95, 70], "Unique Impressions": [40, 20],
        "Unique Clicks": [12, 4], "Unique Conversions": [3, 1], "Revenue (SAR)": [300, 80]})


def test_deck_has_embedded_fonts():
    data = sx.build_deck(_df(), client_name="Acme", period_label="Jun 2026")
    zf = zipfile.ZipFile(io.BytesIO(data))
    names = zf.namelist()
    assert any(n.startswith("ppt/fonts/") and n.endswith(".fntdata") for n in names)
    pres_xml = zf.read("ppt/presentation.xml").decode("utf-8")
    assert "embeddedFontLst" in pres_xml
    assert "DM Sans" in pres_xml
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_font_embed.py -v`
Expected: FAIL (no `ppt/fonts/` parts yet).

- [ ] **Step 3: Implement `embed_fonts` and call it from `build_deck`**

Append to `slides_export.py`:

```python
import os
import zipfile

_FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
# Each entry: (typeface name as used in runs, {style tag: filename})
_EMBED_FONTS = [
    ("DM Sans", {"regular": "DMSans-Regular.ttf", "bold": "DMSans-Bold.ttf"}),
    ("DM Sans Medium", {"regular": "DMSans-Medium.ttf"}),
]
_P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CT_FONT = "application/x-fontdata"
_RT_FONT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"


def embed_fonts(pptx_bytes: bytes) -> bytes:
    """Add DM Sans TTFs as embedded font parts. Best-effort: on any error returns
    the original bytes unchanged (deck still valid, just not embedded)."""
    try:
        src = zipfile.ZipFile(io.BytesIO(pptx_bytes))
        names = set(src.namelist())
        pres = src.read("ppt/presentation.xml").decode("utf-8")
        rels = src.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        ct = src.read("[Content_Types].xml").decode("utf-8")

        existing_rids = [int(x) for x in __import__("re").findall(r'Id="rId(\d+)"', rels)]
        next_rid = (max(existing_rids) + 1) if existing_rids else 1

        font_parts, rels_add, lst_entries, idx = {}, [], [], 1
        for typeface, styles in _EMBED_FONTS:
            font_xml = f'<p:embeddedFont><p:font typeface="{typeface}"/>'
            for style_tag, fname in styles.items():
                path = os.path.join(_FONT_DIR, fname)
                if not os.path.exists(path):
                    continue
                part_name = f"ppt/fonts/font{idx}.fntdata"
                with open(path, "rb") as fh:
                    font_parts[part_name] = fh.read()
                rid = f"rId{next_rid}"; next_rid += 1
                rels_add.append(
                    f'<Relationship Id="{rid}" Type="{_RT_FONT}" Target="fonts/font{idx}.fntdata"/>')
                tag = "regular" if style_tag == "regular" else style_tag
                font_xml += f'<p:{tag} r:id="{rid}"/>'
                idx += 1
            font_xml += "</p:embeddedFont>"
            lst_entries.append(font_xml)

        if not font_parts:
            return pptx_bytes

        # inject embeddedFontLst + embedTrueTypeFonts attr into presentation.xml
        lst = f'<p:embeddedFontLst>{"".join(lst_entries)}</p:embeddedFontLst>'
        if "xmlns:r=" not in pres.split(">", 1)[0]:
            pres = pres.replace("<p:presentation ", f'<p:presentation xmlns:r="{_R_NS}" ', 1)
        pres = pres.replace("<p:presentation ", "<p:presentation embedTrueTypeFonts=\"1\" ", 1)
        pres = pres.replace("<p:sldIdLst", lst + "<p:sldIdLst", 1)

        rels = rels.replace("</Relationships>", "".join(rels_add) + "</Relationships>")
        if _CT_FONT not in ct:
            ct = ct.replace("</Types>",
                            f'<Default Extension="fntdata" ContentType="{_CT_FONT}"/></Types>')

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for n in src.namelist():
                if n == "ppt/presentation.xml":
                    z.writestr(n, pres)
                elif n == "ppt/_rels/presentation.xml.rels":
                    z.writestr(n, rels)
                elif n == "[Content_Types].xml":
                    z.writestr(n, ct)
                else:
                    z.writestr(n, src.read(n))
            for part_name, data in font_parts.items():
                z.writestr(part_name, data)
        return out.getvalue()
    except Exception:
        return pptx_bytes
```

Then change the end of `build_deck` from `return buf.getvalue()` to:

```python
    return embed_fonts(buf.getvalue())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_font_embed.py tests/test_build_deck.py -v`
Expected: all PASS (embedded fonts present; 10-slide test still green).

- [ ] **Step 5: Manually verify the .pptx opens in PowerPoint**

Generate a deck to disk and open it (local check only — not part of shipped behavior):

```bash
.venv/Scripts/python.exe -c "import pandas as pd, slides_export as sx; open('scratchpad/_verify.pptx','wb').write(sx.build_deck(pd.read_csv('<a real cleaned CSV>'), 'Test Client'))"
```

Open `scratchpad/_verify.pptx` in PowerPoint: confirm 10 slides, DM Sans renders, tables `#4472C4`, Sankey fits, Morph animates on transition. If Chromium is missing locally, charts are skipped — that's expected degradation.

- [ ] **Step 6: Commit**

```bash
git add slides_export.py tests/test_font_embed.py
git commit -m "feat: embed DM Sans into the exported deck"
```

---

### Task 7: Wire the Export tab

**Files:**
- Modify: `pages/13_export.py`

**Interfaces:**
- Consumes: `slides_export.build_deck`; `ctx.filtered_df`.

- [ ] **Step 1: Add the deck section to `pages/13_export.py`**

Insert after the `st.header("Export")` line (keep the existing CSV/Excel buttons below):

```python
import slides_export

st.subheader("Client Review Deck (PowerPoint)")
client_name = st.text_input("Client / brand name", value="", key="deck_client")
if st.button("Generate Client Review Deck"):
    if filtered_df is None or filtered_df.empty:
        st.warning("No data for the current filters — adjust filters and try again.")
    else:
        with st.spinner("Building deck (rendering charts)…"):
            try:
                deck_bytes = slides_export.build_deck(filtered_df, client_name=client_name)
                st.session_state["deck_bytes"] = deck_bytes
            except Exception as e:
                st.error(f"Could not build the deck: {e}")
if st.session_state.get("deck_bytes"):
    safe = (client_name or "WebEngage").replace(" ", "_")
    st.download_button(
        "Download Deck (.pptx)", st.session_state["deck_bytes"],
        file_name=f"WebEngage_Review_{safe}.pptx",
        mime="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        key="deck_dl")
```

- [ ] **Step 2: Smoke-run the page imports**

Run: `.venv/Scripts/python.exe -c "import ast; ast.parse(open('pages/13_export.py').read()); print('parse OK')"`
Expected: `parse OK`.

- [ ] **Step 3: Run the app and exercise the button**

Run: `.venv/Scripts/python.exe -m streamlit run app.py` (or the project's run skill), open the Export page, set a client name, click Generate, download, open the file. Confirm the deck matches the theme and has 10 slides.

- [ ] **Step 4: Commit**

```bash
git add pages/13_export.py
git commit -m "feat: add Client Review Deck export button to Export tab"
```

---

### Task 8: Full-suite verification

**Files:** none (verification only)

- [ ] **Step 1: Run the whole deck test suite**

Run: `.venv/Scripts/python.exe -m pytest tests/test_kaleido_export.py tests/test_slides_helpers.py tests/test_slides_charts.py tests/test_slides_narrative.py tests/test_build_deck.py tests/test_font_embed.py -v`
Expected: all PASS.

- [ ] **Step 2: Confirm no regressions in existing tests**

Run: `.venv/Scripts/python.exe -m pytest -q`
Expected: existing suite still green (or unchanged from baseline).

- [ ] **Step 3: Deploy-config sanity check**

Confirm `requirements.txt` includes `python-pptx`, `packages.txt` contains `chromium`, and `assets/fonts/` has the three TTFs committed. On first Streamlit Cloud deploy, generate a deck and confirm charts render (Chromium present); if they don't, apply the verified fallback from Task 1 Step 2 (matplotlib chart path or corrected chromium provisioning).

---

## Self-Review

**Spec coverage:** Title/exec/trend/channels/campaigns/journeys/working/risk/recommendations/action = 10 slides (§6) → Task 5. Segments dropped ✓. Theme (§5) → Task 2 constants. Anti-hallucination (§2) → Task 4 fallbacks + Task 5 stub test. kaleido/Chromium (§3.2) → Task 1 + `_put_chart` degradation. Font embedding (§8, hard-required) → Task 6. Morph (§10) → `add_morph`. WebEngage feature map (§7) → Task 4. Modular slides / future growth → per-slide functions + ordered `build_deck`. Export UX (§11) → Task 7. Graceful degradation (§9) → empty-df guard (Task 7), chart skip (Task 5), AI fallback (Task 4). Testing (§12) → Tasks 5/6/8. All covered.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the one `<a real cleaned CSV>` and `<verified fallback>` are explicit manual-input markers in local-only verification steps, not shipped code.

**Type consistency:** `build_deck(df, client_name="", period_label=None) -> bytes`, `fig_to_png`, `journey_funnel_stages`, `recommend_feature`, `narrate_summary/findings/recommendation`, `embed_fonts` names are consistent across defining and consuming tasks. `narrate_recommendation` returns `(sentence, feature)` and is consumed as such in Task 5.
