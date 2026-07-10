"""Shared dashboard state passed from the entrypoint to page modules."""
from dataclasses import dataclass, field
from typing import Any, Optional

import streamlit as st


@dataclass
class DashboardState:
    df: Any
    filtered_df: Any
    comparison_result: Optional[dict]
    revenue_attribution: str
    conversion_attribution: str
    selected_rev_label: str
    selected_conv_label: str
    date_range: Any
    comparison_mode: str
    channel_costs: dict = field(default_factory=dict)
    filter_options: dict = field(default_factory=dict)
    channels: list = field(default_factory=list)
    campaign_types: list = field(default_factory=list)
    campaigns: list = field(default_factory=list)
    segments: list = field(default_factory=list)
    journeys: list = field(default_factory=list)
    conversion_events: list = field(default_factory=list)

    def attribution_display(self, col_name: str) -> str:
        """Map internal 'Selected Revenue/Conversions' names to the selected label."""
        from attribution import get_attribution_display_label
        return get_attribution_display_label(
            col_name, self.revenue_attribution, self.conversion_attribution
        )


def set_ctx(ctx: DashboardState) -> None:
    st.session_state["ctx"] = ctx


def get_ctx() -> DashboardState:
    """Return the current DashboardState, or gate the page if no CSV is loaded yet."""
    ctx = st.session_state.get("ctx")
    if ctx is None:
        st.info("⬆️ Upload a WebEngage CSV on the main page to begin.")
        st.stop()
    return ctx
