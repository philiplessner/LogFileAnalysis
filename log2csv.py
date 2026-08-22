import logging
import os
import re
import sqlite3
from contextlib import closing
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
    pattern = r'(\d+\.\d+\.\d+\.\d+)\s+-\s+-\s+\[([^\]]+)\]\s+"([^"]+)"\s+(\d{3})\s+\d+\s+"[^"]*"\s+"([^"]+)"'
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


def new_entries(
    path2log: Path,
    database: Path | sqlite3.Connection,
) -> pd.DataFrame:
    df = logfile2df(path2log)
    owns_connection = not isinstance(database, sqlite3.Connection)
    db = sqlite3.connect(database) if owns_connection else database
    latest_datetime = db.execute("SELECT MAX(datetime) FROM logs").fetchone()[0]
    max_date = pd.to_datetime(latest_datetime, utc=True)
    if owns_connection:
        db.close()
    return df[df['datetime'] > max_date]


def filter_df(df: pd.DataFrame) -> pd.DataFrame:
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
    df_robots= df[mask].copy()
    df_human = df[~mask].copy()
    df_human['Agent_Type'] = 'H'
    df_robots['Agent_Type'] = 'R'
    df_combined = pd.concat([df_human, df_robots], ignore_index=True).sort_values(by='datetime')
    return df_combined

def remove_NULL(df: pd.DataFrame) -> pd.DataFrame:
    # Remove rows where endpoint is NULL/NaN before writing to CSV or DB
    before_count = len(df)
    df = df[~df['endpoint'].isna()].copy()
    after_count = len(df)
    if before_count != after_count:
        logger.info(
            "Dropped %d rows with NULL endpoint (from %d to %d)",
            before_count - after_count,
            before_count,
            after_count,
        )
    return df

def main(log_file: Path, path2db: Path) -> None:
    # Get the get the new raw entries
    df_new = new_entries(log_file, path2db)

    # Filter for robots and human user agents
    df_combined = filter_df(df_new)

    # Get the geo data and append geo columns in dataframe
    ips = get_ips(df_combined)
    geo_info = ips2geo(ips)
    df_combined = response2df(geo_info, df_combined)

    # Remove any rows with NULL/NAN in endpoint column
    df_combined = remove_NULL(df_combined)

    # Append the data to logs.db

    with closing(sqlite3.connect(path2db)) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY,
                ip_address TEXT,
                datetime TIMESTAMP,
                request_type TEXT,
                endpoint TEXT,
                http_version TEXT,
                status_code INTEGER,
                user_agent TEXT,
                Agent_Type TEXT,
                country TEXT,
                countryCode TEXT,
                region TEXT,
                regionName TEXT,
                city TEXT,
                zip TEXT,
                lat REAL,
                lon REAL,
                timezone TEXT
            )
        """)

        df_combined.to_sql(
            "logs",
            conn,
            if_exists="append",
            index=False,
        )
        conn.commit()

if __name__ == "__main__":
    # Get the paths
    if (str(Path.cwd()) == '/app'):  # Running in Docker Container
        data_dir = Path('/app/data.philiplessner.com')
        log_file = Path('/app/data.philiplessner.com/www.philiplessner.com.access.log')
    else:
        load_dotenv()
        data_dir = Path(os.environ['DATA_FILE_DIR'])
        log_file = Path(os.environ['LOG_FILE_DIR'], os.environ['LOG_FILE'])
    path2db = data_dir / 'logs.db'

    logging.basicConfig(
        filename=data_dir / 'processed.log',
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s',
        encoding='utf-8',
    )

    logger.info("Data directory: %s", data_dir)
    logger.info("Source log file: %s", log_file)

    main(log_file, path2db)