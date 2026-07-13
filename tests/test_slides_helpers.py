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
