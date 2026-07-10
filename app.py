import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from io import BytesIO
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_squared_error
from statsmodels.tsa.arima.model import ARIMA
try:
    from prophet import Prophet
except ImportError:
    Prophet = None
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

# Register a global Plotly template for consistent styling
import plotly.io as pio

_we_template = go.layout.Template()
_we_template.layout = go.Layout(
    font=dict(family='Inter, Segoe UI, Roboto, sans-serif', size=13, color='#1F2937'),
    title=dict(font=dict(size=18, color='#111827'), x=0, xanchor='left'),
    paper_bgcolor='white',
    plot_bgcolor='white',
    colorway=COLOR_SEQUENCE,
    xaxis=dict(showgrid=False, linecolor='#E5E7EB', linewidth=1),
    yaxis=dict(gridcolor='#F3F4F6', gridwidth=1, linecolor='#E5E7EB', linewidth=1, zerolinecolor='#E5E7EB'),
    legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1, bgcolor='rgba(0,0,0,0)'),
    margin=dict(l=40, r=20, t=50, b=40),
    hovermode='x unified',
)
pio.templates['we_dashboard'] = _we_template
pio.templates.default = 'plotly_white+we_dashboard'


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

def _month_range_options(start_date, end_date):
    if pd.isna(start_date) or pd.isna(end_date):
        return []
    start = pd.Period(pd.to_datetime(start_date), freq='M')
    end = pd.Period(pd.to_datetime(end_date), freq='M')
    months = pd.period_range(start, end, freq='M')
    return [m.to_timestamp() for m in months]

# Define multipage navigation using st.Page + st.navigation
_pages = [
    st.Page("pages/01_automated_insights.py", title="Automated Insights", icon="🎯"),
    st.Page("pages/02_overview.py", title="Overview", icon="📊"),
    st.Page("pages/03_marketing_actions.py", title="Marketing Actions", icon="📈"),
    st.Page("pages/04_campaigns.py", title="Campaigns", icon="🚀"),
    st.Page("pages/05_journeys.py", title="Journeys", icon="🔄"),
    st.Page("pages/06_segments.py", title="Segments", icon="👥"),
    st.Page("pages/07_channels.py", title="Channels", icon="📡"),
    st.Page("pages/08_time_series.py", title="Time Series", icon="📅"),
    st.Page("pages/09_correlations.py", title="Correlations", icon="🔗"),
    st.Page("pages/10_ab_testing.py", title="A/B Testing", icon="🔬"),
    st.Page("pages/11_attribution.py", title="Attribution", icon="📋"),
    st.Page("pages/12_failed_reasons.py", title="Failed Reasons", icon="❌"),
    st.Page("pages/13_export.py", title="Export", icon="📤"),
    st.Page("pages/14_comparisons.py", title="Comparisons", icon="⚖️"),
    st.Page("pages/15_ai_insights.py", title="AI Insights", icon="🤖"),
]
pg = st.navigation(_pages)

st.title("WebEngage CSV Dashboard")

# Upload CSV
uploaded_file = st.file_uploader("Upload WebEngage CSV", type="csv")

if uploaded_file is not None:
    df = load_and_clean_data(uploaded_file)

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

    # Filters
    st.sidebar.header("Filters")
    
    # Global Attribution Filters
    st.sidebar.subheader("Attribution Settings")
    revenue_attribution = st.sidebar.selectbox(
        "Revenue Attribution",
        ["Total", "Impression-Through", "Click-Through"],
        help="Select which type of revenue attribution to use throughout the dashboard"
    )
    
    conversion_attribution = st.sidebar.selectbox(
        "Conversion Attribution",
        ["Total", "Impression-Through", "Click-Through"],
        help="Select which type of conversion attribution to use throughout the dashboard"
    )

    # Display-friendly labels for the selected attribution model
    _REV_ATTR_LABELS = {"Total": "Revenue (SAR)", "Click-Through": "Click-Through Revenue (SAR)", "Impression-Through": "Impression-Through Revenue (SAR)"}
    _CONV_ATTR_LABELS = {"Total": "Unique Conversions", "Click-Through": "Click-Through Conversions", "Impression-Through": "Impression-Through Conversions"}
    selected_rev_label = _REV_ATTR_LABELS.get(revenue_attribution, "Selected Revenue (SAR)")
    selected_conv_label = _CONV_ATTR_LABELS.get(conversion_attribution, "Selected Conversions")
    attribution_rename = {'Selected Revenue (SAR)': selected_rev_label, 'Selected Conversions': selected_conv_label}

    def _attribution_display(col_name):
        """Map internal 'Selected Revenue/Conversions' column names to the user-selected attribution label."""
        return get_attribution_display_label(col_name, revenue_attribution, conversion_attribution)

    if not df.empty:
        min_date = df['Reporting Period Start Date'].min()
        max_date = df['Reporting Period End Date'].max()
        use_month_picker = st.sidebar.toggle("Use Month Picker", value=False)
        if use_month_picker:
            month_options = _month_range_options(min_date, max_date)
            month_labels = [m.strftime('%b %Y') for m in month_options]
            start_month_label = st.sidebar.selectbox("Start Month", month_labels, index=0)
            end_month_label = st.sidebar.selectbox("End Month", month_labels, index=len(month_labels) - 1)
            start_month = month_options[month_labels.index(start_month_label)]
            end_month = month_options[month_labels.index(end_month_label)]
            date_range = (start_month, (end_month + pd.offsets.MonthEnd(0)).date())
        else:
            date_range = st.sidebar.date_input("Date Range", value=(min_date, max_date))
    else:
        use_month_picker = False
        date_range = st.sidebar.date_input("Date Range", [])
    
    # Comparison Period Settings
    st.sidebar.subheader("📊 Comparison Settings")
    comparison_mode = st.sidebar.selectbox(
        "Compare With",
        ["None", "Previous Period (Auto)", "Week over Week", "Month over Month", "Quarter over Quarter", "Custom Date Range"],
        help="Select a comparison period to see trends and changes"
    )
    
    # Custom comparison date range (only show if Custom is selected)
    comparison_date_range = None
    if comparison_mode == "Custom Date Range":
        st.sidebar.markdown("**Comparison Period:**")
        if not df.empty:
            if use_month_picker:
                month_options = _month_range_options(min_date, max_date)
                month_labels = [m.strftime('%b %Y') for m in month_options]
                comp_start_label = st.sidebar.selectbox("Comparison Start Month", month_labels, index=0, key="comp_start_month")
                comp_end_label = st.sidebar.selectbox("Comparison End Month", month_labels, index=min(1, len(month_labels) - 1), key="comp_end_month")
                comp_start = month_options[month_labels.index(comp_start_label)]
                comp_end = month_options[month_labels.index(comp_end_label)]
                comparison_date_range = (comp_start, (comp_end + pd.offsets.MonthEnd(0)).date())
            else:
                comparison_date_range = st.sidebar.date_input(
                    "Custom Comparison Range", 
                    value=(min_date, min_date + pd.Timedelta(days=7)),
                    key="comparison_date_range"
                )
        else:
            comparison_date_range = st.sidebar.date_input("Custom Comparison Range", [], key="comparison_date_range")
    
    # Compute filter option lists once per uploaded file and store them
    _file_id = uploaded_file.file_id if hasattr(uploaded_file, 'file_id') else uploaded_file.name
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

    channels = st.sidebar.multiselect("Channels", _opts['channels'])
    campaign_types = st.sidebar.multiselect("Campaign Type", _opts['campaign_types'], help="Filter by Journey or One-Time campaigns")
    campaigns = st.sidebar.multiselect("Campaigns", _opts['campaigns'])
    segments = st.sidebar.multiselect("Segments", _opts['segments'])
    journeys = st.sidebar.multiselect("Journeys", _opts['journeys'])
    conversion_events = st.sidebar.multiselect("Conversion Event", _opts['conversion_events'], help="Filter by conversion event type (e.g., Order Completed, Cart Submitted)")

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
        filter_options=_opts,
        channels=channels, campaign_types=campaign_types, campaigns=campaigns,
        segments=segments, journeys=journeys, conversion_events=conversion_events,
    ))

pg.run()