import os
import re
import shutil
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from geo import get_ips, ips2geo, response2df


def logfile2df(log_file: Path) -> pd.DataFrame:
    data = {
        'ip_address': [],
        'datetime': [],
        'request_type': [],
        'endpoint': [],
        'http_version': [],
        'status_code': [],
        'user_agent': []
    }
    # Regular expression to parse the access log
    # Format: IP - - [date/time +timezone] "request" status size referrer "user-agent" ...
    pattern = r'(\d+\.\d+\.\d+\.\d+)\s+-\s+-\s+\[([^\]]+)\]\s+"([^"]+)"\s+(\d{3})\s+\d+\s+"-"\s+"([^"]+)"'
    request_pattern = r'^(GET|POST)\s+(\S+)\s+(HTTP/\d\.\d)$'
    # Read and parse the log file
    with open(log_file, 'r') as f:
        for line in f:
            match = re.search(pattern, line)
            if match:
                ip = match.group(1)
                datetime_str = match.group(2)
                request = match.group(3)
                status_code = match.group(4)
                user_agent = match.group(5)

                request_match = re.match(request_pattern, request.strip())
                if request_match:
                    request_type = request_match.group(1)
                    endpoint = request_match.group(2)
                    http_version = request_match.group(3)
                else:
                    request_type = None
                    endpoint = None
                    http_version = None

                data['ip_address'].append(ip)
                data['datetime'].append(datetime_str)
                data['request_type'].append(request_type)
                data['endpoint'].append(endpoint)
                data['http_version'].append(http_version)
                data['status_code'].append(status_code)
                data['user_agent'].append(user_agent)
    # Create DataFrame
    df = pd.DataFrame(data)
    # Convert datetime column to proper datetime format
    df['datetime'] = pd.to_datetime(df['datetime'], format='%d/%b/%Y:%H:%M:%S %z')
    return df


def new_entries(path2log: Path, path2csv: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    df = logfile2df(path2log)
    df_current = pd.read_csv(path2csv, parse_dates=['datetime'])
    max_date = df_current['datetime'].max()
    return df_current, df[df['datetime'] > max_date]


def filter_df(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Filter for robots.txt requests with Google in user agent
    mask = (df['endpoint'].fillna('').str.contains('robots.txt', case=False, na=False)) | \
            (df['user_agent'].fillna('').str.contains('Google', case=False, na=False))

    # Return copies to avoid SettingWithCopyWarning when modifying downstream
    df_filtered = df[mask].copy()
    df = df[~mask].copy()
    return df, df_filtered


if __name__ == "__main__":
    # Get the paths
    load_dotenv()
    data_dir = Path(os.getenv('DATA_FILE_DIR'))
    log_file = Path(os.getenv('LOG_FILE_DIR'), os.getenv('LOG_FILE')) 
    path2raw = data_dir / 'log_raw.csv'

    # Backup current csv files
    shutil.copy(data_dir / 'log_clean.csv', data_dir / 'log_clean.csv.bkp')
    shutil.copy(data_dir / 'log_robots.csv', data_dir / 'log_robots.csv.bkp')
    shutil.copy(data_dir / 'log_raw.csv', data_dir / 'log_raw.csv.bkp')

    # Get the get the current and new entries
    df_current, df_new = new_entries(log_file, path2raw)

    # Filter out robots
    df_clean, df_robots = filter_df(df_new)

    # Get the geo data and append geo columns in dataframe
    ips = get_ips(df_clean)
    geo_info = ips2geo(ips)
    df_clean = response2df(geo_info, df_clean)

    # Combine the new data with the current data
    df_clean_current = pd.read_csv(data_dir / 'log_clean.csv', parse_dates=['datetime'])
    df_clean_combined = pd.concat([df_clean_current, df_clean], ignore_index=True)
    df_robots_current = pd.read_csv(data_dir / 'log_robots.csv', parse_dates=['datetime'] )
    df_robots_combined = pd.concat([df_robots_current, df_robots], ignore_index=True)
    df_raw_combined = pd.concat([df_current, df_new],  ignore_index=True)

    # Write to csv
    df_raw_combined.to_csv(data_dir / 'log_raw.csv', index=False)
    df_robots_combined.to_csv(data_dir / 'log_robots.csv', index=False)
    df_clean_combined.to_csv(data_dir / "log_clean.csv", index=False)

