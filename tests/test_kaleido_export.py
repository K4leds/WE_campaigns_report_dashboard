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
