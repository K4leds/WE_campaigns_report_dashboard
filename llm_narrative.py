"""Optional LLM prose layer on top of insights_engine's deterministic analysis.

insights_engine.py computes every number here (thresholds, dollar-impact
scores, alerts) -- this module is never asked to invent a figure. It only
takes the already-computed facts from generate_executive_summary() and asks
DeepSeek to write them up as one readable paragraph, for the "just read it
for me" use case. The structured alert/opportunity/action lists elsewhere on
the page stay exactly as insights_engine renders them -- this is additive,
not a replacement.

Fully optional: with no DEEPSEEK_API_KEY configured (or on any API failure),
generate_ai_summary() returns None and the caller simply doesn't render this
section. The rest of the dashboard is completely unaffected either way.
"""
import os

import streamlit as st

# DeepSeek is OpenAI-API-compatible via this base_url; deepseek-v4-flash is the
# current non-thinking (fast/cheap) model name -- deepseek-chat/deepseek-reasoner
# are deprecated 2026-07-24.
_DEEPSEEK_BASE_URL = "https://api.deepseek.com"
_DEEPSEEK_MODEL = "deepseek-v4-flash"

_SYSTEM_PROMPT = (
    "You are a marketing analyst writing a short, plain-English executive summary "
    "from pre-computed facts about a WebEngage marketing campaign report. "
    "Use ONLY the numbers, channel names, journey names, and campaign names given below "
    "-- never invent, estimate, or round differently than what's provided. "
    "Write 3-4 sentences of flowing prose, no bullet points, no headers, no markdown. "
    "Keep the entire response under 100 words and always end on a complete sentence -- "
    "prioritize finishing your thought over including every fact."
)


def _get_client():
    api_key = None
    try:
        api_key = st.secrets.get("DEEPSEEK_API_KEY")
    except Exception:
        pass
    api_key = api_key or os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None
    return OpenAI(api_key=api_key, base_url=_DEEPSEEK_BASE_URL, timeout=20.0)


def _format_metric(key: str, value) -> str:
    if not isinstance(value, (int, float)):
        return f"{key}: {value}"
    if key in ("avg_delivery_rate", "avg_ctr", "avg_conversion_rate"):
        return f"{key}: {value:.1%}"
    if key in ("total_revenue",):
        return f"{key}: {value:,.0f} SAR"
    return f"{key}: {value:,.0f}"


def _build_prompt(summary_facts: dict) -> str:
    lines = []

    metrics = summary_facts.get("headline_metrics", {})
    if metrics:
        lines.append("Headline metrics: " + ", ".join(_format_metric(k, v) for k, v in metrics.items()))
        period = summary_facts.get("period")
        if period:
            lines.append(f"Reporting period: {period}")

    narrative = summary_facts.get("narrative_insights", {}) or {}

    headlines = narrative.get("headline_insights", [])
    if headlines:
        lines.append("Headline findings:")
        for item in headlines[:3]:
            lines.append(f"- {item.get('title', '')}: {item.get('message', '')}")

    alerts = narrative.get("performance_alerts", [])
    if alerts:
        lines.append("Top performance alerts:")
        for item in alerts[:3]:
            lines.append(f"- {item.get('title', '')}: {item.get('message', '')}")

    opportunities = narrative.get("opportunities", [])
    if opportunities:
        lines.append("Top opportunities:")
        for item in opportunities[:3]:
            lines.append(f"- {item.get('title', '')}: {item.get('message', '')}")

    actions = summary_facts.get("top_actions", [])
    if actions:
        lines.append("Top recommended actions:")
        for item in actions[:2]:
            lines.append(f"- {item.get('title', '')}: {item.get('action', '')} ({item.get('expected_impact', '')})")

    return "\n".join(lines) if lines else "No significant findings to report this period."


@st.cache_data(ttl=3600, show_spinner=False)
def generate_ai_summary(summary_facts: dict) -> str | None:
    """summary_facts: the dict returned by insights_engine.generate_executive_summary().

    Returns a short prose paragraph, or None if unavailable/failed. Caller must
    treat None as "don't render this section" -- never show an error to the user.
    """
    client = _get_client()
    if client is None:
        return None

    prompt = _build_prompt(summary_facts)
    try:
        resp = client.chat.completions.create(
            model=_DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=700,
        )
        return resp.choices[0].message.content
    except Exception:
        return None
