"""Select only an independently provisioned immutable historical snapshot.

The catalog is trusted operator policy, not a request field or a DB assertion.
Caller supplies a fresh dedicated read-only connection and owns rollback/close.
"""
import copy
from .history_export import _read_records_postgres, MAX_ROWS, MAX_BYTES
from .history_export_v11 import export_records_v11
from .provenance import canonical, digest


def select_snapshot(conn, selection, catalog):
    try:
        if (type(selection) is not dict or set(selection) != {'schema', 'snapshot_id',
                'venue', 'market_type', 'symbol', 'start_ms', 'end_ms'} or
                selection['schema'] != 'grid.history.selection.v1'):
            raise ValueError('SELECTION_SCHEMA')
        pin = selection['snapshot_id']
        if type(pin) is not str or len(pin) != 64 or pin not in catalog:
            raise ValueError('SNAPSHOT_NOT_PROVISIONED')
        # Bound the selected entry before copying it. Never enumerate or query the catalog.
        raw = catalog[pin]
        if len(canonical(raw)) > MAX_BYTES:
            raise ValueError('SNAPSHOT_LIMIT')
        entry = copy.deepcopy(raw)
        if digest(entry) != pin or set(entry) != {'request', 'trust', 'revisions',
                                                   'dataset_id', 'dataset_fingerprint'}:
            raise ValueError('SNAPSHOT_PIN')
        q = entry['request']
        if any(type(selection[k]) is not type(q[k]) or selection[k] != q[k] for k in
                ('venue', 'market_type', 'symbol', 'start_ms', 'end_ms')):
            raise ValueError('SELECTION_MISMATCH')
        revisions = entry['revisions']
        if (type(revisions) is not list or not 1 <= len(revisions) <= MAX_ROWS or
                len(set(revisions)) != len(revisions)):
            raise ValueError('REVISION_PINS')
        records = _read_records_postgres(conn, q, revisions=revisions)
        if [r['dataset_fingerprint'] for r in records] != revisions:
            raise ValueError('SNAPSHOT_REVISIONS')
        result = export_records_v11(records, q, entry['trust'])
        if any(result[k] != entry[k] for k in ('dataset_id', 'dataset_fingerprint')):
            raise ValueError('SNAPSHOT_CONTENT')
        return result
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError('SNAPSHOT_UNAVAILABLE') from exc
