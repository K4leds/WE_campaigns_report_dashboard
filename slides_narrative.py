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
