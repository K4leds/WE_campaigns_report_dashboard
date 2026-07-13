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
