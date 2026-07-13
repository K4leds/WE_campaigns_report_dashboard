import io
import zipfile
import pandas as pd
import pytest
import slides_deck_content as sx
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
