import pandas as pd
import sys
from pathlib import Path
import numpy as np
from scipy import stats

# Add project root to path
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app import clean_data, calculate_journey_health_score


def load_health_df(data_path):
    df = pd.read_csv(data_path)
    df = clean_data(df)

    journey_health_data = []
    unique_journeys = df['Journey Name'].dropna().unique()
    for journey in unique_journeys:
        if str(journey) != 'nan' and journey:
            journey_data = df[df['Journey Name'] == journey]
            health_info = calculate_journey_health_score(journey_data, df)
            journey_health_data.append({
                'Journey Name': journey,
                'Health Score': health_info['health_score'],
                'Tier': health_info['tier'],
                'Revenue (SAR)': journey_data['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in journey_data.columns else journey_data['Revenue (SAR)'].sum(),
                'Unique Conversions': journey_data['Unique Conversions'].sum() if 'Unique Conversions' in journey_data.columns else 0,
                'Delivery Rate': journey_data['Delivery Rate'].mean() if 'Delivery Rate' in journey_data.columns else np.nan,
                'CTR': journey_data['CTR'].mean() if 'CTR' in journey_data.columns else np.nan,
                'Conversion Rate': journey_data['Conversion Rate'].mean() if 'Conversion Rate' in journey_data.columns else np.nan
            })

    health_df = pd.DataFrame(journey_health_data)
    return df, health_df


def tier_from_score(score):
    if score >= 80:
        return 'Excellent'
    elif score >= 60:
        return 'Good'
    elif score >= 40:
        return 'Fair'
    else:
        return 'Poor'


def sanity_checks(health_df):
    issues = []
    # Health score bounds
    if not ((health_df['Health Score'] >= 0) & (health_df['Health Score'] <= 100)).all():
        issues.append('Health Score out of bounds (0-100)')

    # Tier alignment
    mismatch = health_df[health_df.apply(lambda r: r['Tier'] != tier_from_score(r['Health Score']), axis=1)]
    if not mismatch.empty:
        issues.append(f"Tier mismatch for {len(mismatch)} journeys")

    return issues, mismatch


def distribution_checks(health_df):
    counts = health_df['Tier'].value_counts().to_dict()
    total = len(health_df)
    pct_good_excellent = (counts.get('Excellent', 0) + counts.get('Good', 0)) / max(total, 1)
    warnings = []
    # Flag if > 75% in Excellent/Good (may be suspicious depending on org)
    if pct_good_excellent > 0.75:
        warnings.append(f'High concentration: {pct_good_excellent*100:.1f}% journeys are Excellent/Good')
    return counts, warnings


def correlation_checks(health_df):
    results = {}
    # Compute revenue per conversion
    health_df = health_df.copy()
    health_df['Revenue per Conversion'] = health_df.apply(lambda r: (r['Revenue (SAR)'] / r['Unique Conversions']) if r['Unique Conversions'] > 0 else 0, axis=1)

    for metric in ['Revenue per Conversion', 'Conversion Rate', 'CTR', 'Delivery Rate']:
        if metric in health_df.columns and health_df[metric].notna().sum() > 2:
            # Spearman correlation is robust to non-normal distributions
            rho, p = stats.spearmanr(health_df['Health Score'], health_df[metric], nan_policy='omit')
            results[metric] = {'spearman_rho': float(rho), 'p_value': float(p)}
        else:
            results[metric] = {'spearman_rho': None, 'p_value': None}
    return results


def sensitivity_test(df, health_df):
    # Pick the journey with median revenue (or top if none)
    if health_df.empty:
        return {'error': 'No journeys to test'}

    sorted_by_rev = health_df.sort_values('Revenue (SAR)')
    idx = len(sorted_by_rev) // 2
    target = sorted_by_rev.iloc[idx]['Journey Name']

    # Baseline score
    journey_data = df[df['Journey Name'] == target].copy()
    baseline = calculate_journey_health_score(journey_data, df)['health_score']

    # Increase revenue by 100% and recompute
    journey_data_up = journey_data.copy()
    if 'Revenue (SAR)' in journey_data_up.columns:
        journey_data_up['Revenue (SAR)'] = journey_data_up['Revenue (SAR)'] * 2
        up_score = calculate_journey_health_score(journey_data_up, df)['health_score']
    else:
        up_score = None

    # Decrease revenue by 90% and recompute
    journey_data_down = journey_data.copy()
    if 'Revenue (SAR)' in journey_data_down.columns:
        journey_data_down['Revenue (SAR)'] = journey_data_down['Revenue (SAR)'] * 0.1
        down_score = calculate_journey_health_score(journey_data_down, df)['health_score']
    else:
        down_score = None

    return {
        'target_journey': target,
        'baseline': baseline,
        'up_score': up_score,
        'down_score': down_score
    }


def run_all():
    data_file = project_root / 'data' / 'report-Daily.csv'
    print('Loading data from', data_file)
    df, health_df = load_health_df(data_file)

    print('\nSanity Checks:')
    issues, mismatch = sanity_checks(health_df)
    if not issues:
        print('  ✅ All sanity checks passed')
    else:
        print('  ❌ Issues found:')
        for i in issues:
            print('   -', i)
        if not mismatch.empty:
            print('\n  Sample mismatches (first 10):')
            print(mismatch[['Journey Name','Health Score','Tier']].head(10).to_string(index=False))

    print('\nDistribution Checks:')
    counts, warnings = distribution_checks(health_df)
    print('  Tier counts:', counts)
    if not warnings:
        print('  ✅ Distribution looks normal (no strong concentration)')
    else:
        for w in warnings:
            print('  ⚠️', w)

    print('\nCorrelation Checks (Spearman):')
    corr = correlation_checks(health_df)
    for metric, res in corr.items():
        rho = res['spearman_rho']
        p = res['p_value']
        if rho is None:
            print(f"  {metric}: insufficient data")
        else:
            sign = 'positive' if rho > 0 else 'negative' if rho < 0 else 'none'
            strong = abs(rho) >= 0.3
            print(f"  {metric}: rho={rho:.3f}, p={p:.3f} -> {sign}{' (strong)' if strong else ''}")

    print('\nSensitivity Test:')
    sens = sensitivity_test(df, health_df)
    if 'error' in sens:
        print('  ❌', sens['error'])
    else:
        print(f"  Target journey: {sens['target_journey']}")
        print(f"    Baseline score: {sens['baseline']}")
        print(f"    Score after doubling revenue: {sens['up_score']}")
        print(f"    Score after reducing revenue to 10%: {sens['down_score']}")
        if sens['up_score'] is not None and sens['down_score'] is not None:
            if sens['up_score'] > sens['baseline'] and sens['down_score'] < sens['baseline']:
                print('  ✅ Sensitivity behaves as expected (score increases/decreases with revenue)')
            else:
                print('  ⚠️ Sensitivity not behaving as expected; scoring may not be responsive to revenue changes')

    # Summary
    print('\nSummary:')
    failures = len(issues) + len(warnings)
    if failures == 0:
        print('  🎉 All automated validation checks passed')
    else:
        print(f'  ⚠️ {failures} issues/warnings detected — review above and consider tuning scoring weights or thresholds')


if __name__ == '__main__':
    run_all()
