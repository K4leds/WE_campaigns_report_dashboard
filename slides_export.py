"""Builds the client-facing WebEngage review deck (.pptx). Python owns all
numbers and charts; slides_narrative.py owns prose. Never rendered server-side
— build_deck returns bytes for st.download_button."""
import functools
import io
import os
import re
import zipfile

import plotly.graph_objects as go
import plotly.io as pio
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
AMBER   = RGBColor(0xC9, 0x7A, 0x1E)

# Mirrors insights_engine.detect_performance_alerts (delivery <0.85 is
# critical, target is >0.90) and the ROAS tiering already used in
# pages/14_comparisons.py's channel-efficiency display.
BENCHMARK_DELIVERY_RATE = 0.90
BENCHMARK_ROAS_GOOD = 4.0
BENCHMARK_ROAS_OK = 2.0
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


def styled_table(slide, x, y, w, headers, rows, col_widths=None,
                 conditional_cols=None, data_bar_col=None, banded=True):
    """Draw a styled table with optional conditional formatting and data bars.

    v2 upgrades (BCG/McKinsey consulting-grade):
    - banded: alternating row colors for readability (default True).
    - conditional_cols: dict of {col_index: {"benchmark": value, "below": color, "above": color}}
      to color-code cells against a benchmark (e.g., delivery rate < 90% → red).
    - data_bar_col: column index to render an in-cell horizontal data bar,
      encoding the relative magnitude of each row's value in that column.

    Tables are the #1 data display in consulting decks — these small visual
    cues lift them from "spreadsheet dump" to "analyst-grade deliverable."
    """
    n = len(rows) + 1
    tbl = slide.shapes.add_table(n, len(headers), Inches(x), Inches(y),
                                 Inches(w), Inches(0.35 * n)).table
    tbl.first_row = False; tbl.horz_banding = False
    if col_widths:
        for i, cw in enumerate(col_widths):
            tbl.columns[i].width = Inches(cw)

    BAND_A = WHITE
    BAND_B = RGBColor(0xF6, 0xF9, 0xFB)  # 2% tint of brand blue — subtle

    def _cell(cell, s, color, font, bold, align, fill, row_idx=-1, col_idx=-1):
        # Apply conditional formatting if this column has rules
        cell_fill = fill
        cell_color = color
        if conditional_cols and col_idx in conditional_cols:
            rules = conditional_cols[col_idx]
            try:
                val = float(str(s).replace("SAR ", "").replace("%", "").replace("x", "").replace(",", ""))
                benchmark = rules.get("benchmark", 0)
                if val < benchmark:
                    cell_color = rules.get("below", RED)
                elif val > benchmark:
                    cell_color = rules.get("above", GREEN)
            except (ValueError, TypeError):
                pass

        cell.fill.solid(); cell.fill.fore_color.rgb = cell_fill
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        cell.margin_left = Inches(0.12); cell.margin_right = Inches(0.12)
        cell.margin_top = Inches(0.04); cell.margin_bottom = Inches(0.04)
        p = cell.text_frame.paragraphs[0]; p.alignment = align
        r = p.add_run(); r.text = str(s)
        r.font.size = Pt(11.5); r.font.color.rgb = cell_color
        r.font.name = font; r.font.bold = bold

    # Header row
    for c, s in enumerate(headers):
        _cell(tbl.cell(0, c), s, WHITE, F_MED, True,
              PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT, TBL_HDR)

    # Data rows
    for ri, row in enumerate(rows, start=1):
        row_fill = BAND_A if not banded or ri % 2 == 1 else BAND_B
        for c, s in enumerate(row):
            _cell(tbl.cell(ri, c), s, INK, F_REG, False,
                  PP_ALIGN.LEFT if c == 0 else PP_ALIGN.RIGHT,
                  row_fill, row_idx=ri - 1, col_idx=c)

    # Data bars — overlay a thin rectangle inside the cell
    if data_bar_col is not None and rows:
        # Find max value in that column for scaling
        try:
            vals = []
            for row in rows:
                raw = str(row[data_bar_col]).replace("SAR ", "").replace(",", "").replace("%", "").replace("x", "")
                try:
                    vals.append(float(raw))
                except ValueError:
                    vals.append(0)
            max_val = max(vals) if vals else 1
            if max_val > 0:
                for ri, row in enumerate(rows, start=1):
                    try:
                        raw = str(row[data_bar_col]).replace("SAR ", "").replace(",", "").replace("%", "").replace("x", "")
                        val = float(raw)
                    except ValueError:
                        val = 0
                    ratio = val / max_val if max_val > 0 else 0
                    cell = tbl.cell(ri, data_bar_col)
                    cell_x = Inches(x) + sum(Inches(cw) for cw in (col_widths or [])[:data_bar_col])
                    cell_w = Inches(col_widths[data_bar_col]) if col_widths else Inches(w / len(headers))
                    bar_w = cell_w * 0.55 * ratio
                    bar_y = Inches(y) + Inches(0.35 * ri) + Inches(0.28)
                    bar_h = Inches(0.04)
                    rect(slide,
                         cell_x.inches + 0.12, bar_y.inches,
                         bar_w.inches, bar_h.inches,
                         fill=BRAND if ratio > 0.5 else BRAND_D,
                         line=None)
        except Exception:
            pass  # Data bars are cosmetic — never block the table

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


@functools.lru_cache(maxsize=1)
def _ensure_chrome():
    """Ensure kaleido has a Chrome. On Streamlit Cloud packages.txt:chromium is
    unreliable for kaleido v1, so plotly.io.get_chrome() is the sanctioned path.
    Best-effort and cached: if it fails, fall back to any system chromium."""
    try:
        pio.get_chrome()
    except Exception:
        pass


def fig_to_png(fig) -> bytes:
    """Plotly -> PNG at 3x for crisp slides. Needs a system Chromium for kaleido
    (see packages.txt). On Streamlit Community Cloud, packages.txt: chromium
    alone is unreliable for kaleido v1, so we best-effort call
    plotly.io.get_chrome() once (cached) before rendering. Raises if Chromium
    is missing; build_deck degrades per spec."""
    _ensure_chrome()
    return fig.to_image(format="png", scale=3)


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
    fig.update_layout(font=dict(family="DM Sans", size=13, color="#1B2A32"),
                      paper_bgcolor="white", plot_bgcolor="white",
                      margin=dict(l=10, r=150, t=10, b=20), width=880, height=360)
    return fig


# ── v2: BCG-style horizontal bar chart — the #1 consulting chart type ──
def chart_bar_horizontal(labels, values, title="", sort_desc=True,
                         value_prefix="SAR ", highlight_idx=None):
    """Horizontal bar chart — BCG's preferred format for rankings.
    Bars are easier to read left-to-right than vertical bars, and labels
    sit naturally alongside without rotation.

    highlight_idx: if set, color that bar differently (e.g., the top performer).
    """
    pairs = list(zip(labels, values))
    if sort_desc:
        pairs.sort(key=lambda x: x[1], reverse=True)
    labels_sorted = [p[0] for p in pairs]
    values_sorted = [p[1] for p in pairs]

    colors = ["#006FA2"] * len(labels_sorted)
    if highlight_idx is not None and 0 <= highlight_idx < len(colors):
        colors[highlight_idx] = "#1E9E62"  # green for highlighted bar

    fig = go.Figure(go.Bar(
        y=labels_sorted, x=values_sorted, orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{value_prefix}{v:,.0f}" for v in values_sorted],
        textposition="outside", textfont=dict(family="DM Sans", size=13, color="#1B2A32"),
        hovertemplate=f"{value_prefix}%{{x:,.0f}}<extra></extra>",
    ))
    fig.update_layout(
        font=_PLOTLY_FONT, paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(l=10, r=120, t=20 if title else 10, b=10),
        width=1120, height=380,
        xaxis=dict(showgrid=True, gridcolor="#EEF2F4", zeroline=False,
                   showticklabels=False, showline=False),
        yaxis=dict(showgrid=False, showline=False, tickfont=dict(size=13),
                   categoryorder="total ascending" if sort_desc else None),
        title=dict(text=title, font=dict(size=13, color="#6C7A82")) if title else None,
    )
    return fig


# ── v2: Donut chart — for channel share, attribution split ──
def chart_donut(labels, values, center_text="", hole=0.55):
    """Donut chart for part-to-whole relationships (channel share, attribution).
    Consulting-grade: muted palette, center label, no legend clutter."""
    colors = ["#006FA2", "#1685B3", "#3FA0C6", "#66B6D6", "#1E9E62",
              "#C9D4DA", "#9BB8C9", "#4472C4", "#005379", "#A8C5D6"]
    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=hole,
        marker=dict(colors=colors[:len(labels)], line=dict(color="white", width=2)),
        textinfo="label+percent", textfont=dict(family="DM Sans", size=12, color="#1B2A32"),
        direction="clockwise", sort=True,
    ))
    if center_text:
        fig.add_annotation(text=center_text, x=0.5, y=0.5, showarrow=False,
                          font=dict(family="DM Sans", size=18, color="#1B2A32"))
    fig.update_layout(
        font=_PLOTLY_FONT, paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(l=20, r=20, t=20, b=20), width=600, height=400,
        showlegend=False,
    )
    return fig


# ── v2: KPI progress ring — for benchmark vs actual (delivery rate, ROAS) ──
def chart_kpi_ring(actual, benchmark, label="", suffix="%", color=None):
    """A single-value progress/donut ring showing actual vs benchmark.
    The ring fills proportionally to actual/benchmark. Green if >= benchmark,
    amber if within 10%, red if below.

    Perfect for delivery rate, conversion rate, or ROAS benchmarks on exec summary.

    Note: color can be a CSS hex string or a python-pptx RGBColor — both are
    converted to hex strings for Plotly compatibility.
    """
    pct = min(actual / benchmark, 1.0) if benchmark > 0 else 1.0
    remaining = 1.0 - pct

    if color is None:
        if actual >= benchmark:
            color = "#1E9E62"  # GREEN
        elif actual >= benchmark * 0.9:
            color = "#C97A1E"  # AMBER
        else:
            color = "#C03A2B"  # RED
    # Normalize RGBColor → hex string for Plotly
    if hasattr(color, '__iter__') and not isinstance(color, str):
        color = f"#{color[0]:02X}{color[1]:02X}{color[2]:02X}"

    fig = go.Figure(go.Pie(
        values=[pct, remaining], hole=0.72,
        marker=dict(colors=[color, "#EEF2F4"], line=dict(width=0)),
        textinfo="none", sort=False,
    ))
    # avg_delivery_rate / avg_conversion_rate arrive as fractions (0.87), so a
    # "%" ring must scale to 0-100 for display — otherwise 0.87 prints as "0.9%".
    display_val = f"{actual * 100:.1f}%" if suffix == "%" else f"{actual:.1f}{suffix}"
    fig.add_annotation(
        text=f"<b>{display_val}</b><br><span style='font-size:10px;color:#6C7A82'>{label}</span>",
        x=0.5, y=0.5, showarrow=False,
        font=dict(family="DM Sans", size=22, color="#1B2A32"),
    )
    fig.update_layout(
        paper_bgcolor="white", plot_bgcolor="white",
        margin=dict(l=0, r=0, t=0, b=0), width=160, height=160,
        showlegend=False,
    )
    return fig


# ── v2: Chart callout — overlay a key insight directly on the chart ──
def _put_chart_with_callout(slide, fig, x, y, height, callout_text=""):
    """Render chart + place a styled callout box with the key takeaway.
    BCG/McKinsey signature: every chart has a callout that answers 'so what?'"""
    try:
        png = fig_to_png(fig)
    except Exception:
        return False
    slide.shapes.add_picture(io.BytesIO(png), Inches(x), Inches(y), height=Inches(height))
    if callout_text:
        # Callout box: bottom-right of the chart area, semi-transparent
        callout_w = 3.8
        callout_h = 0.55
        callout_x = x + 6.5  # right side
        callout_y = y + height - callout_h - 0.15
        rect(slide, callout_x, callout_y, callout_w, callout_h,
             fill=RGBColor(0xFF, 0xFF, 0xFF), line=BRAND, line_w=1.2)
        rect(slide, callout_x, callout_y, 0.06, callout_h, fill=BRAND)
        text(slide, callout_x + 0.18, callout_y + 0.08, callout_w - 0.3, callout_h - 0.16,
             (callout_text, 10, INK, F_MED, False, None))
    return True


_SLIDE_NUMBER = [0]  # mutable counter so each slide gets a unique number


def _header(slide, eyebrow, title, period_label, story=None, action_title=None):
    """Slide header with BCG-style action titles and consulting-grade layout.

    v2 upgrades:
    - action_title: when provided, replaces the static title with a punchy,
      assertion-style headline (BCG/McKinsey standard). The old 'title' becomes
      the eyebrow. Example: instead of "CHANNEL PERFORMANCE / Where Revenue
      Comes From", you get "EMAIL DROVE 62% OF ALL REVENUE THIS PERIOD" with
      "CHANNEL PERFORMANCE" as the small eyebrow above it.
    - Slide number rendered bottom-right.
    - Footer line with client branding.
    """
    _SLIDE_NUMBER[0] += 1

    rect(slide, 0.55, 0.42, 0.10, 0.62, fill=BRAND)
    text(slide, 0.78, 0.40, 8.5, 0.3, (eyebrow, 10.5, BRAND, F_MED, True, 2.2))

    if action_title:
        # Action title: larger, assertion-style, full slide width
        text(slide, 0.76, 0.60, 12.0, 0.55,
             (action_title, 20, INK, F_BOLD, True, None))
    else:
        text(slide, 0.76, 0.62, 9.5, 0.5, (title, 24, INK, F_BOLD, True, None))

    if story:
        text(slide, 0.78, 1.06, 9.5, 0.25, (story, 11, MUTED, F_REG, False, None))
    if period_label:
        text(slide, 9.2, 0.52, 3.6, 0.5,
             [[("Reporting period  ", 10.5, MUTED, F_REG, False, None)],
              [(period_label, 13, INK, F_MED, True, None)]], align=PP_ALIGN.RIGHT)
    rect(slide, 0.55, 1.28, 12.23, 0.02, fill=LINE)

    # Slide number — bottom-right, subtle
    text(slide, 12.30, 7.10, 0.70, 0.25,
         (str(_SLIDE_NUMBER[0]), 8.5, MUTED, F_REG, False, None),
         align=PP_ALIGN.RIGHT)

    # Footer line — subtle separator with brand accent
    rect(slide, 0.55, 7.05, 12.23, 0.008, fill=LINE)
    text(slide, 0.60, 7.10, 4.0, 0.20,
         ("WebEngage  ·  Confidential", 7.5, MUTED, F_REG, False, None))


def _put_chart(slide, fig, x, y, height):
    """Render + place a chart; skip silently if Chromium/kaleido unavailable."""
    try:
        png = fig_to_png(fig)
    except Exception:
        return False
    slide.shapes.add_picture(io.BytesIO(png), Inches(x), Inches(y), height=Inches(height))
    return True


_FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
# Each entry: (typeface name as used in runs, {style tag: filename})
_EMBED_FONTS = [
    ("DM Sans", {"regular": "DMSans-Regular.ttf", "bold": "DMSans-Bold.ttf"}),
    ("DM Sans Medium", {"regular": "DMSans-Medium.ttf"}),
]
_R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_CT_FONT = "application/x-fontdata"
_RT_FONT = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/font"


def embed_fonts(pptx_bytes: bytes) -> bytes:
    """Add DM Sans TTFs as embedded font parts. Best-effort: on any error returns
    the original bytes unchanged (deck still valid, just not embedded)."""
    try:
        src = zipfile.ZipFile(io.BytesIO(pptx_bytes))
        pres = src.read("ppt/presentation.xml").decode("utf-8")
        rels = src.read("ppt/_rels/presentation.xml.rels").decode("utf-8")
        ct = src.read("[Content_Types].xml").decode("utf-8")

        existing_rids = [int(x) for x in re.findall(r'Id="rId(\d+)"', rels)]
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
        pres_tag_end = pres.index(">", pres.index("<p:presentation"))
        if "xmlns:r=" not in pres[:pres_tag_end]:
            pres = pres.replace("<p:presentation ", f'<p:presentation xmlns:r="{_R_NS}" ', 1)
        pres = pres.replace("<p:presentation ", "<p:presentation embedTrueTypeFonts=\"1\" ", 1)
        if "<p:defaultTextStyle" in pres:
            pres = pres.replace("<p:defaultTextStyle", lst + "<p:defaultTextStyle", 1)
        else:
            pres = re.sub(r"(<p:notesSz[^>]*/>)", r"\1" + lst, pres, count=1)

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
