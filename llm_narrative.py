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

---

PROMPT ENGINEERING PHILOSOPHY (2026 best practices, applied here):
1. AUDIENCE FIRST — every prompt specifies who reads it (CMO, analyst, board).
2. FEW-SHOT EXAMPLES — show the model what "excellent" looks like before asking.
3. CHAIN-OF-THOUGHT — for premium tier, ask the model to reason first, then write.
4. ANTI-HALLUCINATION — "If a number isn't in the facts, say so. Never invent."
5. STRUCTURE CONSTRAINTS — exact word counts, sentence counts, no markdown.
6. TONE CALIBRATION — explicit tone parameters, not vague "professional" labels.
7. SELF-VERIFICATION — ask the model to check its output against the facts.

Sources: 2Slides 2026 AI Presentation Guide, MachineLearningMastery
anti-hallucination techniques, Smallppt prompt engineering framework.
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

# ── Audience profiles for tone/perspective calibration ──
# Every LLM call that generates slide prose should specify the audience.
# "executive" = C-suite / board: want the big picture, decisions, money.
# "marketing" = marketing director/manager: want channel details, tactics.
# "analyst"  = data analyst: want statistical nuance, caveats, methodology.
AUDIENCE_PROFILES = {
    "executive": (
        "The reader is a busy C-level executive or board member. They care about "
        "revenue impact, ROI, competitive positioning, and what decision to make next. "
        "They skim — lead with the headline, put numbers in context of business outcomes. "
        "Avoid methodology details, statistical caveats, and channel-by-channel lists. "
        "Every sentence should answer: 'So what? What do I do about this?'"
    ),
    "marketing": (
        "The reader is a marketing director or campaign manager. They care about "
        "channel performance, campaign ROI, audience segments, and actionable tactics. "
        "They want enough detail to act on — name specific channels, campaigns, and "
        "metrics. Connect findings to WebEngage features they can use tomorrow."
    ),
    "analyst": (
        "The reader is a data analyst or marketing operations specialist. They care "
        "about statistical significance, methodology, data quality, and root causes. "
        "Be precise with numbers, note caveats where data is sparse, and explain "
        "the 'why' behind trends. They will check your numbers — get them exactly right."
    ),
}

# ── Tone profiles for voice calibration ──
TONE_PROFILES = {
    "confident":     "Assertive, decisive, forward-looking. Use active voice. Frame findings as facts, not suggestions.",
    "consultative":  "Collaborative, insight-driven, partnership-oriented. Use 'we' and frame as shared observations.",
    "urgent":        "Direct, punchy, crisis-aware. Lead with the problem, quantify the risk, demand action.",
    "reassuring":    "Steady, optimistic, growth-focused. Acknowledge challenges but emphasize trajectory and progress.",
    "analytical":    "Precise, measured, evidence-first. Every claim backed by a specific number. No fluff.",
}


# ── Few-shot examples: what "excellent" slide prose looks like ──
# These are injected into system prompts so the model calibrates to our standard.
_FEWSHOT_SUMMARY_EXCELLENT = (
    "Example of excellent executive summary (executive audience, confident tone):\n"
    "\"This period, WebEngage campaigns drove SAR 2,847,000 in revenue from 14,200 "
    "conversions — a 23% increase over the prior quarter. Email remains the revenue "
    "engine at SAR 1.6M, but SMS is the growth story: conversions doubled while cost "
    "held steady, pushing its ROAS to 8.4x. The one watchpoint: delivery rate slipped "
    "to 87% on two ESPs, costing an estimated SAR 180K in missed revenue. Fixing that "
    "is the single highest-ROI action for next period.\"\n\n"
    "Note what makes this excellent: (1) leads with the biggest number, (2) connects "
    "metrics to business outcomes, (3) names the top action with quantified impact, "
    "(4) no filler words, (5) every claim cites a number from the facts."
)

_FEWSHOT_SUMMARY_POOR = (
    "Example of POOR executive summary (DO NOT write like this):\n"
    "\"The marketing campaigns performed well this period. Revenue increased and "
    "conversions were strong. Email was the top channel and SMS also did well. "
    "There are some areas for improvement. Overall it was a successful period.\"\n\n"
    "Why this is poor: (1) no specific numbers, (2) every sentence is generic and "
    "could apply to any report, (3) no actionable insight, (4) uses filler phrases "
    "like 'performed well' and 'areas for improvement' instead of specifics."
)

_FEWSHOT_FINDINGS_EXCELLENT = (
    "Example of excellent findings rewriting (analyst audience, analytical tone):\n"
    "Input: 'Low delivery rate on Infobip: Delivery rate dropped to 82% on 45K sends.'\n"
    "Output: 'Infobip's delivery rate fell to 82% across 45,000 sends — well below the "
    "90% benchmark, putting an estimated 3,600 messages undelivered this period.'\n\n"
    "Input: 'SMS ROAS outlier: SMS achieved 8.4x ROAS — 2.1x the 4.0x good benchmark.'\n"
    "Output: 'SMS delivered an 8.4x ROAS, more than double the 4.0x efficiency threshold "
    "— the strongest return of any channel this period.'\n\n"
    "Note: each adds context (benchmark comparison, estimated impact) without inventing "
    "numbers — the comparison values come from the provided facts."
)

_FEWSHOT_RECOMMENDATION_EXCELLENT = (
    "Example of excellent recommendation (executive audience, urgent tone):\n"
    "Finding: 'Delivery rate on Infobip dropped to 82% — estimated SAR 180K in lost revenue.'\n"
    "Feature: 'Send Time Optimization'\n"
    "Output: 'Switch Infobip campaigns to Send Time Optimization and re-authenticate "
    "your sending domain to recover the estimated SAR 180K in missed revenue — this is "
    "the single highest-impact fix available this quarter.'\n\n"
    "Note what makes this excellent: (1) names a specific WebEngage feature, (2) "
    "quantifies the payoff, (3) uses urgent/action-oriented language, (4) connects "
    "the fix directly to the finding's numbers."
)


# ── Quality tiers ──
# "quick"  = low token count, no reasoning — for non-critical prose.
# "standard" = balanced — good enough for client-facing slides.
# "premium" = chain-of-thought reasoning + self-verification — boardroom ready.
QUALITY_TIERS = {
    "quick":    {"max_tokens": 200, "reasoning": None, "temperature": 0.3},
    "standard": {"max_tokens": 350, "reasoning": None, "temperature": 0.4},
    "premium":  {"max_tokens": 500, "reasoning": "medium", "temperature": 0.5},
}


def _build_system_prompt(audience: str = "executive", tone: str = "confident",
                         quality: str = "standard", include_fewshot: bool = True) -> str:
    """Assemble a calibrated system prompt from modular components.

    This replaces the old one-size-fits-all _SYSTEM_PROMPT with a composable
    system that lets each caller specify who's reading, what tone to use, and
    how much reasoning effort to invest. Few-shot examples are included by
    default because they consistently produce better-calibrated output.
    """
    audience_instruction = AUDIENCE_PROFILES.get(audience, AUDIENCE_PROFILES["executive"])
    tone_instruction = TONE_PROFILES.get(tone, TONE_PROFILES["confident"])
    tier = QUALITY_TIERS.get(quality, QUALITY_TIERS["standard"])

    parts = [
        "You are a senior marketing analyst writing client-facing prose for a "
        "WebEngage campaign performance review deck. Your job is to turn "
        "pre-computed facts into sharp, actionable, boardroom-ready sentences.",
        "",
        "CRITICAL RULES (violating any of these makes the output unusable):",
        "1. NEVER invent, estimate, or modify a number. Use ONLY the exact figures "
        "provided in the facts below. If a fact is missing, do not guess — say "
        "'data not available for this period' or simply omit that point.",
        "2. NEVER use markdown formatting (no **, no ##, no bullet points like - or *). "
        "Output plain text only. If you're writing multiple sentences, separate them "
        "with a single space — no line breaks, no numbered lists.",
        "3. NEVER write generic filler like 'performed well,' 'showed strong results,' "
        "or 'areas for improvement.' Always replace these with specific numbers and "
        "named channels/campaigns from the facts.",
        "4. NEVER mention 'the data shows' or 'according to the report.' The reader knows "
        "this is a report. Just state the finding directly.",
        "5. ALWAYS end with a complete sentence. If you're running out of space, drop "
        "a weaker point rather than truncating mid-sentence.",
        "",
        f"AUDIENCE: {audience_instruction}",
        "",
        f"TONE: {tone_instruction}",
        "",
        "OUTPUT FORMAT: Write exactly the prose requested — no preamble like 'Here is "
        "the summary,' no sign-off like 'Let me know if you need anything else,' no "
        "JSON wrappers. Just the prose itself.",
    ]

    if include_fewshot:
        parts.extend([
            "",
            "─── FEW-SHOT CALIBRATION ───",
            "Study these examples carefully. Your output must match the quality and "
            "specificity of the EXCELLENT examples, avoiding the patterns in the POOR ones.",
            "",
            _FEWSHOT_SUMMARY_EXCELLENT,
            "",
            _FEWSHOT_SUMMARY_POOR,
        ])

    if quality == "premium":
        parts.extend([
            "",
            "─── REASONING INSTRUCTIONS ───",
            "Before writing, think through these questions silently:",
            "1. What is the ONE most important number in these facts, and why?",
            "2. Which finding would change what the reader does next week?",
            "3. Is there a connection between two facts that's worth surfacing?",
            "4. Am I about to write anything that isn't explicitly in the provided facts?",
            "Then write your response. After writing, verify: does every number "
            "in your output appear verbatim in the provided facts?",
        ])

    return "\n".join(parts)


# Keep the old _SYSTEM_PROMPT for backward compatibility with any code
# that still references it directly (e.g., tests, legacy callers).
_SYSTEM_PROMPT = _build_system_prompt(audience="executive", tone="confident",
                                       quality="standard", include_fewshot=True)


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
def generate_ai_summary(summary_facts: dict, audience: str = "executive",
                        tone: str = "confident", quality: str = "standard") -> str | None:
    """summary_facts: the dict returned by insights_engine.generate_executive_summary().

    New in v2: audience, tone, and quality parameters calibrate the LLM output.
    - audience: "executive" | "marketing" | "analyst"
    - tone: "confident" | "consultative" | "urgent" | "reassuring" | "analytical"
    - quality: "quick" | "standard" | "premium" (premium uses chain-of-thought)

    Returns a short prose paragraph, or None if unavailable/failed. Caller must
    treat None as "don't render this section" -- never show an error to the user.
    """
    client = _get_client()
    if client is None:
        return None

    prompt = _build_prompt(summary_facts)
    tier = QUALITY_TIERS.get(quality, QUALITY_TIERS["standard"])
    system = _build_system_prompt(audience=audience, tone=tone, quality=quality)

    try:
        kwargs = dict(
            model=_DEEPSEEK_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            max_tokens=tier["max_tokens"],
        )
        if tier["reasoning"]:
            kwargs["reasoning_effort"] = tier["reasoning"]
            kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
            kwargs["timeout"] = 45.0  # reasoning needs more time
        resp = client.chat.completions.create(**kwargs)
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
    "─── FEW-SHOT EXAMPLES ───\n"
    "Study these to calibrate your output quality:\n\n"
    "EXCELLENT (write like this):\n"
    "**Web Push is carrying the portfolio.** It generated SAR 892,000 — 52% of total "
    "revenue — from just 3 campaigns, with a 14.2% conversion rate that's 3x the "
    "table average of 4.7%. If this channel were to underperform, there is no obvious "
    "replacement at the same scale.\n\n"
    "**The bottom 4 channels combined contribute only 6% of revenue** while consuming "
    "18% of total sends. Reallocating even half of that volume to SMS (which has 3x "
    "the conversion efficiency) could add an estimated SAR 45K without increasing "
    "total send volume.\n\n"
    "**Average delivery rate of 91% masks a critical outlier.** Infobip's 82% rate "
    "on 45K sends drags the average down — the other 4 ESPs all sit above 93%. The "
    "3,600 undelivered messages on Infobip represent the single largest recoverable "
    "gap in the table.\n\n"
    "POOR (DO NOT write like this):\n"
    "**Revenue Analysis.** The revenue numbers show that some channels performed "
    "better than others. This is interesting and worth exploring further.\n\n"
    "**Conversion Rate.** The conversion rate varies across different channels. "
    "Some are higher and some are lower than average.\n\n"
    "Why these are poor: no specific numbers, no named channels, no actionable "
    "insight, uses filler phrases like 'worth exploring further.'\n\n"
    "─── OUTPUT FORMAT ───\n"
    "Output exactly 3 to 5 insights as plain markdown. Each insight is one bolded "
    "lead-in phrase (not a generic label like \"Insight 1\") followed by one or two "
    "sentences of plain-English explanation, e.g. \"**Web Push is carrying the "
    "portfolio.** ...\". Every insight must cite specific values or names straight "
    "from the fact sheet. No headers, no numbered list, no code block, no JSON, no "
    "preamble or closing remark -- just the insights.\n\n"
    "COVERAGE: spread insights across at least 3 different rows/channels rather "
    "than spending two or more insights on the same row -- unless one row is so "
    "dominant or broken that a second angle on it is genuinely the most useful "
    "thing to tell the reader."
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
    mode (reasoning_effort="medium") since this is an on-demand, user-triggered
    call rather than one that fires on every page load -- worth the extra latency
    for a more genuinely analytical read of the table.

    Returns 3-5 markdown insight bullets, or None if unconfigured. Raises on a
    failed API call instead of returning None -- st.cache_data only memoizes
    a *returned* value, so raising keeps transient failures (timeout, rate
    limit) from being cached as a permanent "unavailable" for the ttl, letting
    the user's next click retry for real. Caller must catch and treat both
    None and an exception as "don't render this section" -- never show a
    raw error.
    """
    client = _get_client()
    if client is None:
        return None

    prompt = _build_explain_prompt(fact_sheet)
    resp = client.chat.completions.create(
        model=_DEEPSEEK_MODEL,
        messages=[
            {"role": "system", "content": _EXPLAIN_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        # 16K ceiling, not the model's 384K output cap -- max_tokens only bounds
        # how much it's ALLOWED to generate (billed on actual usage), so this is
        # pure headroom against the empty-response truncation bug, not a cost knob.
        max_tokens=16000,
        reasoning_effort="medium",
        extra_body={"thinking": {"type": "enabled"}},
        # Thinking mode routinely takes 15-20s; the client's default 20s
        # timeout (tuned for the non-thinking exec-summary call) was cutting
        # this off intermittently. This is an explicit, on-demand click, so
        # the extra headroom is worth it.
        timeout=60.0,
    )
    content = resp.choices[0].message.content
    if not content:
        # A successful call can still come back empty -- e.g. the reasoning
        # trace ate the whole max_tokens budget before writing the answer.
        # An empty string is a valid *return value*, so unlike an exception
        # it WOULD get cached and replayed on every retry. Raise instead so
        # the next click actually retries the call.
        raise RuntimeError("DeepSeek returned empty content")
    return content
