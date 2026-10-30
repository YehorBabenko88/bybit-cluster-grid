import copy
import unittest
from test_history_export import fixture
from grid.history_export_v11 import export_records_v11
from grid.provenance import digest


def snapshot_fixture():
    rows, q, trust = fixture()
    envelope = export_records_v11(rows, q, trust)
    entry = {'request': q, 'trust': trust, 'revisions': [r['dataset_fingerprint'] for r in rows],
             'dataset_id': envelope['dataset_id'], 'dataset_fingerprint': envelope['dataset_fingerprint']}
    pin = digest(entry)
    selection = {'schema': 'grid.history.selection.v1', 'snapshot_id': pin,
                 **{k: q[k] for k in ('venue', 'market_type', 'symbol', 'start_ms', 'end_ms')}}
    return rows, selection, {pin: entry}, envelope


class Connection:
    def __init__(self, rows): self.rows, self.calls = rows, []
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=None): self.calls.append((sql, params))
    def fetchall(self): return [(r,) for r in self.rows]


class SnapshotSelection(unittest.TestCase):
    def select(self, conn, selection, catalog):
        from grid import history_snapshot
        return history_snapshot.select_snapshot(conn, selection, catalog)

    def test_exact_snapshot_identity_and_revision_filter(self):
        rows, selection, catalog, expected = snapshot_fixture()
        conn = Connection(rows)
        actual = self.select(conn, selection, catalog)
        self.assertEqual(actual, expected)
        self.assertIn('REPEATABLE READ READ ONLY', conn.calls[0][0])
        self.assertIn('fingerprint = ANY(%s)', conn.calls[-1][0])
        self.assertEqual(conn.calls[-1][1][-2], catalog[selection['snapshot_id']]['revisions'])

    def test_wrong_market_range_snapshot_and_mutated_catalog_fail_before_sql(self):
        for key, value in [('symbol', 'ETHUSDT'), ('market_type', 'spot'), ('start_ms', 60000),
                           ('end_ms', 60000), ('snapshot_id', 'f' * 64), ('venue', 'other')]:
            rows, s, c, _ = snapshot_fixture(); s[key] = value; conn = Connection(rows)
            with self.subTest(key=key), self.assertRaises(ValueError): self.select(conn, s, c)
            self.assertEqual(conn.calls, [])
        rows, s, c, _ = snapshot_fixture(); c[s['snapshot_id']]['request']['symbol'] = 'ETHUSDT'
        conn = Connection(rows)
        with self.assertRaises(ValueError): self.select(conn, s, c)
        self.assertEqual(conn.calls, [])

    def test_duplicate_missing_and_wrong_revision_never_select_another_snapshot(self):
        for change in (lambda r: r.append(copy.deepcopy(r[0])), lambda r: r.pop(),
                       lambda r: r[0].update(dataset_fingerprint='0' * 64)):
            rows, s, c, _ = snapshot_fixture(); change(rows)
            with self.assertRaises(ValueError): self.select(Connection(rows), s, c)
