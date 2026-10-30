"""Disposable-only qualification; this DSN must never name production."""
import os
import unittest
from grid.history_export import read_postgres
from grid.history_export_v11 import read_postgres_v11
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
                timed=read_postgres_v11(setup,q,t)
                self.assertEqual(timed['schema'],'grid.history.v1.1')
                self.assertEqual(timed['rows'][0]['watermark_ms'],60000)
                self.assertEqual(setup.execute('SHOW transaction_read_only').fetchone()[0],'on')
            # A later stored revision must not displace the selected snapshot.
            from grid.history_snapshot import select_snapshot
            from test_history_snapshot import snapshot_fixture
            from grid.provenance import digest
            import copy
            _,selection,catalog,expected=snapshot_fixture()
            later=copy.deepcopy(r[0]);later['candle']['close']+=0.25
            later['dataset_fingerprint']=digest({k:v for k,v in later.items() if k!='dataset_fingerprint'})
            setup.execute('INSERT INTO provenance_minutes VALUES(%s,%s,%s,%s)',
                          (Jsonb(later),later['symbol'],later['start_ms'],later['dataset_fingerprint']))
            with setup.transaction():
                chosen=select_snapshot(setup,selection,catalog)
                self.assertEqual(chosen,expected)
                self.assertEqual(setup.execute('SHOW transaction_read_only').fetchone()[0],'on')
            setup.execute('DELETE FROM provenance_minutes WHERE fingerprint=%s',(later['dataset_fingerprint'],))
            with setup.transaction():
                exported=read_postgres(setup,q,t)
                self.assertEqual(len(exported['rows']),len(r))
                self.assertEqual(setup.execute('SHOW transaction_read_only').fetchone()[0],'on')
                # PostgreSQL permits writes to temp tables in read-only tx;
                # attempting to create a regular table must still fail.
                with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):
                    setup.execute('CREATE TABLE forbidden_history_write(id integer)')

if __name__=='__main__':unittest.main()
