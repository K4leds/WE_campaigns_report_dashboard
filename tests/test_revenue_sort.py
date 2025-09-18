import pandas as pd
import sys
from pathlib import Path

# Ensure project root is on sys.path so we can import app.py
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))
from app import clean_data

if __name__ == '__main__':
    data_file = project_root / 'data' / 'report-Daily.csv'
    df = pd.read_csv(data_file)
    df = clean_data(df)

    unique_journeys = df['Journey Name'].dropna().unique()
    journey_health_data = []
    for journey in unique_journeys:
        if str(journey) != 'nan' and journey:
            journey_data = df[df['Journey Name'] == journey]
            selected_rev = journey_data['Selected Revenue (SAR)'].sum() if 'Selected Revenue (SAR)' in journey_data.columns else journey_data['Revenue (SAR)'].sum()
            journey_health_data.append({
                'Journey Name': journey,
                'Health Score': 50.0,
                'Tier': 'Good',
                'Revenue (SAR)': selected_rev,
                'Impression-Through Revenue (SAR)': journey_data['Impression-Through Revenue (SAR)'].sum() if 'Impression-Through Revenue (SAR)' in journey_data.columns else 0,
                'Click-Through Revenue (SAR)': journey_data['Click-Through Revenue (SAR)'].sum() if 'Click-Through Revenue (SAR)' in journey_data.columns else 0,
                'Total Conversions': journey_data['Unique Conversions'].sum()
            })

    health_df = pd.DataFrame(journey_health_data)
    health_df_sorted = health_df.sort_values('Revenue (SAR)', ascending=False)
    print('Top 10 revenues (numeric sort):')
    print(health_df_sorted[['Journey Name','Revenue (SAR)']].head(10).to_string(index=False))
