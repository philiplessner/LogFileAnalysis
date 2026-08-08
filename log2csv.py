import os
import re
import shutil
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from geo import get_ips, ips2geo, response2df


def logfile2df(log_file: Path) -> pd.DataFrame:
    data: dict[str, list[str | None]] = {
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


def new_entries(path2log: Path, path2csv: Path) -> pd.DataFrame:
    df = logfile2df(path2log)
    df_current = pd.read_csv(path2csv, parse_dates=['datetime'])
    max_date = df_current['datetime'].max()
    return df[df['datetime'] > max_date]


def filter_df(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    # Filter for robots.txt requests with Google in user agent
    mask = (df['endpoint'].fillna('').str.contains('robots.txt', case=False, na=False)) | \
            (df['user_agent'].fillna('').str.contains('Google', case=False, na=False)) | \
            (df['user_agent'].fillna('').str.contains('bot', case=False, na=False)) | \
            (df['user_agent'].fillna('').str.contains('scrapy', case=False, na=False))


    # Return copies to avoid SettingWithCopyWarning when modifying downstream
    df_filtered = df[mask].copy()
    df = df[~mask].copy()
    return df, df_filtered


if __name__ == "__main__":
    # Get the paths
    load_dotenv()
    data_dir = Path(os.environ['DATA_FILE_DIR'])
    log_file = Path(os.environ['LOG_FILE_DIR'], os.environ['LOG_FILE'])
    path2raw = data_dir / 'log_raw.csv'
    path2clean = data_dir / 'log_clean.csv'
    path2robots = data_dir / 'log_robots.csv'
    file_raw_exists = path2raw.exists()
    file_clean_exists = path2clean.exists()
    file_robots_exists = path2robots.exists()

    # Backup current csv files
    if file_clean_exists: shutil.copy(path2clean, data_dir / 'log_clean.csv.bkp')
    if file_robots_exists: shutil.copy(path2robots, data_dir / 'log_robots.csv.bkp')
    if file_raw_exists: shutil.copy(path2raw, data_dir / 'log_raw.csv.bkp')

    # Get the get the new entries
    df_new = new_entries(log_file, path2raw)

    # Filter out robots
    df_clean, df_robots = filter_df(df_new)

    # Get the geo data and append geo columns in dataframe
    ips = get_ips(df_clean)
    geo_info = ips2geo(ips)
    df_clean = response2df(geo_info, df_clean)

    # Combine the new data with the current data
    df_clean.to_csv(path2clean, mode='a', header=not file_clean_exists, index=False)
    df_robots.to_csv(path2robots, mode='a', header=not file_robots_exists, index=False)
    df_new.to_csv(path2raw, mode='a', header=not file_raw_exists, index=False)