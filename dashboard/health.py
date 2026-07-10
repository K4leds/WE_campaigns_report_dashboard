"""Health-score calculations for journeys and campaigns.

Extracted verbatim from app.py (Task 4 of the app.py modularization refactor).
"""
import numpy as np
import pandas as pd


def calculate_journey_health_score(df_journey, all_journeys_df=None):
    """
    Calculate a comprehensive Journey Health Score (0-100) using Empirical Bayes methodology
    with small-sample corrections - the gold standard for BI analytics in enterprise environments.

    Scoring Method: Empirical Bayes Shrinkage + Log-transformed Revenue Per Conversion
    - Uses Beta-Binomial shrinkage for conversion rates (handles small samples robustly)
    - Log-transforms Revenue Per Conversion to reduce outlier dominance
    - Applies statistical smoothing used by major tech companies (Meta, Google, Amazon)
    - Provides reliable rankings even with sparse data
    """
    try:
        # Initialize scores
        scores = {}

        # --- Data sufficiency guard ---
        # Avoid labeling very low-activity journeys as 'Good' or 'Excellent'.
        # Heuristic thresholds (conservative defaults) - adjust as needed:
        # - min_sent: minimum total messages sent across the journey
        # - min_conversions: minimum total conversions to consider revenue/conversion metrics meaningful
        # - min_days: minimum number of reporting days for the journey
        min_sent = 10
        min_conversions = 3
        min_days = 3

        # Compute simple activity metrics for this journey
        total_sent_j = df_journey['Sent'].sum() if 'Sent' in df_journey.columns else 0
        total_conversions_j = df_journey['Selected Conversions'].sum() if 'Selected Conversions' in df_journey.columns else (df_journey['Unique Conversions'].sum() if 'Unique Conversions' in df_journey.columns else 0)
        unique_days = df_journey['Reporting Period Start Date'].nunique() if 'Reporting Period Start Date' in df_journey.columns else len(df_journey)

        if total_sent_j < min_sent or total_conversions_j < min_conversions or unique_days < min_days:
            # Return explicit Insufficient Data result so the UI can filter or flag these journeys
            return {
                'health_score': 0.0,
                'tier': 'Insufficient Data',
                'tier_description': 'Insufficient activity to compute reliable score',
                'component_scores': {'delivery': 0, 'engagement': 0, 'conversion': 0, 'revenue': 0},
                'recommendations': [
                    'ℹ️ Insufficient data: Not enough volume or time to compute a reliable health score',
                    '🔎 Consider increasing the lookback window or aggregating similar journeys for stability'
                ],
                'scoring_method': 'Insufficient data guard (volume/time thresholds)'
            }

        # Get baseline data for percentile calculations (use all data if available)
        baseline_df = all_journeys_df if all_journeys_df is not None else df_journey

        # === EMPIRICAL BAYES HELPER FUNCTIONS ===
        def estimate_beta_prior(successes_array, trials_array):
            """Estimate Beta prior parameters using method of moments from population data"""
            # Filter out invalid data
            valid_mask = (trials_array > 0) & (~np.isnan(successes_array)) & (~np.isnan(trials_array))
            if not valid_mask.any():
                return 1.0, 1.0  # Uniform prior fallback

            rates = successes_array[valid_mask] / trials_array[valid_mask]
            rates = rates[(rates >= 0) & (rates <= 1)]  # Valid rates only

            if len(rates) < 2:
                return 1.0, 1.0  # Uniform prior fallback

            mean_rate = np.mean(rates)
            var_rate = np.var(rates, ddof=1)

            # Ensure variance is positive and not too close to theoretical maximum
            if var_rate <= 0 or var_rate >= mean_rate * (1 - mean_rate):
                return 1.0, 1.0  # Uniform prior fallback

            # Method of moments: alpha = mean * (mean*(1-mean)/var - 1), beta = (1-mean) * (...)
            scale = mean_rate * (1 - mean_rate) / var_rate - 1.0
            alpha = max(0.1, mean_rate * scale)
            beta = max(0.1, (1 - mean_rate) * scale)

            return alpha, beta

        def beta_posterior_mean(successes, trials, alpha_prior, beta_prior):
            """Calculate posterior mean for Beta-Binomial model"""
            if trials <= 0:
                return 0.0
            return (successes + alpha_prior) / (trials + alpha_prior + beta_prior)

        # Helper function for percentile-based scoring (now using smoothed values)
        def calculate_percentile_score(value, baseline_values, reverse=False):
            """Convert a value to percentile score (0-100) using statistical ranking"""
            if len(baseline_values) == 0 or pd.isna(value):
                return 50  # Neutral score for missing data

            # Remove NaN values
            clean_values = baseline_values.dropna()
            if len(clean_values) == 0:
                return 50

            # Calculate percentile rank
            if reverse:
                # For metrics where lower is better (e.g., cost per conversion)
                percentile = (1 - (clean_values < value).mean()) * 100
            else:
                # For metrics where higher is better (standard case)
                percentile = (clean_values <= value).mean() * 100

            return min(max(percentile, 0), 100)  # Ensure 0-100 range

        # === PREPARE POPULATION DATA FOR EMPIRICAL BAYES ===

        # Collect journey-level data for prior estimation
        journey_groups = baseline_df.groupby('Journey Name') if 'Journey Name' in baseline_df.columns else [('current', baseline_df)]

        # Delivery rates (usually high success rate, less smoothing needed)
        delivery_rates = []
        delivery_totals = []
        for name, group in journey_groups:
            if 'Delivery Rate' in group.columns:
                rate = group['Delivery Rate'].mean()
                if not pd.isna(rate):
                    delivery_rates.append(rate)
            elif 'Sent' in group.columns and 'Delivered' in group.columns:
                sent = group['Sent'].sum()
                delivered = group['Delivered'].sum()
                if sent > 0:
                    delivery_rates.append(delivered / sent)
                    delivery_totals.append(sent)

        # CTR data for Empirical Bayes
        ctr_clicks = []
        ctr_impressions = []
        for name, group in journey_groups:
            if 'Unique Clicks' in group.columns and 'Unique Impressions' in group.columns:
                clicks = group['Unique Clicks'].sum()
                impressions = group['Unique Impressions'].sum()
                if impressions > 0:
                    ctr_clicks.append(clicks)
                    ctr_impressions.append(impressions)

        # Conversion data for Empirical Bayes
        conv_conversions = []
        conv_clicks = []
        for name, group in journey_groups:
            if 'Unique Conversions' in group.columns and 'Unique Clicks' in group.columns:
                conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
                clicks = group['Unique Clicks'].sum()
                if clicks > 0:
                    conv_conversions.append(conversions)
                    conv_clicks.append(clicks)

        # Revenue Per Conversion data (for log-transformation)
        rpc_values = []
        for name, group in journey_groups:
            if 'Revenue (SAR)' in group.columns and 'Unique Conversions' in group.columns:
                revenue = group['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in group.columns else group['Revenue (SAR)'].sum()
                conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
                if conversions > 0:
                    rpc = revenue / conversions
                    if rpc > 0:  # Only positive RPC values
                        rpc_values.append(rpc)

        # Estimate priors
        ctr_alpha, ctr_beta = estimate_beta_prior(np.array(ctr_clicks), np.array(ctr_impressions))
        conv_alpha, conv_beta = estimate_beta_prior(np.array(conv_conversions), np.array(conv_clicks))

        # === CALCULATE COMPONENT SCORES WITH EMPIRICAL BAYES ===

        # 1. Delivery Performance Score (25% weight) - Less smoothing needed
        if 'Delivery Rate' in df_journey.columns and df_journey['Delivery Rate'].notna().any():
            delivery_rate = df_journey['Delivery Rate'].mean()
        elif 'Sent' in df_journey.columns and 'Delivered' in df_journey.columns:
            total_sent = df_journey['Sent'].sum()
            total_delivered = df_journey['Delivered'].sum()
            delivery_rate = (total_delivered / total_sent) if total_sent > 0 else 0
        else:
            delivery_rate = 0.8  # Industry average 80%

        baseline_delivery = pd.Series(delivery_rates) if delivery_rates else pd.Series([delivery_rate])
        scores['delivery'] = calculate_percentile_score(delivery_rate, baseline_delivery)

        # 2. Engagement Performance Score (25% weight) - WITH EMPIRICAL BAYES SMOOTHING
        # FIXED: Always use aggregate CTR calculation instead of daily average CTR for proper scoring
        if 'Unique Clicks' in df_journey.columns and 'Unique Impressions' in df_journey.columns:
            total_clicks = df_journey['Unique Clicks'].sum()
            total_impressions = df_journey['Unique Impressions'].sum()
            # Apply Empirical Bayes smoothing to aggregate CTR (more reliable than daily averages)
            smoothed_ctr = beta_posterior_mean(total_clicks, total_impressions, ctr_alpha, ctr_beta)
        else:
            smoothed_ctr = 0.02  # Industry average 2%

        # Create baseline of smoothed CTRs for fair comparison
        baseline_ctr_smoothed = []
        for clicks, impressions in zip(ctr_clicks, ctr_impressions):
            baseline_ctr_smoothed.append(beta_posterior_mean(clicks, impressions, ctr_alpha, ctr_beta))
        baseline_ctr = pd.Series(baseline_ctr_smoothed) if baseline_ctr_smoothed else pd.Series([smoothed_ctr])

        scores['engagement'] = calculate_percentile_score(smoothed_ctr, baseline_ctr)

        # 3. Conversion Performance Score (30% weight) - ALWAYS CALCULATE FROM RAW FIELDS
        # Use Selected Conversions if available (attribution-aware), otherwise fall back to Unique Conversions
        if 'Unique Conversions' in df_journey.columns and 'Unique Clicks' in df_journey.columns:
            total_conversions = df_journey['Selected Conversions'].sum() if 'Selected Conversions' in df_journey.columns else df_journey['Unique Conversions'].sum()
            total_clicks = df_journey['Unique Clicks'].sum()
            # Apply Empirical Bayes smoothing
            conv_rate = beta_posterior_mean(total_conversions, total_clicks, conv_alpha, conv_beta)

            # Create baseline of smoothed conversion rates
            baseline_conv_smoothed = []
            for conversions, clicks in zip(conv_conversions, conv_clicks):
                baseline_conv_smoothed.append(beta_posterior_mean(conversions, clicks, conv_alpha, conv_beta))
            baseline_conv = pd.Series(baseline_conv_smoothed) if baseline_conv_smoothed else pd.Series([conv_rate])
        else:
            conv_rate = 0.05  # Industry average 5%
            baseline_conv = pd.Series([conv_rate])

        scores['conversion'] = calculate_percentile_score(conv_rate, baseline_conv)

        # 4. Revenue Efficiency Score (20% weight) - LOG-TRANSFORMED RPC
        # Use Selected Revenue and Selected Conversions if available (attribution-aware)
        if 'Revenue (SAR)' in df_journey.columns and 'Unique Conversions' in df_journey.columns:
            total_revenue = df_journey['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in df_journey.columns else df_journey['Revenue (SAR)'].sum()
            total_conversions = df_journey['Selected Conversions'].sum() if 'Selected Conversions' in df_journey.columns else df_journey['Unique Conversions'].sum()
            revenue_per_conversion = (total_revenue / total_conversions) if total_conversions > 0 else 0

            # Log-transform for better distribution (reduces outlier dominance)
            log_rpc = np.log1p(revenue_per_conversion)  # log(1 + x) handles zero values

            # Create baseline of log-transformed RPCs
            baseline_log_rpc = [np.log1p(rpc) for rpc in rpc_values] if rpc_values else [log_rpc]
            baseline_log_rpc = pd.Series(baseline_log_rpc)

            scores['revenue'] = calculate_percentile_score(log_rpc, baseline_log_rpc)
        else:
            scores['revenue'] = 50  # Neutral score if no revenue data

        # Calculate weighted final score using enterprise-optimized weights
        # Increased revenue weight slightly to improve sensitivity to business outcomes
        weights = {'delivery': 0.20, 'engagement': 0.25, 'conversion': 0.30, 'revenue': 0.25}
        final_score = sum(scores[key] * weights[key] for key in scores)

        # Professional tier classification (McKinsey/BCG standard)
        if final_score >= 80:
            tier = "Excellent"
            tier_description = "Top Quartile Performance"
        elif final_score >= 60:
            tier = "Good"
            tier_description = "Above Average Performance"
        elif final_score >= 40:
            tier = "Fair"
            tier_description = "Below Average Performance"
        else:
            tier = "Poor"
            tier_description = "Bottom Quartile Performance"

        # Generate professional recommendations for executives
        recommendations = []

        if scores['delivery'] < 40:
            recommendations.append("🚨 DELIVERY CRITICAL: Immediate technical review required - poor inbox placement impacting all downstream metrics")
        elif scores['delivery'] < 60:
            recommendations.append("⚠️ DELIVERY OPTIMIZATION: Review sender reputation and content to improve deliverability")

        if scores['engagement'] < 40:
            recommendations.append("🚨 ENGAGEMENT CRITICAL: Content and targeting strategy requires complete overhaul")
        elif scores['engagement'] < 60:
            recommendations.append("⚠️ ENGAGEMENT OPPORTUNITY: A/B test subject lines, send times, and content personalization")

        if scores['conversion'] < 40:
            recommendations.append("🚨 CONVERSION CRITICAL: Landing page and customer journey optimization is priority #1")
        elif scores['conversion'] < 60:
            recommendations.append("⚠️ CONVERSION OPTIMIZATION: Review offer relevance and purchase friction points")

        if scores['revenue'] < 40:
            recommendations.append("🚨 REVENUE EFFICIENCY: Customer value optimization or pricing strategy review needed")
        elif scores['revenue'] < 60:
            recommendations.append("⚠️ REVENUE OPPORTUNITY: Focus on upselling or higher-value customer segments")

        # Success recommendations
        if final_score >= 80:
            recommendations.append("🎯 SCALE SUCCESS: Allocate more budget to this high-performing journey")
            recommendations.append("� BEST PRACTICE: Document and replicate successful elements across other journeys")

        if not recommendations:
            recommendations.append("✅ SOLID PERFORMANCE: Continue current strategy with minor optimizations")

        return {
            'health_score': round(final_score, 1),
            'tier': tier,
            'tier_description': tier_description,
            'component_scores': scores,
            'recommendations': recommendations,
            'scoring_method': 'Empirical Bayes (Beta-Binomial) + Log(RPC) percentiles'
        }

    except Exception as e:
        # Fallback scoring for data quality issues
        return {
            'health_score': 50.0,
            'tier': 'Insufficient Data',
            'tier_description': 'Data Quality Issues',
            'component_scores': {'delivery': 50, 'engagement': 50, 'conversion': 50, 'revenue': 50},
            'recommendations': ['📊 DATA QUALITY: Improve data collection for accurate performance measurement'],
            'scoring_method': 'Fallback scoring due to data limitations'
        }


def calculate_campaign_health_score(df_campaign, all_campaigns_df=None):
    """
    Calculate a comprehensive Campaign Health Score (0-100) using Empirical Bayes methodology
    with small-sample corrections - adapted from journey health scoring for campaign analysis.

    Scoring Method: Empirical Bayes Shrinkage + Log-transformed Revenue Per Conversion
    - Uses Beta-Binomial shrinkage for conversion rates (handles small samples robustly)
    - Log-transforms Revenue Per Conversion to reduce outlier dominance
    - Applies statistical smoothing used by major tech companies (Meta, Google, Amazon)
    - Provides reliable rankings even with sparse data
    """
    try:
        # Initialize scores
        scores = {}

        # --- Data sufficiency guard ---
        # Avoid labeling very low-activity campaigns as 'Good' or 'Excellent'.
        # Heuristic thresholds (conservative defaults) - adjust as needed:
        # - min_sent: minimum total messages sent across the campaign
        # - min_conversions: minimum total conversions to consider revenue/conversion metrics meaningful
        # - min_days: minimum number of reporting days for the campaign
        min_sent = 10
        min_conversions = 3
        min_days = 3

        # Compute simple activity metrics for this campaign
        total_sent_c = df_campaign['Sent'].sum() if 'Sent' in df_campaign.columns else 0
        total_conversions_c = df_campaign['Selected Conversions'].sum() if 'Selected Conversions' in df_campaign.columns else (df_campaign['Unique Conversions'].sum() if 'Unique Conversions' in df_campaign.columns else 0)
        unique_days = df_campaign['Reporting Period Start Date'].nunique() if 'Reporting Period Start Date' in df_campaign.columns else len(df_campaign)

        if total_sent_c < min_sent or total_conversions_c < min_conversions or unique_days < min_days:
            # Return explicit Insufficient Data result so the UI can filter or flag these campaigns
            return {
                'health_score': 0.0,
                'tier': 'Insufficient Data',
                'tier_description': 'Insufficient activity to compute reliable score',
                'component_scores': {'delivery': 0, 'engagement': 0, 'conversion': 0, 'revenue': 0},
                'recommendations': [
                    'ℹ️ Insufficient data: Not enough volume or time to compute a reliable campaign health score',
                    '🔎 Consider increasing the lookback window or aggregating similar campaigns for stability'
                ],
                'scoring_method': 'Insufficient data guard (volume/time thresholds)'
            }

        # Get baseline data for percentile calculations (use all data if available)
        baseline_df = all_campaigns_df if all_campaigns_df is not None else df_campaign

        # === EMPIRICAL BAYES HELPER FUNCTIONS ===
        def estimate_beta_prior(successes_array, trials_array):
            """Estimate Beta prior parameters using method of moments from population data"""
            # Filter out invalid data
            valid_mask = (trials_array > 0) & (~np.isnan(successes_array)) & (~np.isnan(trials_array))
            if not valid_mask.any():
                return 1.0, 1.0  # Uniform prior fallback

            rates = successes_array[valid_mask] / trials_array[valid_mask]
            rates = rates[(rates >= 0) & (rates <= 1)]  # Valid rates only

            if len(rates) < 2:
                return 1.0, 1.0  # Uniform prior fallback

            mean_rate = np.mean(rates)
            var_rate = np.var(rates, ddof=1)

            # Ensure variance is positive and not too close to theoretical maximum
            if var_rate <= 0 or var_rate >= mean_rate * (1 - mean_rate):
                return 1.0, 1.0  # Uniform prior fallback

            # Method of moments: alpha = mean * (mean*(1-mean)/var - 1), beta = (1-mean) * (...)
            scale = mean_rate * (1 - mean_rate) / var_rate - 1.0
            alpha = max(0.1, mean_rate * scale)
            beta = max(0.1, (1 - mean_rate) * scale)

            return alpha, beta

        def beta_posterior_mean(successes, trials, alpha_prior, beta_prior):
            """Calculate posterior mean for Beta-Binomial model"""
            if trials <= 0:
                return 0.0
            return (successes + alpha_prior) / (trials + alpha_prior + beta_prior)

        # Helper function for percentile-based scoring (now using smoothed values)
        def calculate_percentile_score(value, baseline_values, reverse=False):
            """Convert a value to percentile score (0-100) using statistical ranking"""
            if len(baseline_values) == 0 or pd.isna(value):
                return 50  # Neutral score for missing data

            # Remove NaN values
            clean_values = baseline_values.dropna()
            if len(clean_values) == 0:
                return 50

            # Calculate percentile rank
            if reverse:
                # For metrics where lower is better (e.g., cost per conversion)
                percentile = (1 - (clean_values < value).mean()) * 100
            else:
                # For metrics where higher is better (standard case)
                percentile = (clean_values <= value).mean() * 100

            return min(max(percentile, 0), 100)  # Ensure 0-100 range

        # === PREPARE POPULATION DATA FOR EMPIRICAL BAYES ===

        # Collect campaign-level data for prior estimation
        campaign_groups = baseline_df.groupby('Campaign Name') if 'Campaign Name' in baseline_df.columns else [('current', baseline_df)]

        # Delivery rates (usually high success rate, less smoothing needed)
        delivery_rates = []
        delivery_totals = []
        for name, group in campaign_groups:
            if 'Delivery Rate' in group.columns:
                rate = group['Delivery Rate'].mean()
                if not pd.isna(rate):
                    delivery_rates.append(rate)
            elif 'Sent' in group.columns and 'Delivered' in group.columns:
                sent = group['Sent'].sum()
                delivered = group['Delivered'].sum()
                if sent > 0:
                    delivery_rates.append(delivered / sent)
                    delivery_totals.append(sent)

        # CTR data for Empirical Bayes
        ctr_clicks = []
        ctr_impressions = []
        for name, group in campaign_groups:
            if 'Unique Clicks' in group.columns and 'Unique Impressions' in group.columns:
                clicks = group['Unique Clicks'].sum()
                impressions = group['Unique Impressions'].sum()
                if impressions > 0:
                    ctr_clicks.append(clicks)
                    ctr_impressions.append(impressions)

        # Conversion data for Empirical Bayes
        conv_conversions = []
        conv_clicks = []
        for name, group in campaign_groups:
            if 'Unique Conversions' in group.columns and 'Unique Clicks' in group.columns:
                conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
                clicks = group['Unique Clicks'].sum()
                if clicks > 0:
                    conv_conversions.append(conversions)
                    conv_clicks.append(clicks)

        # Revenue Per Conversion data (for log-transformation)
        rpc_values = []
        for name, group in campaign_groups:
            if 'Revenue (SAR)' in group.columns and 'Unique Conversions' in group.columns:
                revenue = group['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in group.columns else group['Revenue (SAR)'].sum()
                conversions = group['Selected Conversions'].sum() if 'Selected Conversions' in group.columns else group['Unique Conversions'].sum()
                if conversions > 0:
                    rpc = revenue / conversions
                    if rpc > 0:  # Only positive RPC values
                        rpc_values.append(rpc)

        # Estimate priors
        ctr_alpha, ctr_beta = estimate_beta_prior(np.array(ctr_clicks), np.array(ctr_impressions))
        conv_alpha, conv_beta = estimate_beta_prior(np.array(conv_conversions), np.array(conv_clicks))

        # === CALCULATE COMPONENT SCORES WITH EMPIRICAL BAYES ===

        # 1. Delivery Performance Score (25% weight) - Less smoothing needed
        if 'Delivery Rate' in df_campaign.columns and df_campaign['Delivery Rate'].notna().any():
            delivery_rate = df_campaign['Delivery Rate'].mean()
        elif 'Sent' in df_campaign.columns and 'Delivered' in df_campaign.columns:
            total_sent = df_campaign['Sent'].sum()
            total_delivered = df_campaign['Delivered'].sum()
            delivery_rate = (total_delivered / total_sent) if total_sent > 0 else 0
        else:
            delivery_rate = 0.8  # Industry average 80%

        baseline_delivery = pd.Series(delivery_rates) if delivery_rates else pd.Series([delivery_rate])
        scores['delivery'] = calculate_percentile_score(delivery_rate, baseline_delivery)

        # 2. Engagement Performance Score (25% weight) - WITH EMPIRICAL BAYES SMOOTHING
        # FIXED: Always use aggregate CTR calculation instead of daily average CTR for proper scoring
        if 'Unique Clicks' in df_campaign.columns and 'Unique Impressions' in df_campaign.columns:
            total_clicks = df_campaign['Unique Clicks'].sum()
            total_impressions = df_campaign['Unique Impressions'].sum()
            # Apply Empirical Bayes smoothing to aggregate CTR (more reliable than daily averages)
            smoothed_ctr = beta_posterior_mean(total_clicks, total_impressions, ctr_alpha, ctr_beta)
        else:
            smoothed_ctr = 0.02  # Industry average 2%

        # Create baseline of smoothed CTRs for fair comparison
        baseline_ctr_smoothed = []
        for clicks, impressions in zip(ctr_clicks, ctr_impressions):
            baseline_ctr_smoothed.append(beta_posterior_mean(clicks, impressions, ctr_alpha, ctr_beta))
        baseline_ctr = pd.Series(baseline_ctr_smoothed) if baseline_ctr_smoothed else pd.Series([smoothed_ctr])

        scores['engagement'] = calculate_percentile_score(smoothed_ctr, baseline_ctr)

        # 3. Conversion Performance Score (30% weight) - WITH EMPIRICAL BAYES SMOOTHING
        # Use the Conversion Rate column when available (calculated in clean_data as decimal: conversions/clicks)
        if 'Conversion Rate' in df_campaign.columns and df_campaign['Conversion Rate'].notna().any():
            # Conversion Rate is already a decimal from clean_data() (e.g., 0.05 = 5%)
            conv_rate = df_campaign['Conversion Rate'].mean()
            # Create baseline from all campaigns' conversion rates
            if 'Conversion Rate' in baseline_df.columns:
                baseline_conv_values = []
                for name, group in baseline_df.groupby('Campaign Name'):
                    campaign_conv_rate = group['Conversion Rate'].mean()
                    if not pd.isna(campaign_conv_rate):
                        baseline_conv_values.append(campaign_conv_rate)
                baseline_conv = pd.Series(baseline_conv_values)
            else:
                baseline_conv = pd.Series([conv_rate])
        elif 'Unique Conversions' in df_campaign.columns and 'Unique Clicks' in df_campaign.columns:
            # Fallback: manual calculation (but this may not be reliable for some data)
            total_conversions = df_campaign['Selected Conversions'].sum() if 'Selected Conversions' in df_campaign.columns else df_campaign['Unique Conversions'].sum()
            total_clicks = df_campaign['Unique Clicks'].sum()
            # Apply Empirical Bayes smoothing for manual calculations
            conv_rate = beta_posterior_mean(total_conversions, total_clicks, conv_alpha, conv_beta)

            # Create baseline of smoothed conversion rates
            baseline_conv_smoothed = []
            for conversions, clicks in zip(conv_conversions, conv_clicks):
                baseline_conv_smoothed.append(beta_posterior_mean(conversions, clicks, conv_alpha, conv_beta))
            baseline_conv = pd.Series(baseline_conv_smoothed) if baseline_conv_smoothed else pd.Series([conv_rate])
        else:
            conv_rate = 0.05  # Industry average 5%
            baseline_conv = pd.Series([conv_rate])

        scores['conversion'] = calculate_percentile_score(conv_rate, baseline_conv)

        # 4. Revenue Efficiency Score (20% weight) - LOG-TRANSFORMED RPC
        if 'Revenue (SAR)' in df_campaign.columns and 'Unique Conversions' in df_campaign.columns:
            total_revenue = df_campaign['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in df_campaign.columns else df_campaign['Revenue (SAR)'].sum()
            total_conversions = df_campaign['Selected Conversions'].sum() if 'Selected Conversions' in df_campaign.columns else df_campaign['Unique Conversions'].sum()
            revenue_per_conversion = (total_revenue / total_conversions) if total_conversions > 0 else 0

            # Log-transform for better distribution (reduces outlier dominance)
            log_rpc = np.log1p(revenue_per_conversion)  # log(1 + x) handles zero values

            # Create baseline of log-transformed RPCs
            baseline_log_rpc = [np.log1p(rpc) for rpc in rpc_values] if rpc_values else [log_rpc]
            baseline_log_rpc = pd.Series(baseline_log_rpc)

            scores['revenue'] = calculate_percentile_score(log_rpc, baseline_log_rpc)
        else:
            scores['revenue'] = 50  # Neutral score if no revenue data

        # Calculate weighted final score using enterprise-optimized weights
        # Increased revenue weight slightly to improve sensitivity to business outcomes
        weights = {'delivery': 0.20, 'engagement': 0.25, 'conversion': 0.30, 'revenue': 0.25}
        final_score = sum(scores[key] * weights[key] for key in scores)

        # Professional tier classification (McKinsey/BCG standard)
        if final_score >= 80:
            tier = "Excellent"
            tier_description = "Top Quartile Performance"
        elif final_score >= 60:
            tier = "Good"
            tier_description = "Above Average Performance"
        elif final_score >= 40:
            tier = "Fair"
            tier_description = "Below Average Performance"
        else:
            tier = "Poor"
            tier_description = "Bottom Quartile Performance"

        # Generate professional recommendations for executives
        recommendations = []

        if scores['delivery'] < 40:
            recommendations.append("🚨 DELIVERY CRITICAL: Immediate technical review required - poor inbox placement impacting all downstream metrics")
        elif scores['delivery'] < 60:
            recommendations.append("⚠️ DELIVERY OPTIMIZATION: Review sender reputation and content to improve deliverability")

        if scores['engagement'] < 40:
            recommendations.append("🚨 ENGAGEMENT CRITICAL: Content and targeting strategy requires complete overhaul")
        elif scores['engagement'] < 60:
            recommendations.append("⚠️ ENGAGEMENT OPPORTUNITY: A/B test subject lines, send times, and content personalization")

        if scores['conversion'] < 40:
            recommendations.append("🚨 CONVERSION CRITICAL: Landing page and customer journey optimization is priority #1")
        elif scores['conversion'] < 60:
            recommendations.append("⚠️ CONVERSION OPTIMIZATION: Review offer relevance and purchase friction points")

        if scores['revenue'] < 40:
            recommendations.append("🚨 REVENUE EFFICIENCY: Customer value optimization or pricing strategy review needed")
        elif scores['revenue'] < 60:
            recommendations.append("⚠️ REVENUE OPPORTUNITY: Focus on upselling or higher-value customer segments")

        # Success recommendations
        if final_score >= 80:
            recommendations.append("🎯 SCALE SUCCESS: Allocate more budget to this high-performing campaign")
            recommendations.append("📈 BEST PRACTICE: Document and replicate successful elements across other campaigns")

        if not recommendations:
            recommendations.append("✅ SOLID PERFORMANCE: Continue current strategy with minor optimizations")

        return {
            'health_score': round(final_score, 1),
            'tier': tier,
            'tier_description': tier_description,
            'component_scores': scores,
            'recommendations': recommendations,
            'scoring_method': 'Empirical Bayes (Beta-Binomial) + Log(RPC) percentiles'
        }

    except Exception as e:
        # Fallback scoring for data quality issues
        return {
            'health_score': 50.0,
            'tier': 'Insufficient Data',
            'tier_description': 'Data Quality Issues',
            'component_scores': {'delivery': 50, 'engagement': 50, 'conversion': 50, 'revenue': 50},
            'recommendations': ['📊 DATA QUALITY: Improve data collection for accurate performance measurement'],
            'scoring_method': 'Fallback scoring due to data limitations'
        }
