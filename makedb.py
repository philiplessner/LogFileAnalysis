import os
import sqlite3
from contextlib import closing
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv


def csv2db(path2csv: Path, path2db: Path) -> None:

    df = pd.read_csv(path2csv, parse_dates=['datetime'])
    df = df.astype(dtype={'status_code': 'Int64', 'lat': 'Float64', 'lon': 'Float64'})

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
        conn.commit()
        df.to_sql(
            "logs",
            conn,
            if_exists="append",
            index=False,
        )
        conn.commit()

if __name__ == '__main__':
    if (str(Path.cwd()) == '/app'):
        data_dir = Path('/app/data.philiplessner.com')
    else:
        load_dotenv()
        data_dir = Path(os.environ['DATA_FILE_DIR'])

    path2csv = Path(data_dir, 'log_processed.csv')
    path2db = Path(data_dir, 'logs.db')
    csv2db(path2csv, path2db)
