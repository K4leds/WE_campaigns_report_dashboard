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
from utils import format_metric, style_total_row, export_chart_image
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

st.title("WebEngage CSV Dashboard")

# Sidebar navigation
page = st.sidebar.selectbox("Navigate to", [
    "🎯 Automated Insights",  # NEW: Featured at top
    "Overview",
    "📈 Marketing Actions",
    "Campaigns",
    "Journeys",
    "Segments",
    "Channels",
    "Time Series",
    "Correlations",
    "A/B Testing",
    "Attribution",
    "Failed Reasons",
    "Comparisons",
    "AI Insights",
    "Export"
])

# Upload CSV
uploaded_file = st.file_uploader("Upload WebEngage CSV", type="csv")


def analyze_individual_journey(journey_name, filtered_df):
    """
    Detailed analysis of an individual journey - returns comprehensive scoring breakdown.
    This is the same logic as the debug script but as a reusable function.
    """
    try:
        # Get the specific journey data
        journey_data = filtered_df[filtered_df['Journey Name'] == journey_name].copy()
        
        if journey_data.empty:
            return {'error': f"Journey '{journey_name}' not found!"}
        
        # Calculate the score with detailed breakdown
        score_result = calculate_journey_health_score(journey_data, filtered_df)
        
        # Calculate raw metrics for this journey
        raw_metrics = {}
        
        # Delivery metrics
        if 'Sent' in journey_data.columns and 'Delivered' in journey_data.columns:
            total_sent = journey_data['Sent'].sum()
            total_delivered = journey_data['Delivered'].sum()
            delivery_rate = (total_delivered / total_sent) if total_sent > 0 else 0
            raw_metrics['delivery'] = {
                'total_sent': total_sent,
                'total_delivered': total_delivered,
                'delivery_rate': delivery_rate
            }
        
        # Engagement metrics
        if 'Unique Clicks' in journey_data.columns and 'Unique Impressions' in journey_data.columns:
            total_clicks = journey_data['Unique Clicks'].sum()
            total_impressions = journey_data['Unique Impressions'].sum()
            ctr = (total_clicks / total_impressions) if total_impressions > 0 else 0
            raw_metrics['engagement'] = {
                'total_clicks': total_clicks,
                'total_impressions': total_impressions,
                'ctr': ctr
            }
        
        # Conversion metrics - ALWAYS CALCULATE FROM RAW FIELDS
        if 'Unique Conversions' in journey_data.columns and 'Unique Clicks' in journey_data.columns:
            total_conversions = journey_data['Unique Conversions'].sum()
            total_clicks = journey_data['Unique Clicks'].sum()
            conv_rate = (total_conversions / total_clicks) if total_clicks > 0 else 0
            raw_metrics['conversion'] = {
                'total_conversions': total_conversions,
                'total_clicks': total_clicks,
                'conversion_rate': conv_rate,
                'source': 'Calculated: Unique Conversions / Unique Clicks'
            }
        
        # Revenue metrics
        if 'Revenue (SAR)' in journey_data.columns and 'Unique Conversions' in journey_data.columns:
            total_revenue = journey_data['Revenue (SAR)'].sum()
            total_conversions = journey_data['Unique Conversions'].sum()
            rpc = (total_revenue / total_conversions) if total_conversions > 0 else 0
            log_rpc = np.log1p(rpc)
            raw_metrics['revenue'] = {
                'total_revenue': total_revenue,
                'total_conversions': total_conversions,
                'revenue_per_conversion': rpc,
                'log_rpc': log_rpc
            }
        
        # Calculate population percentiles for context
        journey_groups = filtered_df.groupby('Journey Name')
        percentiles = {}
        
        # Delivery percentiles
        if 'delivery' in raw_metrics:
            delivery_rates = []
            for name, group in journey_groups:
                if 'Sent' in group.columns and 'Delivered' in group.columns:
                    sent = group['Sent'].sum()
                    delivered = group['Delivered'].sum()
                    if sent > 0:
                        delivery_rates.append(delivered / sent)
            
            if delivery_rates:
                percentile = (np.array(delivery_rates) <= raw_metrics['delivery']['delivery_rate']).mean() * 100
                percentiles['delivery'] = percentile
        
        # CTR percentiles
        if 'engagement' in raw_metrics:
            ctrs = []
            for name, group in journey_groups:
                if 'Unique Clicks' in group.columns and 'Unique Impressions' in group.columns:
                    clicks = group['Unique Clicks'].sum()
                    impressions = group['Unique Impressions'].sum()
                    if impressions > 0:
                        ctrs.append(clicks / impressions)
            
            if ctrs:
                percentile = (np.array(ctrs) <= raw_metrics['engagement']['ctr']).mean() * 100
                percentiles['engagement'] = percentile
        
        # Conversion rate percentiles
        if 'conversion' in raw_metrics:
            conv_rates = []
            # Use the same method as in the scoring function for consistency
            if 'Conversion Rate' in filtered_df.columns:
                for name, group in journey_groups:
                    journey_conv_rate = group['Conversion Rate'].mean()
                    if not pd.isna(journey_conv_rate):
                        conv_rates.append(journey_conv_rate)
            else:
                for name, group in journey_groups:
                    if 'Unique Conversions' in group.columns and 'Unique Clicks' in group.columns:
                        conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
                        clicks = group['Unique Clicks'].sum()
                        if clicks > 0:
                            conv_rates.append(conversions / clicks)
            
            if conv_rates:
                percentile = (np.array(conv_rates) <= raw_metrics['conversion']['conversion_rate']).mean() * 100
                percentiles['conversion'] = percentile
        
        # Revenue per conversion percentiles
        if 'revenue' in raw_metrics:
            rpcs = []
            for name, group in journey_groups:
                if 'Revenue (SAR)' in group.columns and 'Unique Conversions' in group.columns:
                    revenue = group['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in group.columns else group['Revenue (SAR)'].sum()
                    conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
                    if conversions > 0:
                        rpcs.append(revenue / conversions)
            
            if rpcs:
                percentile = (np.array(rpcs) <= raw_metrics['revenue']['revenue_per_conversion']).mean() * 100
                percentiles['revenue'] = percentile
        
        # Component score contributions
        weights = {'delivery': 0.20, 'engagement': 0.25, 'conversion': 0.30, 'revenue': 0.25}
        component_contributions = {}
        for component, score in score_result['component_scores'].items():
            weight = weights[component]
            contribution = score * weight
            component_contributions[component] = {
                'score': score,
                'weight': weight,
                'contribution': contribution
            }
        
        # Summary insights
        worst_components = sorted(score_result['component_scores'].items(), key=lambda x: x[1])
        insights = []
        
        for component, score in worst_components[:2]:  # Show worst 2 components
            if score < 40:
                insights.append(f"🚨 {component.capitalize()} score ({score:.1f}) is critically low")
            elif score < 60:
                insights.append(f"⚠️ {component.capitalize()} score ({score:.1f}) is below average")
        
        return {
            'journey_name': journey_name,
            'data_rows': len(journey_data),
            'score_result': score_result,
            'raw_metrics': raw_metrics,
            'percentiles': percentiles,
            'component_contributions': component_contributions,
            'insights': insights
        }
        
    except Exception as e:
        return {'error': str(e)}

# In the main code, after cleaning
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

    # Page content based on selection
    if page == "Journeys":
        st.header("Journey Analysis")
        
        # Show comparison summary if enabled
        if comparison_result:
            st.info(f"📊 Period Comparison Active: {comparison_result['current_label']} vs {comparison_result['comparison_label']}")
            
            # Calculate journey metrics for both periods
            current_metrics = calculate_period_metrics(comparison_result['current_data'], comparison_result['current_days'], conversion_attribution)
            comp_metrics = calculate_period_metrics(comparison_result['comparison_data'], comparison_result['comparison_days'], conversion_attribution)
            metric_changes = calculate_metric_changes(current_metrics, comp_metrics)
            
            # Show quick comparison
            comp_col1, comp_col2, comp_col3, comp_col4 = st.columns(4)
            with comp_col1:
                change_data = metric_changes['selected_revenue']
                st.metric("Revenue", format_metric(change_data['current'], "SAR"), 
                         delta=f"{change_data['pct_change']:+.1f}%")
            with comp_col2:
                change_data = metric_changes['selected_conversions']
                st.metric("Conversions", format_metric(change_data['current']), 
                         delta=f"{change_data['pct_change']:+.1f}%")
            with comp_col3:
                change_data = metric_changes['ctr']
                st.metric("CTR", f"{change_data['current']:.2%}", 
                         delta=f"{change_data['pct_change']:+.1f}%")
            with comp_col4:
                change_data = metric_changes['conversion_rate']
                st.metric("Conv Rate", f"{change_data['current']:.2%}", 
                         delta=f"{change_data['pct_change']:+.1f}%")
            
            st.markdown("---")
        
        # Revenue Type Selection - Revenue Attribution Models
        st.markdown("**💰 Revenue Attribution Model Selection**")
        st.markdown("*Choose the attribution model for revenue analysis:*")
        
        available_revenue_cols = [col for col in df.columns if 'Revenue' in col]
        if available_revenue_cols:
            # Create user-friendly labels for attribution models
            revenue_labels = {}
            for col in available_revenue_cols:
                if col == 'Revenue (SAR)':
                    revenue_labels[col] = "📊 Total Revenue (Send-Through Attribution)"
                elif col == 'Click-Through Revenue (SAR)':
                    revenue_labels[col] = "🖱️ Click-Through Revenue Attribution"
                elif col == 'Impression-Through Revenue (SAR)':
                    revenue_labels[col] = "👁️ Impression-Through Revenue Attribution"
                else:
                    revenue_labels[col] = col
            
            # Default to total revenue (send-through)
            default_revenue = 'Revenue (SAR)' if 'Revenue (SAR)' in available_revenue_cols else available_revenue_cols[0]
            
            selected_label = st.selectbox(
                "Select Revenue Attribution Model", 
                [revenue_labels[col] for col in available_revenue_cols],
                index=[revenue_labels[col] for col in available_revenue_cols].index(revenue_labels[default_revenue]),
                key='revenue_type'
            )
            
            # Map back to actual column name
            selected_revenue = [col for col, label in revenue_labels.items() if label == selected_label][0]
        else:
            selected_revenue = 'Revenue (SAR)'  # Fallback
            st.warning("⚠️ No revenue columns found in data")
        
        # Journey Health Score Analysis
        st.subheader("🏥 Journey Health Dashboard")
        
        # Professional Methodology Explanation for Executives
        with st.expander("📊 Scoring Methodology (Click to View)", expanded=False):
            st.markdown("""
            ### **Health Score Methodology**

            **Method**: Percentile ranking with Empirical Bayes smoothing

            #### **How Scores are Calculated:**
            - **Relative Ranking**: Each journey is scored against all other journeys in your portfolio (0-100 scale)
            - **Empirical Bayes Smoothing**: Low-volume journeys are adjusted toward the portfolio average to avoid misleading scores from small samples
            - **No Fixed Benchmarks**: Scores reflect your actual portfolio distribution, not arbitrary industry numbers

            #### **Component Weights:**
            - 🚀 **Conversion Performance**: 30% - Conversion rate (clicks to conversions)
            - 🎯 **Engagement Performance**: 25% - Click-through rate (impressions to clicks)
            - 💰 **Revenue Efficiency**: 25% - Revenue per conversion (log-scaled to reduce outlier impact)
            - 📧 **Delivery Performance**: 20% - Delivery rate (sent to delivered)

            #### **Performance Tiers:**
            - **Excellent (80-100)**: Top quartile - scale these journeys
            - **Good (60-79)**: Above average - minor optimizations needed
            - **Fair (40-59)**: Below average - moderate improvements required
            - **Poor (0-39)**: Bottom quartile - immediate action required

            #### **Data Sufficiency:**
            Journeys with fewer than 10 sends, 3 conversions, or 3 days of data are marked "Insufficient Data" to prevent unreliable scores.
            """)
        
        
        # Calculate health scores for all journeys
        journey_health_data = cached_journey_health_scores(filtered_df)
        
        if journey_health_data:
            health_df = pd.DataFrame(journey_health_data)
            health_df = health_df.sort_values('Health Score', ascending=False)
            
            # Display top performers and those needing attention
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("🔥 Top Performing Journeys")
                top_performing_journeys = health_df.head(5)
                for _, row in top_performing_journeys.iterrows():
                    # Use expandable containers for full journey names
                    with st.container():
                        st.markdown(f"**{row['Journey Name']}**")
                        score_col, tier_col = st.columns([2, 1])
                        with score_col:
                            st.markdown(f"🏥 **{row['Health Score']:.1f}/100**")
                        with tier_col:
                            tier_color = "🟢" if row['Tier'] == "Excellent" else "🟡" if row['Tier'] == "Good" else "🟠"
                            st.markdown(f"{tier_color} {row['Tier']}")
                        st.markdown("---")
            
            with col2:
                st.subheader("🚨 Journeys Needing Attention")
                bottom_journeys = health_df[health_df['Health Score'] < 60].head(5)
                if not bottom_journeys.empty:
                    for _, row in bottom_journeys.iterrows():
                        # Use expandable containers for full journey names
                        with st.container():
                            st.markdown(f"**{row['Journey Name']}**")
                            score_col, tier_col = st.columns([2, 1])
                            with score_col:
                                st.markdown(f"🏥 **{row['Health Score']:.1f}/100**")
                            with tier_col:
                                tier_color = "🔴" if row['Tier'] == "Poor" else "🟠" if row['Tier'] == "Fair" else "🟡"
                                st.markdown(f"{tier_color} {row['Tier']}")
                            st.markdown("---")
                else:
                    st.success("🎉 All journeys are performing well!")
            
            # Health Score Distribution
            st.subheader("📊 Health Score Distribution")
            fig_health_dist = px.histogram(health_df, x='Health Score', nbins=20,
                                         title="Distribution of Journey Health Scores",
                                         color_discrete_sequence=[COLORS['primary']])
            fig_health_dist.add_vline(x=health_df['Health Score'].mean(),
                                    line_dash="dash", line_color=COLORS['danger'],
                                    annotation_text=f"Average: {health_df['Health Score'].mean():.1f}")
            st.plotly_chart(fig_health_dist, use_container_width=True)
            
            # Complete Health Dashboard Table
            st.subheader("📋 Complete Journey Health Report")
            
            # Add search and filter options
            search_col, filter_col = st.columns([2, 1])
            
            with search_col:
                search_term = st.text_input("🔍 Search Journey Names", placeholder="Type to filter journeys...", key='journey_search')
            
            with filter_col:
                tier_filter = st.selectbox("Filter by Tier", ['All'] + list(health_df['Tier'].unique()), key='tier_filter')
            
            # Apply filters
            display_health_df = health_df.copy()
            
            if search_term:
                display_health_df = display_health_df[
                    display_health_df['Journey Name'].str.contains(search_term, case=False, na=False)
                ]
            
            if tier_filter != 'All':
                display_health_df = display_health_df[display_health_df['Tier'] == tier_filter]
            
            # Prepare numeric dataframe for display while keeping numeric types so Streamlit sorts correctly
            numeric_display_df = display_health_df.copy()

            # Ensure numeric columns are numeric (coerce if necessary)
            numeric_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Total Conversions',
                            'Health Score', 'Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']
            for col in numeric_cols:
                if col in numeric_display_df.columns:
                    numeric_display_df[col] = pd.to_numeric(numeric_display_df[col], errors='coerce')

            # Add tier emojis to a separate display column (keep original Tier for filtering logic)
            tier_emojis = {
                'Excellent': '🟢',
                'Good': '🟡', 
                'Fair': '🟠',
                'Poor': '🔴'
            }
            # Create a human-friendly Tier display column
            numeric_display_df['Tier Display'] = numeric_display_df['Tier'].apply(lambda x: f"{tier_emojis.get(x, '⚪')} {x}")

            # Show filtered results count
            st.info(f"📊 Showing {len(numeric_display_df)} journeys (filtered from {len(health_df)} total)")

            # Define columns order for display
            columns_order = ['Journey Name', 'Health Score', 'Tier Display', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)',
                             'Click-Through Revenue (SAR)', 'Total Conversions', 'Delivery Score', 'Engagement Score',
                             'Conversion Score', 'Revenue Score']

            # Create formatters for Styler so values look nice but remain numeric underneath (preserves numeric sorting)
            formatters = {}
            if 'Health Score' in numeric_display_df.columns:
                formatters['Health Score'] = lambda x: f"{x:.1f}/100"
            if 'Revenue (SAR)' in numeric_display_df.columns:
                formatters['Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
                formatters['Impression-Through Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
                formatters['Click-Through Revenue (SAR)'] = lambda x: format_metric(x, "SAR")
            if 'Total Conversions' in numeric_display_df.columns:
                formatters['Total Conversions'] = lambda x: format_metric(x)
            for score in ['Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']:
                if score in numeric_display_df.columns:
                    formatters[score] = lambda x: f"{x:.1f}"

            # Use pandas Styler to format display without changing underlying dtypes
            try:
                styled = numeric_display_df[columns_order].style.format(formatters)
                st.dataframe(styled, width='stretch', height=400)
            except Exception:
                # Fallback: if Styler isn't supported in this environment, fall back to pre-formatted strings
                fallback = numeric_display_df[columns_order].copy()
                if 'Health Score' in fallback.columns:
                    fallback['Health Score'] = fallback['Health Score'].apply(lambda x: f"{x:.1f}/100")
                if 'Revenue (SAR)' in fallback.columns:
                    fallback['Revenue (SAR)'] = fallback['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                    fallback['Impression-Through Revenue (SAR)'] = fallback['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                    fallback['Click-Through Revenue (SAR)'] = fallback['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                if 'Total Conversions' in fallback.columns:
                    fallback['Total Conversions'] = fallback['Total Conversions'].apply(format_metric)
                if 'Tier Display' in fallback.columns:
                    fallback = fallback.rename(columns={'Tier Display': 'Tier'})

                st.dataframe(fallback, width='stretch', height=400)
            
            # Component Scores Radar Chart for Selected Journey
            st.subheader("🎯 Journey Performance Breakdown")
            selected_journey_health = st.selectbox("Select Journey for Detailed Analysis", 
                                                  health_df['Journey Name'].tolist(), 
                                                  key='health_journey')
            
            if selected_journey_health:
                selected_health_data = health_df[health_df['Journey Name'] == selected_journey_health].iloc[0]
                
                # Create radar chart for component scores with better visualization
                categories = ['Delivery Score', 'Engagement Score', 'Conversion Score', 'Revenue Score']
                values = [selected_health_data[cat] for cat in categories]
                
                # Debug information to understand the values
                st.write("**📊 Component Score Values:**")
                score_cols = st.columns(4)
                for i, (cat, val) in enumerate(zip(categories, values)):
                    with score_cols[i]:
                        st.metric(cat.replace(' Score', ''), f"{val:.1f}/100")
                
                # Create enhanced radar chart
                fig_radar = go.Figure()
                
                # Add the main data trace
                fig_radar.add_trace(go.Scatterpolar(
                    r=values,
                    theta=categories,
                    fill='toself',
                    name=selected_journey_health,
                    line=dict(color='rgb(0, 123, 255)', width=3),
                    fillcolor='rgba(0, 123, 255, 0.3)',
                    marker=dict(size=8, color='rgb(0, 123, 255)')
                ))
                
                # Add reference lines for performance levels
                excellent_line = [80] * len(categories)
                good_line = [60] * len(categories)
                
                fig_radar.add_trace(go.Scatterpolar(
                    r=excellent_line,
                    theta=categories,
                    mode='lines',
                    name='Excellent (80+)',
                    line=dict(color=COLORS['success'], width=2, dash='dash'),
                    showlegend=True
                ))
                
                fig_radar.add_trace(go.Scatterpolar(
                    r=good_line,
                    theta=categories,
                    mode='lines',
                    name='Good (60+)',
                    line=dict(color=COLORS['warning'], width=2, dash='dot'),
                    showlegend=True
                ))
                
                # Update layout with better styling
                fig_radar.update_layout(
                    polar=dict(
                        radialaxis=dict(
                            visible=True,
                            range=[0, 100],
                            tickmode='linear',
                            tick0=0,
                            dtick=20,
                            gridcolor='lightgray',
                            gridwidth=1
                        ),
                        angularaxis=dict(
                            gridcolor='lightgray',
                            gridwidth=1
                        )
                    ),
                    showlegend=True,
                    title=dict(
                        text=f"Performance Breakdown: {selected_journey_health}",
                        x=0.5,
                        font=dict(size=16)
                    ),
                    width=600,
                    height=500,
                    margin=dict(l=80, r=80, t=80, b=80)
                )
                st.plotly_chart(fig_radar, use_container_width=True)
                radar_img = export_chart_image(fig_radar, 'journey_radar')
                if radar_img:
                    st.download_button("Download Radar Chart", radar_img, "journey_radar.png", "image/png", key='dl_jour_radar')

                # Show recommendations
                journey_data_for_rec = filtered_df[filtered_df['Journey Name'] == selected_journey_health]
                health_info_for_rec = calculate_journey_health_score(journey_data_for_rec, filtered_df)
                
                st.subheader("💡 Recommendations")
                for rec in health_info_for_rec['recommendations']:
                    st.info(rec)

                # 🔍 DETAILED INDIVIDUAL JOURNEY ANALYSIS
                st.subheader("🔍 Detailed Journey Analysis")
                st.markdown("*Get the complete story behind this journey's score - same analysis as our debug script*")
                
                # Call our analysis function
                individual_analysis = analyze_individual_journey(selected_journey_health, filtered_df)
                
                if 'error' in individual_analysis:
                    st.error(f"❌ Error analyzing journey: {individual_analysis['error']}")
                else:
                    # Journey Summary
                    st.markdown(f"**📊 Journey:** {individual_analysis['journey_name']}")
                    st.markdown(f"**📈 Data Points:** {individual_analysis['data_rows']} rows of data")
                    st.markdown(f"**🎯 Final Score:** {individual_analysis['score_result']['health_score']:.1f}/100 ({individual_analysis['score_result']['tier']})")
                    st.markdown(f"**🔬 Method:** {individual_analysis['score_result']['scoring_method']}")
                    
                    # Raw Metrics Breakdown
                    with st.expander("📈 Raw Metrics Breakdown", expanded=True):
                        if 'delivery' in individual_analysis['raw_metrics']:
                            delivery_data = individual_analysis['raw_metrics']['delivery']
                            st.markdown("**📤 Delivery Performance:**")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Sent", format_metric(delivery_data['total_sent']))
                            with col2:
                                st.metric("Delivered", format_metric(delivery_data['total_delivered']))
                            with col3:
                                st.metric("Delivery Rate", f"{delivery_data['delivery_rate']:.1%}")
                        
                        if 'engagement' in individual_analysis['raw_metrics']:
                            engagement_data = individual_analysis['raw_metrics']['engagement']
                            st.markdown("**👆 Engagement Performance:**")
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Impressions", format_metric(engagement_data['total_impressions']))
                            with col2:
                                st.metric("Clicks", format_metric(engagement_data['total_clicks']))
                            with col3:
                                st.metric("CTR (Click Rate)", f"{engagement_data['ctr']:.2%}",
                                         help="Impressions → Clicks: How many people who saw it clicked it")
                        
                        if 'conversion' in individual_analysis['raw_metrics']:
                            conversion_data = individual_analysis['raw_metrics']['conversion']
                            journey_data = individual_analysis.get('journey_data', filtered_df[filtered_df['Journey Name'] == selected_journey_health])
                            
                            st.markdown("**💰 Conversion Performance:**")
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric("Clicks", format_metric(conversion_data['total_clicks']))
                            with col2:
                                st.metric("Conversions", format_metric(conversion_data['total_conversions']))
                            with col3:
                                st.metric("Conversion Rate (CVR)", f"{conversion_data['conversion_rate']:.2%}", 
                                         help="Clicks → Conversions: How many people who clicked actually converted")
                            with col4:
                                if 'source' in conversion_data:
                                    st.caption(f"Source: {conversion_data['source']}")
                            
                            # Additional attribution rates
                            st.markdown("**📊 Additional Attribution Metrics:**")
                            attr_col1, attr_col2, attr_col3 = st.columns(3)
                            
                            with attr_col1:
                                # Impression-Through Rate
                                if 'Unique Impression-Through Conversions' in journey_data.columns and 'Unique Impressions' in journey_data.columns:
                                    imp_conv = journey_data['Unique Impression-Through Conversions'].sum()
                                    imp_total = journey_data['Unique Impressions'].sum()
                                    imp_rate = (imp_conv / imp_total * 100) if imp_total > 0 else 0
                                    st.metric("Impression-Through Rate", f"{imp_rate:.2%}",
                                             help="Impressions → Conversions: People who converted after seeing (no click)")
                            
                            with attr_col2:
                                # Click-Through Rate (already shown above, but for completeness)
                                if 'Unique Click-Through Conversions' in journey_data.columns and 'Unique Clicks' in journey_data.columns:
                                    click_conv = journey_data['Unique Click-Through Conversions'].sum()
                                    click_total = journey_data['Unique Clicks'].sum()
                                    click_rate = (click_conv / click_total * 100) if click_total > 0 else 0
                                    st.metric("Click-Through Rate", f"{click_rate:.2%}",
                                             help="Clicks → Conversions: People who converted after clicking (same as CVR above)")
                            
                            with attr_col3:
                                # Overall Rate (Sent)
                                if 'Sent' in journey_data.columns:
                                    sent_total = journey_data['Sent'].sum()
                                    overall_rate = (conversion_data['total_conversions'] / sent_total * 100) if sent_total > 0 else 0
                                    st.metric("Overall Rate (Sent)", f"{overall_rate:.2%}",
                                             help="Sent → Conversions: End-to-end conversion rate from send to conversion")
                        
                        if 'revenue' in individual_analysis['raw_metrics']:
                            revenue_data = individual_analysis['raw_metrics']['revenue']
                            st.markdown("**💵 Revenue Performance:**")
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric(selected_rev_label, format_metric(revenue_data['total_revenue'], "SAR"))
                            with col2:
                                st.metric("Conversions", format_metric(revenue_data['total_conversions']))
                            with col3:
                                st.metric("Rev/Conversion", format_metric(revenue_data['revenue_per_conversion'], "SAR"))
                            with col4:
                                st.metric("Log(RPC)", f"{revenue_data['log_rpc']:.2f}")
                    
                    # Population Comparison & Percentiles
                    with st.expander("📊 Population Comparison & Percentiles", expanded=True):
                        st.markdown("**How this journey compares to all other journeys in your portfolio:**")
                        
                        percentile_cols = st.columns(2)
                        with percentile_cols[0]:
                            if 'delivery' in individual_analysis['percentiles']:
                                perc = individual_analysis['percentiles']['delivery']
                                color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                                st.markdown(f"📤 **Delivery**: {color} {perc:.0f}th percentile")
                            
                            if 'engagement' in individual_analysis['percentiles']:
                                perc = individual_analysis['percentiles']['engagement']
                                color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                                st.markdown(f"👆 **CTR**: {color} {perc:.0f}th percentile")
                        
                        with percentile_cols[1]:
                            if 'conversion' in individual_analysis['percentiles']:
                                perc = individual_analysis['percentiles']['conversion']
                                color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                                st.markdown(f"💰 **Conversion**: {color} {perc:.0f}th percentile")
                            
                            if 'revenue' in individual_analysis['percentiles']:
                                perc = individual_analysis['percentiles']['revenue']
                                color = "🟢" if perc >= 80 else "🟡" if perc >= 60 else "🟠" if perc >= 40 else "🔴"
                                st.markdown(f"💵 **Revenue/Conv**: {color} {perc:.0f}th percentile")
                    
                    # Component Score Contributions
                    with st.expander("🔢 Component Score Contributions", expanded=True):
                        st.markdown("**How each component contributes to the final health score:**")
                        
                        # Create a detailed breakdown table
                        contribution_data = []
                        total_contribution = 0
                        
                        for component, details in individual_analysis['component_contributions'].items():
                            contribution_data.append({
                                'Component': component.capitalize(),
                                'Score': f"{details['score']:.1f}/100",
                                'Weight': f"{details['weight']:.0%}",
                                'Contribution': f"{details['contribution']:.1f} points"
                            })
                            total_contribution += details['contribution']
                        
                        # Display as a nice table
                        contrib_df = pd.DataFrame(contribution_data)
                        st.dataframe(contrib_df, use_container_width=True)
                        
                        # Show final calculation
                        st.markdown(f"**🎯 Total Weighted Score: {total_contribution:.1f}/100**")
                        
                        # Show the weights explanation
                        st.caption("💡 Weights: Conversion 30% (most critical for ROI) • Delivery 20% • Engagement 25% • Revenue 25%")
                    
                    # Key Insights & Problem Areas
                    if individual_analysis['insights']:
                        with st.expander("🎯 Key Insights & Problem Areas", expanded=True):
                            st.markdown("**Why this journey scored the way it did:**")
                            for insight in individual_analysis['insights']:
                                st.warning(insight)
                    
                    # Actionable Recommendations (already shown above but repeated here for completeness)
                    st.markdown("**💡 Action Items for this Journey:**")
                    for rec in individual_analysis['score_result']['recommendations']:
                        st.info(rec)
        
        # Advanced Funnel Analysis
        st.subheader("🎯 Advanced Conversion Funnel Analysis")
        
        funnel_journey = st.selectbox("Select Journey for Funnel Analysis", 
                                    unique_journeys, 
                                    key='funnel_journey')
        
        if funnel_journey and str(funnel_journey) != 'nan':
            funnel_data = filtered_df[filtered_df['Journey Name'] == funnel_journey]
            funnel_analysis = analyze_journey_funnel(funnel_data)
            
            # Display funnel visualization
            if funnel_analysis['funnel_data']:
                funnel_stages = []
                funnel_values = []
                
                for stage, value in funnel_analysis['funnel_data'].items():
                    if value > 0:
                        funnel_stages.append(stage)
                        funnel_values.append(value)
                
                if funnel_stages:
                    fig_funnel = go.Figure(go.Funnel(
                        y=funnel_stages,
                        x=funnel_values,
                        textposition="inside",
                        textinfo="value+percent initial+percent previous",
                        opacity=0.65,
                        marker={"color": ["deepskyblue", "lightsalmon", "tan", "teal", "silver"]},
                        connector={"line": {"color": "royalblue", "dash": "dot", "width": 3}}
                    ))
                    fig_funnel.update_layout(title=f"Conversion Funnel: {funnel_journey}")
                    st.plotly_chart(fig_funnel)
            
            # Display conversion rates
            if funnel_analysis['conversion_rates']:
                st.subheader("📈 Conversion Rates Between Stages")
                rates_col1, rates_col2 = st.columns(2)
                
                rate_items = list(funnel_analysis['conversion_rates'].items())
                mid_point = len(rate_items) // 2
                
                with rates_col1:
                    for rate_name, rate_value in rate_items[:mid_point]:
                        st.metric(rate_name, f"{rate_value:.2%}")
                
                with rates_col2:
                    for rate_name, rate_value in rate_items[mid_point:]:
                        st.metric(rate_name, f"{rate_value:.2%}")
            
            # Display insights
            if funnel_analysis['insights']:
                st.subheader("🔍 Funnel Insights")
                for insight in funnel_analysis['insights']:
                    st.warning(insight)
        
        # Anomaly Detection
        st.subheader("🚨 Journey Anomaly Detection")
        
        col1, col2 = st.columns([2, 1])
        with col2:
            lookback_days = st.slider("Analysis Period (days)", 7, 90, 30, key='anomaly_days')
        
        with col1:
            st.write("Detecting unusual performance patterns in journeys...")
        
        if st.button("🔍 Detect Anomalies", key='detect_anomalies'):
            with st.spinner("Analyzing journey performance patterns..."):
                anomalies = detect_journey_anomalies(filtered_df, lookback_days)
                
                if anomalies:
                    st.subheader(f"🚨 {len(anomalies)} Anomalies Detected")
                    
                    # Group by severity
                    critical_anomalies = [a for a in anomalies if '🚨 Critical' in a.get('severity', '')]
                    warning_anomalies = [a for a in anomalies if '⚠️ Warning' in a.get('severity', '')]
                    
                    if critical_anomalies:
                        st.error(f"🚨 {len(critical_anomalies)} Critical Issues Require Immediate Attention")
                        for anomaly in critical_anomalies[:5]:  # Show top 5
                            with st.expander(f"{anomaly['journey']} - {anomaly['metric']} {anomaly.get('direction', '')}"):
                                col1, col2, col3 = st.columns(3)
                                with col1:
                                    st.metric("Historical", f"{anomaly['historical_value']:.3f}")
                                with col2:
                                    st.metric("Recent", f"{anomaly['recent_value']:.3f}")
                                with col3:
                                    st.metric("Change", f"{anomaly['change_pct']:+.1f}%")
                                st.info(f"💡 {anomaly['recommendation']}")
                    
                    if warning_anomalies:
                        st.warning(f"⚠️ {len(warning_anomalies)} Performance Changes Detected")
                        with st.expander("View Warning Anomalies"):
                            for anomaly in warning_anomalies:
                                st.write(f"**{anomaly['journey']}** - {anomaly['metric']}: {anomaly['change_pct']:+.1f}% change")
                                st.write(f"   💡 {anomaly['recommendation']}")
                else:
                    st.success("✅ No significant anomalies detected. All journeys are performing within normal ranges!")
        
        # Revenue Attribution Waterfall
        st.subheader("💰 Revenue Attribution Analysis")
        
        waterfall_journey = st.selectbox("Select Journey for Revenue Attribution", 
                                       unique_journeys, 
                                       key='waterfall_journey')
        
        if waterfall_journey and str(waterfall_journey) != 'nan':
            waterfall_data_full = filtered_df[filtered_df['Journey Name'] == waterfall_journey]
            waterfall_result = create_revenue_attribution_waterfall(waterfall_data_full)
            
            if waterfall_result['total_revenue'] > 0:
                # Proper waterfall chart showing attribution flow
                wf_data = waterfall_result['waterfall_data']
                wf_labels = [d['step'] for d in wf_data if d['step'] != 'Starting Point']
                wf_values = []
                wf_measures = []
                for d in wf_data:
                    if d['step'] == 'Starting Point':
                        continue
                    if d['step'] == 'Total Revenue':
                        wf_measures.append('total')
                        wf_values.append(d['cumulative'])
                    else:
                        wf_measures.append('relative')
                        wf_values.append(d['value'])

                fig_waterfall = go.Figure(go.Waterfall(
                    x=wf_labels,
                    y=wf_values,
                    measure=wf_measures,
                    text=[format_metric(v, "SAR") for v in wf_values],
                    textposition='outside',
                    connector=dict(line=dict(color='#E5E7EB', width=1)),
                    increasing=dict(marker=dict(color=COLORS['primary'])),
                    decreasing=dict(marker=dict(color=COLORS['danger'])),
                    totals=dict(marker=dict(color=COLORS['success'])),
                ))
                fig_waterfall.update_layout(
                    title=f"Revenue Attribution Breakdown: {waterfall_journey}",
                    yaxis_title="Revenue (SAR)",
                    showlegend=False,
                )
                st.plotly_chart(fig_waterfall, use_container_width=True)
                
                # Attribution breakdown table
                st.subheader("📊 Attribution Breakdown")
                attr_col1, attr_col2 = st.columns(2)
                
                with attr_col1:
                    for source, percentage in waterfall_result['attribution_breakdown'].items():
                        st.metric(f"{source} Attribution", f"{percentage:.1f}%")
                
                with attr_col2:
                    # Create pie chart for attribution
                    fig_attr_pie = px.pie(
                        values=list(waterfall_result['attribution_breakdown'].values()),
                        names=list(waterfall_result['attribution_breakdown'].keys()),
                        title="Revenue Attribution Distribution"
                    )
                    st.plotly_chart(fig_attr_pie)
                
                # Attribution insights
                st.subheader("🎯 Attribution Insights")
                max_source = max(waterfall_result['attribution_breakdown'], key=waterfall_result['attribution_breakdown'].get)
                max_percentage = waterfall_result['attribution_breakdown'][max_source]
                
                if max_percentage > 60:
                    st.info(f"🎯 **{max_source}** is the dominant revenue driver ({max_percentage:.1f}%). Consider optimizing this channel further.")
                elif max_percentage < 40:
                    st.info("🔄 Revenue is well-distributed across attribution sources. This indicates a healthy multi-touch journey.")
                else:
                    st.info(f"⚖️ **{max_source}** leads revenue attribution. Monitor the balance between different touchpoints.")
            else:
                st.warning("No revenue data available for this journey.")
        
        # Journey Lifecycle Analysis
        st.subheader("🔄 Journey Lifecycle Analytics")
        
        with st.spinner("Analyzing journey maturity and performance curves..."):
            lifecycle_data = cached_journey_lifecycle(filtered_df)
            
            if lifecycle_data and not isinstance(lifecycle_data, dict) and len(lifecycle_data) > 0:
                lifecycle_df = pd.DataFrame(lifecycle_data)
                
                # Maturity distribution
                col1, col2 = st.columns(2)
                
                with col1:
                    st.subheader("📊 Journey Maturity Distribution")
                    maturity_counts = lifecycle_df['maturity_stage'].value_counts()
                    fig_maturity = px.pie(values=maturity_counts.values, names=maturity_counts.index,
                                        title="Journeys by Maturity Stage")
                    st.plotly_chart(fig_maturity)
                
                with col2:
                    st.subheader("📈 Performance vs Age")
                    fig_age_perf = px.scatter(lifecycle_df, 
                                            x='journey_age_days', 
                                            y='efficiency_score',
                                            color='maturity_stage',
                                            size='total_revenue',
                                            hover_data=['journey', 'growth_trend'],
                                            title="Journey Performance vs Age")
                    fig_age_perf.update_xaxes(title="Journey Age (Days)")
                    fig_age_perf.update_yaxes(title="Efficiency Score")
                    st.plotly_chart(fig_age_perf)
                
                # Lifecycle insights table
                st.subheader("🔍 Journey Lifecycle Insights")
                
                # Sort by efficiency score for display
                lifecycle_display = lifecycle_df.sort_values('efficiency_score', ascending=False)
                
                # Format the table for better readability
                display_cols = ['journey', 'maturity_stage', 'journey_age_days', 'activity_frequency', 
                              'consistency_score', 'growth_trend', 'efficiency_score', 'recommendation']
                
                for idx, row in lifecycle_display.head(10).iterrows():
                    with st.expander(f"{row['journey']} - {row['maturity_stage']} ({row['efficiency_score']:.1f} efficiency)"):
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Age", f"{row['journey_age_days']} days")
                            st.metric("Activity", f"{row['activity_frequency']:.1f}%")
                        with col2:
                            st.metric("Consistency", f"{row['consistency_score']:.1f}/100")
                            st.metric("Trend", row['growth_trend'])
                        with col3:
                            st.metric("Efficiency", f"{row['efficiency_score']:.1f}/100")
                            st.metric("Revenue", format_metric(row['total_revenue'], "SAR"))
                        with col4:
                            st.metric("Conversions", format_metric(row['total_conversions']))
                            st.metric("Active Days", f"{row['active_days']}")
                        
                        st.info(f"💡 **Recommendation:** {row['recommendation']}")
            else:
                st.info("No journey lifecycle data available. Journeys need at least 2 data points over time for lifecycle analysis.")
        
        # Journey Comparison Tool
        st.subheader("🔄 Advanced Journey Comparison")
        
        comparison_col1, comparison_col2 = st.columns(2)
        
        with comparison_col1:
            journey_comp_1 = st.selectbox("Select First Journey", unique_journeys, key='compare_journey_1')
        with comparison_col2:
            journey_comp_2 = st.selectbox("Select Second Journey", 
                                        [j for j in unique_journeys if j != journey_comp_1], 
                                        key='compare_journey_2')
        
        if journey_comp_1 and journey_comp_2 and str(journey_comp_1) != 'nan' and str(journey_comp_2) != 'nan':
            if st.button("🔍 Compare Journeys", key='compare_button'):
                with st.spinner("Performing statistical comparison..."):
                    comparison_result = create_journey_comparison_analysis(filtered_df, journey_comp_1, journey_comp_2)
                    
                    if 'error' not in comparison_result:
                        st.subheader(f"📊 Comparison: {journey_comp_1} vs {journey_comp_2}")
                        
                        # Overall winner
                        if comparison_result['overall_winner'] != "Tie":
                            st.success(f"🏆 **Overall Winner:** {comparison_result['overall_winner']} (Confidence: {comparison_result['confidence']})")
                        else:
                            st.info("🤝 **Result:** Performance is very similar between both journeys")
                        
                        # Detailed metrics comparison
                        st.subheader("📈 Detailed Metrics Comparison")
                        
                        for metric_name, metric_data in comparison_result['metrics'].items():
                            with st.expander(f"{metric_name} Comparison"):
                                comp_col1, comp_col2, comp_col3 = st.columns(3)
                                
                                with comp_col1:
                                    st.metric(f"{journey_comp_1} (Avg)", 
                                            format_metric(metric_data['journey1_avg'], "SAR" if "Revenue" in metric_name else ""))
                                    st.write(f"Total: {format_metric(metric_data['journey1_total'], 'SAR' if 'Revenue' in metric_name else '')}")
                                
                                with comp_col2:
                                    st.metric(f"{journey_comp_2} (Avg)", 
                                            format_metric(metric_data['journey2_avg'], "SAR" if "Revenue" in metric_name else ""))
                                    st.write(f"Total: {format_metric(metric_data['journey2_total'], 'SAR' if 'Revenue' in metric_name else '')}")
                                
                                with comp_col3:
                                    diff_color = "normal" if abs(metric_data['pct_difference']) < 10 else "inverse" if metric_data['pct_difference'] < 0 else "normal"
                                    st.metric("Difference", 
                                            f"{metric_data['pct_difference']:+.1f}%",
                                            delta=f"Winner: {metric_data['winner']}")
                                    
                                    if metric_data['significance'] != "N/A":
                                        significance_color = "🟢" if metric_data['significance'] == "Significant" else "🟡"
                                        st.write(f"{significance_color} Statistical Significance: {metric_data['significance']}")
                                        if metric_data['p_value']:
                                            st.write(f"p-value: {metric_data['p_value']:.4f}")
                        
                        # Recommendations based on comparison
                        st.subheader("💡 Comparison Insights & Recommendations")
                        
                        winner = comparison_result['overall_winner']
                        if winner != "Tie":
                            st.info(f"🎯 **Primary Recommendation:** Scale up **{winner}** and apply its successful elements to **{journey_comp_1 if winner == journey_comp_2 else journey_comp_2}**")
                            
                            # Specific metric recommendations
                            strong_metrics = [name for name, data in comparison_result['metrics'].items() if data['winner'] == winner and abs(data['pct_difference']) > 20]
                            if strong_metrics:
                                st.success(f"🔥 **{winner}** excels in: {', '.join(strong_metrics)}")
                            
                        else:
                            st.info("🤝 Both journeys perform similarly. Consider A/B testing specific elements to find optimization opportunities.")
                    
                    else:
                        st.error(f"Comparison failed: {comparison_result['error']}")
        
        # Professional BI Section: Custom Date Range Analysis
        st.markdown("---")
        st.header("📊 Advanced Business Intelligence Analytics")
        
        # Executive Summary Cards - Use wider layout
        st.subheader("📈 Executive Summary")
        exec_col1, exec_col2, exec_col3, exec_col4, exec_col5, exec_col6 = st.columns(6)
        
        with exec_col1:
            total_journeys = len(filtered_df['Journey Name'].dropna().unique())
            st.metric("🎯 Active Journeys", total_journeys)
        
        with exec_col2:
            total_revenue = filtered_df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in filtered_df.columns else filtered_df['Revenue (SAR)'].sum()
            st.metric("💰 Total Revenue", format_metric(total_revenue, "SAR"))
        
        with exec_col3:
            total_conversions = filtered_df['Unique Conversions'].sum()
            st.metric("🔄 Total Conversions", format_metric(total_conversions))
        
        with exec_col4:
            avg_health_score = pd.DataFrame(journey_health_data)['Health Score'].mean() if journey_health_data else 0
            st.metric("🏥 Avg Health Score", f"{avg_health_score:.1f}/100")
        
        with exec_col5:
            total_sent = filtered_df['Sent'].sum()
            st.metric("📧 Total Sent", format_metric(total_sent))
        
        with exec_col6:
            avg_conversion_rate = (filtered_df['Unique Conversions'].sum() / filtered_df['Sent'].sum() * 100) if filtered_df['Sent'].sum() > 0 else 0
            st.metric("📊 Avg Conv. Rate", f"{avg_conversion_rate:.2f}%")
        
        # Custom Date Range Comparison Tool - Optimized for wide layout
        st.subheader("📅 Custom Period Comparison Analysis")
        st.markdown("*Compare journey performance between any two custom date ranges*")
        
        # Date range selection with professional layout - better use of wide screen
        date_col1, date_col2, date_col3 = st.columns([1, 1, 1])
        
        with date_col1:
            st.markdown("**📅 Period 1 (Baseline)**")
            period1_start = st.date_input("Start Date", value=filtered_df['Reporting Period Start Date'].min() if not filtered_df.empty else pd.Timestamp.now() - pd.Timedelta(days=30), key='p1_start')
            period1_end = st.date_input("End Date", value=filtered_df['Reporting Period Start Date'].min() + pd.Timedelta(days=14) if not filtered_df.empty else pd.Timestamp.now() - pd.Timedelta(days=16), key='p1_end')
        
        with date_col2:
            st.markdown("**📅 Period 2 (Comparison)**")
            period2_start = st.date_input("Start Date", value=filtered_df['Reporting Period Start Date'].max() - pd.Timedelta(days=14) if not filtered_df.empty else pd.Timestamp.now() - pd.Timedelta(days=14), key='p2_start')
            period2_end = st.date_input("End Date", value=filtered_df['Reporting Period Start Date'].max() if not filtered_df.empty else pd.Timestamp.now(), key='p2_end')
        
        with date_col3:
            st.markdown("**🎯 Analysis Options**")
            # Journey selection for focused analysis
            selected_journeys_for_comparison = st.multiselect(
                "Select Journeys (leave empty for all)",
                unique_journeys,
                help="Select specific journeys to focus the comparison analysis"
            )
            # Analysis trigger
            run_comparison = st.button("🔍 Run Period Comparison Analysis", key='run_period_comparison')
        
        if run_comparison:
            with st.spinner("🔄 Analyzing performance across periods..."):
                date_range_1 = [period1_start, period1_end]
                date_range_2 = [period2_start, period2_end]
                
                comparison_result = create_custom_date_range_comparison(
                    filtered_df, 
                    date_range_1, 
                    date_range_2, 
                    selected_journeys_for_comparison if selected_journeys_for_comparison else None
                )
                
                if 'error' not in comparison_result:
                    # Results Header
                    st.markdown("---")
                    st.header("📊 Period Comparison Results")
                    
                    # Period Overview
                    period_col1, period_col2, period_col3 = st.columns([1, 1, 1])
                    
                    with period_col1:
                        st.info(f"**📅 Period 1 (Baseline)**\n{comparison_result['period1_label']}")
                    
                    with period_col2:
                        st.info(f"**📅 Period 2 (Comparison)**\n{comparison_result['period2_label']}")
                    
                    with period_col3:
                        overall_trend = comparison_result['statistical_summary']['overall_trend']
                        trend_emoji = "📈" if overall_trend == "Positive" else "📉" if overall_trend == "Negative" else "➡️"
                        st.info(f"**{trend_emoji} Overall Trend**\n{overall_trend}")
                    
                    # Key Metrics Comparison
                    st.subheader("📊 Key Performance Metrics")
                    
                    metrics_data = []
                    for metric_name, metric_data in comparison_result['metrics'].items():
                        metrics_data.append({
                            'Metric': metric_name,
                            'Period 1 (Daily Avg)': format_metric(metric_data['period1_daily_avg'], "SAR" if "Revenue" in metric_name else ""),
                            'Period 2 (Daily Avg)': format_metric(metric_data['period2_daily_avg'], "SAR" if "Revenue" in metric_name else ""),
                            'Change %': f"{metric_data['pct_change']:+.1f}%",
                            'Trend': metric_data['trend'],
                            'Statistical Significance': metric_data['significance']
                        })
                    
                    metrics_df = pd.DataFrame(metrics_data)
                    st.dataframe(metrics_df, width='stretch')
                    
                    # Visual Comparison Charts
                    st.subheader("📈 Visual Performance Comparison")
                    
                    # Create comparison charts
                    chart_col1, chart_col2 = st.columns(2)
                    
                    with chart_col1:
                        # Revenue comparison
                        if 'Revenue (SAR)' in comparison_result['metrics']:
                            rev_data = comparison_result['metrics']['Revenue (SAR)']
                            fig_rev = go.Figure(data=[
                                go.Bar(name='Period 1', x=['Daily Average Revenue'], y=[rev_data['period1_daily_avg']], marker_color=COLORS['info']),
                                go.Bar(name='Period 2', x=['Daily Average Revenue'], y=[rev_data['period2_daily_avg']], marker_color=COLORS['primary'])
                            ])
                            fig_rev.update_layout(title="Revenue Comparison", yaxis_title="Revenue (SAR)")
                            st.plotly_chart(fig_rev, use_container_width=True)
                    
                    with chart_col2:
                        # Conversion comparison
                        if 'Unique Conversions' in comparison_result['metrics']:
                            conv_data = comparison_result['metrics']['Unique Conversions']
                            fig_conv = go.Figure(data=[
                                go.Bar(name='Period 1', x=['Daily Average Conversions'], y=[conv_data['period1_daily_avg']], marker_color=COLORS['info']),
                                go.Bar(name='Period 2', x=['Daily Average Conversions'], y=[conv_data['period2_daily_avg']], marker_color=COLORS['success'])
                            ])
                            fig_conv.update_layout(title="Conversions Comparison", yaxis_title="Conversions")
                            st.plotly_chart(fig_conv, use_container_width=True)
                    
                    # Journey-Level Breakdown (if journeys were selected)
                    if comparison_result['journey_breakdown']:
                        st.subheader("🎯 Journey-Level Performance Breakdown")
                        
                        for journey_name, journey_metrics in comparison_result['journey_breakdown'].items():
                            with st.expander(f"📊 {journey_name}"):
                                journey_col1, journey_col2 = st.columns(2)
                                
                                with journey_col1:
                                    if 'Unique Conversions' in journey_metrics:
                                        conv_metric = journey_metrics['Unique Conversions']
                                        st.metric(
                                            "Daily Conversions",
                                            format_metric(conv_metric['period2_daily_avg']),
                                            delta=f"{conv_metric['pct_change']:+.1f}% vs Period 1"
                                        )
                                
                                with journey_col2:
                                    if 'Revenue (SAR)' in journey_metrics:
                                        rev_metric = journey_metrics['Revenue (SAR)']
                                        st.metric(
                                            "Daily Revenue",
                                            format_metric(rev_metric['period2_daily_avg'], "SAR"),
                                            delta=f"{rev_metric['pct_change']:+.1f}% vs Period 1"
                                        )
                    
                    # Statistical Summary and Insights
                    st.subheader("🔬 Statistical Analysis Summary")
                    
                    stat_col1, stat_col2, stat_col3 = st.columns(3)
                    
                    with stat_col1:
                        sig_improvements = comparison_result['statistical_summary']['significant_improvements']
                        st.metric("📈 Significant Improvements", sig_improvements)
                    
                    with stat_col2:
                        sig_declines = comparison_result['statistical_summary']['significant_declines']
                        st.metric("📉 Significant Declines", sig_declines)
                    
                    with stat_col3:
                        confidence_level = "High" if sig_improvements + sig_declines >= 2 else "Medium" if sig_improvements + sig_declines >= 1 else "Low"
                        st.metric("🎯 Analysis Confidence", confidence_level)
                    
                    # Business Intelligence Insights
                    st.subheader("💡 Business Intelligence Insights")
                    
                    insights = []
                    
                    # Revenue insights
                    if 'Revenue (SAR)' in comparison_result['metrics']:
                        rev_change = comparison_result['metrics']['Revenue (SAR)']['pct_change']
                        if rev_change > 10:
                            insights.append(f"🚀 **Strong Revenue Growth**: {rev_change:+.1f}% increase in daily revenue indicates successful optimization")
                        elif rev_change < -10:
                            insights.append(f"⚠️ **Revenue Decline Alert**: {rev_change:+.1f}% decrease requires immediate investigation")
                        else:
                            insights.append(f"➡️ **Stable Revenue**: {rev_change:+.1f}% change shows consistent performance")
                    
                    # Conversion insights
                    if 'Unique Conversions' in comparison_result['metrics']:
                        conv_change = comparison_result['metrics']['Unique Conversions']['pct_change']
                        if conv_change > 15:
                            insights.append(f"🎯 **Conversion Optimization Success**: {conv_change:+.1f}% improvement in conversion rate")
                        elif conv_change < -15:
                            insights.append(f"🚨 **Conversion Drop**: {conv_change:+.1f}% decline needs funnel analysis")
                    
                    # Volume insights
                    if 'Sent' in comparison_result['metrics']:
                        sent_change = comparison_result['metrics']['Sent']['pct_change']
                        if sent_change > 20:
                            insights.append(f"📈 **Scale Expansion**: {sent_change:+.1f}% increase in campaign volume")
                        elif sent_change < -20:
                            insights.append(f"📉 **Volume Reduction**: {sent_change:+.1f}% decrease in send volume")
                    
                    # Display insights
                    if insights:
                        for insight in insights:
                            st.info(insight)
                    else:
                        st.info("📊 Performance appears stable across both periods with no significant changes detected.")
                    
                    # Recommendations
                    st.subheader("🎯 Strategic Recommendations")
                    
                    recommendations = []
                    
                    if comparison_result['statistical_summary']['overall_trend'] == "Positive":
                        recommendations.append("✅ **Scale Success**: Current strategies are working - consider increasing budget allocation")
                        recommendations.append("🔄 **Replicate Winners**: Apply successful elements to underperforming journeys")
                    elif comparison_result['statistical_summary']['overall_trend'] == "Negative":
                        recommendations.append("🔍 **Deep Dive Analysis**: Investigate root causes of performance decline")
                        recommendations.append("⚡ **Quick Wins**: Focus on highest-impact optimizations first")
                    else:
                        recommendations.append("🎯 **A/B Testing**: Mixed results suggest opportunities for targeted experiments")
                        recommendations.append("📊 **Granular Analysis**: Drill down into segment and channel performance")
                    
                    for rec in recommendations:
                        st.success(rec)
                
                else:
                    st.error(f"Analysis failed: {comparison_result['error']}")
        
        # Cohort Analysis Section
        st.markdown("---")
        st.subheader("👥 Cohort Performance Analysis")
        
        cohort_period = st.selectbox("Select Cohort Period", ['week', 'month'], key='cohort_period')
        
        if st.button("📊 Generate Cohort Analysis", key='run_cohort'):
            with st.spinner("Analyzing cohort performance..."):
                cohort_result = create_cohort_analysis(filtered_df, cohort_period)
                
                if isinstance(cohort_result, pd.DataFrame) and not cohort_result.empty:
                    st.subheader(f"📈 {cohort_period.title()}ly Cohort Performance")
                    
                    # Display cohort data
                    cohort_display = cohort_result.copy()
                    cohort_display['Revenue (SAR)'] = cohort_display['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                    cohort_display['Unique Conversions'] = cohort_display['Unique Conversions'].apply(format_metric)
                    
                    st.dataframe(cohort_display.head(20), use_container_width=True)
                    
                    # Growth rate visualization
                    if 'Revenue (SAR)_growth' in cohort_result.columns:
                        fig_growth = px.line(cohort_result, 
                                           x='cohort_str', 
                                           y='Revenue (SAR)_growth', 
                                           color='Journey Name',
                                           title=f"Revenue Growth Rate by {cohort_period.title()}")
                        fig_growth.update_xaxes(title=f"{cohort_period.title()} Period")
                        fig_growth.update_yaxes(title="Growth Rate (%)")
                        st.plotly_chart(fig_growth, use_container_width=True)
                
                else:
                    st.warning("Insufficient data for cohort analysis")
        
        # Top Journeys
        st.subheader("Top Journeys")
        jour_metric_options = ['Delivered Rate', 'Unique Clicks', 'Unique Conversions', 'Selected Revenue (SAR)', 'Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
        if 'Selected Revenue (SAR)' not in filtered_df.columns:
            jour_metric_options = [m for m in jour_metric_options if m != 'Selected Revenue (SAR)']
        # Add conversion attribution options if they exist
        if 'Unique Click-Through Conversions' in filtered_df.columns:
            jour_metric_options.insert(3, 'Unique Click-Through Conversions')
        if 'Unique Impression-Through Conversions' in filtered_df.columns:
            jour_metric_options.insert(3, 'Unique Impression-Through Conversions')
        jour_metric = st.selectbox("Metric", jour_metric_options, key='jour_metric', format_func=_attribution_display)
        top_jour = get_top_journeys(filtered_df, jour_metric)
        
        # Create display version for table
        top_jour_display = top_jour.copy()
        
        # Store original numeric values for sorting
        original_values = top_jour_display[jour_metric].copy()
        
        # Format the metric column for display
        if 'Revenue' in jour_metric:
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(lambda x: format_metric(x, "SAR"))
        elif jour_metric in ['Unique Clicks', 'Unique Conversions', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions']:
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(format_metric)
        elif 'Rate' in jour_metric:
            # For rates, convert to percentage
            top_jour_display[jour_metric] = top_jour_display[jour_metric].apply(lambda x: f"{x*100:.1f}%")
        
        # Display table with proper sorting
        st.dataframe(top_jour_display.rename(columns=attribution_rename))

        # Create chart with original numeric values
        fig2 = px.bar(top_jour, x='Journey Name', y=jour_metric, title=f"Top Journeys by {_attribution_display(jour_metric)}",
                      color_discrete_sequence=COLOR_SEQUENCE)
        st.plotly_chart(fig2, use_container_width=True)
        
        # Journey Drill-Down
        st.subheader("Journey Drill-Down")
        selected_journeys = st.multiselect("Select Journeys for Details", filtered_df['Journey Name'].unique(), key='drill_jour')
        if selected_journeys:
            jour_details = filtered_df[filtered_df['Journey Name'].isin(selected_journeys)]
            
            # Summary KPIs
            col1, col2, col3, col4, col5, col6 = st.columns(6)
            with col1:
                st.metric("Total Sent", format_metric(jour_details['Sent'].sum()))
            with col2:
                st.metric("Total Delivered", format_metric(jour_details['Delivered'].sum()))
            with col3:
                st.metric(selected_conv_label, format_metric(jour_details['Unique Conversions'].sum()))
            with col4:
                st.metric("Send-Through Revenue", format_metric(jour_details['Revenue (SAR)'].sum(), "SAR"))
            with col5:
                st.metric("Impression-Through Revenue", format_metric(jour_details['Impression-Through Revenue (SAR)'].sum(), "SAR"))
            with col6:
                st.metric("Click-Through Revenue", format_metric(jour_details['Click-Through Revenue (SAR)'].sum(), "SAR"))
            
            # Performance by Channel
            st.subheader("Performance by Channel")
            chan_perf_jour = jour_details.groupby('Channel').agg({
                'Sent': 'sum',
                'Delivered': 'sum',
                'Unique Conversions': 'sum',
                'Revenue (SAR)': 'sum',
                'Impression-Through Revenue (SAR)': 'sum',
                'Click-Through Revenue (SAR)': 'sum'
            }).reset_index()
            # Add total row
            total_row_jour = {'Channel': 'Total'}
            for col in chan_perf_jour.columns:
                if col != 'Channel':
                    total_row_jour[col] = chan_perf_jour[col].sum()
            chan_perf_jour_with_total = pd.concat([chan_perf_jour, pd.DataFrame([total_row_jour])], ignore_index=True)
            # Format columns for display
            chan_perf_jour_display = chan_perf_jour_with_total.copy()
            chan_perf_jour_display['Sent'] = chan_perf_jour_display['Sent'].apply(format_metric)
            chan_perf_jour_display['Delivered'] = chan_perf_jour_display['Delivered'].apply(format_metric)
            chan_perf_jour_display['Unique Conversions'] = chan_perf_jour_display['Unique Conversions'].apply(format_metric)
            chan_perf_jour_display['Revenue (SAR)'] = chan_perf_jour_display['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            chan_perf_jour_display['Impression-Through Revenue (SAR)'] = chan_perf_jour_display['Impression-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
            chan_perf_jour_display['Click-Through Revenue (SAR)'] = chan_perf_jour_display['Click-Through Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))

            # Display table with formatted values
            st.dataframe(style_total_row(chan_perf_jour_display), use_container_width=True, hide_index=True)
            
            # Chart data - chan_perf_jour is already numeric, no parsing needed
            conv_display_name = get_selected_conversion_display_name(conversion_attribution)
            fig_chan_jour = px.bar(chan_perf_jour, x='Channel', y='Unique Conversions',
                                   title=f"{conv_display_name} by Channel for Selected Journeys",
                                   color='Channel', color_discrete_map=CHANNEL_COLORS,
                                   labels={'Unique Conversions': conv_display_name})
            fig_chan_jour.update_layout(showlegend=False)
            st.plotly_chart(fig_chan_jour, use_container_width=True)
            
            # Time Series for Selected Journeys
            st.subheader("Time Series Performance")
            # For rates, use mean; for counts/revenue, use sum
            if 'Rate' in jour_metric:
                ts_jour = jour_details.groupby(['Reporting Period Start Date', 'Journey Name'])[jour_metric].mean().reset_index()
            else:
                ts_jour = jour_details.groupby(['Reporting Period Start Date', 'Journey Name'])[jour_metric].sum().reset_index()
            if not ts_jour.empty:
                # Format y-axis for rates
                if 'Rate' in jour_metric:
                    ts_jour[jour_metric] = ts_jour[jour_metric] * 100  # Convert to percentage for display
                    fig_ts_jour = px.line(ts_jour, x='Reporting Period Start Date', y=jour_metric, color='Journey Name',
                                           title=f"{jour_metric} Over Time for Selected Journeys",
                                           color_discrete_sequence=COLOR_SEQUENCE)
                    fig_ts_jour.update_yaxes(tickformat=".1f", title=f"{jour_metric} (%)")
                else:
                    fig_ts_jour = px.line(ts_jour, x='Reporting Period Start Date', y=jour_metric, color='Journey Name',
                                           title=f"{jour_metric} Over Time for Selected Journeys",
                                           color_discrete_sequence=COLOR_SEQUENCE)
                fig_ts_jour.update_traces(line_width=2.5)
                st.plotly_chart(fig_ts_jour, use_container_width=True)
                
                # Journey Performance Insights
                st.subheader("📊 Journey Performance Insights")
                
                # Calculate gaps and stopped periods
                for journey in selected_journeys:
                    journey_data = ts_jour[ts_jour['Journey Name'] == journey].copy()
                    journey_data = journey_data.sort_values('Reporting Period Start Date')
                    
                    if len(journey_data) > 1:
                        # Calculate gaps between dates
                        journey_data['Date'] = pd.to_datetime(journey_data['Reporting Period Start Date'])
                        journey_data['Days_Gap'] = journey_data['Date'].diff().dt.days
                        
                        # Find periods where journey was stopped (gaps > 7 days)
                        stopped_periods = journey_data[journey_data['Days_Gap'] > 7]
                        
                        # Count total stopped days and periods
                        total_stopped_days = stopped_periods['Days_Gap'].sum() if not stopped_periods.empty else 0
                        total_stopped_periods = len(stopped_periods)
                        
                        if not stopped_periods.empty:
                            st.write(f"**{journey} - Campaign Interruptions:**")
                            st.write(f"• **Total Stopped Periods:** {total_stopped_periods}")
                            st.write(f"• **Total Days Stopped:** {int(total_stopped_days)} days")
                            
                            for _, row in stopped_periods.iterrows():
                                prev_date = journey_data[journey_data['Date'] < row['Date']].iloc[-1]['Date'] if len(journey_data[journey_data['Date'] < row['Date']]) > 0 else None
                                if prev_date is not None:
                                    gap_days = int(row['Days_Gap'])
                                    st.write(f"  - Stopped for {gap_days} days: {prev_date.strftime('%Y-%m-%d')} → {row['Date'].strftime('%Y-%m-%d')}")
                        
                        # Performance metrics - handle rates differently
                        is_rate_metric = 'Rate' in jour_metric
                        
                        if is_rate_metric:
                            # For rates, show as percentages and calculate meaningful stats
                            avg_metric = journey_data[jour_metric].mean() * 100  # Convert to percentage
                            max_metric = journey_data[jour_metric].max() * 100
                            min_metric = journey_data[jour_metric].min() * 100
                            consistency = journey_data[jour_metric].std() * 100 if not journey_data[jour_metric].empty else 0
                            
                            # Weighted average by volume (if we have sent data)
                            journey_full_data = jour_details[jour_details['Journey Name'] == journey]
                            if not journey_full_data.empty and 'Sent' in journey_full_data.columns:
                                weighted_avg = (journey_full_data[jour_metric] * journey_full_data['Sent']).sum() / journey_full_data['Sent'].sum() * 100
                            else:
                                weighted_avg = avg_metric
                            
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric(f"Average {jour_metric}", f"{avg_metric:.1f}%")
                            with col2:
                                st.metric(f"Volume-Weighted {jour_metric}", f"{weighted_avg:.1f}%")
                            with col3:
                                st.metric(f"Peak {jour_metric}", f"{max_metric:.1f}%")
                            with col4:
                                st.metric("Rate Variability", f"±{consistency:.1f}pp")
                            
                            st.info(f"💡 **Rate Explanation:** {jour_metric} shows delivery/conversion efficiency. Higher % = better performance. Volume-weighted average accounts for campaign size.")
                        
                        else:
                            # For count/revenue metrics, use original calculations
                            total_metric = journey_data[jour_metric].sum()
                            avg_metric = journey_data[jour_metric].mean()
                            max_metric = journey_data[jour_metric].max()
                            min_metric = journey_data[jour_metric].min()
                            consistency = journey_data[jour_metric].std() / journey_data[jour_metric].mean() if journey_data[jour_metric].mean() > 0 else 0
                            
                            col1, col2, col3, col4 = st.columns(4)
                            with col1:
                                st.metric(f"Total {jour_metric.replace(' (SAR)', '')}", format_metric(total_metric, "SAR" if "Revenue" in jour_metric else ""))
                            with col2:
                                st.metric(f"Average {jour_metric.replace(' (SAR)', '')}", format_metric(avg_metric, "SAR" if "Revenue" in jour_metric else ""))
                            with col3:
                                st.metric(f"Peak {jour_metric.replace(' (SAR)', '')}", format_metric(max_metric, "SAR" if "Revenue" in jour_metric else ""))
                            with col4:
                                st.metric("Consistency", f"{consistency:.2f}")
                            
                            st.info(f"💡 **{jour_metric.replace(' (SAR)', '')} Explanation:** {jour_metric} represents total volume. Consistency shows performance stability (lower = more consistent).")
                        
                        # Trend analysis
                        if len(journey_data) >= 3:
                            if is_rate_metric:
                                recent_avg = journey_data[jour_metric].tail(3).mean() * 100
                                earlier_avg = journey_data[jour_metric].head(len(journey_data)-3).mean() * 100 if len(journey_data) > 3 else journey_data[jour_metric].mean() * 100
                            else:
                                recent_avg = journey_data[jour_metric].tail(3).mean()
                                earlier_avg = journey_data[jour_metric].head(len(journey_data)-3).mean() if len(journey_data) > 3 else journey_data[jour_metric].mean()
                            
                            if earlier_avg > 0:
                                trend_pct = ((recent_avg - earlier_avg) / earlier_avg) * 100
                                trend_direction = "📈 Improving" if trend_pct > 5 else "📉 Declining" if trend_pct < -5 else "➡️ Stable"
                                st.write(f"**Trend:** {trend_direction} ({trend_pct:+.1f}% change in recent performance)")
                        
                        # Best and worst performing periods
                        if is_rate_metric:
                            best_period = journey_data.loc[journey_data[jour_metric].idxmax()]
                            worst_period = journey_data.loc[journey_data[jour_metric].idxmin()]
                            best_value = best_period[jour_metric] * 100
                            worst_value = worst_period[jour_metric] * 100
                            unit = "%"
                        else:
                            best_period = journey_data.loc[journey_data[jour_metric].idxmax()]
                            worst_period = journey_data.loc[journey_data[jour_metric].idxmin()]
                            best_value = best_period[jour_metric]
                            worst_value = worst_period[jour_metric]
                            unit = "SAR" if "Revenue" in jour_metric else ""
                        
                        st.write(f"**Best Period:** {best_period['Reporting Period Start Date'].strftime('%Y-%m-%d')} with {format_metric(best_value, unit)}")
                        st.write(f"**Worst Period:** {worst_period['Reporting Period Start Date'].strftime('%Y-%m-%d')} with {format_metric(worst_value, unit)}")
                        
                        # Activity frequency
                        total_days = (journey_data['Date'].max() - journey_data['Date'].min()).days + 1  # +1 to include both start and end
                        active_days = len(journey_data)
                        frequency = active_days / max(total_days, 1) * 100
                        st.write(f"**Activity Frequency:** {frequency:.1f}% of days had activity ({active_days}/{max(total_days, 1)} days)")
                        
                        # Lost Revenue Estimation for Stopped Periods
                        if total_stopped_days > 0 and not is_rate_metric and 'Revenue' in jour_metric:
                            st.subheader("💰 Lost Revenue Estimation")
                            
                            # Calculate average daily revenue during active periods
                            active_revenue = journey_data[jour_metric].sum()
                            active_days_calc = len(journey_data)
                            avg_daily_revenue = active_revenue / active_days_calc if active_days_calc > 0 else 0
                            
                            estimated_lost_revenue = avg_daily_revenue * total_stopped_days
                            
                            st.warning(f"⚠️ **Estimated Lost Revenue:** {format_metric(estimated_lost_revenue, 'SAR')} over {int(total_stopped_days)} stopped days")
                            st.write(f"   - Based on average daily revenue of {format_metric(avg_daily_revenue, 'SAR')} from {selected_revenue}")
                            st.write(f"   - This represents {estimated_lost_revenue/active_revenue*100:.1f}% of total journey revenue if stopped periods had performed at average levels")
                            
                            # Prophet-based estimation if enough data
                            if len(journey_data) >= 7:  # Need minimum data for Prophet
                                try:
                                    st.write("**AI-Powered Revenue Projection:**")
                                    # Prepare data for Prophet
                                    prophet_data = journey_data[['Date', jour_metric]].rename(columns={'Date': 'ds', jour_metric: 'y'})
                                    
                                    model = Prophet(daily_seasonality=True)
                                    model.fit(prophet_data)
                                    
                                    # Create future dates including the stopped periods
                                    last_date = prophet_data['ds'].max()
                                    future_dates = pd.date_range(start=journey_data['Date'].min(), end=last_date, freq='D')
                                    future_df = pd.DataFrame({'ds': future_dates})
                                    
                                    forecast = model.predict(future_df)
                                    
                                    # Calculate what revenue would have been during stopped periods
                                    stopped_dates = []
                                    for _, row in stopped_periods.iterrows():
                                        prev_date = journey_data[journey_data['Date'] < row['Date']].iloc[-1]['Date'] if len(journey_data[journey_data['Date'] < row['Date']]) > 0 else None
                                        if prev_date is not None:
                                            gap_dates = pd.date_range(start=prev_date + pd.Timedelta(days=1), end=row['Date'] - pd.Timedelta(days=1), freq='D')
                                            stopped_dates.extend(gap_dates)
                                    
                                    if stopped_dates:
                                        stopped_forecast = forecast[forecast['ds'].isin(stopped_dates)]
                                        ai_estimated_lost = stopped_forecast['yhat'].sum()
                                        st.info(f"🤖 **AI Estimated Lost Revenue:** {format_metric(ai_estimated_lost, 'SAR')} (using Prophet forecasting)")
                                        st.write("   - This accounts for seasonal patterns and trends in the data")
                                    
                                except Exception as e:
                                    st.write(f"AI forecasting not available: {str(e)}")
                        
                    else:
                        st.write(f"**{journey}:** Insufficient data for detailed analysis (only {len(journey_data)} data point)")
            else:
                st.write("No time series data available for selected journeys.")
            
            # Conversion Attribution
            st.subheader("Conversion Attribution")
            attr_jour = {
                'Impression-Through': jour_details['Unique Impression-Through Conversions'].sum(),
                'Click-Through': jour_details['Unique Click-Through Conversions'].sum(),
                'Direct/Open-Through': jour_details['Unique Conversions'].sum() - jour_details['Unique Impression-Through Conversions'].sum() - jour_details['Unique Click-Through Conversions'].sum()
            }
            attr_df_jour = pd.DataFrame(list(attr_jour.items()), columns=['Source', 'Conversions'])
            attr_df_jour['Conversions'] = attr_df_jour['Conversions'].apply(format_metric)
            fig_attr_jour = px.pie(attr_df_jour, names='Source', values='Conversions', title="Attribution for Selected Journeys",
                                    color_discrete_sequence=COLOR_SEQUENCE)
            st.plotly_chart(fig_attr_jour, use_container_width=True)
            
            # Failed Reasons for Selected Journeys
            st.subheader("Failed Reasons")
            failed_cols = [col for col in jour_details.columns if 'Failed' in col and col != 'Failed']
            if failed_cols:
                failed_jour = jour_details[failed_cols].sum().reset_index().rename(columns={'index': 'Reason', 0: 'Count'})
                failed_jour['Count'] = failed_jour['Count'].apply(format_metric)
                fig_fail_jour = px.bar(failed_jour, x='Reason', y='Count', title="Failed Reasons for Selected Journeys",
                                       color_discrete_sequence=[COLORS['danger']])
                st.plotly_chart(fig_fail_jour, use_container_width=True)

        # 🚨 Stopped Journey Analysis with Revenue Loss Estimation
        st.markdown("---")
        st.header("🚨 Stopped Journey Analysis & Revenue Loss Estimation")

        st.markdown("""
        **🎯 Advanced Analytics for Journey Performance Issues**

        This analysis identifies journeys with zero delivery periods and estimates revenue loss using:
        - **📊 Statistical Forecasting**: Time-series analysis with confidence intervals
        - **🎪 Multiple Attribution Models**: Send-through, impression-through, and click-through revenue
        - **📈 Machine Learning**: Prophet model for revenue prediction during stopped periods
        - **💰 Loss Quantification**: Daily revenue loss estimation with confidence ranges
        """)

        # Analysis parameters
        stopped_col1, stopped_col2, stopped_col3 = st.columns(3)

        with stopped_col1:
            stopped_threshold_days = st.slider("🚫 Stopped Threshold (days)", 1, 14, 3,
                                             help="Minimum consecutive days with zero delivery to consider journey 'stopped'")
            st.write(f"**Threshold:** {stopped_threshold_days} consecutive zero-delivery days")

        with stopped_col2:
            lookback_period = st.slider("📅 Analysis Period (days)", 30, 180, 90,
                                      help="How far back to analyze journey performance")
            st.write(f"**Analysis Window:** {lookback_period} days")

        with stopped_col3:
            confidence_level = st.selectbox("🎯 Confidence Level", [0.80, 0.90, 0.95, 0.99], index=2,
                                          help="Statistical confidence level for revenue loss estimates")
            st.write(f"**Confidence:** {int(confidence_level*100)}%")

        if st.button("🔍 Analyze Stopped Journeys", key='analyze_stopped'):
            with st.spinner("🔄 Analyzing journey delivery patterns and estimating revenue loss..."):

                # Create stopped journey analysis
                stopped_analysis = analyze_stopped_journeys(
                    filtered_df,
                    stopped_threshold_days=stopped_threshold_days,
                    lookback_period=lookback_period,
                    confidence_level=confidence_level
                )

                if stopped_analysis and 'stopped_journeys' in stopped_analysis:

                    stopped_journeys = stopped_analysis['stopped_journeys']

                    if stopped_journeys:
                        st.error(f"🚨 **{len(stopped_journeys)} Journeys Identified with Stopped Delivery**")
                        
                        # Check for journeys that were never active
                        never_active_count = 0
                        for journey in stopped_journeys:
                            for period in journey['stopped_periods']['periods']:
                                if not period.get('was_active_before', True):
                                    never_active_count += 1
                                    break  # Count journey only once
                        
                        if never_active_count > 0:
                            st.warning(f"⚠️ **Note:** {never_active_count} journey(s) had zero delivery periods but were never active before. These might be journeys that haven't launched yet rather than journeys that stopped.")

                        # Summary metrics
                        total_revenue_loss = sum(journey['estimated_revenue_loss']['total_loss'] for journey in stopped_journeys)
                        total_stopped_days = sum(journey['stopped_periods']['total_stopped_days'] for journey in stopped_journeys)

                        summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)

                        with summary_col1:
                            st.metric("🚫 Stopped Journeys", len(stopped_journeys))
                        with summary_col2:
                            st.metric("📅 Total Stopped Days", format_metric(total_stopped_days))
                        with summary_col3:
                            st.metric("💰 Total Revenue Loss", format_metric(total_revenue_loss, "SAR"))
                        with summary_col4:
                            avg_daily_loss = total_revenue_loss / total_stopped_days if total_stopped_days > 0 else 0
                            st.metric("📊 Avg Daily Loss", format_metric(avg_daily_loss, "SAR"))

                        # Detailed analysis for each stopped journey
                        st.subheader("🔍 Detailed Stopped Journey Analysis")

                        for journey in stopped_journeys:
                            journey_name = journey['journey_name']

                            with st.expander(f"🚨 {journey_name} - Revenue Loss: {format_metric(journey['estimated_revenue_loss']['total_loss'], 'SAR')}", expanded=True):

                                # Journey overview
                                overview_col1, overview_col2, overview_col3 = st.columns(3)

                                with overview_col1:
                                    st.metric("📅 Stopped Days", journey['stopped_periods']['total_stopped_days'])
                                    st.metric("📊 Stopped Periods", len(journey['stopped_periods']['periods']))

                                with overview_col2:
                                    loss_data = journey['estimated_revenue_loss']
                                    st.metric("💰 Total Loss", format_metric(loss_data['total_loss'], "SAR"))
                                    st.metric("📈 Daily Loss", format_metric(loss_data['avg_daily_loss'], "SAR"))

                                with overview_col3:
                                    confidence_range = loss_data['confidence_interval']
                                    st.metric("🎯 Confidence Range",
                                            f"{format_metric(confidence_range[0], 'SAR')} - {format_metric(confidence_range[1], 'SAR')}")
                                    
                                    # Show model quality indicator
                                    model_quality = loss_data.get('model_quality', 'medium')
                                    if model_quality == 'high':
                                        quality_icon = "✅"
                                        quality_label = "High Reliability"
                                        quality_color = "green"
                                    elif model_quality == 'medium':
                                        quality_icon = "⚠️"
                                        quality_label = "Moderate Reliability"
                                        quality_color = "orange"
                                    else:
                                        quality_icon = "ℹ️"
                                        quality_label = "Directional Estimate"
                                        quality_color = "gray"
                                    
                                    st.markdown(f"<div style='padding: 10px; border-left: 4px solid {quality_color};'>"
                                              f"{quality_icon} <b>{quality_label}</b></div>", 
                                              unsafe_allow_html=True)

                                # Revenue attribution breakdown
                                st.subheader("💰 Revenue Loss by Attribution Model")

                                attr_loss_col1, attr_loss_col2, attr_loss_col3 = st.columns(3)

                                loss_breakdown = loss_data['attribution_breakdown']

                                with attr_loss_col1:
                                    send_loss = loss_breakdown.get('Revenue (SAR)', 0)
                                    st.metric("📊 Send-Through Loss", format_metric(send_loss, "SAR"))

                                with attr_loss_col2:
                                    impression_loss = loss_breakdown.get('Impression-Through Revenue (SAR)', 0)
                                    st.metric("👁️ Impression-Through Loss", format_metric(impression_loss, "SAR"))

                                with attr_loss_col3:
                                    click_loss = loss_breakdown.get('Click-Through Revenue (SAR)', 0)
                                    st.metric("🖱️ Click-Through Loss", format_metric(click_loss, "SAR"))

                                # Stopped periods timeline
                                st.subheader("📅 Stopped Periods Timeline")

                                periods_data = journey['stopped_periods']['periods']
                                if periods_data:
                                    periods_df = pd.DataFrame(periods_data)

                                    # Create timeline visualization
                                    fig_timeline = go.Figure()

                                    for _, period in periods_df.iterrows():
                                        fig_timeline.add_trace(go.Scatter(
                                            x=[period['start_date'], period['end_date']],
                                            y=[journey_name, journey_name],
                                            mode='lines+markers',
                                            name=f"Stopped Period ({period['days_stopped']} days)",
                                            line=dict(color=COLORS['danger'], width=4),
                                            marker=dict(size=8, color=COLORS['danger']),
                                            showlegend=False
                                        ))

                                    fig_timeline.update_layout(
                                        title=f"Stopped Delivery Periods: {journey_name}",
                                        xaxis_title="Date",
                                        yaxis_title="Journey",
                                        showlegend=False,
                                        height=200
                                    )

                                    st.plotly_chart(fig_timeline)

                                    # Detailed periods table
                                    st.subheader("📋 Stopped Period Details")
                                    periods_display = periods_df.copy()
                                    
                                    # Calculate expected days from dates for verification
                                    periods_display['calculated_days'] = (
                                        (periods_display['end_date'] - periods_display['start_date']).dt.days + 1
                                    )
                                    
                                    # Format dates
                                    periods_display['start_date'] = periods_display['start_date'].dt.strftime('%Y-%m-%d')
                                    periods_display['end_date'] = periods_display['end_date'].dt.strftime('%Y-%m-%d')
                                    
                                    # Add verification indicator
                                    periods_display['days_match'] = periods_display.apply(
                                        lambda row: '✓' if row['days_stopped'] == row['calculated_days'] else f'⚠️ Mismatch!',
                                        axis=1
                                    )
                                    
                                    periods_display['days_stopped'] = periods_display['days_stopped'].apply(format_metric)
                                    periods_display['calculated_days'] = periods_display['calculated_days'].apply(format_metric)
                                    
                                    # Add activity information
                                    if 'was_active_before' in periods_display.columns:
                                        periods_display['Status'] = periods_display.apply(
                                            lambda row: f"✅ Was Active ({format_metric(row['active_days_before_stop'])} days, avg: {format_metric(row['avg_delivery_before_stop'])} delivered)" 
                                            if row.get('was_active_before', False) 
                                            else "⚠️ Never Active", 
                                            axis=1
                                        )
                                        display_cols = ['start_date', 'end_date', 'days_stopped', 'calculated_days', 'days_match', 'Status']
                                    else:
                                        display_cols = ['start_date', 'end_date', 'days_stopped', 'calculated_days', 'days_match']
                                    
                                    # Add estimated_daily_loss if available
                                    if 'estimated_daily_loss' in periods_display.columns:
                                        periods_display['estimated_daily_loss'] = periods_display['estimated_daily_loss'].apply(lambda x: format_metric(x, "SAR"))
                                        display_cols.append('estimated_daily_loss')
                                    else:
                                        # Add placeholder if missing
                                        periods_display['estimated_daily_loss'] = 'N/A'
                                        display_cols.append('estimated_daily_loss')
                                    
                                    st.dataframe(periods_display[display_cols], use_container_width=True)

                                # Recommendations
                                st.subheader("💡 Recommendations & Actions")

                                recommendations = journey.get('recommendations', [])

                                if recommendations:
                                    for rec in recommendations:
                                        st.info(f"🎯 {rec}")
                                else:
                                    st.info("🔍 **Analysis Complete:** Review journey configuration and delivery settings to prevent future stoppages.")

                    else:
                        st.success("✅ **No Stopped Journeys Detected!** All journeys are actively delivering.")

                else:
                    st.error("❌ Analysis failed. Please check your data and try again.")

    elif page == "Segments":
        st.header("Top Segments")
        # Safe column selection - only use columns that exist in both reports
        safe_revenue_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
        if 'Selected Revenue (SAR)' in filtered_df.columns:
            safe_revenue_cols.insert(0, 'Selected Revenue (SAR)')
        safe_conversion_cols = ['Unique Conversions', 'Unique Clicks']

        # Add conversion attribution options if they exist
        if 'Unique Click-Through Conversions' in filtered_df.columns:
            safe_conversion_cols.append('Unique Click-Through Conversions')
        if 'Unique Impression-Through Conversions' in filtered_df.columns:
            safe_conversion_cols.append('Unique Impression-Through Conversions')

        # Add Total columns if they exist (Monthly report)
        if 'Total Conversions' in filtered_df.columns:
            safe_conversion_cols.append('Total Conversions')

        all_metrics = safe_conversion_cols + safe_revenue_cols
        seg_metric = st.selectbox("Metric", all_metrics, key='seg_metric', format_func=_attribution_display)
        top_seg = top_segments(filtered_df, seg_metric)

        # Create display version for table
        top_seg_display = top_seg.copy().rename(columns=attribution_rename)
        seg_metric_display = _attribution_display(seg_metric)
        # Format the metric column for display
        if 'Revenue' in seg_metric:
            top_seg_display[seg_metric_display] = top_seg_display[seg_metric_display].apply(lambda x: format_metric(x, "SAR"))
        elif seg_metric in ['Unique Conversions', 'Total Conversions', 'Unique Clicks', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions']:
            top_seg_display[seg_metric_display] = top_seg_display[seg_metric_display].apply(format_metric)
        st.dataframe(top_seg_display)

        # Create chart with original numeric values
        fig3 = px.bar(top_seg, x='Segment Name', y=seg_metric, title=f"Top Segments by {seg_metric_display}",
                       color_discrete_sequence=COLOR_SEQUENCE)
        st.plotly_chart(fig3, use_container_width=True)

    elif page == "Channels":
        st.header("Channel Analysis")
        chan_df = channel_analysis(filtered_df)

        # Channel conversion rate based on selected conversion attribution
        conv_rate_source_col = 'Selected Conversions' if 'Selected Conversions' in chan_df.columns else 'Unique Conversions'
        if conv_rate_source_col in chan_df.columns and 'Unique Clicks' in chan_df.columns:
            chan_df['Conversion Rate'] = np.where(
                chan_df['Unique Clicks'] > 0,
                (chan_df[conv_rate_source_col] / chan_df['Unique Clicks']) * 100,
                0
            )

        # Create display version for table - keep selected attribution columns visible
        chan_df_display = chan_df.copy()
        # For Total attribution, Selected Revenue (SAR) == Revenue (SAR) and will be renamed to it,
        # so drop the raw Revenue (SAR) first to avoid a duplicate after the rename.
        # For CT/IT attribution, keep Revenue (SAR) so total revenue stays visible in the table.
        if (selected_rev_label == 'Revenue (SAR)'
                and 'Selected Revenue (SAR)' in chan_df_display.columns
                and 'Revenue (SAR)' in chan_df_display.columns):
            chan_df_display = chan_df_display.drop(columns=['Revenue (SAR)'])
        if 'Selected Conversions' in chan_df_display.columns and 'Unique Conversions' in chan_df_display.columns:
            chan_df_display = chan_df_display.drop(columns=['Unique Conversions'])

        # If selected labels match existing raw attribution columns, drop the raw duplicate first.
        # Example: selecting Click-Through makes 'Selected Revenue (SAR)' rename to
        # 'Click-Through Revenue (SAR)', which may already exist in chan_df_display.
        selected_rev_display = attribution_rename.get('Selected Revenue (SAR)')
        if selected_rev_display and selected_rev_display != 'Selected Revenue (SAR)' and selected_rev_display in chan_df_display.columns:
            chan_df_display = chan_df_display.drop(columns=[selected_rev_display])

        selected_conv_display = attribution_rename.get('Selected Conversions')
        if selected_conv_display and selected_conv_display != 'Selected Conversions' and selected_conv_display in chan_df_display.columns:
            chan_df_display = chan_df_display.drop(columns=[selected_conv_display])

        # Rename selected attribution columns in display table only
        chan_df_display = chan_df_display.rename(columns=attribution_rename)

        # Safety guard: ensure concat/reindex operations always see unique columns.
        if not chan_df_display.columns.is_unique:
            chan_df_display = chan_df_display.loc[:, ~chan_df_display.columns.duplicated(keep='first')]
        
        # If comparison mode is active, calculate comparison metrics and add percentage changes
        if comparison_result:
            # Calculate channel metrics for comparison period
            chan_df_comparison = channel_analysis(comparison_result['comparison_data'])
            
            # Create a new display dataframe with values and percentage changes
            chan_df_with_changes = chan_df_display.copy()

            # Compare metric values for each channel
            display_metric_cols = [c for c in chan_df_display.columns if c != 'Channel']

            for display_col in display_metric_cols:
                source_col = resolve_source_column(display_col, revenue_attribution, conversion_attribution)

                if source_col not in chan_df.columns:
                    continue

                new_col_data = []
                for channel in chan_df_display['Channel']:
                    if source_col == 'AOV (SAR)':
                        curr_rev = chan_df.loc[chan_df['Channel'] == channel, 'Selected Revenue (SAR)'] if 'Selected Revenue (SAR)' in chan_df.columns else chan_df.loc[chan_df['Channel'] == channel, 'Revenue (SAR)']
                        curr_conv = chan_df.loc[chan_df['Channel'] == channel, 'Selected Conversions'] if 'Selected Conversions' in chan_df.columns else chan_df.loc[chan_df['Channel'] == channel, 'Unique Conversions']
                        current_val = curr_rev.sum() / curr_conv.sum() if curr_conv.sum() > 0 else 0

                        comp_val = 0
                        if 'Selected Revenue (SAR)' in chan_df_comparison.columns and 'Selected Conversions' in chan_df_comparison.columns:
                            comp_rev = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, 'Selected Revenue (SAR)']
                            comp_conv = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, 'Selected Conversions']
                            comp_val = comp_rev.sum() / comp_conv.sum() if comp_conv.sum() > 0 else 0
                    elif source_col == 'Conversion Rate':
                        curr_clicks = chan_df.loc[chan_df['Channel'] == channel, 'Unique Clicks'].sum()
                        curr_conv = chan_df.loc[chan_df['Channel'] == channel, conv_rate_source_col].sum() if conv_rate_source_col in chan_df.columns else 0
                        current_val = (curr_conv / curr_clicks) * 100 if curr_clicks > 0 else 0

                        comp_val = 0
                        if conv_rate_source_col in chan_df_comparison.columns and 'Unique Clicks' in chan_df_comparison.columns:
                            comp_clicks = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, 'Unique Clicks'].sum()
                            comp_conv = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, conv_rate_source_col].sum()
                            comp_val = (comp_conv / comp_clicks) * 100 if comp_clicks > 0 else 0
                    else:
                        current_val = chan_df.loc[chan_df['Channel'] == channel, source_col].values
                        current_val = current_val[0] if len(current_val) > 0 else 0

                        comp_val = 0
                        if source_col in chan_df_comparison.columns:
                            comp_val = chan_df_comparison.loc[chan_df_comparison['Channel'] == channel, source_col].values
                            comp_val = comp_val[0] if len(comp_val) > 0 else 0

                    if comp_val > 0:
                        pct_change = ((current_val - comp_val) / comp_val) * 100
                        if pct_change > 0:
                            pct_str = f" <span style='color: #28a745; font-weight: 600; white-space: nowrap; display: inline-block;'>▲&nbsp;{pct_change:.1f}%</span>"
                        elif pct_change < 0:
                            pct_str = f" <span style='color: #dc3545; font-weight: 600; white-space: nowrap; display: inline-block;'>▼&nbsp;{abs(pct_change):.1f}%</span>"
                        else:
                            pct_str = " <span style='color: #6c757d; white-space: nowrap; display: inline-block;'>→&nbsp;0%</span>"
                    elif current_val > 0 and comp_val == 0:
                        pct_str = " <span style='color: #17a2b8; font-weight: 600; white-space: nowrap; display: inline-block;'>🆕</span>"
                    else:
                        pct_str = ""

                    if source_col == 'Conversion Rate':
                        formatted_val = f"{current_val:.2f}%"
                    elif 'Revenue' in source_col or 'AOV' in source_col:
                        formatted_val = format_metric(current_val, "SAR", abbreviate=True)
                    else:
                        formatted_val = format_metric(current_val, "", abbreviate=True)

                    new_col_data.append(formatted_val + pct_str)

                chan_df_with_changes[display_col] = new_col_data

            # Add total row with comparisons
            total_row_chan = {'Channel': 'Total'}
            for display_col in display_metric_cols:
                source_col = resolve_source_column(display_col, revenue_attribution, conversion_attribution)

                if source_col not in chan_df.columns:
                    continue

                current_total = chan_df[source_col].sum()
                comp_total = chan_df_comparison[source_col].sum() if source_col in chan_df_comparison.columns else 0

                if source_col == 'AOV (SAR)':
                    total_rev = chan_df['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in chan_df.columns else chan_df['Revenue (SAR)'].sum()
                    total_conv = chan_df['Selected Conversions'].sum() if 'Selected Conversions' in chan_df.columns else chan_df['Unique Conversions'].sum()
                    current_total = total_rev / total_conv if total_conv > 0 else 0
                    comp_total = 0
                    if 'Selected Revenue (SAR)' in chan_df_comparison.columns and 'Selected Conversions' in chan_df_comparison.columns:
                        comp_rev = chan_df_comparison['Selected Revenue (SAR)'].sum()
                        comp_conv = chan_df_comparison['Selected Conversions'].sum()
                        comp_total = comp_rev / comp_conv if comp_conv > 0 else 0
                elif source_col == 'Conversion Rate':
                    current_clicks = chan_df['Unique Clicks'].sum() if 'Unique Clicks' in chan_df.columns else 0
                    current_conv = chan_df[conv_rate_source_col].sum() if conv_rate_source_col in chan_df.columns else 0
                    current_total = (current_conv / current_clicks) * 100 if current_clicks > 0 else 0

                    comp_clicks = chan_df_comparison['Unique Clicks'].sum() if 'Unique Clicks' in chan_df_comparison.columns else 0
                    comp_conv = chan_df_comparison[conv_rate_source_col].sum() if conv_rate_source_col in chan_df_comparison.columns else 0
                    comp_total = (comp_conv / comp_clicks) * 100 if comp_clicks > 0 else 0
                else:
                    current_total = chan_df[source_col].sum()
                    comp_total = chan_df_comparison[source_col].sum() if source_col in chan_df_comparison.columns else 0

                if comp_total > 0:
                    pct_change = ((current_total - comp_total) / comp_total) * 100
                    if pct_change > 0:
                        pct_str = f" <span style='color: #28a745; font-weight: 600; white-space: nowrap; display: inline-block;'>▲&nbsp;{pct_change:.1f}%</span>"
                    elif pct_change < 0:
                        pct_str = f" <span style='color: #dc3545; font-weight: 600; white-space: nowrap; display: inline-block;'>▼&nbsp;{abs(pct_change):.1f}%</span>"
                    else:
                        pct_str = " <span style='color: #6c757d; white-space: nowrap; display: inline-block;'>→&nbsp;0%</span>"
                elif current_total > 0:
                    pct_str = " <span style='color: #17a2b8; font-weight: 600; white-space: nowrap; display: inline-block;'>🆕</span>"
                else:
                    pct_str = ""

                if source_col == 'Conversion Rate':
                    formatted_total = f"{current_total:.2f}%"
                elif 'Revenue' in source_col or 'AOV' in source_col:
                    formatted_total = format_metric(current_total, "SAR", abbreviate=True)
                else:
                    formatted_total = format_metric(current_total, "", abbreviate=True)

                total_row_chan[display_col] = formatted_total + pct_str

            chan_df_with_changes = pd.concat([chan_df_with_changes, pd.DataFrame([total_row_chan])], ignore_index=True)
            chan_df_display = chan_df_with_changes
        else:
            # No comparison - use regular formatting
            # Add total row
            total_row_chan = {'Channel': 'Total'}
            for col in chan_df_display.columns:
                if col == 'Channel':
                    continue
                if 'AOV' in col:
                    continue
                total_row_chan[col] = chan_df_display[col].sum()

            # Compute total AOV from total revenue/total conversions
            if 'Selected Revenue (SAR)' in chan_df.columns and 'Selected Conversions' in chan_df.columns:
                total_conv = chan_df['Selected Conversions'].sum()
                total_rev = chan_df['Selected Revenue (SAR)'].sum()
            elif 'Revenue (SAR)' in chan_df.columns and 'Unique Conversions' in chan_df.columns:
                total_conv = chan_df['Unique Conversions'].sum()
                total_rev = chan_df['Revenue (SAR)'].sum()
            else:
                total_conv = 0
                total_rev = 0

            total_aov = (total_rev / total_conv) if total_conv > 0 else 0
            for col in [c for c in chan_df_display.columns if 'AOV' in c]:
                total_row_chan[col] = total_aov

            # Compute total conversion rate from totals (not sum of row percentages)
            if 'Conversion Rate' in chan_df_display.columns:
                total_clicks = chan_df['Unique Clicks'].sum() if 'Unique Clicks' in chan_df.columns else 0
                total_conv_for_rate = chan_df[conv_rate_source_col].sum() if conv_rate_source_col in chan_df.columns else 0
                total_row_chan['Conversion Rate'] = (total_conv_for_rate / total_clicks) * 100 if total_clicks > 0 else 0

            chan_df_display = pd.concat([chan_df_display, pd.DataFrame([total_row_chan])], ignore_index=True)
            # Format columns
            conversion_col = None
            for col in [selected_conv_label, 'Selected Conversions', 'Unique Conversions', 'Total Conversions']:
                if col in chan_df_display.columns:
                    conversion_col = col
                    break

            numeric_cols = ['Sent', 'Delivered', 'Unique Impressions', 'Unique Clicks']
            if conversion_col:
                numeric_cols.append(conversion_col)
            if 'Total Conversions' in chan_df_display.columns and 'Total Conversions' not in numeric_cols:
                numeric_cols.append('Total Conversions')

            for col in numeric_cols:
                if col in chan_df_display.columns:
                    chan_df_display[col] = chan_df_display[col].apply(format_metric)
            revenue_cols = [col for col in chan_df_display.columns if 'Revenue' in col]
            for col in revenue_cols:
                chan_df_display[col] = chan_df_display[col].apply(lambda x: format_metric(x, "SAR"))
            # Format AOV columns
            aov_cols = [col for col in chan_df_display.columns if 'AOV' in col]
            for col in aov_cols:
                chan_df_display[col] = chan_df_display[col].apply(lambda x: format_metric(x, "SAR"))
            if 'Conversion Rate' in chan_df_display.columns:
                chan_df_display['Conversion Rate'] = chan_df_display['Conversion Rate'].apply(lambda x: f"{x:.2f}%")
        
        # Display table with HTML rendering if comparison is active
        if comparison_result:
            table_html = chan_df_display.to_html(escape=False, index=False)
            components.html(
                """
                <style>
                @media (prefers-color-scheme: dark) {
                    .channel-compare-table {
                        color: rgba(250, 250, 250, 0.95);
                    }
                    .channel-compare-table table {
                        background: #0e1117;
                        border: 1px solid rgba(250, 250, 250, 0.2);
                    }
                    .channel-compare-table th {
                        background: rgba(38, 39, 48, 0.8);
                        border-bottom: 1px solid rgba(250, 250, 250, 0.2);
                    }
                    .channel-compare-table td {
                        border-bottom: 1px solid rgba(250, 250, 250, 0.1);
                    }
                    .channel-compare-table tr:nth-child(even) td {
                        background: rgba(250, 250, 250, 0.03);
                    }
                    .channel-compare-table tr:hover td {
                        background: rgba(250, 250, 250, 0.08);
                    }
                    .channel-compare-table tbody tr:last-child td {
                        background: rgba(100, 150, 255, 0.15);
                        border-top: 2px solid rgba(100, 150, 255, 0.5);
                    }
                }
                @media (prefers-color-scheme: light) {
                    .channel-compare-table {
                        color: #262730;
                    }
                    .channel-compare-table table {
                        background: #ffffff;
                        border: 1px solid #e6e6e6;
                    }
                    .channel-compare-table th {
                        background: #f6f7f9;
                        border-bottom: 1px solid #e6e6e6;
                    }
                    .channel-compare-table td {
                        border-bottom: 1px solid #f0f0f0;
                    }
                    .channel-compare-table tr:nth-child(even) td {
                        background: #fafafa;
                    }
                    .channel-compare-table tr:hover td {
                        background: #f0f7ff;
                    }
                    .channel-compare-table tbody tr:last-child td {
                        background: #e8f4ff;
                        border-top: 2px solid #4a90e2;
                    }
                }
                .channel-compare-table {
                    font-family: "Source Sans Pro", -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
                    font-size: 14px;
                }
                .channel-compare-table table {
                    width: 100%;
                    border-collapse: collapse;
                }
                .channel-compare-table th,
                .channel-compare-table td {
                    white-space: nowrap;
                    padding: 8px 10px;
                    text-align: left;
                    vertical-align: middle;
                }
                .channel-compare-table th {
                    font-weight: 600;
                    position: sticky;
                    top: 0;
                    z-index: 1;
                }
                .channel-compare-table tbody tr:last-child td {
                    font-weight: 700;
                }
                </style>
                """ + f"<div class='channel-compare-table'>{table_html}</div>",
                height=360,
                scrolling=True
            )
        else:
            st.dataframe(style_total_row(chan_df_display), use_container_width=True, hide_index=True)

        # Revenue Distribution (Donut Chart)
        rev_display_name = get_selected_revenue_display_name(revenue_attribution)
        st.subheader(f"Revenue Distribution Across Channels - {rev_display_name}")
        if 'Selected Revenue (SAR)' in chan_df.columns:
            # Calculate total revenue for center annotation
            total_revenue = chan_df['Selected Revenue (SAR)'].sum()

            # Create donut chart for revenue share
            fig_donut = px.pie(
                chan_df,
                values='Selected Revenue (SAR)',
                names='Channel',
                title=f"Channel Revenue Share<br><sub>Using: {rev_display_name}</sub>",
                color='Channel',
                color_discrete_map=CHANNEL_COLORS,
                hole=0.4  # Makes it a donut chart
            )
            fig_donut.update_traces(
                textposition='inside',
                textinfo='percent+label',
                hovertemplate='<b>%{label}</b><br>' +
                              'Revenue: %{value:,.0f} SAR<br>' +
                              'Share: %{percent}<br>' +
                              '<extra></extra>'
            )
            fig_donut.update_layout(
                showlegend=True,
                legend=dict(orientation='h', yanchor='bottom', y=-0.2, xanchor='center', x=0.5),
                annotations=[dict(
                    text=f'<b>Total</b><br>{format_metric(total_revenue, "SAR", abbreviate=True)}',
                    x=0.5, y=0.5,
                    font_size=16,
                    showarrow=False
                )]
            )
            st.plotly_chart(fig_donut, use_container_width=True)

        # Revenue + Conversions by Channel (using selected attribution)
        st.subheader("Revenue & Conversions Comparison")
        rev_conv_col1, rev_conv_col2 = st.columns(2)
        with rev_conv_col1:
            if 'Selected Revenue (SAR)' in chan_df.columns:
                rev_display_name = get_selected_revenue_display_name(revenue_attribution)
                fig_rev_chan = px.bar(
                    chan_df, x='Channel', y='Selected Revenue (SAR)',
                    title=f"{rev_display_name} by Channel",
                    color='Channel', color_discrete_map=CHANNEL_COLORS,
                    labels={'Selected Revenue (SAR)': rev_display_name}
                )
                fig_rev_chan.update_layout(showlegend=False)
                st.plotly_chart(fig_rev_chan, use_container_width=True)
        with rev_conv_col2:
            conv_col = 'Selected Conversions' if 'Selected Conversions' in chan_df.columns else 'Unique Conversions'
            conv_display_name = get_selected_conversion_display_name(conversion_attribution) if conv_col == 'Selected Conversions' else 'Unique Conversions'
            fig_conv_chan = px.bar(
                chan_df, x='Channel', y=conv_col,
                title=f"{conv_display_name} by Channel",
                color='Channel', color_discrete_map=CHANNEL_COLORS,
                labels={conv_col: conv_display_name}
            )
            fig_conv_chan.update_layout(showlegend=False)
            st.plotly_chart(fig_conv_chan, use_container_width=True)

        # Compute derived rates for deeper channel analysis
        chan_rates = chan_df.copy()
        chan_rates['Delivery Rate'] = np.where(
            chan_rates['Sent'] > 0,
            (chan_rates['Delivered'] / chan_rates['Sent']) * 100, 0
        )
        chan_rates['CTR'] = np.where(
            chan_rates['Unique Impressions'] > 0,
            (chan_rates['Unique Clicks'] / chan_rates['Unique Impressions']) * 100, 0
        )
        chan_rates['Conversion Rate'] = np.where(
            chan_rates['Unique Clicks'] > 0,
            (chan_rates[conv_rate_source_col] / chan_rates['Unique Clicks']) * 100,
            0
        )

        # Charts: Delivery Rate + CTR + Conversion Rate
        st.subheader("Engagement & Delivery Rates")
        ch_col1, ch_col2, ch_col3 = st.columns(3)
        with ch_col1:
            fig_dr = px.bar(
                chan_rates, x='Channel', y='Delivery Rate',
                title="Delivery Rate by Channel (%)",
                color='Channel', color_discrete_map=CHANNEL_COLORS,
            )
            fig_dr.update_layout(showlegend=False, yaxis_title="Delivery Rate (%)")
            fig_dr.add_hline(y=95, line_dash="dash", line_color=COLORS['muted'],
                             annotation_text="95% target", annotation_position="top right")
            st.plotly_chart(fig_dr, use_container_width=True)
        with ch_col2:
            fig_ctr = px.bar(
                chan_rates, x='Channel', y='CTR',
                title="Click-Through Rate by Channel (%)",
                color='Channel', color_discrete_map=CHANNEL_COLORS,
            )
            fig_ctr.update_layout(showlegend=False, yaxis_title="CTR (%)")
            st.plotly_chart(fig_ctr, use_container_width=True)
        with ch_col3:
            fig_cvr = px.bar(
                chan_rates, x='Channel', y='Conversion Rate',
                title="Conversion Rate by Channel (%)",
                color='Channel', color_discrete_map=CHANNEL_COLORS,
            )
            fig_cvr.update_layout(showlegend=False, yaxis_title="Conversion Rate (%)")
            st.plotly_chart(fig_cvr, use_container_width=True)

        # Volume comparison (Sent vs Delivered side-by-side)
        st.subheader("Send Volume & Delivery")
        volume_melt = chan_df[['Channel', 'Sent', 'Delivered']].melt(
            id_vars='Channel', var_name='Metric', value_name='Count'
        )
        fig_vol = px.bar(
            volume_melt, x='Channel', y='Count', color='Metric',
            barmode='group', title="Sent vs Delivered by Channel",
            color_discrete_map={'Sent': COLORS['primary'], 'Delivered': COLORS['success']},
        )
        st.plotly_chart(fig_vol, use_container_width=True)

        # Revenue Attribution Comparison (all three side-by-side)
        rev_compare_cols = [c for c in ['Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Impression-Through Revenue (SAR)'] if c in chan_df.columns]
        if len(rev_compare_cols) > 1:
            st.subheader("Revenue Attribution Comparison")
            rev_melt = chan_df[['Channel'] + rev_compare_cols].melt(
                id_vars='Channel', var_name='Attribution Model', value_name='Revenue'
            )
            # Shorten labels for readability
            rev_melt['Attribution Model'] = rev_melt['Attribution Model'].str.replace(' (SAR)', '', regex=False).str.replace('Revenue', '').str.strip()
            fig_rev_compare = px.bar(
                rev_melt, x='Channel', y='Revenue', color='Attribution Model',
                barmode='group', title="Revenue by Channel & Attribution Model",
                color_discrete_sequence=COLOR_SEQUENCE,
            )
            st.plotly_chart(fig_rev_compare, use_container_width=True)

        # Campaign Type Performance by Channel (One-Time vs Journey)
        if 'Type of Campaign' in filtered_df.columns and 'Channel' in filtered_df.columns:
            type_vals = filtered_df['Type of Campaign'].dropna().unique()
            if len(type_vals) > 0:
                st.subheader("One-Time vs Journey Performance by Channel")
                rev_col_type = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
                conv_col_type = 'Selected Conversions' if 'Selected Conversions' in filtered_df.columns else 'Unique Conversions'

                # Aggregate all available revenue and conversion columns
                type_chan_agg = {'Sent': 'sum', 'Delivered': 'sum'}
                # Always include selected attribution columns
                if conv_col_type in filtered_df.columns:
                    type_chan_agg[conv_col_type] = 'sum'
                if rev_col_type in filtered_df.columns:
                    type_chan_agg[rev_col_type] = 'sum'
                # Also aggregate all other revenue/conversion columns for detail view
                extra_rev_cols = [c for c in ['Revenue (SAR)', 'Click-Through Revenue (SAR)', 'Impression-Through Revenue (SAR)'] if c in filtered_df.columns and c != rev_col_type]
                extra_conv_cols = [c for c in ['Unique Conversions', 'Unique Click-Through Conversions', 'Unique Impression-Through Conversions'] if c in filtered_df.columns and c != conv_col_type]
                for c in extra_rev_cols + extra_conv_cols:
                    type_chan_agg[c] = 'sum'
                type_chan_df = filtered_df.groupby(['Channel', 'Type of Campaign']).agg(type_chan_agg).reset_index()

                # Toggle for showing all revenue/conversion types
                show_all_attrs = st.checkbox("Show all revenue & conversion types", value=False, key='chan_type_show_all')

                # Build display columns
                default_cols = ['Channel', 'Type of Campaign', 'Sent', 'Delivered', conv_col_type, rev_col_type]
                default_cols = [c for c in default_cols if c in type_chan_df.columns]
                if show_all_attrs:
                    display_cols = default_cols + [c for c in extra_rev_cols + extra_conv_cols if c not in default_cols]
                else:
                    display_cols = default_cols

                type_chan_display = type_chan_df[display_cols].copy()
                # Format numeric columns
                for col in ['Sent', 'Delivered'] + extra_conv_cols + ([conv_col_type] if conv_col_type in type_chan_display.columns else []):
                    if col in type_chan_display.columns:
                        type_chan_display[col] = type_chan_display[col].apply(format_metric)
                for col in [rev_col_type] + extra_rev_cols:
                    if col in type_chan_display.columns:
                        type_chan_display[col] = type_chan_display[col].apply(lambda x: format_metric(x, "SAR"))
                # Rename Selected columns to show actual attribution model
                type_chan_display = type_chan_display.rename(columns=attribution_rename)
                st.dataframe(type_chan_display, use_container_width=True, hide_index=True)

                # Stacked bar: Revenue by Channel, stacked by Campaign Type
                type_chan_col1, type_chan_col2 = st.columns(2)
                with type_chan_col1:
                    if rev_col_type in type_chan_df.columns:
                        rev_display_name = get_selected_revenue_display_name(revenue_attribution)
                        fig_type_chan_rev = px.bar(
                            type_chan_df, x='Channel', y=rev_col_type, color='Type of Campaign',
                            barmode='stack', title=f"{rev_display_name} by Channel & Campaign Type",
                            color_discrete_sequence=COLOR_SEQUENCE,
                            labels={rev_col_type: rev_display_name}
                        )
                        fig_type_chan_rev.update_layout(legend=dict(orientation='h', y=-0.2))
                        st.plotly_chart(fig_type_chan_rev, use_container_width=True)
                with type_chan_col2:
                    conv_display_name = get_selected_conversion_display_name(conversion_attribution)
                    fig_type_chan_conv = px.bar(
                        type_chan_df, x='Channel', y=conv_col_type, color='Type of Campaign',
                        barmode='stack', title=f"{conv_display_name} by Channel & Campaign Type",
                        color_discrete_sequence=COLOR_SEQUENCE,
                        labels={conv_col_type: conv_display_name}
                    )
                    fig_type_chan_conv.update_layout(legend=dict(orientation='h', y=-0.2))
                    st.plotly_chart(fig_type_chan_conv, use_container_width=True)

                # Share breakdown: what % of each channel's revenue comes from journeys vs one-time
                if rev_col_type in type_chan_df.columns:
                    channel_totals = type_chan_df.groupby('Channel')[rev_col_type].sum().reset_index()
                    channel_totals.columns = ['Channel', 'Total']
                    type_share = type_chan_df.merge(channel_totals, on='Channel')
                    type_share['Revenue Share'] = np.where(
                        type_share['Total'] > 0,
                        type_share[rev_col_type] / type_share['Total'] * 100, 0
                    )
                    fig_share = px.bar(
                        type_share, x='Channel', y='Revenue Share', color='Type of Campaign',
                        barmode='stack', title="Revenue Share by Campaign Type per Channel (%)",
                        color_discrete_sequence=COLOR_SEQUENCE,
                        custom_data=['Type of Campaign']
                    )
                    fig_share.update_traces(
                        hovertemplate='<b>%{x}</b><br>' +
                                      'Campaign Type: %{customdata[0]}<br>' +
                                      'Revenue Share: %{y:.1f}%<br>' +
                                      '<extra></extra>'
                    )
                    fig_share.update_layout(
                        yaxis_title="Revenue Share (%)", yaxis_range=[0, 100],
                        legend=dict(orientation='h', y=-0.2)
                    )
                    st.plotly_chart(fig_share, use_container_width=True)

        # ESP Analysis
        esp_df = esp_analysis(filtered_df)
        if not esp_df.empty:
            st.subheader("ESP/SSP Analysis")
            esp_df_display = esp_df.copy()
            numeric_cols = ['Sent', 'Delivered', 'Unique Conversions']
            for col in numeric_cols:
                if col in esp_df_display.columns:
                    esp_df_display[col] = esp_df_display[col].apply(format_metric)
            revenue_cols = [col for col in esp_df_display.columns if 'Revenue' in col]
            for col in revenue_cols:
                esp_df_display[col] = esp_df_display[col].apply(lambda x: format_metric(x, "SAR"))
            st.dataframe(esp_df_display)

            esp_col1, esp_col2 = st.columns(2)
            with esp_col1:
                fig_esp = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Delivered',
                                 title="Delivered by ESP", color_discrete_sequence=COLOR_SEQUENCE)
                st.plotly_chart(fig_esp, use_container_width=True)
            with esp_col2:
                if 'Revenue (SAR)' in esp_df.columns:
                    fig_esp_rev = px.bar(esp_df, x='ESP/SSP/WSP/RSP name', y='Revenue (SAR)',
                                         title="Send-Through Revenue by ESP", color_discrete_sequence=COLOR_SEQUENCE,
                                         labels={'Revenue (SAR)': 'Send-Through Revenue (SAR)'})
                    st.plotly_chart(fig_esp_rev, use_container_width=True)

    elif page == "Time Series":
        st.header("Time Series Analysis")
        # Safe column selection - only use columns that exist in both reports
        safe_revenue_cols = ['Revenue (SAR)', 'Impression-Through Revenue (SAR)', 'Click-Through Revenue (SAR)']
        if 'Selected Revenue (SAR)' in filtered_df.columns:
            safe_revenue_cols.insert(0, 'Selected Revenue (SAR)')
        safe_conversion_cols = ['Unique Conversions', 'Unique Clicks']

        # Add Total columns if they exist (Monthly report)
        if 'Total Conversions' in filtered_df.columns:
            safe_conversion_cols.append('Total Conversions')

        all_metrics = safe_conversion_cols + safe_revenue_cols
        ts_metric = st.selectbox("Metric", all_metrics, key='ts_metric', format_func=_attribution_display)
        ts_df = time_series_analysis(filtered_df, ts_metric)
        if not ts_df.empty:
            fig_ts = px.line(ts_df, x='Reporting Period Start Date', y=ts_metric, title=f"{_attribution_display(ts_metric)} Over Time",
                             color_discrete_sequence=[COLORS['primary']])
            fig_ts.update_traces(line_width=2.5)
            st.plotly_chart(fig_ts, use_container_width=True)
        else:
            st.write("No time series data available.")

    elif page == "Correlations":
        st.header("Correlations")
        # Focus on key business metrics for a readable correlation matrix
        key_metric_cols = [c for c in [
            'Sent', 'Delivered', 'Unique Impressions', 'Unique Clicks',
            'Unique Conversions', 'Selected Conversions', 'Selected Revenue (SAR)',
            'Revenue (SAR)', 'CTR', 'Conversion Rate', 'Delivery Rate',
            'AOV', 'Revenue Per Click', 'Revenue Per Send', 'ROAS',
            'Campaign Cost', 'Engagement Rate',
        ] if c in filtered_df.columns]

        if key_metric_cols:
            corr = filtered_df[key_metric_cols].corr()
            fig_corr = px.imshow(corr, text_auto='.2f', title="Key Metrics Correlation Matrix",
                                 color_continuous_scale='RdBu_r', aspect='auto',
                                 zmin=-1, zmax=1)
            fig_corr.update_layout(width=900, height=700)
            st.plotly_chart(fig_corr, use_container_width=True)

            # Highlight strongest correlations
            st.subheader("Strongest Correlations")
            corr_pairs = []
            for i in range(len(corr.columns)):
                for j in range(i + 1, len(corr.columns)):
                    val = corr.iloc[i, j]
                    if abs(val) >= 0.5 and abs(val) < 1.0:
                        corr_pairs.append({
                            'Metric 1': corr.columns[i],
                            'Metric 2': corr.columns[j],
                            'Correlation': val,
                            'Strength': 'Strong' if abs(val) >= 0.7 else 'Moderate'
                        })
            if corr_pairs:
                corr_pairs_df = pd.DataFrame(corr_pairs).sort_values('Correlation', key=abs, ascending=False)
                corr_pairs_df['Correlation'] = corr_pairs_df['Correlation'].apply(lambda x: f"{x:+.3f}")
                st.dataframe(corr_pairs_df, use_container_width=True)
            else:
                st.info("No strong correlations (|r| >= 0.5) found between key metrics.")
        else:
            st.write("No numeric data for correlation.")

    elif page == "A/B Testing":
        st.header("A/B Testing Analysis")
        ab_df = ab_testing_analysis(filtered_df)
        if not ab_df.empty:
            st.dataframe(ab_df)
            fig_ab = px.bar(ab_df, x='Campaign Name', y='Lift', title="Conversion Lift by Campaign",
                            color='Lift', color_continuous_scale=[[0, COLORS['danger']], [0.5, COLORS['warning']], [1, COLORS['success']]])
            st.plotly_chart(fig_ab, use_container_width=True)
        else:
            st.write("No A/B testing data available (no control groups).")

    elif page == "Attribution":
        st.header("Attribution Analysis")
        attr_df = attribution_analysis(filtered_df)
        # Create display version for table
        attr_df_display = attr_df.copy()
        attr_df_display['Conversions'] = attr_df_display['Conversions'].apply(format_metric)
        st.dataframe(attr_df_display)
        
        # Create chart with original numeric values
        fig_attr = px.pie(attr_df, names='Source', values='Conversions', title="Conversions by Attribution Source",
                          color_discrete_sequence=COLOR_SEQUENCE)
        st.plotly_chart(fig_attr, use_container_width=True)

    elif page == "Failed Reasons":
        st.header("Failed Reasons Analysis")
        failed_df = failed_reasons_analysis(filtered_df)
        if not failed_df.empty:
            # Create display version for table
            failed_df_display = failed_df.copy()
            # Format counts
            failed_df_display['Count'] = failed_df_display['Count'].apply(format_metric)
            st.dataframe(failed_df_display)

            # Create chart with original numeric values
            fig_fail = px.bar(failed_df, x='Reason', y='Count', title="Failed Reasons Breakdown",
                              color_discrete_sequence=[COLORS['danger']])
            st.plotly_chart(fig_fail, use_container_width=True)

            # Drill-down: Failed reasons by channel
            st.subheader("Failed Reasons by Channel")
            failed_cols = [col for col in filtered_df.columns if 'Failed' in col and col != 'Failed']
            if failed_cols:
                failed_by_channel = filtered_df.groupby('Channel')[failed_cols].sum().reset_index()
                # Create display version for table
                failed_by_channel_display = failed_by_channel.copy()
                # Format failed counts
                for col in failed_cols:
                    failed_by_channel_display[col] = failed_by_channel_display[col].apply(format_metric)
                st.dataframe(failed_by_channel_display)

                # Melt for plotting (use original numeric values)
                failed_melt = failed_by_channel.melt(id_vars='Channel', var_name='Reason', value_name='Count')
                fig_fail_chan = px.bar(failed_melt, x='Channel', y='Count', color='Reason',
                                      title="Failed Reasons by Channel",
                                      color_discrete_sequence=COLOR_SEQUENCE)
                st.plotly_chart(fig_fail_chan, use_container_width=True)
        else:
            st.write("No failed reasons data available.")

    elif page == "Export":
        st.header("Export")
        # Compute aggregates for export
        camp_metric = 'Unique Conversions'
        top_camp = top_campaigns(filtered_df, camp_metric)
        jour_metric = 'Unique Conversions'
        top_jour = get_top_journeys(filtered_df, jour_metric)
        seg_metric = 'Unique Conversions'
        top_seg = top_segments(filtered_df, seg_metric)
        chan_df = channel_analysis(filtered_df)
        esp_df = esp_analysis(filtered_df)
        ts_metric = 'Unique Conversions'
        ts_df = time_series_analysis(filtered_df, ts_metric)
        failed_df = failed_reasons_analysis(filtered_df)
        
        if st.button("Download Cleaned Data as CSV"):
            csv = filtered_df.to_csv(index=False)
            st.download_button("Download CSV", csv, "cleaned_data.csv", "text/csv", key='csv_dl')

        if st.button("Download Aggregated Report as Excel"):
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                top_camp.to_excel(writer, sheet_name='Top Campaigns', index=False)
                top_jour.to_excel(writer, sheet_name='Top Journeys', index=False)
                top_seg.to_excel(writer, sheet_name='Top Segments', index=False)
                chan_df.to_excel(writer, sheet_name='Channel Analysis', index=False)
                esp_df.to_excel(writer, sheet_name='ESP Analysis', index=False)
                ts_df.to_excel(writer, sheet_name='Time Series', index=False)
                failed_df.to_excel(writer, sheet_name='Failed Reasons', index=False)
            buffer.seek(0)
            st.download_button("Download Excel", buffer, "aggregated_report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key='excel_dl')

    elif page == "Comparisons":
        st.header("📊 Period-over-Period Comparisons")
        st.markdown("*Analyze performance trends across different time periods with detailed metrics*")
        
        # Check if comparison is enabled
        if comparison_result:
            st.success(f"✅ Comparison Mode Active: **{comparison_result['current_label']}** vs **{comparison_result['comparison_label']}**")
            
            # Calculate comprehensive metrics
            current_metrics = calculate_period_metrics(comparison_result['current_data'], comparison_result['current_days'], conversion_attribution)
            comp_metrics = calculate_period_metrics(comparison_result['comparison_data'], comparison_result['comparison_days'], conversion_attribution)
            metric_changes = calculate_metric_changes(current_metrics, comp_metrics)
            
            # === EXECUTIVE SUMMARY ===
            st.markdown("---")
            st.subheader("📈 Executive Summary")
            
            # Key highlights
            revenue_trend = metric_changes['selected_revenue']
            conv_trend = metric_changes['selected_conversions']
            ctr_trend = metric_changes['ctr']
            delivery_trend = metric_changes['delivery_rate']
            
            # Determine overall trend
            positive_trends = sum([
                revenue_trend['pct_change'] > 0,
                conv_trend['pct_change'] > 0,
                ctr_trend['pct_change'] > 0,
                delivery_trend['pct_change'] > 0
            ])
            
            if positive_trends >= 3:
                st.success("🎯 **Overall Trend: POSITIVE** - Most metrics are improving")
            elif positive_trends >= 2:
                st.info("➡️ **Overall Trend: MIXED** - Some metrics improving, others declining")
            else:
                st.warning("⚠️ **Overall Trend: NEEDS ATTENTION** - Most metrics are declining")
            
            # Key metrics comparison
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Revenue Change",
                    f"{revenue_trend['pct_change']:+.1f}%",
                    delta=format_metric(revenue_trend['absolute_change'], "SAR")
                )
            
            with col2:
                st.metric(
                    "Conversion Change",
                    f"{conv_trend['pct_change']:+.1f}%",
                    delta=format_metric(conv_trend['absolute_change'])
                )
            
            with col3:
                st.metric(
                    "CTR Change",
                    f"{ctr_trend['pct_change']:+.1f}%",
                    delta=f"{ctr_trend['absolute_change']:+.2%}"
                )
            
            with col4:
                st.metric(
                    "Delivery Rate Change",
                    f"{delivery_trend['pct_change']:+.1f}%",
                    delta=f"{delivery_trend['absolute_change']:+.2%}"
                )
            
            # Business Intelligence Metrics
            st.markdown("#### 💰 Business Intelligence")
            biz_col1, biz_col2, biz_col3 = st.columns(3)
            
            aov_trend = metric_changes['aov']
            rpc_trend = metric_changes['revenue_per_click']
            eng_trend = metric_changes['engagement_rate']
            
            with biz_col1:
                st.metric(
                    "AOV Change",
                    f"{aov_trend['pct_change']:+.1f}%",
                    delta=format_metric(aov_trend['absolute_change'], "SAR"),
                    help="Average Order Value - Revenue per conversion"
                )
            
            with biz_col2:
                st.metric(
                    "RPC Change",
                    f"{rpc_trend['pct_change']:+.1f}%",
                    delta=format_metric(rpc_trend['absolute_change'], "SAR"),
                    help="Revenue Per Click - Measures click quality"
                )
            
            with biz_col3:
                st.metric(
                    "Engagement Rate Change",
                    f"{eng_trend['pct_change']:+.1f}%",
                    delta=f"{eng_trend['absolute_change']:+.2%}",
                    help="Combined engagement (clicks + opens) / impressions"
                )
            
            # ROI & Cost Efficiency
            st.markdown("#### 💵 ROI & Cost Efficiency")
            cost_col1, cost_col2, cost_col3, cost_col4 = st.columns(4)
            
            roas_trend = metric_changes['roas']
            rps_trend = metric_changes['revenue_per_send']
            cpc_trend = metric_changes['cost_per_conversion']
            profit_trend = metric_changes['profit']
            
            with cost_col1:
                current_roas = roas_trend['current']
                if current_roas >= 4:
                    roas_status = "🟢"
                elif current_roas >= 2:
                    roas_status = "🟡"
                else:
                    roas_status = "🔴"
                
                st.metric(
                    f"ROAS Change {roas_status}",
                    f"{roas_trend['pct_change']:+.1f}%",
                    delta=f"{roas_trend['current']:.2f}x now",
                    help=f"Return on Ad Spend: {roas_trend['current']:.2f}x (was {roas_trend['comparison']:.2f}x)"
                )
            
            with cost_col2:
                st.metric(
                    "Revenue Per Send Change",
                    f"{rps_trend['pct_change']:+.1f}%",
                    delta=f"{rps_trend['absolute_change']:.4f} SAR",
                    help="KEY efficiency metric - answers your 'doubled sends, less revenue' question"
                )
            
            with cost_col3:
                st.metric(
                    "Cost Per Conversion",
                    f"{cpc_trend['pct_change']:+.1f}%",
                    delta=format_metric(cpc_trend['absolute_change'], "SAR"),
                    delta_color="inverse" if cpc_trend['pct_change'] >= 0 else "normal",
                    help="Lower is better"
                )
            
            with cost_col4:
                st.metric(
                    "Profit Change",
                    f"{profit_trend['pct_change']:+.1f}%",
                    delta=format_metric(profit_trend['absolute_change'], "SAR"),
                    help="Revenue - Cost"
                )
            
            # === DETAILED METRICS TABLE ===
            st.markdown("---")
            st.subheader("📊 Detailed Metrics Comparison")
            
            # Create comparison dataframe
            comparison_data = []
            metric_names = {
                'selected_revenue': ('Total Revenue (SAR)', 'SAR'),
                'selected_conversions': ('Total Conversions', ''),
                'total_clicks': ('Total Clicks', ''),
                'total_impressions': ('Total Impressions', ''),
                'total_sent': ('Total Sent', ''),
                'total_delivered': ('Total Delivered', ''),
                'total_cost': ('Total Campaign Cost', 'SAR'),
                'profit': ('Profit (Revenue - Cost)', 'SAR'),
                'ctr': ('Click-Through Rate', '%'),
                'conversion_rate': ('Conversion Rate', '%'),
                'delivery_rate': ('Delivery Rate', '%'),
                'aov': ('Average Order Value (AOV)', 'SAR'),
                'revenue_per_click': ('Revenue Per Click (RPC)', 'SAR'),
                'revenue_per_send': ('Revenue Per Send (RPS)', 'SAR'),
                'engagement_rate': ('Engagement Rate', '%'),
                'roas': ('ROAS (Return on Ad Spend)', 'ratio'),
                'cost_per_conversion': ('Cost Per Conversion', 'SAR'),
                'cost_per_click': ('Cost Per Click', 'SAR'),
                'profit_margin': ('Profit Margin', '%'),
                'revenue_per_conversion': ('Revenue per Conversion', 'SAR'),
                'daily_revenue': ('Daily Avg Revenue', 'SAR'),
                'daily_conversions': ('Daily Avg Conversions', ''),
                'daily_cost': ('Daily Avg Cost', 'SAR'),
            }
            
            for metric_key, (metric_label, unit) in metric_names.items():
                if metric_key in metric_changes:
                    change_data = metric_changes[metric_key]
                    
                    if unit == '%':
                        current_val = f"{change_data['current']:.2%}"
                        comp_val = f"{change_data['comparison']:.2%}"
                    elif unit == 'SAR':
                        current_val = format_metric(change_data['current'], 'SAR')
                        comp_val = format_metric(change_data['comparison'], 'SAR')
                    elif unit == 'ratio':
                        current_val = f"{change_data['current']:.2f}x"
                        comp_val = f"{change_data['comparison']:.2f}x"
                    else:
                        current_val = format_metric(change_data['current'])
                        comp_val = format_metric(change_data['comparison'])
                    
                    comparison_data.append({
                        'Metric': metric_label,
                        'Current Period': current_val,
                        'Comparison Period': comp_val,
                        'Change %': f"{change_data['pct_change']:+.1f}%",
                        'Trend': change_data['trend']
                    })
            
            comparison_df = pd.DataFrame(comparison_data)
            st.dataframe(comparison_df, use_container_width=True)
            
            # === VISUALIZATION ===
            st.markdown("---")
            st.subheader("📈 Visual Comparison")
            
            # Select metric to visualize
            viz_metric = st.selectbox(
                "Select Metric to Visualize",
                ["Revenue (SAR)", "Conversions", "Clicks", "CTR", "Conversion Rate", "Delivery Rate"],
                key="comparison_viz_metric"
            )
            
            # Map selection to data keys
            viz_mapping = {
                "Revenue (SAR)": 'selected_revenue',
                "Conversions": 'selected_conversions',
                "Clicks": 'total_clicks',
                "CTR": 'ctr',
                "Conversion Rate": 'conversion_rate',
                "Delivery Rate": 'delivery_rate'
            }
            
            selected_key = viz_mapping[viz_metric]
            change_data = metric_changes[selected_key]
            
            # Create comparison bar chart
            fig_comparison = go.Figure()
            
            fig_comparison.add_trace(go.Bar(
                name='Comparison Period',
                x=[comparison_result['comparison_label']],
                y=[change_data['comparison']],
                marker_color=COLORS['info'],
                text=[format_metric(change_data['comparison'], 'SAR' if 'Revenue' in viz_metric else '')],
                textposition='auto'
            ))
            
            fig_comparison.add_trace(go.Bar(
                name='Current Period',
                x=[comparison_result['current_label']],
                y=[change_data['current']],
                marker_color=COLORS['success'] if change_data['pct_change'] > 0 else COLORS['danger'],
                text=[format_metric(change_data['current'], 'SAR' if 'Revenue' in viz_metric else '')],
                textposition='auto'
            ))
            
            fig_comparison.update_layout(
                title=f"{viz_metric} Comparison",
                xaxis_title="Period",
                yaxis_title=viz_metric,
                barmode='group',
                height=400
            )
            
            st.plotly_chart(fig_comparison, use_container_width=True)
            comp_img = export_chart_image(fig_comparison, 'period_comparison')
            if comp_img:
                st.download_button("Download Comparison Chart", comp_img, "period_comparison.png", "image/png", key='dl_comparison')

            # === CHANNEL-LEVEL COMPARISON ===
            if 'Channel' in comparison_result['current_data'].columns:
                st.markdown("---")
                st.subheader("📡 Channel-Level Comparison")
                
                # Aggregate by channel for both periods
                current_by_channel = comparison_result['current_data'].groupby('Channel').agg({
                    'Selected Revenue (SAR)': 'sum',
                    'Selected Conversions': 'sum',
                    'Unique Clicks': 'sum'
                }).reset_index()
                
                comp_by_channel = comparison_result['comparison_data'].groupby('Channel').agg({
                    'Selected Revenue (SAR)': 'sum',
                    'Selected Conversions': 'sum',
                    'Unique Clicks': 'sum'
                }).reset_index()
                
                # Merge and calculate changes
                channel_comparison = current_by_channel.merge(
                    comp_by_channel, 
                    on='Channel', 
                    how='outer',
                    suffixes=('_current', '_comp')
                ).fillna(0)
                
                channel_comparison['Revenue Change %'] = ((channel_comparison['Selected Revenue (SAR)_current'] - channel_comparison['Selected Revenue (SAR)_comp']) / 
                                                          channel_comparison['Selected Revenue (SAR)_comp'].replace(0, 1) * 100)
                
                channel_comparison['Conversion Change %'] = ((channel_comparison['Selected Conversions_current'] - channel_comparison['Selected Conversions_comp']) / 
                                                             channel_comparison['Selected Conversions_comp'].replace(0, 1) * 100)
                
                # Display
                channel_display = channel_comparison[['Channel', 'Revenue Change %', 'Conversion Change %']].copy()
                st.dataframe(channel_display, use_container_width=True)
                
                # Channel comparison chart
                fig_channel = go.Figure()
                
                fig_channel.add_trace(go.Bar(
                    name='Revenue Change %',
                    x=channel_comparison['Channel'],
                    y=channel_comparison['Revenue Change %'],
                    marker_color=[COLORS['success'] if x > 0 else COLORS['danger'] for x in channel_comparison['Revenue Change %']]
                ))
                
                fig_channel.update_layout(
                    title="Revenue Change % by Channel",
                    xaxis_title="Channel",
                    yaxis_title="Change %",
                    height=400
                )
                
                st.plotly_chart(fig_channel, use_container_width=True)
            
            # === INSIGHTS & RECOMMENDATIONS ===
            st.markdown("---")
            st.subheader("💡 Insights & Recommendations")
            
            insights = []
            
            # Revenue insights
            if revenue_trend['pct_change'] > 10:
                insights.append(f"✅ **Strong Revenue Growth**: Revenue increased by {revenue_trend['pct_change']:.1f}%. Consider scaling successful campaigns.")
            elif revenue_trend['pct_change'] < -10:
                insights.append(f"⚠️ **Revenue Decline**: Revenue decreased by {abs(revenue_trend['pct_change']):.1f}%. Investigate underperforming channels and campaigns.")
            
            # Conversion insights
            if conv_trend['pct_change'] > 10:
                insights.append(f"✅ **Conversion Improvement**: Conversions up {conv_trend['pct_change']:.1f}%. Current strategies are working well.")
            elif conv_trend['pct_change'] < -10:
                insights.append(f"⚠️ **Conversion Drop**: Conversions down {abs(conv_trend['pct_change']):.1f}%. Review landing pages and offers.")
            
            # CTR insights
            if ctr_trend['pct_change'] > 10:
                insights.append(f"✅ **Engagement Increase**: CTR improved by {ctr_trend['pct_change']:.1f}%. Content resonates with audience.")
            elif ctr_trend['pct_change'] < -10:
                insights.append(f"⚠️ **Engagement Decline**: CTR down {abs(ctr_trend['pct_change']):.1f}%. Consider refreshing creative assets.")
            
            # Delivery insights
            if delivery_trend['pct_change'] < -5:
                insights.append(f"🚨 **Delivery Issue**: Delivery rate dropped {abs(delivery_trend['pct_change']):.1f}%. Check ESP settings and sender reputation.")
            
            # Display insights
            if insights:
                for insight in insights:
                    st.markdown(f"- {insight}")
            else:
                st.info("Performance is relatively stable with no significant changes to highlight.")
        
        else:
            st.info("🔍 **No Comparison Selected** - Enable comparison mode in the sidebar to analyze period-over-period trends")
            st.markdown("---")
            
            # Show month-over-month trend analysis as fallback
            st.subheader("📅 Monthly Trend Analysis")
            
            # Group by month
            monthly_df = filtered_df.copy()
            monthly_df['Month'] = monthly_df['Reporting Period Start Date'].dt.to_period('M').astype(str)
            
            monthly_agg = monthly_df.groupby('Month').agg({
                'Revenue (SAR)': 'sum',
                'Unique Conversions': 'sum',
                'Unique Clicks': 'sum',
                'Sent': 'sum',
                'Delivered': 'sum'
            }).reset_index()
            
            # Sort by month
            monthly_agg['Month'] = pd.to_datetime(monthly_agg['Month'] + '-01')
            monthly_agg = monthly_agg.sort_values('Month')
            monthly_agg['Month'] = monthly_agg['Month'].dt.strftime('%Y-%m')
            
            if not monthly_agg.empty and len(monthly_agg) > 1:
                st.subheader("Monthly Summary")
                # Add total row
                total_row_monthly = {'Month': 'Total'}
                for col in monthly_agg.columns:
                    if col != 'Month':
                        total_row_monthly[col] = monthly_agg[col].sum()
                monthly_agg_with_total = pd.concat([monthly_agg, pd.DataFrame([total_row_monthly])], ignore_index=True)
                # Format columns for display
                monthly_agg_display = monthly_agg_with_total.copy()
                monthly_agg_display['Revenue (SAR)'] = monthly_agg_display['Revenue (SAR)'].apply(lambda x: format_metric(x, "SAR"))
                monthly_agg_display['Unique Conversions'] = monthly_agg_display['Unique Conversions'].apply(format_metric)
                monthly_agg_display['Unique Clicks'] = monthly_agg_display['Unique Clicks'].apply(format_metric)
                monthly_agg_display['Sent'] = monthly_agg_display['Sent'].apply(format_metric)
                monthly_agg_display['Delivered'] = monthly_agg_display['Delivered'].apply(format_metric)
                st.dataframe(style_total_row(monthly_agg_display), use_container_width=True, hide_index=True)
                
                # Chart
                fig_comp = px.line(monthly_agg, x='Month', y='Revenue (SAR)', title="Revenue Over Months", markers=True)
                st.plotly_chart(fig_comp, use_container_width=True)
            else:
                st.write("Not enough monthly data for trend analysis.")

    elif page == "AI Insights":
        st.header("🤖 AI-Powered Insights")
        
        # Forecasting
        st.subheader("📈 Revenue Forecasting")
        if not filtered_df.empty:
            monthly_df = filtered_df.copy()
            monthly_df['Month'] = monthly_df['Reporting Period Start Date'].dt.to_period('M').dt.to_timestamp()
            monthly_rev = monthly_df.groupby('Month')['Revenue (SAR)'].sum().reset_index()
            if len(monthly_rev) > 2:
                # Prepare data for Prophet
                df_prophet = monthly_rev.rename(columns={'Month': 'ds', 'Revenue (SAR)': 'y'})
                try:
                    model = Prophet()
                    model.fit(df_prophet)
                    future = model.make_future_dataframe(periods=3, freq='M')
                    forecast = model.predict(future)
                    # Build Plotly figure from Prophet forecast data
                    fig_forecast = go.Figure()
                    fig_forecast.add_trace(go.Scatter(
                        x=df_prophet['ds'], y=df_prophet['y'],
                        mode='markers', name='Actual', marker=dict(color=COLORS['primary'], size=8)
                    ))
                    fig_forecast.add_trace(go.Scatter(
                        x=forecast['ds'], y=forecast['yhat'],
                        mode='lines', name='Forecast', line=dict(color=COLORS['success'], width=2)
                    ))
                    fig_forecast.add_trace(go.Scatter(
                        x=pd.concat([forecast['ds'], forecast['ds'][::-1]]),
                        y=pd.concat([forecast['yhat_upper'], forecast['yhat_lower'][::-1]]),
                        fill='toself', fillcolor='rgba(5,150,105,0.15)', line=dict(width=0),
                        name='Confidence Interval'
                    ))
                    fig_forecast.update_layout(title="Revenue Forecast (Next 3 Months)", xaxis_title="Date", yaxis_title="Revenue (SAR)")
                    st.plotly_chart(fig_forecast, use_container_width=True)
                    st.write("**Forecast Insights:** Next 3 months revenue prediction with confidence intervals.")
                except Exception as e:
                    st.write(f"Forecasting error: {e}")
            else:
                st.write("Not enough data for forecasting.")
        
        # Segmentation
        st.subheader("👥 Advanced Customer Segmentation")
        if not filtered_df.empty:
            seg_agg = filtered_df.groupby('Segment Name').agg({
                'Revenue (SAR)': 'sum',
                'Unique Conversions': 'sum',
                'Unique Clicks': 'sum',
                'Sent': 'sum'
            }).reset_index()
            if len(seg_agg) > 3:
                features = seg_agg[['Revenue (SAR)', 'Unique Conversions', 'Unique Clicks', 'Sent']]
                try:
                    kmeans = KMeans(n_clusters=3, random_state=42)
                    seg_agg['Cluster'] = kmeans.fit_predict(features)
                    fig_seg = px.scatter(seg_agg, x='Revenue (SAR)', y='Unique Conversions', color='Cluster', hover_data=['Segment Name'])
                    st.plotly_chart(fig_seg)
                    st.write("**Segmentation Insights:** Segments grouped by behavior. High-value clusters should be prioritized.")
                except Exception as e:
                    st.write(f"Segmentation error: {e}")
            else:
                st.write("Not enough segments for clustering.")
        
        # Optimization
        st.subheader("🎯 Campaign Optimization Recommendations")
        top_camp = top_campaigns(filtered_df, 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)')
        if not top_camp.empty:
            best_camp = top_camp.iloc[0]['Campaign Name']
            st.success(f"🚀 **Top Performer:** {best_camp} - Allocate more budget here!")
            underperformers = top_camp.tail(3)['Campaign Name'].tolist()
            st.warning(f"⚠️ **Underperformers:** {', '.join(underperformers)} - Consider pausing or optimizing.")
        
        # ROI Analysis
        st.subheader("💰 ROI Analysis")
        rev_col_roi = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in filtered_df.columns else 'Revenue (SAR)'
        roi_df = filtered_df.groupby('Channel').agg({
            rev_col_roi: 'sum',
            'Sent': 'sum',
            'Campaign Cost': 'sum',
        }).reset_index()
        roi_df = roi_df.rename(columns={'Campaign Cost': 'Cost (SAR)', rev_col_roi: 'Revenue (SAR)'})
        roi_df['Profit (SAR)'] = roi_df['Revenue (SAR)'] - roi_df['Cost (SAR)']
        roi_df['ROAS'] = np.where(roi_df['Cost (SAR)'] > 0, roi_df['Revenue (SAR)'] / roi_df['Cost (SAR)'], 0)
        roi_df['Revenue Per Send'] = np.where(roi_df['Sent'] > 0, roi_df['Revenue (SAR)'] / roi_df['Sent'], 0)

        # Format for display
        roi_display = roi_df.copy()
        for col in ['Revenue (SAR)', 'Cost (SAR)', 'Profit (SAR)']:
            roi_display[col] = roi_display[col].apply(lambda x: format_metric(x, "SAR"))
        roi_display['Sent'] = roi_display['Sent'].apply(format_metric)
        roi_display['ROAS'] = roi_display['ROAS'].apply(lambda x: f"{x:.2f}x")
        roi_display['Revenue Per Send'] = roi_display['Revenue Per Send'].apply(lambda x: f"{x:.4f} SAR")
        st.dataframe(roi_display, use_container_width=True)

        # ROI chart
        fig_roi = px.bar(roi_df, x='Channel', y=['Revenue (SAR)', 'Cost (SAR)'], barmode='group',
                         title="Revenue vs Cost by Channel", color_discrete_sequence=[COLORS['success'], COLORS['danger']])
        st.plotly_chart(fig_roi, use_container_width=True)

        # Dynamic Actionable Recommendations
        st.subheader("📋 Actionable Recommendations")
        # Generate recommendations based on actual data
        _recs = []
        if not roi_df.empty:
            best_roas_ch = roi_df.loc[roi_df['ROAS'].idxmax(), 'Channel'] if roi_df['ROAS'].max() > 0 else None
            best_rps_ch = roi_df.loc[roi_df['Revenue Per Send'].idxmax(), 'Channel'] if roi_df['Revenue Per Send'].max() > 0 else None
            highest_cost_ch = roi_df.loc[roi_df['Cost (SAR)'].idxmax(), 'Channel'] if roi_df['Cost (SAR)'].max() > 0 else None

            if best_roas_ch:
                _recs.append(f"- **Scale {best_roas_ch}:** Highest ROAS ({roi_df.loc[roi_df['Channel']==best_roas_ch, 'ROAS'].values[0]:.1f}x) - consider increasing budget")
            if best_rps_ch and best_rps_ch != best_roas_ch:
                _recs.append(f"- **Leverage {best_rps_ch}:** Best revenue per send - efficient at converting messages to revenue")
            if highest_cost_ch:
                cost_ch_roas = roi_df.loc[roi_df['Channel']==highest_cost_ch, 'ROAS'].values[0]
                if cost_ch_roas < 2:
                    _recs.append(f"- **Optimize {highest_cost_ch}:** Highest cost channel with ROAS of only {cost_ch_roas:.1f}x - review targeting and content")

        # Add data-driven segment and campaign recommendations
        if 'Selected Conversions' in filtered_df.columns:
            ch_conv = filtered_df.groupby('Channel')['Selected Conversions'].sum()
            low_conv_channels = ch_conv[ch_conv > 0].nsmallest(2).index.tolist()
            if low_conv_channels:
                _recs.append(f"- **Improve conversion on {', '.join(low_conv_channels)}:** Low conversion volume - test different CTAs and offers")

        _recs.append("- **A/B test creatives:** For campaigns with below-average CTR")
        _recs.append("- **Monitor forecasts:** Use revenue predictions above for budget planning")

        st.markdown("\n".join(_recs))

else:
    st.write("Please upload a CSV file.")
