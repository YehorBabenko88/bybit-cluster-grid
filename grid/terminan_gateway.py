"""Read-only snapshot service for Terminan. No exchange subscriptions or writes.

Run inside the existing Grid environment with psycopg installed. Bind to loopback.
Set TERMINAN_GRID_DSN to a dedicated read-only PostgreSQL role.
"""
import json
import os
import re
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


def qualified_snapshot(route, symbol, limit):
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
                                  'footprint': 'UNAVAILABLE', 'live_l2': False}
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
    return result

def snapshot(route,symbol='BTCUSDT',limit=300):
    if route.startswith('/internal/v1/'):
        return qualified_snapshot(route, symbol, limit)
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
        rows=query('SELECT node_id,hostname,last_seen,cpu_pct,ram_pct,disk_free,assigned_symbols FROM nodes ORDER BY node_id LIMIT 200')
        return {'version':1,'nodes':[dict(node_id=r[0],hostname=r[1],last_seen=r[2].isoformat() if r[2] else None,cpu_pct=float(r[3]) if r[3] is not None else None,ram_pct=float(r[4]) if r[4] is not None else None,disk_free_bytes=r[5],assigned_symbols=r[6]) for r in rows]}
    raise KeyError(route)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u=urlsplit(self.path);q=parse_qs(u.query)
        try:
            result=snapshot(u.path,q.get('symbol',['BTCUSDT'])[0],q.get('limit',[300])[0]);status=200
        except (ValueError,KeyError) as e:result={'error':str(e)};status=400
        except Exception:result={'error':'source unavailable'};status=503
        body=json.dumps(result,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

def main():
    ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('TERMINAN_GRID_PORT','18766'))),Handler).serve_forever()

if __name__=='__main__':main()
