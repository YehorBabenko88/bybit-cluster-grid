"""Read-only snapshot service for Terminan. No exchange subscriptions or writes.

Run inside the existing Grid environment with psycopg installed. Bind to loopback.
Set TERMINAN_GRID_DSN to a dedicated read-only PostgreSQL role.
"""
import json
import os
import re
from decimal import Decimal
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urlsplit,parse_qs

SYMBOL=re.compile(r'^[A-Z0-9]{2,30}$')


def market_decimal(value):
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError('non-finite market numeric')
    return format(value, 'f')


def epoch_milliseconds(value):
    stamp = int(value)
    if stamp != value or abs(stamp) > 2**53 - 1:
        raise ValueError('invalid epoch milliseconds')
    return stamp

def query(sql,args=()):
    import psycopg
    dsn=os.environ['TERMINAN_GRID_DSN']
    with psycopg.connect(dsn,connect_timeout=3,options='-c default_transaction_read_only=on -c statement_timeout=3000') as conn:
        with conn.cursor() as cur:
            cur.execute(sql,args)
            return cur.fetchall()

def snapshot(route,symbol='BTCUSDT',limit=300):
    if not SYMBOL.fullmatch(symbol):raise ValueError('invalid symbol')
    limit=max(1,min(int(limit),1000))
    if route=='/v1/instruments':
        return {'version':1,'symbols':[r[0] for r in query('SELECT DISTINCT symbol FROM candles_1m ORDER BY symbol LIMIT 2000')]}
    if route in ('/v1/candles', '/v2/candles'):
        rows=query("""SELECT extract(epoch from ts)*1000,open,high,low,close,buy_volume,sell_volume,
                      delta,trade_count,poc_price,COALESCE(to_jsonb(c)->>'quality_status','UNKNOWN'),
                      COALESCE(to_jsonb(c)->'quality_reasons','[]'::jsonb)
                      FROM candles_1m c WHERE symbol=%s ORDER BY ts DESC LIMIT %s""",(symbol,limit))
        fields = ('o', 'h', 'l', 'c', 'buy', 'sell', 'delta')
        return {'version':2, 'symbol':symbol, 'timeframe':'1m',
                'provenance':{'owner':'Grid','dataset':'candles_1m','timestamp':'unix_ms_utc'}, 'rows':[
            {'t': epoch_milliseconds(row[0]), **dict(zip(fields, map(market_decimal, row[1:8]))),
             'trades': row[8], 'poc': market_decimal(row[9]),
             'quality_status': row[10], 'quality_reasons': row[11]}
            for row in reversed(rows)
        ]}
    if route in ('/v1/footprint', '/v2/footprint'):
        rows=query('SELECT extract(epoch from ts)*1000,price,buy_volume,sell_volume,delta,volume FROM footprint_1m WHERE symbol=%s ORDER BY ts DESC,price DESC LIMIT %s',(symbol,limit+1))
        fields = ('price', 'buy', 'sell', 'delta', 'volume')
        truncated = len(rows) > limit
        boundary_partial = truncated and rows[limit-1][0] == rows[limit][0]
        return {'version':2, 'symbol':symbol, 'timeframe':'1m',
                'provenance':{'owner':'Grid','dataset':'footprint_1m','timestamp':'unix_ms_utc'},
                'coverage':{'status':'PARTIAL', 'reason':'EXCHANGE_COMPLETENESS_UNATTESTED',
                            'row_limit_reached':truncated,
                            'partial_bucket_t':epoch_milliseconds(rows[limit][0]) if boundary_partial else None}, 'rows':[
            {'t': epoch_milliseconds(row[0]), **dict(zip(fields, map(market_decimal, row[1:])))}
            for row in rows[:limit]
        ]}
    if route=='/v1/nodes':
        rows=query('SELECT node_id,hostname,last_seen,cpu_pct,ram_pct,disk_free,assigned_symbols FROM nodes ORDER BY node_id LIMIT 200')
        return {'version':1,'nodes':[dict(node_id=r[0],hostname=r[1],last_seen=r[2].isoformat() if r[2] else None,cpu_pct=float(r[3]) if r[3] is not None else None,ram_pct=float(r[4]) if r[4] is not None else None,disk_free_bytes=r[5],assigned_symbols=r[6]) for r in rows]}
    raise KeyError(route)

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        u=urlsplit(self.path);q=parse_qs(u.query)
        try:
            result=snapshot(u.path,q.get('symbol',['BTCUSDT'])[0],q.get('limit',[300])[0]);status=200
            body=json.dumps(result,allow_nan=False).encode()
        except (ValueError,KeyError) as e:result={'error':str(e)};status=400
        except Exception:result={'error':'source unavailable'};status=503
        if status != 200:
            body=json.dumps(result,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)

def main():
    ThreadingHTTPServer(('127.0.0.1',int(os.environ.get('TERMINAN_GRID_PORT','18766'))),Handler).serve_forever()

if __name__=='__main__':main()
