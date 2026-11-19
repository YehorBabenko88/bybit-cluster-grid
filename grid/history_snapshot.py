"""Select only an independently provisioned immutable historical snapshot.

The catalog is trusted operator policy, not a request field or a DB assertion.
Caller supplies a fresh dedicated read-only connection and owns rollback/close.
"""
import copy
import math
from .history_export import _read_records_postgres, MAX_ROWS, MAX_BYTES
from .history_export_v11 import export_records_v11
from .provenance import canonical, digest

TIMEFRAME_MINUTES = {'5m': 5, '15m': 15, '1h': 60}


def rollup_snapshot(envelope, timeframe):
    """Project a verified, contiguous v1.1 minute envelope to UTC candle windows."""
    minutes = TIMEFRAME_MINUTES[timeframe]
    rows = envelope['rows']
    if envelope['evidence_class'] != 'HISTORICAL' or not rows or len(rows) % minutes:
        raise ValueError('ROLLUP_SOURCE_UNAVAILABLE')
    candles = []
    try:
        for i in range(0, len(rows), minutes):
            window = rows[i:i + minutes]
            first, last = window[0], window[-1]
            candles.append({
                'event_start_ms': first['event_start_ms'],
                'event_end_ms': last['event_end_ms'],
                'open': first['open'], 'close': last['close'],
                'high': max(row['high'] for row in window),
                'low': min(row['low'] for row in window),
                'volume': math.fsum(row['volume'] for row in window),
                'available_at_ms': max(row['available_at_ms'] for row in window),
                'watermark_ms': max(row['watermark_ms'] for row in window),
            })
    except OverflowError as exc:
        raise ValueError('ROLLUP_VOLUME') from exc
    result = {
        'schema': 'grid.history.rollup.v1',
        'timeframe': timeframe,
        'request': envelope['request'],
        'source': envelope['source'],
        'evidence_class': envelope['evidence_class'],
        'parent_dataset_id': envelope['dataset_id'],
        'parent_dataset_fingerprint': envelope['dataset_fingerprint'],
        'rows': candles,
    }
    return dict(result, dataset_fingerprint=digest(result))


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
