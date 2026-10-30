"""Disposable-only qualification; this DSN must never name production."""
import os
import unittest
from grid.history_export import read_postgres
from test_history_export import fixture

@unittest.skipUnless(os.environ.get('HISTORY_DISPOSABLE_DSN'),'disposable PostgreSQL not configured')
class DisposablePostgres(unittest.TestCase):
    def test_export_and_readonly(self):
        import psycopg
        from psycopg.types.json import Jsonb
        dsn=os.environ['HISTORY_DISPOSABLE_DSN']
        r,q,t=fixture()
        with psycopg.connect(dsn,autocommit=True) as setup:
            setup.execute('CREATE TEMP TABLE provenance_minutes(record jsonb,symbol text,start_ms bigint,fingerprint text)')
            with setup.cursor() as cur:
                cur.executemany('INSERT INTO provenance_minutes VALUES(%s,%s,%s,%s)',
                    [(Jsonb(x),x['symbol'],x['start_ms'],x['dataset_fingerprint']) for x in r])
            # Use explicit transaction, so SET TRANSACTION is first statement.
            with setup.transaction():
                exported=read_postgres(setup,q,t)
                self.assertEqual(len(exported['rows']),len(r))
                self.assertEqual(setup.execute('SHOW transaction_read_only').fetchone()[0],'on')
                # PostgreSQL permits writes to temp tables in read-only tx;
                # attempting to create a regular table must still fail.
                with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                    setup.execute('CREATE TABLE forbidden_history_write(id integer)')

if __name__=='__main__':unittest.main()
