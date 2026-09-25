"""Offline data-integrity checks for the SQLite-to-MySQL importer."""

from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from migrate import COLUMNS, compare_rows, convert_row, snapshot_database, sqlite_readonly, utc_datetime


def sample_row(**changes):
    values = {name: None for name in COLUMNS}
    values.update(id=7, datetime='2026-09-25 14:00:00.123456+02:00',
                  status_code=200, Agent_Type='H', zip='00123', lat=1.25, lon=-2.5)
    values.update(changes)
    return tuple(values[name] for name in COLUMNS)


class MigrationTests(unittest.TestCase):
    def test_utc_conversion_preserves_instant_and_microseconds(self):
        self.assertEqual(utc_datetime('2026-09-25 14:00:00.123456+02:00'),
                         datetime(2026, 9, 25, 12, 0, 0, 123456))
        self.assertIsNone(utc_datetime(None))

    def test_ambiguous_and_overprecise_dates_are_rejected(self):
        for value in ('2026-09-25 12:00:00', '2026-09-25 12:00:00.1234567+00:00'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                utc_datetime(value)

    def test_text_nulls_and_postal_codes_are_preserved(self):
        row = convert_row(sample_row(endpoint='/café/🧪 ', user_agent="quote' slash\\", region=''))
        self.assertEqual(row[4], '/café/🧪 ')
        self.assertEqual(row[7], "quote' slash\\")
        self.assertEqual(row[11], '')
        self.assertIsNone(row[12])
        self.assertEqual(row[14], '00123')
        self.assertEqual(row[15:17], (1.25, -2.5))

    def test_values_that_mysql_would_coerce_or_truncate_are_rejected(self):
        for changes in (dict(status_code='200'), dict(status_code=-1),
                        dict(Agent_Type='Human'), dict(lat=float('inf')),
                        dict(user_agent='🧪' * 16384)):
            with self.subTest(changes=list(changes)), self.assertRaises(ValueError):
                convert_row(sample_row(**changes))

    def test_verification_detects_changed_values_and_missing_rows(self):
        row = convert_row(sample_row())
        changed = convert_row(sample_row(zip='123'))
        with self.assertRaisesRegex(ValueError, 'zip'):
            compare_rows([row], [changed])
        with self.assertRaisesRegex(ValueError, 'Row count mismatch'):
            compare_rows([row], [])

    def test_missing_source_is_not_created(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / 'missing.db'
            with self.assertRaises(sqlite3.OperationalError):
                sqlite_readonly(path)
            self.assertFalse(path.exists())

    def test_snapshot_includes_wal_records_and_refuses_overwrite(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source.db'
            snapshot = Path(tmp) / 'snapshot.db'
            with closing(sqlite3.connect(source)) as conn:
                conn.execute('PRAGMA journal_mode=WAL')
                conn.execute('CREATE TABLE sample (value TEXT)')
                conn.execute('INSERT INTO sample VALUES (?)', ('committed in WAL',))
                conn.commit()
                snapshot_database(source, snapshot)
                with closing(sqlite_readonly(snapshot)) as copied:
                    self.assertEqual(copied.execute('SELECT value FROM sample').fetchone(),
                                     ('committed in WAL',))
                    with self.assertRaises(sqlite3.OperationalError):
                        copied.execute('DELETE FROM sample')
                with self.assertRaises(FileExistsError):
                    snapshot_database(source, snapshot)


if __name__ == '__main__':
    unittest.main()
