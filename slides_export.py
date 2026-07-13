"""Builds the client-facing WebEngage review deck (.pptx). Python owns all
numbers and charts; slides_narrative.py owns prose. Never rendered server-side
— build_deck returns bytes for st.download_button."""
import functools
import io

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
