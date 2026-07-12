"""Optional LLM prose layer on top of insights_engine's deterministic analysis.

insights_engine.py computes every number here (thresholds, dollar-impact
scores, alerts) -- this module is never asked to invent a figure. It only
takes the already-computed facts from generate_executive_summary() and asks
DeepSeek to write them up as one readable paragraph, for the "just read it
for me" use case. The structured alert/opportunity/action lists elsewhere on
the page stay exactly as insights_engine renders them -- this is additive,
not a replacement.

The same discipline applies to explain_table_data(): it never receives a raw
DataFrame, only a fact sheet that Python has already computed (totals, means,
max/min with the row that holds them, a bounded sample of rows). The model is
asked to interpret and rank patterns in those given numbers, never to do its
own arithmetic or invent a comparison that isn't already in the fact sheet.

Fully optional: with no DEEPSEEK_API_KEY configured (or on any API failure),
these functions return None and the caller simply doesn't render that
section. The rest of the dashboard is completely unaffected either way.
"""
import json
import os

import pandas as pd
import streamlit as st

# DeepSeek is OpenAI-API-compatible via this base_url; deepseek-v4-flash is the
# current model name -- deepseek-chat/deepseek-reasoner are deprecated
# 2026-07-24 and mapped to deepseek-v4-flash's non-thinking/thinking modes.
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


def is_configured() -> bool:
    """Whether a DeepSeek key is available -- callers use this to decide whether
    to even show an AI affordance (e.g. an "Explain" button), rather than
    showing one that will silently fail."""
    return _get_client() is not None


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


_EXPLAIN_SYSTEM_PROMPT = (
    "You are a sharp, candid marketing data analyst helping a busy, non-technical "
    "stakeholder make sense of one table from a WebEngage campaign report. You will "
    "receive a fact sheet: the row count, per-column totals/mean/max/min (with the row "
    "each max/min belongs to, where known), and a sample of the actual rows -- all "
    "ALREADY COMPUTED by the reporting system. You must never perform your own "
    "arithmetic, round differently than given, estimate a figure that isn't present, "
    "or state a comparison unless both values it relies on appear explicitly in the "
    "fact sheet.\n\n"
    "Read the fact sheet the way an experienced analyst scans a report before a "
    "meeting: look for what's genuinely worth flagging -- a row that dominates the "
    "rest, a gap between the best and worst performer, a total that's concentrated in "
    "very few rows, a metric that looks strong on average but hides a weak outlier, or "
    "a pattern across columns. Reason quietly through the numbers first; then write up "
    "only the findings that would change what the reader does next. Skip anything "
    "trivial or already obvious from the column headers alone.\n\n"
    "Output exactly 3 to 5 insights as plain markdown. Each insight is one bolded "
    "lead-in phrase (not a generic label like \"Insight 1\") followed by one or two "
    "sentences of plain-English explanation, e.g. \"**Web Push is carrying the "
    "portfolio.** ...\". Every insight must cite specific values or names straight "
    "from the fact sheet. No headers, no numbered list, no code block, no JSON, no "
    "preamble or closing remark -- just the insights."
)


def build_table_fact_sheet(df: pd.DataFrame, label: str, max_rows: int = 12) -> dict:
    """Compute a compact, LLM-ready fact sheet for one table -- entirely in Python.

    This is the anti-hallucination boundary: explain_table_data() only ever sees
    these already-computed numbers, never the raw DataFrame, so the model has
    nothing to do its own (error-prone) arithmetic on.
    """
    numeric_cols = [c for c in df.columns if pd.api.types.is_numeric_dtype(df[c])]
    text_cols = [c for c in df.columns if c not in numeric_cols]
    key_col = text_cols[0] if text_cols else None

    column_stats: dict[str, dict] = {}
    for col in numeric_cols:
        series = df[col].dropna()
        if series.empty:
            continue
        stat = {
            "total": round(float(series.sum()), 2),
            "mean": round(float(series.mean()), 2),
            "max": round(float(series.max()), 2),
            "min": round(float(series.min()), 2),
        }
        if key_col is not None:
            stat["max_row"] = str(df.loc[series.idxmax(), key_col])
            stat["min_row"] = str(df.loc[series.idxmin(), key_col])
        column_stats[col] = stat

    sort_col = numeric_cols[0] if numeric_cols else None
    top_df = df.sort_values(sort_col, ascending=False).head(max_rows) if sort_col else df.head(max_rows)

    rows = []
    for _, row in top_df.iterrows():
        rows.append({
            col: (round(row[col], 2) if col in numeric_cols and pd.notna(row[col]) else str(row[col]))
            for col in df.columns
        })

    return {
        "label": label,
        "row_count": len(df),
        "columns": list(df.columns),
        "column_stats": column_stats,
        "rows": rows,
    }


def _build_explain_prompt(fact_sheet: dict) -> str:
    return (
        f"Table: {fact_sheet.get('label', 'Untitled table')}\n"
        f"Total rows: {fact_sheet.get('row_count')}\n"
        f"Columns: {', '.join(fact_sheet.get('columns', []))}\n\n"
        f"Column statistics (JSON): {json.dumps(fact_sheet.get('column_stats', {}), default=str)}\n\n"
        f"Sample rows, sorted by the first numeric column (JSON): "
        f"{json.dumps(fact_sheet.get('rows', []), default=str)}"
    )


@st.cache_data(ttl=3600, show_spinner=False)
def explain_table_data(fact_sheet: dict, label: str) -> str | None:
    """fact_sheet: output of build_table_fact_sheet(). Runs DeepSeek in thinking
    mode (reasoning_effort="high") since this is an on-demand, user-triggered call
    rather than one that fires on every page load -- worth the extra latency for a
    more genuinely analytical read of the table.

    Returns 3-5 markdown insight bullets, or None if unavailable/failed. Caller
    must treat None as "don't render this section" -- never show an error.
    """
    client = _get_client()
    if client is None:
        return None

    prompt = _build_explain_prompt(fact_sheet)
    try:
        resp = client.chat.completions.create(
            model=_DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": _EXPLAIN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_tokens=4000,
            reasoning_effort="high",
            extra_body={"thinking": {"type": "enabled"}},
            # Thinking mode routinely takes 15-20s; the client's default 20s
            # timeout (tuned for the non-thinking exec-summary call) was cutting
            # this off intermittently. This is an explicit, on-demand click, so
            # the extra headroom is worth it.
            timeout=60.0,
        )
        return resp.choices[0].message.content
    except Exception:
        return None
