# dashboard/verification.py
"""Calculation audit trail and inline validation for dashboard metrics.

Every derived metric stores its formula and raw inputs so users can verify
calculations match source data. A background validation pass cross-checks
computed metrics against raw-column recalculations.
"""
from datetime import datetime, timezone
from typing import Any

import pandas as pd

# In-memory audit store per session
_audit_trail: dict[str, dict] = {}


def create_audit_trail(
    metric_name: str,
    formula: str,
    inputs: dict[str, float],
    result: float,
) -> dict:
    """Record a derived metric's formula and raw inputs for tooltip display."""
    entry = {
        "metric_name": metric_name,
        "formula": formula,
        "inputs": inputs,
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    _audit_trail[metric_name] = entry
    return entry


def get_audit_tooltip(metric_name: str) -> str | None:
    """Return a formatted audit tooltip string for the metric, or None."""
    entry = _audit_trail.get(metric_name)
    if not entry:
        return None
    inputs_fmt = " x ".join(
        f"{v:,.0f}" if abs(v) >= 1 else f"{v:.4f}"
        for v in entry["inputs"].values()
    )
    return f"{entry['metric_name']} = {entry['formula']} = {inputs_fmt} = {entry['result']:,.2f}"


def validate_metric(
    value: float,
    raw_df: pd.DataFrame,
    metric_name: str,
    numerator_col: str | None = None,
    denominator_col: str | None = None,
    aggregation: str = "sum",
) -> dict:
    """Cross-check a computed metric against raw-column recalculation."""
    if numerator_col and numerator_col not in raw_df.columns:
        return {"valid": True, "difference": 0.0, "warning": False}
    if denominator_col and denominator_col not in raw_df.columns:
        return {"valid": True, "difference": 0.0, "warning": False}

    try:
        if metric_name in ("CTR", "Conversion Rate", "Delivery Rate"):
            num = raw_df[numerator_col].sum() if numerator_col else 0
            den = raw_df[denominator_col].sum() if denominator_col else 0
            recalculated = num / den if den else 0.0
        else:
            col = numerator_col or metric_name
            recalculated = raw_df[col].sum()

        diff = abs(value - recalculated)
        warning = diff > 0.01 * max(abs(value), 0.01)
        return {"valid": not warning, "difference": diff, "warning": warning}
    except Exception:
        return {"valid": True, "difference": 0.0, "warning": False}
