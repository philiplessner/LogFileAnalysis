"""Offline and opt-in temporary-table tests for the MySQL log importer."""

from datetime import datetime
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import MagicMock, patch

import pandas as pd
import pymysql

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('log2db_mysql', ROOT / 'log2db-mysql.py')
importer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(importer)

BROWSER = 'Mozilla/5.0 Chrome/140.0.0.0 Safari/537.36'


def log_line(timestamp='25/Sep/2026:14:00:00 +0200', request='GET /café/🧪 HTTP/1.1', agent=BROWSER):
    return f'203.0.113.1 - - [{timestamp}] "{request}" 200 12 "-" "{agent}"\n'


def sample_frame():
    return pd.DataFrame([dict(
        ip_address='203.0.113.1', datetime=pd.Timestamp('2026-09-25T14:00:00.123456+02:00'),
        request_type='GET', endpoint='/café/🧪 ', http_version='HTTP/1.1',
        status_code='200', user_agent="quote' slash\\", Agent_Type='H',
        zip='00123', region=pd.NA, lat=float('nan'), lon=1.25,
        timezone='Europe/Paris',
    )])


class ImporterTests(unittest.TestCase):
    def setUp(self):
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.log = Path(tmp.name) / 'access.log'
        self.log.write_text(log_line(), encoding='utf-8')
        self.db = MagicMock()
        self.cursor = self.db.cursor.return_value.__enter__.return_value
        self.cursor.warning_count = 0

    def test_parser_preserves_original_fixture(self):
        from log2db import logfile2df
        source = ROOT / 'tests/www.philiplessner.com.access-test.log'
        expected = logfile2df(source)
        expected['datetime'] = pd.to_datetime(expected['datetime'], utc=True)
        pd.testing.assert_frame_equal(importer.logfile2df(source), expected)

    def test_mixed_offsets_and_empty_logs(self):
        self.log.write_text(log_line('01/Nov/2026:01:30:00 -0400') +
                            log_line('01/Nov/2026:01:30:00 -0500'), encoding='utf-8')
        df = importer.logfile2df(self.log)
        self.assertEqual(df['datetime'].tolist(), [pd.Timestamp('2026-11-01T05:30:00Z'),
                                                  pd.Timestamp('2026-11-01T06:30:00Z')])
        self.log.write_text('unmatched line\n', encoding='utf-8')
        self.assertTrue(importer.logfile2df(self.log).empty)

    def test_empty_table_and_utc_cutoff(self):
        self.cursor.fetchone.return_value = (None,)
        self.assertEqual(len(importer.new_entries(self.log, self.db)), 1)
        self.cursor.fetchone.return_value = (datetime(2026, 9, 25, 11, 59, 59),)
        self.assertEqual(len(importer.new_entries(self.log, self.db)), 1)
        self.cursor.fetchone.return_value = (datetime(2026, 9, 25, 12),)
        self.assertTrue(importer.new_entries(self.log, self.db).empty)

    def test_no_new_or_supported_entries_skips_geolocation(self):
        with patch.object(importer, 'ips2geo') as geo, patch.object(importer, 'append2db') as append:
            self.cursor.fetchone.return_value = (datetime(2026, 9, 25, 12),)
            importer.main(self.log, self.db)
            self.cursor.fetchone.return_value = (None,)
            self.log.write_text(log_line(request='HEAD / HTTP/1.1'), encoding='utf-8')
            importer.main(self.log, self.db)
            geo.assert_not_called()
            append.assert_not_called()

    def test_insert_binds_values_and_converts_missing_values(self):
        importer.append2db(self.db, sample_frame())
        sql, rows = self.cursor.executemany.call_args.args
        self.assertNotIn('café', sql)
        self.assertNotIn('`id`', sql)
        row = dict(zip(importer.INSERT_COLUMNS, rows[0], strict=True))
        self.assertEqual(row['datetime'], datetime(2026, 9, 25, 12, 0, 0, 123456))
        self.assertEqual(row['status_code'], 200)
        self.assertEqual(row['zip'], '00123')
        self.assertIsNone(row['lat'])
        self.assertIsNone(row['region'])
        self.assertIsNone(row['country'])
        self.db.commit.assert_called_once()

    def test_mysql_warnings_roll_back(self):
        self.cursor.warning_count = 1
        with self.assertRaisesRegex(ValueError, 'warnings'):
            importer.append2db(self.db, sample_frame())
        self.db.rollback.assert_called_once()
        self.db.commit.assert_not_called()


@unittest.skipUnless(os.environ.get('MYSQL_INTEGRATION_TESTS') == '1',
                     'Set MYSQL_INTEGRATION_TESTS=1 for live MySQL checks')
class MySQLImporterIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.db = pymysql.connect(**importer.mysql_settings(ROOT / '.mysql.env'))
        self.addCleanup(self.db.close)
        with self.db.cursor() as cursor:
            cursor.execute('SET SESSION sql_mode = %s', (importer.SQL_MODE,))
            # This temporary table shadows logs only for this connection.
            ddl = (ROOT / 'mysql/schema.sql').read_text().replace(
                'CREATE TABLE IF NOT EXISTS logs', 'CREATE TEMPORARY TABLE logs', 1)
            cursor.execute(ddl)
        self.db.commit()

    def test_roundtrip_utc_nulls_unicode_and_generated_id(self):
        importer.append2db(self.db, sample_frame())
        with self.db.cursor() as cursor:
            cursor.execute('SELECT id, datetime, endpoint, user_agent, zip, region, lat, lon, timezone FROM logs')
            self.assertEqual(cursor.fetchone(), (
                1, datetime(2026, 9, 25, 12, 0, 0, 123456), '/café/🧪 ', "quote' slash\\",
                '00123', None, None, 1.25, 'Europe/Paris',
            ))

    def test_later_batch_failure_rolls_back_all_inserts(self):
        frame = pd.concat([sample_frame()] * 1001, ignore_index=True)
        frame.loc[1000, 'user_agent'] = 'x' * 65536
        with self.assertRaises(pymysql.DataError):
            importer.append2db(self.db, frame)
        with self.db.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM logs')
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_pipeline_and_repeat_import(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / 'access.log'
            source.write_text(log_line() + log_line(agent='curl/8.0') +
                              log_line(request='HEAD / HTTP/1.1'), encoding='utf-8')
            with patch.object(importer, 'ips2geo', return_value=[{'zip': '00123'}, {}]) as geo:
                importer.main(source, self.db)
                self.assertEqual(len(geo.call_args.args[0]), 2)
                importer.main(source, self.db)
                geo.assert_called_once()
            with self.db.cursor() as cursor:
                cursor.execute('SELECT Agent_Type, zip FROM logs ORDER BY id')
                self.assertEqual(cursor.fetchall(), (('H', '00123'), ('R', None)))


if __name__ == '__main__':
    unittest.main()
