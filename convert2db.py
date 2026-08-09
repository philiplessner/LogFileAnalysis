import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from geo import get_ips, ips2geo, response2df

if __name__ == '__main__':
    load_dotenv()
    data_dir = Path(os.environ['DATA_FILE_DIR'])
    path2robots = data_dir / 'log_robots.csv'
    path2clean = data_dir / 'log_clean.csv'
    # Get ip info for robots file
    df_robots = pd.read_csv(path2robots, parse_dates=['datetime'])
    ips = get_ips(df_robots)
    geo_info = ips2geo(ips)
    df_robots= response2df(geo_info, df_robots)
    # Mark robots records with "R"
    df_robots['Agent_Type'] = 'R'
    # Get clean file
    df_clean = pd.read_csv(path2clean, parse_dates=['datetime'])
    # Mark these records with "H" (for human)
    df_clean['Agent_Type'] = 'H'
    # Combine the dataframes and sort by date
    df_combined = pd.concat([df_robots, df_clean], ignore_index=True).sort_values(
        by='datetime'
    ).reset_index(drop=True)
    # Write to csv
    df_combined.to_csv(data_dir / 'log.csv', index=False)

