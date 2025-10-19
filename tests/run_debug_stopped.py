import pandas as pd
from debug_stopped_journeys import debug_stopped_detection

p = 'tests/Daily Q2_Q3.csv'
df = pd.read_csv(p)

# normalize date column
if 'Reporting Period Start Date' in df.columns:
    df['date'] = pd.to_datetime(df['Reporting Period Start Date'])
elif 'Day' in df.columns:
    df['date'] = pd.to_datetime(df['Day'])
else:
    raise SystemExit('No date column')

# pick a few journeys to test
journeys = df['Journey Name'].dropna().unique()
print('Found journeys:', len(journeys))

# choose up to 5 sample journeys (largest by rows)
journey_counts = df[df['Journey Name'].notna()].groupby('Journey Name').size().sort_values(ascending=False)
samples = journey_counts.head(5).index.tolist()
print('Samples to test:', samples)

for j in samples:
    debug_stopped_detection(df, j)
    print('\n' + '='*80 + '\n')
