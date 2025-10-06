# 📊 Shareholder Report - User Guide

## Overview
The **Overview** page has been transformed into a comprehensive **Shareholder Report** designed for executive presentations and board meetings.

## What's New

### 1. **Executive Summary Section** 🎯
- Automatic period detection (Weekly, Monthly, Multi-Month)
- Date range display
- Clean, professional layout

### 2. **Key Performance Indicators with Period Comparison** 📈
All hero metrics now show:
- **Current period value**
- **Growth vs previous period** (% or percentage points)
- **Color-coded indicators**: 
  - 🟢 Green ▲ = Improvement
  - 🔴 Red ▼ = Decline
  - ⚪ Gray = No change

**Metrics displayed:**
- Total Revenue (SAR)
- Conversions
- Click-Through Rate
- Conversion Rate
- Delivery Rate
- Revenue per Conversion
- Messages Sent
- Impressions

### 3. **Revenue Analysis** 💰

#### Revenue Trend Over Time
- Interactive line chart showing daily revenue trends
- Three lines:
  - **Total Revenue** (solid blue line)
  - **Click-Through Revenue** (dashed orange)
  - **Impression-Through Revenue** (dotted green)

#### Revenue Attribution (CORRECTED) ✅
**Fixed the attribution logic!** Now correctly shows:

```
Send-Through Revenue (Total)
    ├── Impression-Through Revenue (subset)
    │       └── Click-Through Revenue (subset)
```

**The pie chart now shows non-overlapping portions:**
- **Send-Through Only**: Conversions without tracked impression/click (usually largest)
- **Impression-Through Only**: Users who saw but didn't click, yet converted
- **Click-Through**: Users who clicked and converted (most engaged)

**Verification numbers shown below the chart:**
- Total Revenue (Send-Through)
- Impression-Through with percentage
- Click-Through with percentage

#### Revenue by Channel with Comparison
- Bar chart showing revenue by channel
- **Period-over-period comparison** showing:
  - Revenue growth % per channel
  - Conversion growth % per channel
  - Visual indicators (📈 up, 📉 down, ➡️ flat)

### 4. **Top Performers** 🏆

#### Top 10 Journeys by Revenue
- Journey name
- Revenue (formatted)
- Conversions (formatted)
- Health Score (0-100)
- Status with emoji indicators

#### Top 10 Campaigns by Revenue
- Campaign name
- Revenue (formatted)
- Conversions (formatted)
- Health Score (0-100)
- Status with emoji indicators

**Note:** Only includes journeys/campaigns with sufficient data volume (filters out "Insufficient Data" entries)

### 5. **Marketing Funnel Performance** 📊
- Enhanced funnel visualization showing:
  - Sent → Delivered → Impressions → Clicks → Conversions
  - Percentage of initial at each stage
  - Percentage of previous stage
- Side metrics panel with:
  - Delivery Success Rate
  - Impression Rate
  - Click-Through Rate
  - Conversion Rate
  - Overall Efficiency (conversions as % of sent)

### 6. **Key Insights & Recommendations** 💡
Automated insights generation based on your data:

**Insights include:**
- Revenue concentration analysis
- Top channel performance
- Conversion rate assessment
- Delivery rate evaluation
- Engagement (CTR) analysis

**Recommendations include:**
- Diversification strategies
- Optimization priorities
- Quick wins identified
- Risk mitigation

### 7. **Export Functionality** 📥
- **Download Full Report (Excel)** button
- Excel file includes:
  - Summary metrics sheet
  - Top Journeys sheet
  - Top Campaigns sheet
  - Channel Performance sheet
- Filename includes date range for easy organization

## How to Use

### Running the Report

1. **Upload your WebEngage CSV file**
   - Can be 1 week, 1 month, 3 months, or 6 months of data
   - More data = better period comparisons

2. **Use Sidebar Filters** (optional)
   - Attribution Settings: Choose revenue/conversion attribution type
   - Date Range: Focus on specific dates
   - Channels, Campaigns, Segments, Journeys: Filter by specific items

3. **Navigate to "Overview" page**
   - This is now your Shareholder Report
   - Scroll through all sections
   - Use expanders for more details

4. **Export for Presentations**
   - Click "Download Full Report (Excel)" button
   - Use the Excel file in PowerPoint or share directly
   - Or take screenshots of the visualizations

## Period Comparison Logic

The system automatically compares your selected period with the **immediately preceding period of equal length**.

**Example:**
- If you select March 1-31 (31 days)
- Comparison will be to Jan 30 - Feb 28 (previous 31 days)

**Requirements for comparison:**
- You need data spanning at least 2x your reporting period
- If no previous period data exists, metrics show without delta
- You'll see a message indicating no comparison data available

## Understanding the Metrics

### Revenue Attribution (Corrected!)

**WebEngage uses nested/hierarchical attribution:**

```
Total Revenue (Send-Through) = 100,000 SAR
   ├── 80,000 SAR had impressions (Impression-Through)
   │     └── 50,000 SAR had clicks (Click-Through)
   └── 20,000 SAR no impression tracked
```

**The pie chart breaks this down as:**
- **Send-Through Only**: 20,000 SAR (20%)
- **Impression-Through Only**: 30,000 SAR (30%) = 80k - 50k
- **Click-Through**: 50,000 SAR (50%)

**Total = 100,000 SAR** ✅

### Growth Indicators

- **%** = Percentage growth (for volumes like revenue, conversions)
- **pp** = Percentage points (for rates like CTR, conversion rate)
  - Example: 5% → 7% = +2pp growth

### Health Scores

- **Excellent (80-100)**: Top quartile - scale these
- **Good (60-79)**: Above average - minor optimizations
- **Fair (40-59)**: Below average - improvements needed
- **Poor (0-39)**: Bottom quartile - immediate action required
- **Insufficient Data**: Not enough volume to calculate reliable score

## Tips for Shareholders Meetings

1. **Start with Hero Metrics** - Show the period comparison at the top
2. **Highlight Revenue Trends** - Use the line chart to show growth trajectory
3. **Explain Attribution** - Use the pie chart to show engagement quality
4. **Focus on Top Performers** - Show which journeys/campaigns drive results
5. **Address the Funnel** - Identify where users drop off
6. **Share Insights** - Use the automated insights section for storytelling
7. **Provide Recommendations** - Show you have an action plan

## Troubleshooting

### "No previous period data available"
- **Solution**: Upload data spanning a longer time period
- Need at least 2x your reporting period for comparison

### "Insufficient Data" for journeys/campaigns
- **Cause**: Not enough volume to calculate reliable health scores
- These are automatically filtered from Top Performers tables

### Attribution numbers don't add up
- **This is correct!** They are hierarchical, not additive
- Refer to the "Understanding Revenue Attribution" expander in the report

### Comparison shows unexpected results
- **Check**: Are you comparing similar time periods?
- **Consider**: Seasonality, holidays, campaign launches
- **Verify**: Filter settings (channels, campaigns, etc.)

## What Didn't Change

✅ All other pages remain intact:
- Campaigns
- Journeys
- Segments
- Channels
- Time Series
- Correlations
- A/B Testing
- Attribution
- Failed Reasons
- ESP Performance
- Comparisons
- AI Insights
- Export

✅ All existing functionality preserved
✅ All filters work the same way
✅ All health scoring algorithms unchanged

## Next Steps

Want to customize further? You can:
1. Adjust the insights thresholds in the code
2. Add more metrics to the comparison
3. Customize the color schemes
4. Add more charts/visualizations
5. Export to different formats (PDF, PowerPoint)

---

**Questions?** Check the code comments or refer to the WebEngage documentation for data definitions.
