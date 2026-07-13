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
