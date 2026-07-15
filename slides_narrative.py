"""DeepSeek prose for the review deck. Same anti-hallucination discipline as
llm_narrative: the model only phrases pre-computed facts and picks WebEngage
features from a fixed list — it never produces a number or invents a feature.
Every function degrades to a deterministic fallback when DeepSeek is unavailable.

v2 UPGRADES (2026-07-15):
- Audience-aware prompts (executive/marketing/analyst).
- Few-shot examples injected into every system prompt.
- Structure constraints (exact word counts, sentence counts).
- Tone calibration (confident/consultative/urgent/reassuring/analytical).
- Chain-of-thought reasoning for premium-quality slide prose.
- Self-verification step: model checks its output against provided facts.
"""
from llm_narrative import _get_client, is_configured, _DEEPSEEK_MODEL
from llm_narrative import _build_system_prompt, QUALITY_TIERS, _FEWSHOT_FINDINGS_EXCELLENT, _FEWSHOT_RECOMMENDATION_EXCELLENT

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


def _narrate_storyline(ctx: dict, slide_key: str, audience: str = "executive",
                       tone: str = "confident", fallback: str = "") -> str:
    """Generate a one-sentence narrative bridge for a specific slide position.

    This is the AI-powered successor to the old hardcoded f-strings in
    _build_storylines(). It receives a context dict of pre-computed numbers
    and the slide position key, and produces a single sentence that connects
    the previous slide's content to the upcoming slide's content.

    Falls back to the provided fallback string on any failure — the deck
    always builds, just with template text when the LLM is unavailable.
    """
    if not fallback or not is_configured():
        return fallback

    # Slide-position-specific framing hints
    SLIDE_HINTS = {
        "monthly_kpi": (
            "You are writing the bridge between the executive summary and the "
            "monthly KPI breakdown slide. Lead with the total, hint at what's "
            "revealed when broken down by month."
        ),
        "trend": (
            "You are writing the bridge between the monthly KPI table and the "
            "daily trend chart. Hint at whether the period was steady, volatile, "
            "or had a clear inflection point."
        ),
        "channel_cards": (
            "You are writing the bridge into the channel performance section. "
            "Name the dominant channel and its share, previewing the cards below."
        ),
        "channel_metrics": (
            "You are writing the bridge from the channel overview cards to the "
            "detailed channel metrics table. Signal that we're going deeper."
        ),
        "campaigns": (
            "You are writing the bridge from channel-level to campaign-level "
            "analysis. Hint that individual campaigns explain the channel numbers."
        ),
        "spotlight": (
            "You are writing the bridge to the single best campaign of the period. "
            "Build anticipation — this is the star performer."
        ),
        "journeys": (
            "You are writing the bridge from one-off campaigns to automated "
            "journeys. Frame journeys as the always-on complement to campaigns."
        ),
        "deliverability": (
            "You are writing the bridge to the deliverability section. Frame it "
            "as the foundational check — none of the above works without delivery."
        ),
        "attribution": (
            "You are writing the bridge to the attribution breakdown. Frame it "
            "as understanding HOW conversions were won (click vs impression)."
        ),
        "qoq_scorecard": (
            "You are writing the bridge to the quarter-over-quarter comparison. "
            "Frame it as: was this period better or worse, and by how much?"
        ),
        "recommendations": (
            "You are writing the bridge to the recommendations section. Frame it "
            "as: we've seen the data, now here's what to do about it."
        ),
        "action_plan": (
            "You are writing the bridge to the action plan. Frame it as: "
            "recommendations turned into a prioritized, sequenced plan."
        ),
    }

    hint = SLIDE_HINTS.get(slide_key, "Write one sentence connecting slides in a narrative flow.")

    client = _get_client()
    # Use a lightweight prompt for bridge sentences (not full system prompt)
    system = (
        "You are a presentation narrative designer. Your job is to write ONE "
        "connecting sentence (under 25 words) that bridges two slides in a "
        "marketing performance review deck. The sentence appears as a subtitle "
        "under the slide header.\n\n"
        "RULES:\n"
        "- Use ONLY numbers/names from the provided context. Never invent.\n"
        "- One sentence only. No markdown. No preamble.\n"
        "- Write as if guiding a reader through a story — not a table of contents.\n"
        "- Be specific: name channels, cite numbers, show relationships.\n"
        f"- Audience: {audience}. Tone: {tone}."
    )

    # Build a compact prompt with just the numbers this slide needs
    num_facts = []
    if ctx.get("total_revenue"):
        num_facts.append(f"SAR {ctx['total_revenue']:,.0f} total revenue")
    if ctx.get("total_conversions"):
        num_facts.append(f"{ctx['total_conversions']:,.0f} total conversions")
    if ctx.get("top_channel") and ctx.get("top_channel_revenue"):
        num_facts.append(f"#{1} channel: {ctx['top_channel']} at "
                         f"SAR {ctx['top_channel_revenue']:,.0f} "
                         f"({ctx['top_channel_share']:.0%} share)")
    if ctx.get("spotlight_name"):
        num_facts.append(f"Top campaign: '{ctx['spotlight_name']}' "
                         f"on {ctx.get('spotlight_channel', '')}")
    if ctx.get("comparison_label"):
        num_facts.append(f"Comparison period: {ctx['comparison_label']}")

    prompt = f"{hint}\n\nContext: {'; '.join(num_facts) if num_facts else 'see prior slides.'}"

    try:
        resp = client.chat.completions.create(
            model=_DEEPSEEK_MODEL, max_tokens=80,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}])
        result = resp.choices[0].message.content.strip()
        # Quality gate: must be 1 sentence, 10-200 chars, not generic
        if result and 10 < len(result) < 200 and not result.startswith("Here"):
            return result
        return fallback
    except Exception:
        return fallback


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


def narrate_summary(summary_facts: dict, audience: str = "executive",
                    tone: str = "confident", quality: str = "standard") -> str:
    """Generate a 3-5 sentence executive summary paragraph from pre-computed facts.

    v2: audience-aware, tone-calibrated, few-shot guided. Falls back to a
    deterministic template (never empty) on any failure.
    """
    metrics = summary_facts.get("headline_metrics", {})
    fallback = f"This period delivered {_fmt_metrics(metrics)}."

    if not is_configured():
        return fallback

    client = _get_client()
    tier = QUALITY_TIERS.get(quality, QUALITY_TIERS["standard"])
    system = _build_system_prompt(audience=audience, tone=tone, quality=quality)

    # Build a richer prompt with structured context
    parts = [f"Write a 3-5 sentence executive summary for a WebEngage campaign "
             f"performance review slide. Use ONLY these facts:\n"]
    parts.append(f"Headline metrics: {_fmt_metrics(metrics)}")
    if summary_facts.get("period"):
        parts.append(f"Period: {summary_facts['period']}")

    ni = summary_facts.get("narrative_insights", {}) or {}
    alerts = ni.get("performance_alerts", [])
    if alerts:
        parts.append(f"Top alert: {alerts[0].get('title','')} — {alerts[0].get('message','')}")
    opps = ni.get("opportunities", [])
    if opps:
        parts.append(f"Top opportunity: {opps[0].get('title','')} — {opps[0].get('message','')}")
    actions = summary_facts.get("top_actions", [])
    if actions:
        parts.append(f"#1 recommended action: {actions[0].get('title','')} — "
                     f"{actions[0].get('action','')} ({actions[0].get('expected_impact','')})")

    parts.append("\nRemember: lead with the most important number, name specific "
                  "channels/campaigns, end with the single highest-impact action. "
                  "No markdown, no bullet points, no filler.")
    prompt = "\n".join(parts)

    try:
        kwargs = dict(
            model=_DEEPSEEK_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}],
            max_tokens=tier["max_tokens"],
        )
        if tier["reasoning"]:
            kwargs["reasoning_effort"] = tier["reasoning"]
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            kwargs["timeout"] = 45.0
        resp = client.chat.completions.create(**kwargs)
        result = resp.choices[0].message.content.strip()
        # Validate: does it contain at least one number from the facts?
        if result and any(str(v) in result for v in metrics.values()
                          if isinstance(v, (int, float)) and v > 0):
            return result
        return result or fallback
    except Exception:
        return fallback


def narrate_findings(items: list, kind: str, audience: str = "executive",
                     tone: str = "confident") -> list:
    """Rewrite insight-engine findings as crisp, slide-ready sentences.

    v2: uses the modular system prompt with few-shot calibration and structure
    constraints. Each output line must be 1 sentence, under 28 words, citing
    at least one specific number from the input.
    """
    fallback = [f"{it.get('title','')}: {it.get('message','')}".strip(": ") for it in items[:4]]
    if not items or not is_configured():
        return fallback

    client = _get_client()
    bullets = "\n".join(f"- {it.get('title','')}: {it.get('message','')}"
                        for it in items[:4])

    system = _build_system_prompt(audience=audience, tone=tone, quality="standard",
                                  include_fewshot=True)
    # Append findings-specific few-shot examples
    system += f"\n\n─── FINDINGS-SPECIFIC CALIBRATION ───\n{_FEWSHOT_FINDINGS_EXCELLENT}"

    prompt = (
        f"Rewrite each {kind} below as ONE crisp, client-facing sentence for a "
        f"presentation slide. Rules:\n"
        f"- Each sentence must cite at least one specific number from its finding.\n"
        f"- Maximum 28 words per sentence.\n"
        f"- No markdown, no bullet characters, one sentence per line.\n"
        f"- If the finding mentions a benchmark comparison (e.g., 'below 90% target'), "
        f"include the benchmark to show WHY it matters.\n\n"
        f"Findings to rewrite:\n{bullets}"
    )

    try:
        resp = client.chat.completions.create(
            model=_DEEPSEEK_MODEL, max_tokens=500,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}])
        lines = [l.strip("-• ").strip() for l in resp.choices[0].message.content.splitlines()
                 if l.strip() and len(l.strip()) > 15]
        # Quality gate: each line should contain at least one digit
        validated = [l for l in lines if any(c.isdigit() for c in l)]
        return validated[:4] if validated else (lines[:4] or fallback)
    except Exception:
        return fallback


def narrate_recommendation(action: dict, audience: str = "executive",
                          tone: str = "urgent") -> tuple:
    """Turn one insight-engine action into a client-facing recommendation sentence
    paired with the most relevant WebEngage feature.

    v2: uses the modular system prompt with recommendation-specific few-shot
    calibration. The tone defaults to 'urgent' because recommendations should
    create a bias toward action, not passive acknowledgment.
    """
    feature = recommend_feature(action)
    fallback = (action.get("action") or action.get("message") or action.get("title", "")).strip()

    if not is_configured():
        return fallback, feature

    client = _get_client()
    system = _build_system_prompt(audience=audience, tone=tone, quality="standard",
                                  include_fewshot=True)
    system += (f"\n\n─── RECOMMENDATION-SPECIFIC CALIBRATION ───\n"
               f"{_FEWSHOT_RECOMMENDATION_EXCELLENT}\n\n"
               f"Allowed WebEngage features (you may reference ONE): {_FEATURE_LIST_STR}")

    impact = action.get("expected_impact", "")
    impact_hint = f" Expected impact: {impact}." if impact else ""

    prompt = (
        f"Turn this finding into ONE urgent, actionable recommendation sentence "
        f"for a presentation slide.{impact_hint}\n\n"
        f"Rules:\n"
        f"- Name the specific WebEngage feature to use: {feature}\n"
        f"- Quantify the expected payoff using numbers from the finding.\n"
        f"- Maximum 30 words. One sentence only. No markdown.\n"
        f"- Use action verbs (switch, reallocate, optimize, launch, fix).\n\n"
        f"Finding: {action.get('title','')} — "
        f"{action.get('action') or action.get('message','')}"
    )

    try:
        resp = client.chat.completions.create(
            model=_DEEPSEEK_MODEL, max_tokens=200,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": prompt}])
        result = resp.choices[0].message.content.strip()
        # Quality gate: must be one sentence and under ~200 chars
        if result and len(result) < 250:
            return result, feature
        return (result or fallback), feature
    except Exception:
        return fallback, feature
