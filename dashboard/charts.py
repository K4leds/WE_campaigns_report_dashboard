"""Shared presentation helpers for dashboard pages."""
from utils import format_metric, style_total_row, export_chart_image  # noqa: F401
from attribution import get_attribution_display_label


def attribution_display(ctx, col_name):
    """Map 'Selected Revenue/Conversions' column names to the user-selected label."""
    return get_attribution_display_label(
        col_name, ctx.revenue_attribution, ctx.conversion_attribution
    )
