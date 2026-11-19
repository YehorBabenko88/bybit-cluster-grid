"""Select only an independently provisioned immutable historical snapshot.

The catalog is trusted operator policy, not a request field or a DB assertion.
Caller supplies a fresh dedicated read-only connection and owns rollback/close.
"""
import copy
import math
import re
from .history_export import _read_records_postgres, MAX_ROWS, MAX_BYTES
from .history_export_v11 import export_records_v11
from .provenance import canonical, digest

TIMEFRAME_MINUTES = {'5m': 5, '15m': 15, '1h': 60}
MULTIPIN_MINUTES = {'1h': 60, '4h': 240, '1d': 1440, '1w': 10080}
IDENTITY_FIELDS = ('venue', 'market_type', 'symbol')
MAX_SEQUENCE_CANDLES = 32
MAX_SEQUENCE_MINUTES = 2 * MULTIPIN_MINUTES['1w']
MAX_SEQUENCE_PINS = 16


def _candle(window):
    first, last = window[0], window[-1]
    try:
        return {
            'event_start_ms': first['event_start_ms'], 'event_end_ms': last['event_end_ms'],
            'open': first['open'], 'close': last['close'],
            'high': max(row['high'] for row in window),
            'low': min(row['low'] for row in window),
            'volume': math.fsum(row['volume'] for row in window),
            'available_at_ms': max(row['available_at_ms'] for row in window),
            'watermark_ms': max(row['watermark_ms'] for row in window),
        }
    except OverflowError as exc:
        raise ValueError('ROLLUP_VOLUME') from exc


def plan_multipin(selection, catalog):
    """Require complete aligned candles and an ordered list of catalog pages."""
    if set(selection) != {'schema', 'timeframe', 'snapshot_ids', 'start_ms', 'end_ms', *IDENTITY_FIELDS}:
        raise ValueError('MULTIPIN_SCHEMA')
    if selection['schema'] not in ('grid.history.selection.v3', 'grid.history.selection.v4'):
        raise ValueError('MULTIPIN_SCHEMA')
    sequence = selection['schema'] == 'grid.history.selection.v4'
    timeframe = selection['timeframe']
    if type(timeframe) is not str or timeframe not in MULTIPIN_MINUTES:
        raise ValueError('MULTIPIN_TIMEFRAME')
    start, end = selection['start_ms'], selection['end_ms']
    width = MULTIPIN_MINUTES[timeframe] * 60000
    anchor = 4 * 86400000 if timeframe == '1w' else 0  # 1970-01-05 Monday UTC
    max_span = min(MAX_SEQUENCE_CANDLES * width, MAX_SEQUENCE_MINUTES * 60000) if sequence else width
    if (type(start) is not int or type(end) is not int or not 0 <= start < end <= 2**53 - 1
            or not width <= end - start <= max_span
            or (start - anchor) % width or (end - anchor) % width):
        raise ValueError('MULTIPIN_ALIGNMENT')
    if any(type(selection[key]) is not str or not selection[key] for key in IDENTITY_FIELDS):
        raise ValueError('MULTIPIN_IDENTITY')
    pins = selection['snapshot_ids']
    if (type(pins) is not list or not 1 <= len(pins) <= (MAX_SEQUENCE_PINS if sequence else 8)
            or any(type(pin) is not str or not re.fullmatch('[0-9a-f]{64}', pin) for pin in pins)
            or len(set(pins)) != len(pins)):
        raise ValueError('MULTIPIN_PINS')

    pages = []
    cursor = start
    common = None
    for pin in pins:
        entry = catalog.get(pin)
        if type(entry) is not dict or digest(entry) != pin:
            raise ValueError('MULTIPIN_PIN')
        request, trust = entry.get('request'), entry.get('trust')
        if type(request) is not dict or type(trust) is not dict or trust.get('evidence_class') != 'HISTORICAL':
            raise ValueError('MULTIPIN_SOURCE')
        if any(request.get(key) != selection[key] for key in IDENTITY_FIELDS):
            raise ValueError('MULTIPIN_IDENTITY')
        lo, hi = request.get('start_ms'), request.get('end_ms')
        if (type(lo) is not int or type(hi) is not int or lo != cursor or hi > end
                or hi % 60000 or not 60000 <= hi - lo <= MAX_ROWS * 60000):
            raise ValueError('MULTIPIN_CONTINUITY')
        lineage = (request.get('as_of_ms'), request.get('units'),
                   *(trust.get(key) for key in ('identity', 'source_revision', 'epoch')))
        if common is not None and lineage != common:
            raise ValueError('MULTIPIN_LINEAGE')
        common = lineage
        pages.append({'schema': 'grid.history.selection.v1', 'snapshot_id': pin,
                      'start_ms': lo, 'end_ms': hi, **{key: selection[key] for key in IDENTITY_FIELDS}})
        cursor = hi
    if cursor != end:
        raise ValueError('MULTIPIN_CONTINUITY')
    return pages


def read_multipin_rollup(conn, selection, pages, catalog):
    rows, parents = [], []
    for page in pages:
        envelope = select_snapshot(conn, page, catalog, continuing=bool(parents))
        rows.extend(envelope['rows'])
        parents.append({'snapshot_id': page['snapshot_id'], 'dataset_id': envelope['dataset_id'],
                        'dataset_fingerprint': envelope['dataset_fingerprint']})
    sequence = selection['schema'] == 'grid.history.selection.v4'
    minutes = MULTIPIN_MINUTES[selection['timeframe']]
    result = {'schema': 'grid.history.rollup.v3' if sequence else 'grid.history.rollup.v2', 'request': selection,
              'timeframe': selection['timeframe'], 'source': envelope['source'],
              'units': envelope['request']['units'], 'as_of_ms': envelope['request']['as_of_ms'],
              'evidence_class': 'HISTORICAL', 'parents': parents,
              'rows': [_candle(rows[i:i + minutes]) for i in range(0, len(rows), minutes)]}
    return dict(result, dataset_fingerprint=digest(result))


def rollup_snapshot(envelope, timeframe):
    """Project a verified, contiguous v1.1 minute envelope to UTC candle windows."""
    minutes = TIMEFRAME_MINUTES[timeframe]
    rows = envelope['rows']
    if envelope['evidence_class'] != 'HISTORICAL' or not rows or len(rows) % minutes:
        raise ValueError('ROLLUP_SOURCE_UNAVAILABLE')
    candles = [_candle(rows[i:i + minutes]) for i in range(0, len(rows), minutes)]
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


def select_snapshot(conn, selection, catalog, *, continuing=False):
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
        records = _read_records_postgres(conn, q, revisions=revisions, continuing=continuing)
        if [r['dataset_fingerprint'] for r in records] != revisions:
            raise ValueError('SNAPSHOT_REVISIONS')
        result = export_records_v11(records, q, entry['trust'])
        if any(result[k] != entry[k] for k in ('dataset_id', 'dataset_fingerprint')):
            raise ValueError('SNAPSHOT_CONTENT')
        return result
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError('SNAPSHOT_UNAVAILABLE') from exc
