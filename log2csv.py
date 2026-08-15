import logging
import os
import re
import shutil
import sqlite3
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from geo import get_ips, ips2geo, response2df


logger = logging.getLogger(__name__)


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
    BOT_USER_AGENT_PATTERN = (
        r'bot|crawl|spider|slurp|scrapy|headlesschrome|censys|'
        r'internet[-_ ]?measurement|panscient|turnitin|siteradar|'
        r'facebookexternalhit|meta-(?:externalagent|webindexer)|'
        r'googleassociationservice|google-site-verification|y!j-asr|'
        r'go-http-client|python[-_/ ]?(?:requests|urllib)|curl/|wget/|'
        r'libwww|aiohttp|httpx|okhttp|apache-httpclient|node-fetch|axios|'
        r'postmanruntime|powershell|selenium|playwright|puppeteer|phantomjs|'
        r'crusader-worker|vuln[_ -]?scanner|rust[_ -]?sniffer|masscan|zgrab|'
        r'nmap|nikto|sqlmap|nuclei|chrome privacy preserving prefetch proxy|'
        r'ui-homepage-check|^git/'
    )

    BROWSER_USER_AGENT_PATTERN = (
        r'(?:Chrome|CriOS|Firefox|FxiOS|EdgA?|OPR|SamsungBrowser)/\d|'
        r'Version/\d.*Safari/\d'
    )
    user_agent = df['user_agent'].fillna('').str.strip()

    known_bot = (
        user_agent.eq('')
        | user_agent.eq('-')
        | user_agent.str.contains(
            BOT_USER_AGENT_PATTERN, case=False, regex=True, na=False
        )
    )
    browser_candidate = (
        user_agent.str.match(r'^Mozilla/5\.0', case=False, na=False)
        & user_agent.str.contains(
            BROWSER_USER_AGENT_PATTERN, case=False, regex=True, na=False
        )
    )

    # Keep only full browser user agents. Unknown/minimal clients are retained in
    # the filtered output along with known bots so they can still be inspected.
    mask = (
        df['endpoint'].fillna('').str.contains(
            'robots.txt', case=False, regex=False, na=False
        )
        | known_bot
        | ~browser_candidate
    )

    # Return copies to avoid SettingWithCopyWarning when modifying downstream
    df_filtered = df[mask].copy()
    df = df[~mask].copy()
    return df, df_filtered


if __name__ == "__main__":
    # Get the paths
    if (str(Path.cwd()) == '/app'):
        data_dir = Path('/app/data.philiplessner.com')
        log_file = Path('/app/data.philiplessner.com/www.philiplessner.com.access.log')
    else:
        load_dotenv()
        data_dir = Path(os.environ['DATA_FILE_DIR'])
        log_file = Path(os.environ['LOG_FILE_DIR'], os.environ['LOG_FILE'])
    logging.basicConfig(
        filename=data_dir / 'processed.log',
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        encoding='utf-8',
    )
    path2raw = data_dir / 'log_raw.csv'
    path2processed = data_dir / 'log_processed.csv'
    file_raw_exists = path2raw.exists()
    file_processed_exists = path2processed.exists()
    logger.info("Data directory: %s", data_dir)
    logger.info("Source log file: %s", log_file)

    # Backup current csv files
    if file_processed_exists: shutil.copy(path2processed, data_dir / 'log_processed.csv.bkp')
    if file_raw_exists: shutil.copy(path2raw, data_dir / 'log_raw.csv.bkp')

    # Get the get the new raw entries
    df_new = new_entries(log_file, path2raw)
    # Write the new raw entries
    df_new.to_csv(path2raw, mode='a', header=not file_processed_exists, index=False)

    # Filter for robots and human user agents
    df_human, df_robots = filter_df(df_new)
    df_human['Agent_Type'] = 'H'
    df_robots['Agent_Type'] = 'R'
    # Combine the dataframes
    df_combined = pd.concat([df_human, df_robots], ignore_index=True).sort_values(by='datetime')

    # Get the geo data and append geo columns in dataframe
    ips = get_ips(df_combined)
    geo_info = ips2geo(ips)
    df_combined = response2df(geo_info, df_combined)

    # Append the data to log_processed.csv
    df_combined.to_csv(path2processed, mode='a', header=not file_processed_exists, index=False)

    # Append the data to logs.db
    conn = sqlite3.connect(Path(data_dir, 'logs.db'))
    df_combined.to_sql("logs", conn, if_exists="append", index=False)
    conn.close()
