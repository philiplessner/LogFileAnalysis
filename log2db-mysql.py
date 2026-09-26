"""Import new access-log entries into the MySQL logs table."""

import argparse
import logging
import re
from contextlib import closing
from pathlib import Path

import pandas as pd
import pymysql

from geo import get_ips, ips2geo, response2df
from log2db import filter_df, get_paths, remove_NULL
from mysql.migrate import COLUMNS, ROOT, SQL_MODE, mysql_settings

logger = logging.getLogger(__name__)
INSERT_COLUMNS = COLUMNS[1:]  # MySQL generates the id.


def logfile2df(log_file: Path) -> pd.DataFrame:
    # Match the same log format and request methods as log2db.py. Parse dates
    # directly into UTC, including files spanning a daylight-saving transition.
    pattern = re.compile(
        r'(\d+\.\d+\.\d+\.\d+)\s+-\s+-\s+\[([^\]]+)\]\s+"([^"]+)"'
        r'\s+(\d{3})\s+\d+\s+"[^"]*"\s+"([^"]+)"'
    )
    request_pattern = re.compile(r'^(GET|POST)\s+(\S+)\s+(HTTP/\d\.\d)$')
    rows = []
    with log_file.open(encoding='utf-8') as source:
        for line in source:
            match = pattern.search(line)
            if match:
                ip, timestamp, request, status, agent = match.groups()
                request_match = request_pattern.match(request.strip())
                method, endpoint, version = (
                    request_match.groups() if request_match else (None, None, None)
                )
                rows.append((ip, timestamp, method, endpoint, version, status, agent))
    df = pd.DataFrame(rows, columns=INSERT_COLUMNS[:7])
    df['datetime'] = pd.to_datetime(
        df['datetime'], format='%d/%b/%Y:%H:%M:%S %z', utc=True,
    )
    return df


def connect_database(env_file: Path = ROOT / '.mysql.env') -> pymysql.Connection:
    """Connect using the migration credentials and initialize the logs table."""
    db = pymysql.connect(**mysql_settings(env_file))
    try:
        with db.cursor() as cursor:
            cursor.execute("SET SESSION time_zone = '+00:00'")
            cursor.execute('SET SESSION sql_mode = %s', (SQL_MODE,))
            cursor.execute((ROOT / 'mysql/schema.sql').read_text(encoding='utf-8'))
        db.commit()
    except Exception:
        db.close()
        raise
    return db


def new_entries(path2log: Path, database: pymysql.Connection) -> pd.DataFrame:
    df = logfile2df(path2log)
    with database.cursor() as cursor:
        cursor.execute('SELECT MAX(datetime) FROM logs')
        latest_datetime = cursor.fetchone()[0]
    if latest_datetime is None:
        return df
    # DATETIME(6) is stored as UTC without a timezone in MySQL.
    max_date = pd.to_datetime(latest_datetime, utc=True)
    return df[df['datetime'] > max_date].copy()


def append2db(database: pymysql.Connection, df_combined: pd.DataFrame) -> None:
    """Append one atomic batch, preserving SQL NULLs and UTC timestamps."""
    if df_combined.empty:
        return
    df = df_combined.reindex(columns=INSERT_COLUMNS).copy()
    df['datetime'] = pd.to_datetime(df['datetime'], utc=True).dt.tz_localize(None)
    rows = []
    for record in df.itertuples(index=False, name=None):
        values = []
        for name, value in zip(INSERT_COLUMNS, record, strict=True):
            if pd.isna(value):
                value = None
            elif name == 'datetime':
                value = value.to_pydatetime()
            elif name == 'status_code':
                value = int(value)
            elif name in ('lat', 'lon'):
                value = float(value)
            values.append(value)
        rows.append(tuple(values))

    names = ', '.join(f'`{name}`' for name in INSERT_COLUMNS)
    placeholders = ', '.join(['%s'] * len(INSERT_COLUMNS))
    statement = f'INSERT INTO logs ({names}) VALUES ({placeholders})'
    try:
        with database.cursor() as cursor:
            # Keep every batch in the same transaction so failures cannot leave
            # a partially imported log file behind.
            for start in range(0, len(rows), 1000):
                cursor.executemany(statement, rows[start:start + 1000])
                if cursor.warning_count:
                    raise ValueError('MySQL returned warnings during insertion')
        database.commit()
    except Exception:
        database.rollback()
        raise
    logger.info('Appended %d rows to MySQL', len(rows))


def main(log_file: Path, database: pymysql.Connection) -> None:
    df_new = new_entries(log_file, database)
    # Drop unsupported requests before spending API calls on their locations.
    df_new = remove_NULL(df_new)
    if df_new.empty:
        logger.info('No new entries to import')
        return
    df_combined = filter_df(df_new)
    geo_info = ips2geo(get_ips(df_combined))
    df_combined = response2df(geo_info, df_combined)
    append2db(database, df_combined)


def cli() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.mysql.env',
                        help='MySQL credentials file (default: repository .mysql.env)')
    parser.add_argument('--log-file', type=Path,
                        help='Access log; defaults to the same paths as log2db.py')
    args = parser.parse_args()
    if args.log_file is None:
        data_dir, log_file = get_paths()
    else:
        log_file = args.log_file
        data_dir = log_file.parent
    logging.basicConfig(
        filename=data_dir / 'processed-mysql.log', level=logging.INFO,
        format='%(asctime)s %(levelname)s %(name)s: %(message)s', encoding='utf-8',
    )
    logger.info('Source log file: %s', log_file)
    with closing(connect_database(args.env_file)) as database:
        main(log_file, database)


if __name__ == '__main__':
    cli()
