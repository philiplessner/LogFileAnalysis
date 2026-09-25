"""Opt-in checks on a temporary table in the running MySQL test container."""

from contextlib import closing
import os
from pathlib import Path
import unittest

import pymysql

from migrate import COLUMNS, ROOT, SQL_MODE, compare_rows, convert_row, mysql_settings
from test_migrate import sample_row


@unittest.skipUnless(os.environ.get('MYSQL_INTEGRATION_TESTS') == '1', 'Set MYSQL_INTEGRATION_TESTS=1 for live MySQL checks')
class MySQLIntegrationTests(unittest.TestCase):
    def test_roundtrip_generated_ids_and_transaction_rollback(self):
        with closing(pymysql.connect(**mysql_settings(ROOT / '.mysql.env'))) as conn, conn.cursor() as cursor:
            cursor.execute('SELECT VERSION()')
            self.assertEqual(cursor.fetchone()[0], '8.0.40')
            cursor.execute('SET SESSION sql_mode = %s', (SQL_MODE,))
            ddl = (ROOT / 'mysql/schema.sql').read_text().replace(
                'CREATE TABLE IF NOT EXISTS logs', 'CREATE TEMPORARY TABLE migration_probe', 1)
            cursor.execute(ddl)
            conn.commit()
            rows = [convert_row(sample_row(id=key, endpoint=endpoint, user_agent="café 🧪 quote' slash\\", region=''))
                    for key, endpoint in [(0, '/Case'), (7, '/case'), (9, '/case ')]]
            names = ', '.join(f'`{name}`' for name in COLUMNS)
            statement = f'INSERT INTO migration_probe ({names}) VALUES (' + ', '.join(['%s'] * len(COLUMNS)) + ')'
            conn.begin()
            cursor.executemany(statement, rows)
            self.assertEqual(cursor.warning_count, 0)
            cursor.execute(f'SELECT {names} FROM migration_probe ORDER BY id')
            compare_rows(rows, list(cursor.fetchall()))
            cursor.execute('SELECT endpoint, COUNT(*) FROM migration_probe GROUP BY endpoint')
            self.assertEqual(dict(cursor.fetchall()), {'/Case': 1, '/case': 1, '/case ': 1})
            cursor.execute('INSERT INTO migration_probe (endpoint) VALUES (%s)', ('/generated',))
            self.assertEqual(cursor.lastrowid, 10)
            conn.rollback()
            cursor.execute('SELECT COUNT(*) FROM migration_probe')
            self.assertEqual(cursor.fetchone()[0], 0)
            conn.begin()
            cursor.execute('INSERT INTO migration_probe (id) VALUES (100)')
            with self.assertRaises(pymysql.IntegrityError):
                cursor.execute('INSERT INTO migration_probe (id) VALUES (100)')
            conn.rollback()
            cursor.execute('SELECT COUNT(*) FROM migration_probe')
            self.assertEqual(cursor.fetchone()[0], 0)
            # The temporary table disappears when this connection closes.


if __name__ == '__main__':
    unittest.main()
