import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from log2csv import logfile2df, new_entries


@dataclass
class MyPaths:
    path2log: Path
    path2raw: Path
    path2db : Path


mypaths = MyPaths(path2log=Path('./tests/www.philiplessner.com.access-test.log'),
                  path2raw=Path('./tests/log_raw-test.csv'),
                  path2db=Path('./tests/logs-test.db'))


@pytest.fixture
def db():
    disk_conn = sqlite3.connect(mypaths.path2db)
    memory_conn = sqlite3.connect(":memory:")
    disk_conn.backup(memory_conn)
    disk_conn.close()

    yield memory_conn

    memory_conn.close()


def test_records_from_log():
    df = logfile2df(mypaths.path2log)
    row_count = len(df)
    assert row_count == 209


def test_new_records():
    df_new = new_entries(Path('./tests/www.philiplessner.com.access-test.log'), Path('./tests/log_raw-test.csv'))
    row_count = len(df_new)
    assert row_count == 134