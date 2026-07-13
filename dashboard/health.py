"""Health-score calculations for journeys and campaigns.

Method: percentile ranking *within the current view* (relative scoring), with
Beta-Binomial (Empirical Bayes) smoothing on funnel rates so low-volume
entities shrink toward the portfolio average instead of dominating the tails.

Components & weights:
    revenue    0.35  log1p(total revenue) percentile — volume-aware business
                     impact, so a 26-conversion campaign can't outrank the
                     portfolio's revenue drivers on efficiency ratios alone
    conversion 0.25  click-through conversions ÷ unique clicks (EB-smoothed;
                     a valid binomial — click-through converters are a subset
                     of clickers, unlike total-attribution conversions)
    engagement 0.20  unique clicks ÷ unique impressions (EB-smoothed)
    delivery   0.20  delivered ÷ sent (aggregate, volume-weighted)

Scores are percentiles of THIS upload/filter: "80" means "better than 80% of
the entities currently in view", not an absolute industry benchmark.
"""
import numpy as np
import pandas as pd

WEIGHTS = {'delivery': 0.20, 'engagement': 0.20, 'conversion': 0.25, 'revenue': 0.35}

# Below any of these the score would be mostly prior/noise — the entity is
# reported as 'Insufficient Data' instead of ranked. Tune per client volume.
MIN_SENT = 100
MIN_CONVERSIONS = 5
MIN_DAYS = 3

_TIERS = [(80, "Excellent", "Top of this portfolio"),
          (60, "Good", "Above portfolio average"),
          (40, "Fair", "Below portfolio average"),
          (0, "Poor", "Bottom of this portfolio")]


def _cvr_numerator_col(df):
    """Click-through conversions when available (valid successes⊆trials binomial);
    falls back to the selected/total conversions column."""
    if 'Unique Click-Through Conversions' in df.columns:
        return 'Unique Click-Through Conversions'
    return 'Selected Conversions' if 'Selected Conversions' in df.columns else 'Unique Conversions'


def _estimate_beta_prior(successes, trials):
    """Method-of-moments Beta prior from per-entity (successes, trials) arrays."""
    successes, trials = np.asarray(successes, dtype=float), np.asarray(trials, dtype=float)
    valid = (trials > 0) & ~np.isnan(successes) & ~np.isnan(trials)
    if not valid.any():
        return 1.0, 1.0
    rates = successes[valid] / trials[valid]
    rates = rates[(rates >= 0) & (rates <= 1)]
    if len(rates) < 2:
        return 1.0, 1.0
    mean, var = np.mean(rates), np.var(rates, ddof=1)
    if var <= 0 or var >= mean * (1 - mean):
        return 1.0, 1.0
    scale = mean * (1 - mean) / var - 1.0
    return max(0.1, mean * scale), max(0.1, (1 - mean) * scale)


def _posterior_mean(successes, trials, alpha, beta):
    if trials <= 0:
        return 0.0
    return (successes + alpha) / (trials + alpha + beta)


def _percentile(value, baseline):
    """Percentile rank (0-100) of value within a baseline Series."""
    clean = pd.Series(baseline).dropna()
    if len(clean) == 0 or pd.isna(value):
        return 50.0
    return float(min(max((clean <= value).mean() * 100, 0), 100))


def _sums(group, ct_col, rev_col):
    """Aggregate funnel counts for one entity."""
    def s(col):
        return group[col].sum() if col in group.columns else 0
    return {
        'sent': s('Sent'), 'delivered': s('Delivered'),
        'impressions': s('Unique Impressions'), 'clicks': s('Unique Clicks'),
        'ct_conv': s(ct_col), 'revenue': s(rev_col),
    }


def _insufficient(entity_label):
    return {
        'health_score': 0.0,
        'tier': 'Insufficient Data',
        'tier_description': 'Insufficient activity to compute a reliable score',
        'component_scores': {'delivery': 0, 'engagement': 0, 'conversion': 0, 'revenue': 0},
        'component_contributions': {},
        'recommendations': [
            f'ℹ️ Insufficient data: fewer than {MIN_SENT} sends, {MIN_CONVERSIONS} conversions, '
            f'or {MIN_DAYS} reporting days — not enough volume to rank this {entity_label} reliably',
            '🔎 Widen the date range or let it accumulate more volume before acting on its score',
        ],
        'scoring_method': 'Insufficient data guard (volume/time thresholds)',
    }


def _calculate_health_score(df_entity, baseline_df, entity_col, entity_label):
    """Shared scorer behind calculate_{campaign,journey}_health_score."""
    try:
        # --- Data sufficiency guard (on total activity, not click-through) ---
        total_sent = df_entity['Sent'].sum() if 'Sent' in df_entity.columns else 0
        total_conv = (df_entity['Selected Conversions'].sum() if 'Selected Conversions' in df_entity.columns
                      else df_entity['Unique Conversions'].sum() if 'Unique Conversions' in df_entity.columns else 0)
        unique_days = (df_entity['Reporting Period Start Date'].nunique()
                       if 'Reporting Period Start Date' in df_entity.columns else len(df_entity))
        if total_sent < MIN_SENT or total_conv < MIN_CONVERSIONS or unique_days < MIN_DAYS:
            return _insufficient(entity_label)

        baseline_df = baseline_df if baseline_df is not None else df_entity
        ct_col = _cvr_numerator_col(baseline_df)
        rev_col = 'Selected Revenue (SAR)' if 'Selected Revenue (SAR)' in baseline_df.columns else 'Revenue (SAR)'

        # --- Per-entity population sums (baseline for priors and percentiles) ---
        # ponytail: O(entities × rows) when pages loop over every entity; results
        # are @st.cache_data'd by callers — precompute a shared baseline if slow.
        if entity_col in baseline_df.columns:
            pop = [_sums(g, ct_col, rev_col) for _, g in baseline_df.groupby(entity_col)]
        else:
            pop = [_sums(baseline_df, ct_col, rev_col)]

        ctr_alpha, ctr_beta = _estimate_beta_prior(
            [p['clicks'] for p in pop], [p['impressions'] for p in pop])
        conv_alpha, conv_beta = _estimate_beta_prior(
            [p['ct_conv'] for p in pop], [p['clicks'] for p in pop])

        me = _sums(df_entity, ct_col, rev_col)
        scores = {}

        # 1. Delivery: aggregate delivered/sent vs population
        delivery_rate = me['delivered'] / me['sent'] if me['sent'] > 0 else 0
        baseline_delivery = [p['delivered'] / p['sent'] for p in pop if p['sent'] > 0]
        scores['delivery'] = _percentile(delivery_rate, baseline_delivery)

        # 2. Engagement: EB-smoothed CTR vs equally-smoothed population
        smoothed_ctr = _posterior_mean(me['clicks'], me['impressions'], ctr_alpha, ctr_beta)
        baseline_ctr = [_posterior_mean(p['clicks'], p['impressions'], ctr_alpha, ctr_beta)
                        for p in pop if p['impressions'] > 0]
        scores['engagement'] = _percentile(smoothed_ctr, baseline_ctr)

        # 3. Conversion: EB-smoothed click-through CVR vs equally-smoothed population
        smoothed_cvr = _posterior_mean(me['ct_conv'], me['clicks'], conv_alpha, conv_beta)
        baseline_cvr = [_posterior_mean(p['ct_conv'], p['clicks'], conv_alpha, conv_beta)
                        for p in pop if p['clicks'] > 0]
        scores['conversion'] = _percentile(smoothed_cvr, baseline_cvr)

        # 4. Revenue impact: log-scaled total revenue vs population (volume-aware)
        scores['revenue'] = _percentile(np.log1p(me['revenue']),
                                        [np.log1p(p['revenue']) for p in pop])

        final_score = sum(scores[k] * WEIGHTS[k] for k in scores)
        for threshold, tier, tier_description in _TIERS:
            if final_score >= threshold:
                break

        # --- Actionable output: what to do, per weak component ---
        recommendations = []
        if scores['delivery'] < 40:
            recommendations.append("🚨 DELIVERY CRITICAL: Immediate technical review — poor delivery caps every downstream metric")
        elif scores['delivery'] < 60:
            recommendations.append("⚠️ DELIVERY: Review sender reputation, contact hygiene, and channel availability")
        if scores['engagement'] < 40:
            recommendations.append("🚨 ENGAGEMENT CRITICAL: Content and targeting need an overhaul — audience isn't clicking")
        elif scores['engagement'] < 60:
            recommendations.append("⚠️ ENGAGEMENT: A/B test subject lines, send times, and personalization")
        if scores['conversion'] < 40:
            recommendations.append("🚨 CONVERSION CRITICAL: Clicks aren't converting — review landing page and offer")
        elif scores['conversion'] < 60:
            recommendations.append("⚠️ CONVERSION: Review offer relevance and purchase friction after the click")
        if scores['revenue'] < 40:
            recommendations.append(f"🚨 REVENUE IMPACT: This {entity_label} contributes little revenue — scale it up or retire it")
        elif scores['revenue'] < 60:
            recommendations.append("⚠️ REVENUE: Below the portfolio's revenue mid-line — grow volume or target higher-value segments")
        if final_score >= 80:
            recommendations.append(f"🎯 SCALE SUCCESS: Allocate more budget to this high-performing {entity_label}")
            recommendations.append(f"📈 BEST PRACTICE: Document and replicate its elements across other {entity_label}s")
        if not recommendations:
            recommendations.append("✅ SOLID PERFORMANCE: Continue current strategy with minor optimizations")

        return {
            'health_score': round(final_score, 1),
            'tier': tier,
            'tier_description': tier_description,
            'component_scores': scores,
            'component_contributions': {
                k: {'score': scores[k], 'weight': WEIGHTS[k], 'contribution': scores[k] * WEIGHTS[k]}
                for k in scores
            },
            'recommendations': recommendations,
            'scoring_method': 'Portfolio percentiles: log-revenue impact + EB-smoothed funnel rates',
        }
    except Exception:
        return {
            'health_score': 50.0,
            'tier': 'Insufficient Data',
            'tier_description': 'Data Quality Issues',
            'component_scores': {'delivery': 50, 'engagement': 50, 'conversion': 50, 'revenue': 50},
            'component_contributions': {},
            'recommendations': ['📊 DATA QUALITY: Improve data collection for accurate performance measurement'],
            'scoring_method': 'Fallback scoring due to data limitations',
        }


def calculate_journey_health_score(df_journey, all_journeys_df=None):
    """Journey Health Score (0-100): percentile rank within the current view."""
    return _calculate_health_score(df_journey, all_journeys_df, 'Journey Name', 'journey')


def calculate_campaign_health_score(df_campaign, all_campaigns_df=None):
    """Campaign Health Score (0-100): percentile rank within the current view."""
    return _calculate_health_score(df_campaign, all_campaigns_df, 'Campaign Name', 'campaign')
