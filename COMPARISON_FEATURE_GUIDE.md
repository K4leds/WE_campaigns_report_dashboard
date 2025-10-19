# 📊 Period-over-Period Comparison Feature Guide

## Overview
The dashboard now includes comprehensive period-over-period comparison functionality, allowing you to analyze trends and performance changes across different time periods.

## 🎯 Key Features

### 1. **Comparison Mode Selector** (Sidebar)
Located in the sidebar under "📊 Comparison Settings", you can select from multiple comparison modes:

- **None** - No comparison (default)
- **Previous Period (Auto)** - Automatically compares with the previous period of equal duration
- **Week over Week** - Compare current week vs previous week
- **Month over Month** - Compare current month vs previous month
- **Quarter over Quarter** - Compare current quarter vs previous quarter
- **Custom Date Range** - Select any custom date range for comparison

### 2. **Custom Date Range Comparison**
When you select "Custom Date Range", an additional date picker appears allowing you to specify exactly which period you want to compare against.

## 📈 Available on All Major Pages

### **Overview Page**
- All metrics display with percentage change indicators
- Shows trend arrows (↗ increasing, → stable, ↘ decreasing)
- Color-coded deltas (green for positive, red for negative)
- Comprehensive period comparison summary with daily averages
- Key changes highlighted for quick insights

**Metrics with Comparison:**
- Total Revenue
- Total Conversions
- Total Clicks
- Total Impressions
- Average CTR
- Average Conversion Rate
- Average Delivery Rate

### **Comparisons Page** (Enhanced)
The dedicated Comparisons page now includes:

#### Executive Summary Section
- Overall trend assessment (Positive, Mixed, or Needs Attention)
- Key metric changes at a glance
- Revenue, Conversion, CTR, and Delivery Rate change percentages

#### Detailed Metrics Table
Complete breakdown of all metrics comparing:
- Current period values
- Comparison period values
- Absolute and percentage changes
- Trend indicators

#### Visual Comparison Charts
- Interactive bar charts for selected metrics
- Side-by-side period comparison
- Color-coded performance (green for improvement, red for decline)

#### Channel-Level Comparison
- Revenue and conversion changes by channel
- Identify which channels improved or declined
- Visual charts for easy interpretation

#### Insights & Recommendations
Auto-generated insights based on:
- Revenue trends (>10% change triggers insights)
- Conversion performance
- Engagement metrics (CTR)
- Delivery issues
- Specific, actionable recommendations for each insight

### **Campaigns Page**
- Quick comparison metrics banner at top
- Shows Revenue, Conversions, CTR, and Conversion Rate changes
- All metrics display with trend indicators when comparison is active

### **Journeys Page**
- Quick comparison metrics banner at top
- Shows Revenue, Conversions, CTR, and Conversion Rate changes
- All metrics display with trend indicators when comparison is active

## 🔢 How It Works

### Automatic Period Calculation
The system automatically:
1. Calculates the duration of your selected date range
2. Determines the comparison period based on your selected mode
3. Applies the same filters (channels, campaigns, segments, journeys) to both periods
4. Computes metrics for both periods with proper normalization

### Daily Averages
To ensure fair comparison between periods of different durations:
- All totals are converted to daily averages
- Percentage changes are calculated on normalized values
- Period duration information is always displayed

### Metric Calculations
For each comparison, the system calculates:
- **Absolute Change**: Current value - Comparison value
- **Percentage Change**: ((Current - Comparison) / Comparison) × 100
- **Trend Direction**: Based on percentage change magnitude
  - Stable: < 1% change
  - Increasing: > 1% positive change
  - Decreasing: > 1% negative change

## 📊 Example Use Cases

### Use Case 1: Week-over-Week Campaign Performance
**Scenario**: You want to see if last week's campaign optimizations improved performance.

**Steps**:
1. Set date range to the current week
2. Select "Week over Week" from Comparison Settings
3. Navigate to Campaigns page
4. View metric changes with trend indicators

### Use Case 2: Month-over-Month Revenue Trend
**Scenario**: Compare this month's revenue to last month.

**Steps**:
1. Set date range to current month
2. Select "Month over Month" from Comparison Settings
3. Navigate to Overview page
4. See revenue change percentage and trend
5. Go to Comparisons page for detailed breakdown

### Use Case 3: Custom Period Comparison
**Scenario**: Compare performance during a promotional period vs a normal period.

**Steps**:
1. Set date range to your promotional period (e.g., Dec 1-15)
2. Select "Custom Date Range" from Comparison Settings
3. Set comparison range to a normal period (e.g., Nov 1-15)
4. Navigate to Comparisons page
5. Analyze detailed metrics and channel-level performance

### Use Case 4: Quarter Performance Analysis
**Scenario**: Analyze Q4 performance vs Q3.

**Steps**:
1. Set date range to Q4 (Oct 1 - Dec 31)
2. Select "Quarter over Quarter" from Comparison Settings
3. Navigate to Comparisons page
4. Review executive summary and insights
5. Check channel-level comparison for areas of improvement

## 💡 Best Practices

### 1. **Select Appropriate Comparison Periods**
- Use Week over Week for recent tactical changes
- Use Month over Month for strategic campaign analysis
- Use Quarter over Quarter for business planning
- Use Custom ranges for special events or promotions

### 2. **Consider Seasonality**
- Be aware of seasonal effects when comparing periods
- The system will show the insights but won't automatically account for seasonality
- Use custom ranges to compare similar periods year-over-year

### 3. **Focus on Daily Averages**
- When periods have different durations, focus on daily average metrics
- The system automatically normalizes for fair comparison
- Look at "Daily Avg Revenue" and "Daily Avg Conversions" in comparison summaries

### 4. **Combine with Filters**
- Use channel, campaign, segment, and journey filters
- Comparison respects all filters for both periods
- Isolate specific campaigns or channels for targeted analysis

### 5. **Act on Insights**
- Pay attention to auto-generated insights on the Comparisons page
- Red alerts (⚠️) indicate metrics needing immediate attention
- Green checkmarks (✅) highlight successful strategies to scale

## 🎨 Visual Indicators Guide

### Trend Arrows
- **↗** (Green) = Metric is increasing (positive trend)
- **→** (Blue) = Metric is stable (< 1% change)
- **↘** (Red) = Metric is decreasing (negative trend)

### Delta Colors
- **Green** = Positive change (improvement)
- **Red** = Negative change (decline)
- Automatically applied based on whether higher or lower is better for each metric

### Insight Severity
- **🚨 Red** = Critical issues requiring immediate action
- **⚠️ Orange** = Warnings for metrics declining but not critical
- **ℹ️ Blue** = Informational insights
- **✅ Green** = Positive trends and successes

## 🔧 Technical Details

### Supported Metrics
All comparisons work with these key metrics:
- Revenue (Total, Impression-Through, Click-Through)
- Conversions (Total, Selected Attribution)
- Clicks (Unique)
- Impressions (Unique)
- CTR (Click-Through Rate)
- Conversion Rate
- Delivery Rate
- Revenue Per Conversion
- Daily Averages (Revenue, Conversions, Clicks, Sent)

### Attribution Support
The comparison feature respects your selected attribution models:
- Revenue Attribution: Total, Impression-Through, Click-Through
- Conversion Attribution: Total, Impression-Through, Click-Through
- Changes are calculated on the selected attribution method

### Performance
- All comparison calculations are optimized
- Data is cached where possible
- Even with large datasets, comparison calculations are fast

## 📝 Notes

1. **Comparison is Optional**: If you don't need comparison, keep it set to "None"
2. **Date Range Required**: Comparison only works when a valid date range is selected
3. **Filter Consistency**: The same filters apply to both periods for fair comparison
4. **Missing Data**: If a comparison period has no data, the system will indicate this
5. **Percentage Calculations**: When comparison period is zero, system shows 100% change for non-zero current values

## 🆘 Troubleshooting

### Issue: Comparison not showing
**Solution**: Ensure you have:
- Selected a valid date range
- Chosen a comparison mode other than "None"
- Data available for both periods

### Issue: "No data available for comparison period"
**Solution**: 
- Check if your dataset includes the comparison period dates
- Try a different comparison mode
- Verify filters aren't excluding all data

### Issue: Unexpected percentage changes
**Solution**:
- Review the daily averages (not just totals)
- Check if period durations are very different
- Look at absolute changes in addition to percentages

## 🚀 Future Enhancements

Potential future additions:
- Year-over-year comparison option
- Multi-period comparison (compare 3+ periods)
- Statistical significance testing
- Anomaly detection in period comparisons
- Export comparison reports to PDF/Excel

---

**Need Help?** Check the inline tooltips and expanders throughout the dashboard for additional guidance.
