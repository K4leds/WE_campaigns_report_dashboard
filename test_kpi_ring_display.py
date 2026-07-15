"""Guards the KPI-ring percent display fix: fractional rates (0.87) must render
as '87.0%', not '0.9%'. Run: python test_kpi_ring_display.py"""
from slides_export import chart_kpi_ring


def test_percent_ring_scales_fraction_to_100():
    fig = chart_kpi_ring(0.87, 0.90, label="Delivery Rate", suffix="%")
    txt = fig.layout.annotations[0].text
    assert "87.0%" in txt, txt
    assert "0.9%" not in txt, txt


def test_conv_rate_ring():
    fig = chart_kpi_ring(0.05, 0.05, label="Conv. Rate", suffix="%")
    txt = fig.layout.annotations[0].text
    assert "5.0%" in txt, txt


def test_nonpercent_suffix_untouched():
    fig = chart_kpi_ring(4.2, 4.0, label="ROAS", suffix="x")
    txt = fig.layout.annotations[0].text
    assert "4.2x" in txt, txt


if __name__ == "__main__":
    test_percent_ring_scales_fraction_to_100()
    test_conv_rate_ring()
    test_nonpercent_suffix_untouched()
    print("ok")
