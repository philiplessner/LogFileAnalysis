import os
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from geo import get_ips, ips2geo, response2df

if __name__ == '__main__':
    load_dotenv()
    data_dir = Path(os.environ['DATA_FILE_DIR'])
    path2robots = data_dir / 'log_robots.csv'
    df_robots = pd.read_csv(path2robots)
    ips = get_ips(df_robots)
    geo_info = ips2geo(ips)
    df_robots= response2df(geo_info, df_robots)
    df_robots['Agent_Type'] = 'R'
    df_robots.to_csv(data_dir / 'log_robots_geo.csv', index=False)
