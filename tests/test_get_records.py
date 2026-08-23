import sqlite3
from dataclasses import dataclass
from pathlib import Path

import pytest

from geo import get_ips, ips2geo, response2df
from log2csv import append2db, filter_df, logfile2df, main, new_entries, remove_NULL


@dataclass
class MyPaths:
    path2log: Path
    path2raw: Path
    path2db : Path


mypaths = MyPaths(path2log=Path('./tests/www.philiplessner.com.access-test.log'),
                  path2raw=Path('./tests/log_raw-test.csv'),
                  path2db=Path('./tests/logs-test.db'))


@dataclass
class NumRecords:
    log_file_records: int
    new_records: int
    NULL_records: int


numrecords = NumRecords(log_file_records=209, new_records=134, NULL_records=5)


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
    assert row_count == numrecords.log_file_records


def test_processed(db):
    df_new = new_entries(mypaths.path2log, db)
    assert len(df_new) == numrecords.new_records
    df_combined = filter_df(df_new)
    assert len(df_combined) == numrecords.new_records
    ips = get_ips(df_combined)
    assert len(ips) == numrecords.new_records
    geo_info = ips2geo(ips)
    assert len(geo_info) == numrecords.new_records
    df_combined = response2df(geo_info, df_combined)
    assert len(df_combined) == numrecords.new_records
    df_combined = remove_NULL(df_combined)
    assert len(df_combined) == numrecords.new_records - numrecords.NULL_records
    record_count_before = db.execute(
        "SELECT COUNT(*) FROM logs"
    ).fetchone()[0]
    append2db(db, df_combined)
    record_count_after = db.execute(
        "SELECT COUNT(*) FROM logs"
    ).fetchone()[0]
    assert record_count_after - record_count_before == len(df_combined)
    db.rollback()


def test_main(db):
    record_count_before = db.execute(
        "SELECT COUNT(*) FROM logs"
    ).fetchone()[0]
    main(mypaths.path2log, db)
    record_count_after = db.execute(
        "SELECT COUNT(*) FROM logs"
    ).fetchone()[0]
    assert record_count_after - record_count_before == numrecords.new_records - numrecords.NULL_records

