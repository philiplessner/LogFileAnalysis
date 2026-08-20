import sqlite3
from pathlib import Path

import pytest

from log2csv import new_entries


@pytest.fixture
def db():
    disk_conn = sqlite3.connect("data.philiplessner.com/logs.db")
    memory_conn = sqlite3.connect(":memory:")
    disk_conn.backup(memory_conn)
    disk_conn.close()

    yield memory_conn

    memory_conn.close()

def test_new_records():
    df_new = new_entries(Path('./tests/www.philiplessner.com.access-test.log'), Path('./tests/log_raw-test.csv'))
    row_count = len(df_new)
    assert row_count == 134
