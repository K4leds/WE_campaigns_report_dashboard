import os
import hashlib
import json
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import warnings
warnings.filterwarnings('ignore')

# Import centralized configuration and attribution logic
from config import CHANNEL_COSTS, REQUIRED_COLUMNS, COLORS, COLOR_SEQUENCE, CHANNEL_COLORS
from attribution import apply_attribution, apply_dimension_filters, get_attribution_display_label, get_selected_revenue_display_name, get_selected_conversion_display_name, resolve_source_column
from data_processing import clean_data
from utils import format_metric, style_total_row
from analysis import (
    top_campaigns, get_top_journeys, top_segments, channel_analysis,
    time_series_analysis, failed_reasons_analysis, esp_analysis,
    ab_testing_analysis, attribution_analysis,
)
from dashboard.health import calculate_journey_health_score, calculate_campaign_health_score
from dashboard.funnels import analyze_campaign_funnel, analyze_journey_funnel, calculate_funnel_conversion_rates
from dashboard.anomalies import detect_campaign_anomalies, detect_journey_anomalies, get_anomaly_recommendation
from dashboard.lifecycle import (
    create_revenue_attribution_waterfall, analyze_journey_lifecycle, get_lifecycle_recommendation,
    analyze_stopped_journeys, estimate_revenue_loss_ml, generate_stopped_journey_recommendations,
    create_cohort_analysis,
)
from dashboard.comparisons_logic import (
    create_journey_comparison_analysis, create_custom_date_range_comparison,
    calculate_comparison_periods, calculate_uplift_significance,
    calculate_period_metrics, calculate_metric_changes,
)
from dashboard.data_pipeline import (
    load_and_clean_data, apply_filters_and_attribution, cached_executive_summary,
    cached_journey_health_scores, cached_journey_lifecycle, cached_comparison,
)
from dashboard.charts import attribution_display
from dashboard.state import DashboardState, set_ctx

# --- Theme detection ---
# Streamlit's dark/light picker (in the "..." menu) is a client-side-only setting:
# switching it does NOT trigger a script rerun, so st.context.theme only reflects
# the current choice once *some* rerun happens (any widget interaction, filter
# change, etc.). There is no supported way to set the theme from Python --
# st._config.set_option("theme.base", ...) was tested and does not move the
# actual rendered theme, only st.context.theme can be *read*, not set.
_theme_type = st.context.theme.type if hasattr(st.context, "theme") else "dark"
_is_dark = _theme_type == "dark"

# Register a global Plotly template for consistent styling
import plotly.io as pio

_we_template = go.layout.Template()
_we_template.layout = go.Layout(
    font=dict(
        family='Inter, Segoe UI, Roboto, sans-serif',
        size=13,
        color='#F1F5F9' if _is_dark else '#1F2937',
    ),
    title=dict(
        font=dict(size=18, color='#F1F5F9' if _is_dark else '#111827'),
        x=0.02,
        xanchor='left',
    ),
    paper_bgcolor='rgba(0,0,0,0)',
    plot_bgcolor='rgba(0,0,0,0)',
    colorway=COLOR_SEQUENCE,
    xaxis=dict(
        showgrid=True,
        gridcolor='#334155' if _is_dark else '#F3F4F6',
        gridwidth=1,
        linecolor='#475569' if _is_dark else '#E5E7EB',
        linewidth=1,
        title=dict(standoff=12),
    ),
    yaxis=dict(
        gridcolor='#334155' if _is_dark else '#F3F4F6',
        gridwidth=1,
        linecolor='#475569' if _is_dark else '#E5E7EB',
        linewidth=1,
        zerolinecolor='#475569' if _is_dark else '#E5E7EB',
    ),
    legend=dict(
        orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1,
        bgcolor='rgba(0,0,0,0)',
        font=dict(color='#94A3B8' if _is_dark else '#6B7280'),
    ),
    margin=dict(l=40, r=20, t=60, b=40),
    hovermode='x unified',
)
pio.templates['we_dashboard'] = _we_template
pio.templates.default = 'we_dashboard'


# Import our new insights engine
from insights_engine import (
    generate_narrative_insights,
    predict_revenue_forecast,
    generate_top_actions,
    generate_executive_summary
)

# Configure page layout for wide mode - better for BI dashboards
st.set_page_config(
    page_title="WebEngage Analytics Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Placeholder for brand logo — replace with actual logo path
# st.logo("assets/logo.png", size="large")

def _hash_filters(filters_dict):
    """Stable MD5 hash of filter values to detect changes without widget callbacks."""
    raw = json.dumps(filters_dict, sort_keys=True, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _month_range_options(start_date, end_date):
    if pd.isna(start_date) or pd.isna(end_date):
        return []
    start = pd.Period(pd.to_datetime(start_date), freq='M')
    end = pd.Period(pd.to_datetime(end_date), freq='M')
    months = pd.period_range(start, end, freq='M')
    return [m.to_timestamp() for m in months]

# Define grouped multipage navigation using st.Page + st.navigation
_overview_pages = [
    st.Page("pages/02_overview.py", title="Executive Overview", icon=":material/dashboard:", default=True),
    st.Page("pages/03_marketing_actions.py", title="Marketing Actions", icon=":material/campaign:"),
]

_analysis_pages = [
    st.Page("pages/04_campaigns.py", title="Campaigns", icon=":material/rocket_launch:"),
    st.Page("pages/05_journeys.py", title="Journeys", icon=":material/route:"),
    st.Page("pages/07_channels.py", title="Channels", icon=":material/satellite_alt:"),
    st.Page("pages/06_segments.py", title="Segments", icon=":material/groups:"),
    st.Page("pages/11_attribution.py", title="Attribution", icon=":material/assignment:"),
    st.Page("pages/10_ab_testing.py", title="A/B Testing", icon=":material/science:"),
    st.Page("pages/08_time_series.py", title="Time Series & Correlations", icon=":material/trending_up:"),
]

_ai_pages = [
    st.Page("pages/01_automated_insights.py", title="AI Insights & Recommendations", icon=":material/psychology:"),
    st.Page("pages/14_comparisons.py", title="Comparisons", icon=":material/compare_arrows:"),
]

_export_pages = [
    st.Page("pages/13_export.py", title="Export Reports", icon=":material/download:"),
]

_pages = {
    "🔍  Overview": _overview_pages,
    "📈  Analysis": _analysis_pages,
    "🤖  AI & Forecasting": _ai_pages,
    "📤  Export": _export_pages,
}

pg = st.navigation(_pages)

# --- Theme sync affordance ---
# Streamlit's own dark/light/system picker (⋮ menu, top right) is the actual
# theme control -- there's no supported way to drive it from Python. Switching
# it doesn't rerun the script, so our Plotly/CSS (which read _theme_type once
# per rerun) can lag by one interaction. This button just forces that resync;
# any other widget interaction (filters, etc.) does the same thing implicitly.
with st.sidebar:
    st.caption(f"{'🌙 Dark' if _is_dark else '☀️ Light'} theme — switch via the ⋮ menu (top right)")
    if st.button("🔄 Sync charts to theme", help="Refresh charts/styling to match your current theme selection", use_container_width=True):
        st.rerun()
    st.markdown("---")

# --- Inject global CSS variables and Inter font ---
def _inject_global_styles():
    """Inject CSS variables and global styles via st.markdown."""
    bg_color = "#0F172A" if _is_dark else "#F8FAFC"
    surface_color = "#1E293B" if _is_dark else "#FFFFFF"
    text_color = "#F1F5F9" if _is_dark else "#0F172A"
    text_muted = "#94A3B8" if _is_dark else "#64748B"
    border_color = "#334155" if _is_dark else "#E2E8F0"

    st.markdown(
        f"""
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

            :root {{
                --st-font: 'Inter', 'Segoe UI', Roboto, sans-serif;
                --st-primary-color: #0EA5E9;
                --st-background-color: {bg_color};
                --st-secondary-background-color: {surface_color};
                --st-text-color: {text_color};
                --st-text-muted: {text_muted};
                --st-border-color: {border_color};
                --st-success-color: #22C55E;
                --st-warning-color: #F59E0B;
                --st-danger-color: #EF4444;
                --st-info-color: #6366F1;
            }}

            html, body, [class*="css"] {{
                font-family: var(--st-font);
            }}

            /* Metric cards */
            div[data-testid="metric-container"] {{
                background: var(--st-secondary-background-color);
                border: 1px solid var(--st-border-color);
                border-radius: 8px;
                padding: 12px 16px;
            }}

            div[data-testid="metric-container"] label {{
                color: var(--st-text-muted) !important;
                font-size: 13px !important;
            }}

            div[data-testid="metric-container"] div[data-testid="stMetricValue"] {{
                color: var(--st-text-color) !important;
            }}

            /* Expander styling */
            div[data-testid="stExpander"] {{
                border-color: var(--st-border-color) !important;
            }}

            /* Dataframe styling */
            div[data-testid="stDataFrame"] {{
                border: 1px solid var(--st-border-color);
                border-radius: 8px;
                overflow: hidden;
            }}

            /* Tabs styling */
            button[data-baseweb="tab"] {{
                font-size: 14px !important;
                font-weight: 500 !important;
            }}

            /* Progress bar override */
            div[role="progressbar"] {{
                background-color: var(--st-primary-color) !important;
            }}

            /* General transitions for theme switching */
            * {{
                transition: background-color 0.2s ease, color 0.2s ease, border-color 0.2s ease;
            }}
        </style>
        """,
        unsafe_allow_html=True,
    )

_inject_global_styles()

st.title("WebEngage CSV Dashboard")

# Upload CSV
uploaded_file = st.file_uploader("Upload WebEngage CSV", type="csv")

# Test-only fallback: set DASHBOARD_TEST_CSV to a local path to skip manual
# upload during automated/browser testing. Never active otherwise.
if uploaded_file is None:
    _test_csv_path = os.environ.get("DASHBOARD_TEST_CSV")
    if _test_csv_path and os.path.exists(_test_csv_path):
        uploaded_file = _test_csv_path

if uploaded_file is not None:
    # Channel cost overrides — different clients negotiate different per-channel
    # rates, so the hardcoded config.CHANNEL_COSTS defaults won't fit everyone.
    # Collected before cleaning so Campaign Cost/ROAS/Cost-Per-* reflect them.
    with st.sidebar.expander("💰 Channel Costs (SAR per message)", expanded=False):
        st.caption("Override with this client's actual negotiated rates. Defaults shown are the dashboard's built-in estimates.")
        channel_cost_overrides = {}
        for channel, default_cost in CHANNEL_COSTS.items():
            channel_cost_overrides[channel] = st.number_input(
                channel, min_value=0.0, value=float(default_cost), step=0.0001,
                key=f"channel_cost_{channel}", format="%.4f",
            )

    channel_costs_tuple = tuple(sorted(channel_cost_overrides.items()))
    df = load_and_clean_data(uploaded_file, channel_costs=channel_costs_tuple)

    # Validate required columns exist
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        st.error(
            f"**Missing required columns:** {', '.join(missing_cols)}. "
            f"This does not appear to be a standard WebEngage daily campaign export. "
            f"Expected columns: {', '.join(REQUIRED_COLUMNS)}"
        )
        st.stop()

    # Warn about recommended columns
    recommended_cols = ['Unique Impressions', 'Unique Clicks', 'Unique Conversions', 'Revenue (SAR)', 'Journey Name']
    missing_recommended = [col for col in recommended_cols if col not in df.columns]
    if missing_recommended:
        st.warning(f"**Optional columns missing** (some features will be limited): {', '.join(missing_recommended)}")

    st.success("Data cleaned and normalized!")

    # Compute filter option lists once per uploaded file and store them
    _file_id = uploaded_file.file_id if hasattr(uploaded_file, 'file_id') else getattr(uploaded_file, 'name', uploaded_file)
    if st.session_state.get('_filter_options_file_id') != _file_id:
        st.session_state['_filter_options_file_id'] = _file_id
        st.session_state['_filter_options'] = {
            'channels': sorted(df['Channel'].dropna().unique().tolist()) if not df.empty else [],
            'campaign_types': sorted(df['Type of Campaign'].dropna().unique().tolist()) if (not df.empty and 'Type of Campaign' in df.columns) else [],
            'campaigns': sorted([c for c in df['Campaign Name'].dropna().unique().tolist() if c != 'nan']) if not df.empty else [],
            'segments': sorted([s for s in df['Segment Name'].dropna().unique().tolist() if s != 'nan']) if not df.empty else [],
            'journeys': sorted([j for j in df['Journey Name'].dropna().unique().tolist() if j != 'nan']) if not df.empty else [],
            'conversion_events': sorted(df['Conversion Event'].dropna().unique().tolist()) if (not df.empty and 'Conversion Event' in df.columns) else [],
        }
    _opts = st.session_state['_filter_options']

    # Store date bounds in session_state so the fragment can access them when
    # re-running in isolation (without the main flow re-executing).
    if not df.empty:
        st.session_state['_df_min_date'] = df['Reporting Period Start Date'].min()
        st.session_state['_df_max_date'] = df['Reporting Period End Date'].max()
    else:
        st.session_state['_df_min_date'] = None
        st.session_state['_df_max_date'] = None

    # --- Sidebar filter fragment ---
    # When a widget inside this fragment changes, only the fragment re-runs.
    # Hash-based change detection triggers st.rerun(scope="app") to propagate
    # the new values to the main flow without blocking the UI.
    @st.fragment
    def _sidebar_filters():
        st.header("Filters")

        # Global Attribution Filters
        st.subheader("Attribution Settings")
        revenue_attribution = st.selectbox(
            "Revenue Attribution",
            ["Total", "Impression-Through", "Click-Through"],
            help="Select which type of revenue attribution to use throughout the dashboard",
            key="_frag_rev_attr"
        )
        conversion_attribution = st.selectbox(
            "Conversion Attribution",
            ["Total", "Impression-Through", "Click-Through"],
            help="Select which type of conversion attribution to use throughout the dashboard",
            key="_frag_conv_attr"
        )

        # Date range picker
        min_date = st.session_state.get('_df_min_date')
        max_date = st.session_state.get('_df_max_date')
        if min_date is not None and max_date is not None:
            use_month_picker = st.toggle("Use Month Picker", value=False, key="_frag_month_picker")
            if use_month_picker:
                month_options = _month_range_options(min_date, max_date)
                month_labels = [m.strftime('%b %Y') for m in month_options]
                if month_labels:
                    start_month_label = st.selectbox("Start Month", month_labels, index=0, key="_frag_start_month")
                    end_month_label = st.selectbox("End Month", month_labels, index=len(month_labels) - 1, key="_frag_end_month")
                    start_month = month_options[month_labels.index(start_month_label)]
                    end_month = month_options[month_labels.index(end_month_label)]
                    date_range = (start_month, (end_month + pd.offsets.MonthEnd(0)).date())
                else:
                    date_range = (min_date, max_date)
            else:
                date_range = st.date_input("Date Range", value=(min_date, max_date), key="_frag_date_range")
        else:
            use_month_picker = False
            date_range = st.date_input("Date Range", [], key="_frag_date_range")

        # Comparison Period Settings
        st.subheader("📊 Comparison Settings")
        comparison_mode = st.selectbox(
            "Compare With",
            ["None", "Previous Period (Auto)", "Week over Week", "Month over Month",
             "Quarter over Quarter", "Custom Date Range"],
            help="Select a comparison period to see trends and changes",
            key="_frag_comp_mode"
        )

        comparison_date_range = None
        if comparison_mode == "Custom Date Range":
            st.markdown("**Comparison Period:**")
            if min_date is not None and max_date is not None:
                if use_month_picker:
                    month_options = _month_range_options(min_date, max_date)
                    month_labels = [m.strftime('%b %Y') for m in month_options]
                    if month_labels:
                        comp_start_label = st.selectbox(
                            "Comparison Start Month", month_labels, index=0,
                            key="_frag_comp_start"
                        )
                        comp_end_label = st.selectbox(
                            "Comparison End Month", month_labels,
                            index=min(1, len(month_labels) - 1), key="_frag_comp_end"
                        )
                        comp_start = month_options[month_labels.index(comp_start_label)]
                        comp_end = month_options[month_labels.index(comp_end_label)]
                        comparison_date_range = (comp_start, (comp_end + pd.offsets.MonthEnd(0)).date())
                else:
                    comparison_date_range = st.date_input(
                        "Custom Comparison Range",
                        value=(min_date, min_date + pd.Timedelta(days=7)),
                        key="_frag_comp_date_range"
                    )
            else:
                comparison_date_range = st.date_input("Custom Comparison Range", [], key="_frag_comp_date_range")

        # Multi-select filters
        _opts = st.session_state.get('_filter_options', {})
        channels = st.multiselect("Channels", _opts.get('channels', []), key="_frag_channels")
        campaign_types = st.multiselect(
            "Campaign Type", _opts.get('campaign_types', []),
            help="Filter by Journey or One-Time campaigns", key="_frag_camp_types"
        )
        campaigns = st.multiselect("Campaigns", _opts.get('campaigns', []), key="_frag_campaigns")
        segments = st.multiselect("Segments", _opts.get('segments', []), key="_frag_segments")
        journeys = st.multiselect("Journeys", _opts.get('journeys', []), key="_frag_journeys")
        conversion_events = st.multiselect(
            "Conversion Event", _opts.get('conversion_events', []),
            help="Filter by conversion event type (e.g., Order Completed, Cart Submitted)",
            key="_frag_conv_events"
        )

        # Build filter values dict and detect changes via stable hash comparison
        current_filters = {
            'revenue_attribution': revenue_attribution,
            'conversion_attribution': conversion_attribution,
            'date_range': date_range,
            'use_month_picker': use_month_picker,
            'comparison_mode': comparison_mode,
            'comparison_date_range': comparison_date_range,
            'channels': channels,
            'campaign_types': campaign_types,
            'campaigns': campaigns,
            'segments': segments,
            'journeys': journeys,
            'conversion_events': conversion_events,
        }
        current_hash = _hash_filters(current_filters)
        applied_hash = st.session_state.get('_filter_applied_hash')

        if applied_hash is not None and current_hash != applied_hash:
            # User changed a filter — store values and trigger full app rerun
            st.session_state['_filter_draft'] = current_filters
            st.session_state['_filter_applied_hash'] = current_hash
            st.rerun(scope="app")
        elif applied_hash is None:
            # Initial load — store values without triggering rerun
            st.session_state['_filter_draft'] = current_filters
            st.session_state['_filter_applied_hash'] = current_hash

    with st.sidebar:
        _sidebar_filters()

    # Read filter values from session_state (populated by the fragment above)
    _fv = st.session_state.get('_filter_draft', {})
    revenue_attribution = _fv.get('revenue_attribution', 'Total')
    conversion_attribution = _fv.get('conversion_attribution', 'Total')
    date_range = _fv.get('date_range', ())
    comparison_mode = _fv.get('comparison_mode', 'None')
    comparison_date_range = _fv.get('comparison_date_range', None)
    channels = _fv.get('channels', [])
    campaign_types = _fv.get('campaign_types', [])
    campaigns = _fv.get('campaigns', [])
    segments = _fv.get('segments', [])
    journeys = _fv.get('journeys', [])
    conversion_events = _fv.get('conversion_events', [])

    # Display-friendly labels for the selected attribution model
    _REV_ATTR_LABELS = {"Total": "Revenue (SAR)", "Click-Through": "Click-Through Revenue (SAR)", "Impression-Through": "Impression-Through Revenue (SAR)"}
    _CONV_ATTR_LABELS = {"Total": "Unique Conversions", "Click-Through": "Click-Through Conversions", "Impression-Through": "Impression-Through Conversions"}
    selected_rev_label = _REV_ATTR_LABELS.get(revenue_attribution, "Selected Revenue (SAR)")
    selected_conv_label = _CONV_ATTR_LABELS.get(conversion_attribution, "Selected Conversions")

    def _attribution_display(col_name):
        """Map internal 'Selected Revenue/Conversions' column names to the user-selected attribution label."""
        return get_attribution_display_label(col_name, revenue_attribution, conversion_attribution)

    # Apply filters using cached function
    filtered_df = apply_filters_and_attribution(df, revenue_attribution, conversion_attribution, date_range, channels, campaign_types, campaigns, segments, journeys, conversion_events)

    # Calculate comparison data if comparison mode is enabled
    comparison_result = None
    if comparison_mode != "None":
        comparison_result = cached_comparison(
            df, revenue_attribution, conversion_attribution,
            tuple(channels), tuple(campaign_types), tuple(campaigns),
            tuple(segments), tuple(journeys), tuple(conversion_events or []),
            date_range, comparison_mode, comparison_date_range
        )

    st.write(f"Filtered data: {len(filtered_df)} rows")
    if comparison_result:
        st.info(f"📊 Comparing **{comparison_result['current_label']}** vs **{comparison_result['comparison_label']}**")

    set_ctx(DashboardState(
        df=df, filtered_df=filtered_df, comparison_result=comparison_result,
        revenue_attribution=revenue_attribution,
        conversion_attribution=conversion_attribution,
        selected_rev_label=selected_rev_label, selected_conv_label=selected_conv_label,
        date_range=date_range, comparison_mode=comparison_mode,
        channel_costs=channel_cost_overrides,
        filter_options=_opts,
        channels=channels, campaign_types=campaign_types, campaigns=campaigns,
        segments=segments, journeys=journeys, conversion_events=conversion_events,
    ))

pg.run()