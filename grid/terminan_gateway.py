"""Read-only snapshot service for Terminan. No exchange subscriptions or writes.

Run inside the existing Grid environment with psycopg installed. Bind to loopback.
Set TERMINAN_GRID_DSN to a dedicated read-only PostgreSQL role.
"""
import json
import os
import re
import socket
import threading
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs

SYMBOL=re.compile(r'^[A-Z0-9]{2,30}$')

def query(sql,args=()):
    import psycopg
    dsn=os.environ['TERMINAN_GRID_DSN']
    with psycopg.connect(dsn,connect_timeout=3,options='-c default_transaction_read_only=on -c statement_timeout=3000') as conn:
        with conn.cursor() as cur:
            cur.execute(sql,args)
            return cur.fetchall()


def immutable_minutes(symbol, limit, before_ms):
    import psycopg
    with psycopg.connect(os.environ['TERMINAN_GRID_DSN'], connect_timeout=3,
            options='-c default_transaction_read_only=on -c statement_timeout=3000') as conn:
        with conn.cursor() as cur:
            cur.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            cur.execute("""SELECT CASE WHEN sum(octet_length(record::text)) OVER() <= 8388608
                    AND max(octet_length(record::text)) OVER() <= 1048576 THEN record ELSE NULL END, versions
                FROM (SELECT record,count(*) OVER(PARTITION BY start_ms) AS versions,start_ms,fingerprint
                    FROM provenance_minutes WHERE symbol=%s AND start_ms<%s
                    ORDER BY start_ms DESC,fingerprint DESC LIMIT %s) page ORDER BY start_ms DESC,fingerprint DESC""", (symbol, before_ms, limit))
            rows = cur.fetchall()
            if any(r[0] is None or r[1] != 1 for r in rows):
                raise ValueError('ambiguous minute revisions')
            return [r[0] for r in rows]


def _utc_text(value):
    if value is None:
        return None
    from datetime import datetime,timezone
    if type(value) is not datetime or value.tzinfo is None:
        raise ValueError('invalid Grid timestamp')
    return value.astimezone(timezone.utc).isoformat().replace('+00:00','Z')


def instrument_state(symbol):
    """Read Grid's saved registry entry; never claim the exchange is live."""
    if type(symbol) is not str or not SYMBOL.fullmatch(symbol):
        raise ValueError('invalid instrument identity')
    rows = query("""SELECT status,contract_type,tick_size,last_seen
        FROM instruments WHERE symbol=%s LIMIT 2""", (symbol,))
    if len(rows) > 1:
        raise ValueError('ambiguous instrument identity')
    result = {'api_version': {'major': 1, 'minor': 0},
              'producer': 'bybit-cluster-grid', 'venue': 'Bybit',
              'market_type': 'linear', 'symbol': symbol,
              'read_only': True, 'status': 'UNAVAILABLE',
              'exchange_connection': 'NOT_ATTESTED',
              'history_coverage': 'NOT_ATTESTED',
              'source_provenance': 'NOT_ATTESTED',
              'execution_authority': False, 'trading_authorized': False,
              'reason': 'NO_GRID_INSTRUMENT_RECORD'}
    if not rows:
        return result
    state,kind,tick,last_seen = rows[0]
    from decimal import Decimal
    if (type(state) is not str or state not in ('Trading', 'Retired') or
            (kind is not None and type(kind) is not str) or
            (tick is not None and
             (type(tick) is not Decimal or not tick.is_finite() or tick <= 0))):
        raise ValueError('invalid Grid instrument record')
    result.update(status='INFORMATIONAL', recorded_status=state,
                  contract_type=kind, tick_size=str(tick) if tick is not None else None,
                  last_seen_utc=_utc_text(last_seen),
                  reason='REGISTRY_RECORD_NOT_SOURCE_READINESS')
    return result


def backfill_state(symbol):
    """Informational Grid queue state, never evidence of complete exchange history.

    A pre-existing Grid loopback reader only. Unified owns any remote Gateway,
    identity, authorization and rate limiting; never publish this listener on LAN.
    """
    if type(symbol) is not str or not SYMBOL.fullmatch(symbol):
        raise ValueError('invalid instrument identity')
    rows = query("""SELECT status,attempts,next_end_ms,oldest_loaded_ts,newest_loaded_ts
        FROM market_backfill_state WHERE symbol=%s AND timeframe='1' LIMIT 2""", (symbol,))
    if len(rows) > 1:
        raise ValueError('ambiguous Grid backfill state')
    result = {'api_version': {'major': 1, 'minor': 0},
              'producer': 'bybit-cluster-grid', 'resource': 'market_backfill_state',
              'read_only': True, 'symbol': symbol, 'timeframe': '1',
              'status': 'UNAVAILABLE', 'state': 'UNKNOWN',
              'history_coverage': 'NOT_ATTESTED', 'source_provenance': 'NOT_ATTESTED',
              'execution_authority': False, 'trading_authorized': False,
              'reason': 'NO_GRID_BACKFILL_RECORD'}
    if not rows:
        return result
    state,attempts,cursor,oldest,newest = rows[0]
    if (type(state) is not str or state not in
            ('queued','retry','running','done','failed','retired') or
            type(attempts) is not int or not 0 <= attempts <= 2147483647 or
            (cursor is not None and
             (type(cursor) is not int or not -1 <= cursor <= 9223372036854775807))):
        raise ValueError('invalid Grid backfill state')
    result.update(status='INFORMATIONAL', state=state, attempts=attempts,
                  next_end_ms=cursor, oldest_loaded_utc=_utc_text(oldest),
                  newest_loaded_utc=_utc_text(newest),
                  reason='QUEUE_STATE_NOT_HISTORY_COMPLETENESS_PROOF')
    return result

def _snapshot_catalog():
    """Operator-provisioned local policy; never accept catalog trust from HTTP."""
    import pathlib
    import stat
    raw_path=os.environ.get('GRID_PINNED_HISTORY_CATALOG','')
    if not raw_path or len(raw_path)>2048:
        raise RuntimeError('snapshot catalog not provisioned')
    path=pathlib.Path(raw_path)
    if not path.is_absolute() or path.is_symlink():
        raise RuntimeError('snapshot catalog path unavailable')
    flags=os.O_RDONLY|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0)
    fd=os.open(path,flags)
    try:
        before=os.fstat(fd)
        if (not stat.S_ISREG(before.st_mode) or not 0<before.st_size<=8388608
                or before.st_mode & 0o022):
            raise RuntimeError('snapshot catalog file unavailable')
        raw=os.read(fd,before.st_size+1)
        after=os.fstat(fd)
        if (len(raw)!=before.st_size or len(raw)>8388608 or
                (before.st_dev,before.st_ino,before.st_size,before.st_mtime_ns)!=
                (after.st_dev,after.st_ino,after.st_size,after.st_mtime_ns)):
            raise RuntimeError('snapshot catalog changed during read')
    finally:
        os.close(fd)
    def pairs(items):
        obj={}
        for k,v in items:
            if k in obj:raise ValueError('duplicate snapshot catalog key')
            obj[k]=v
        return obj
    catalog=json.loads(raw,object_pairs_hook=pairs,
                       parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite catalog')))
    if type(catalog) is not dict or len(catalog)>10000:
        raise ValueError('invalid snapshot catalog')
    return catalog


def pinned_history(selection):
    """Bounded, immutable historical read; source authenticity is EXTERNAL.

    Grid supplies custody and digest checks; Unified supplies authentication
    and the independently provisioned trust catalog. No live readiness claim.
    """
    if (type(selection) is not dict or
            set(selection)!={'schema','snapshot_id','venue','market_type','symbol','start_ms','end_ms'} or
            selection.get('schema')!='grid.history.selection.v1' or
            type(selection.get('snapshot_id')) is not str or
            re.fullmatch('[0-9a-f]{64}',selection['snapshot_id']) is None or
            any(type(selection.get(k)) is not str or not selection[k]
                for k in ('venue','market_type','symbol')) or
            type(selection.get('start_ms')) is not int or
            type(selection.get('end_ms')) is not int or
            selection['start_ms']<0 or selection['end_ms']<=selection['start_ms'] or
            selection['end_ms']-selection['start_ms']>120000000):
        raise ValueError('invalid pinned history selection')
    catalog=_snapshot_catalog()
    entry=catalog.get(selection['snapshot_id'])
    if type(entry) is not dict or type(entry.get('request')) is not dict:
        raise ValueError('snapshot not provisioned')
    expected=entry['request']
    for key in ('venue','market_type','symbol','start_ms','end_ms'):
        if type(selection[key]) is not type(expected.get(key)) or selection[key]!=expected[key]:
            raise ValueError('snapshot identity or time mismatch')
    from .history_snapshot import select_snapshot
    import psycopg
    with psycopg.connect(os.environ['TERMINAN_GRID_DSN'],connect_timeout=3,
                         options='-c default_transaction_read_only=on -c statement_timeout=3000') as conn:
        envelope=select_snapshot(conn,selection,catalog)
    return {'schema':'grid.history.snapshot.response.v1',
            'status':'PINNED_HISTORICAL_SOURCE_UNATTESTED',
            'read_only':True,'source_authentication':'EXTERNAL_NOT_INDEPENDENTLY_VERIFIED',
            'snapshot':envelope,'execution_authority':False,'trading_authorized':False}


def qualified_snapshot(route, symbol, limit, before_ms=None):
    """Versioned boundary. Current tables do not carry qualifying provenance."""
    result = {
        'api_version': {'major': 1, 'minor': 0},
        'producer': 'bybit-cluster-grid', 'read_only': True,
        'status': 'UNAVAILABLE', 'reason': 'SOURCE_PROVENANCE_UNAVAILABLE',
        'source': {'market_type': None, 'epoch': None, 'freshness_utc_ms': None,
                   'release_digest': None, 'identity': None},
    }
    if route == '/internal/v1/capabilities':
        result['capabilities'] = {'candles': 'UNAVAILABLE',
                                  'footprint': 'UNAVAILABLE', 'live_l2': False,
                                  'immutable_market_snapshots_v1_1': True,
                                  'research_handoff_validation_v1_1': True,
                                  'public_trades': 'UNAVAILABLE',
                                  'orderbook_snapshots': 'UNAVAILABLE',
                                  'open_interest': 'UNAVAILABLE',
                                  'funding_rate': 'UNAVAILABLE',
                                  'market_data_coverage': 'NOT_ATTESTED',
                                  'replay_cursor': 'NOT_ATTESTED'}
        result['meta_absorption'] = {
            'schema': 'grid.meta.dataset-capabilities.v1',
            'exchange_owner': 'Grid',
            'database_writer_owner': 'Grid',
            'history_provenance': 'NOT_ATTESTED',
            'consumer_cutover': False,
            'execution_authority': False,
            'trading_authorized': False,
        }
        return result
    if route == '/internal/v1/health':
        result['database'] = 'UNAVAILABLE'
        try:
            rows = query("SELECT current_setting('server_version_num')::int, current_setting('transaction_read_only')")
            if len(rows) == 1 and rows[0][0] >= 180000 and rows[0][1] == 'on':
                result['database'] = 'READ_ONLY'
        except Exception:
            pass  # Never return exception text, DSNs or credentials.
        return result
    if route == '/internal/v1/instrument-state':
        if before_ms is not None:
            raise ValueError('instrument state does not accept a cursor')
        return instrument_state(symbol)
    if route == '/internal/v1/backfill-state':
        if before_ms is not None:
            raise ValueError('backfill state does not accept a cursor')
        return backfill_state(symbol)
    # Dataset contracts awaiting verified provenance and bounded readback.
    # Refuse to reinterpret status/aggregate rows as raw trades, L2 or OI.
    if route in ('/internal/v1/trades', '/internal/v1/orderbook',
                 '/internal/v1/open-interest', '/internal/v1/funding',
                 '/internal/v1/mark-price', '/internal/v1/index-price',
                 '/internal/v1/premium-index'):
        if type(symbol) is not str or not SYMBOL.fullmatch(symbol):
            raise ValueError('invalid instrument identity')
        if isinstance(limit, str) and re.fullmatch(r'[1-9][0-9]{0,3}', limit):
            limit = int(limit)
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('invalid dataset page limit')
        if before_ms is not None:
            if (type(before_ms) is not str or
                    re.fullmatch(r'[1-9][0-9]{0,15}', before_ms) is None):
                raise ValueError('invalid dataset cursor')
        return dict(result, resource=route.rsplit('/', 1)[-1],
                    venue='Bybit', market_type='linear', symbol=symbol,
                    limit=limit, rows=[], next_before_ms=None,
                    representation='NOT_ATTESTED',
                    coverage='NOT_ATTESTED', sequence='NOT_ATTESTED',
                    source_provenance='NOT_ATTESTED',
                    execution_authority=False, trading_authorized=False)
    if route not in ('/internal/v1/candles', '/internal/v1/footprint'):
        raise KeyError('unknown route')
    if not isinstance(symbol, str) or not SYMBOL.fullmatch(symbol):
        raise ValueError('invalid symbol')
    if isinstance(limit, str) and re.fullmatch(r'[1-9][0-9]{0,3}', limit):
        limit = int(limit)
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ValueError('limit must be an integer from 1 to 1000')
    result.update(symbol=symbol, timeframe='1m', rows=[], limit=limit,
                  representation='historical_aggregate')
    from .provenance_gateway import read_snapshot
    return read_snapshot(result, symbol, limit, before_ms, immutable_minutes)

def snapshot(route,symbol='BTCUSDT',limit=300,before_ms=None):
    if route.startswith('/internal/v1/'):
        return qualified_snapshot(route, symbol, limit, before_ms)
    if not SYMBOL.fullmatch(symbol):raise ValueError('invalid symbol')
    limit=max(1,min(int(limit),1000))
    if route=='/v1/instruments':
        return {'version':1,'symbols':[r[0] for r in query('SELECT DISTINCT symbol FROM candles_1m ORDER BY symbol LIMIT 2000')]}
    if route=='/v1/candles':
        rows=query('SELECT extract(epoch from ts)*1000,open,high,low,close,buy_volume,sell_volume,delta,trade_count,poc_price FROM candles_1m WHERE symbol=%s ORDER BY ts DESC LIMIT %s',(symbol,limit))
        return {'version':1,'symbol':symbol,'timeframe':'1m','rows':[dict(zip(('t','o','h','l','c','buy','sell','delta','trades','poc'),map(float,r))) for r in reversed(rows)]}
    if route=='/v1/footprint':
        rows=query('SELECT extract(epoch from ts)*1000,price,buy_volume,sell_volume,delta,volume FROM footprint_1m WHERE symbol=%s ORDER BY ts DESC,price DESC LIMIT %s',(symbol,limit))
        return {'version':1,'symbol':symbol,'rows':[dict(zip(('t','price','buy','sell','delta','volume'),map(float,r))) for r in rows]}
    if route=='/v1/nodes':
        # Cluster inventory and cross-host orchestration belong to Unified System.
        # Keep the legacy route non-disclosing until every consumer migrates.
        return {'version':1,'status':'UNAVAILABLE',
                'reason':'UNIFIED_SYSTEM_NODE_OWNER','nodes':[]}
    raise KeyError(route)

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Request lines may contain tokens; never log caller-controlled paths.
        return

    def handle(self):
        # One absolute deadline covers headers and body, including slow drips.
        def expire():
            try:self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        timer=threading.Timer(3,expire)
        timer.daemon=True
        self.connection.settimeout(3)
        timer.start()
        try:
            super().handle()
        finally:
            timer.cancel()
            timer.join()

    def do_POST(self):
        route=urlsplit(self.path).path
        if route not in ('/internal/v1/research-handoffs/validate',
                         '/internal/v1/history/snapshots/read'):
            self.send_error(404)
            return
        try:
            self.connection.settimeout(3)
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('chunked requests unavailable')
            size = int(self.headers.get('Content-Length', '0'))
            limit = 4096 if route=='/internal/v1/history/snapshots/read' else 8388608
            if not 0 < size <= limit:
                raise ValueError('bounded request required')
            body=self.rfile.read(size)
            if len(body)!=size:
                raise ValueError('truncated request')
            if route=='/internal/v1/history/snapshots/read':
                if self.headers.get('Content-Type')!='application/json':
                    raise ValueError('JSON content type required')
                def unique(pairs):
                    out={}
                    for k,v in pairs:
                        if k in out:raise ValueError('duplicate selection field')
                        out[k]=v
                    return out
                selection=json.loads(body,object_pairs_hook=unique,
                                     parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
                result=pinned_history(selection)
            else:
                from .research_handoff import accept_handoff
                configured = json.loads(os.environ.get('GRID_TRUSTED_RESEARCH_SOURCES', '[]'))
                trusted = {(x['identity'], x['source_revision'], x['run_id'], x['completion_receipt']) for x in configured}
                result = accept_handoff(json.loads(body), trusted)
            status = 200
        except ValueError:
            result,status={'status':'UNAVAILABLE','reason':'INVALID_SNAPSHOT_OR_HANDOFF','execution_authority':False},400
        except Exception:
            if route=='/internal/v1/history/snapshots/read':
                result,status={'status':'UNAVAILABLE','reason':'SOURCE_READ_UNAVAILABLE','execution_authority':False},503
            else:
                result,status={'status':'UNAVAILABLE','reason':'INVALID_HANDOFF_REQUEST','execution_authority':False},400
        data = json.dumps(result,allow_nan=False).encode()
        self.send_response(status)
        self.send_header('Content-Type','application/json')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Length',str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        try:
            if len(self.path.encode('utf-8'))>2048:
                raise ValueError('query too large')
            u=urlsplit(self.path)
            q=parse_qs(u.query,keep_blank_values=True,max_num_fields=3,strict_parsing=True)
            if u.path in ('/internal/v1/backfill-state', '/internal/v1/instrument-state') and set(q) != {'symbol'}:
                raise ValueError('explicit symbol required for Grid backfill state')
            if any(k not in ('symbol','limit','before_ms') or len(v)!=1 for k,v in q.items()):
                raise ValueError('invalid query parameters')
            result=snapshot(u.path,q.get('symbol',['BTCUSDT'])[0],q.get('limit',[300])[0],q.get('before_ms',[None])[0]);status=200
        except (ValueError,KeyError):result={'error':'INVALID_QUERY_OR_ROUTE'};status=400
        except Exception:result={'error':'source unavailable'};status=503
        body=json.dumps(result,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

def main():
    ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('TERMINAN_GRID_PORT','18766'))),Handler).serve_forever()

if __name__=='__main__':main()
