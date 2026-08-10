import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from geo import get_ips, ips2geo, response2df
from log2csv import filter_df

if __name__ == '__main__':
    load_dotenv()
    data_dir = Path(os.environ['DATA_FILE_DIR'])
    path2raw = data_dir / 'log_raw2.csv'
    path2processed = data_dir / 'log_processed2.csv'

    # Filter the raw data
    df_raw = pd.read_csv(path2raw, parse_dates=['datetime'])
    df_human, df_robots = filter_df(df_raw)
    df_human['Agent_Type'] = 'H'
    df_robots['Agent_Type'] = 'R'
    df_combined = pd.concat([df_human, df_robots], ignore_index=True).sort_values(by='datetime').reset_index(drop=True)

    # Get ip info
    ips = get_ips(df_combined)
    geo_info = ips2geo(ips)
    df_combined= response2df(geo_info, df_combined)

    # Write to csv
    df_combined.to_csv(path2processed, index=False)

