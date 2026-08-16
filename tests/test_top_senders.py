"""Top senders ranking: no rows dropped, no programs collapsed into one bucket."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
from analysis import top_senders


def _df():
    return pd.DataFrame({
        # 'nan'/'' mimic clean_data()'s astype(str) of missing names (Arrow cast).
        'Campaign Name': ['Msg A', 'Msg B', 'Flash Sale', 'Flash Sale', 'nan'],
        'Journey Name': ['Winback', 'Winback', 'nan', np.nan, ''],
        'Type of Campaign': ['Journey', 'Journey', 'One-Time', 'One-Time', 'One-Time'],
        'Channel': ['WhatsApp', 'WhatsApp', 'WhatsApp', 'Email', 'WhatsApp'],
        'Sent': [300, 200, 400, 50, 7],
        'Delivered': [290, 190, 380, 48, 7],
        'Unique Clicks': [30, 20, 40, 5, 1],
        'Unique Conversions': [3, 2, 8, 1, 0],
        'Revenue (SAR)': [100.0, 50.0, 900.0, 20.0, 0.0],
    })


def test_top_senders():
    df = _df()
    out, rev_col, conv_col = top_senders(df)

    assert out['Sent'].sum() == df['Sent'].sum(), "rows lost or double-counted"
    assert out['Program'].notna().all()
    # Journey rows collapse under the journey name, not per-message.
    winback = out[out['Program'] == 'Winback']
    assert len(winback) == 1 and winback['Sent'].iloc[0] == 500
    # A one-time campaign stays split by channel.
    assert set(out[out['Program'] == 'Flash Sale']['Channel']) == {'WhatsApp', 'Email'}
    # Ranked by volume: the journey outsends the biggest single campaign.
    assert out.iloc[0]['Program'] == 'Winback'
    # Missing names don't merge into a NaN bucket that tops the ranking.
    assert '(unnamed)' in set(out['Program'])
    assert rev_col == 'Revenue (SAR)' and conv_col == 'Unique Conversions'


if __name__ == '__main__':
    test_top_senders()
    print("ok")
