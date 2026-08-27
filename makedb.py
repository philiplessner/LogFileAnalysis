import os
import sqlite3
from contextlib import closing
from pathlib import Path

from dotenv import load_dotenv

from geo import get_ips, ips2geo, response2df
from log2db import filter_df, logfile2df, remove_NULL


def logfile2db(path2logfile: Path, path2db: Path) -> None:

    df_new = logfile2df(path2logfile)
    df_combined = filter_df(df_new)
    ips = get_ips(df_combined)
    geo_info = ips2geo(ips)
    df_combined = response2df(geo_info, df_combined)
    df = remove_NULL(df_combined)

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
        data_dir = Path('/app/data.holouganda.org')
    else:
        load_dotenv()
        data_dir = Path(os.environ['DATA_FILE_DIR'])

    path2logfile = Path(data_dir, 'www.holouganda.org.access.log')
    path2db = Path(data_dir, 'logs.db')

    logfile2db(path2logfile, path2db)
