import copy
import unittest
from grid.provenance import digest
from grid.history_export import export_records, read_postgres


def fixture(n=80):
    rows=[]; receipts={}
    for i in range(n):
        r={'symbol':'BTCUSDT','start_ms':i*60000,'end_ms':i*60000+59999,
           'source':{'identity':'fixture','source_revision':'a'*40,'epoch':'fixture-epoch','market_type':'linear'},
           'representation':'historical_aggregate','status':'PARTIAL',
           'candle':{'open':100+i*.1,'high':102+i*.1,'low':99+i*.1,'close':101+i*.1,'buy_volume':2.,'sell_volume':1.}}
        r['dataset_fingerprint']=digest(r); rows.append(r)
        receipts[r['dataset_fingerprint']]={'fingerprint':r['dataset_fingerprint'], 'venue':'bybit',
            'available_at_ms':(i+1)*60000,'complete':True,'watermark_ms':(i+1)*60000,
            'units':{'price':'USDT/BTC','volume':'BTC'},'evidence_class':'SYNTHETIC'}
    req={'schema':'grid.history.request.v1','venue':'bybit','market_type':'linear','symbol':'BTCUSDT',
         'start_ms':0,'end_ms':n*60000,'as_of_ms':n*60000,'max_age_ms':60000,
         'units':{'price':'USDT/BTC','volume':'BTC'}}
    trust={'identity':'fixture','source_revision':'a'*40,'epoch':'fixture-epoch',
           'receipts':receipts,'receipt_pins':{k:digest(v) for k,v in receipts.items()},'evidence_class':'SYNTHETIC'}
    return rows,req,trust


class ExportTest(unittest.TestCase):
    def test_valid_and_reproducible(self):
        rows,req,trust=fixture()
        a=export_records(rows,req,trust)
        self.assertEqual(a,export_records(rows,req,trust))
        self.assertEqual(a['schema'],'grid.history.v1')
        self.assertEqual(a['evidence_class'],'SYNTHETIC')
        self.assertFalse(a['trading_authorized'])

    def test_fail_closed(self):
        mutations=[lambda r,q,t:r.pop(), lambda r,q,t:r.append(r[-1]),
          lambda r,q,t:r[0]['candle'].update(close=999),lambda r,q,t:t.update(receipt_pins={}),
          lambda r,q,t:q.update(symbol='ETHUSDT'), lambda r,q,t:q.update(units={'price':'USD/BTC','volume':'BTC'}),
          lambda r,q,t:q.update(as_of_ms=999999999),lambda r,q,t:t.update(identity='forged'),
          lambda r,q,t:next(iter(t['receipts'].values())).update(available_at_ms=999999999),
          lambda r,q,t:t.update(evidence_class='HISTORICAL')]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                r,q,t=fixture(); mutate(r,q,t)
                with self.assertRaises(ValueError):export_records(r,q,t)

    def test_readonly_sql(self):
        r,q,t=fixture()
        class Cursor:
            def __enter__(s):return s
            def __exit__(s,*args):pass
            def execute(s,sql,args=None):s.calls.append((sql,args))
            def fetchall(s):return [(x,) for x in r]
        c=Cursor();c.calls=[]
        class Conn:
            def cursor(s):return c
        self.assertEqual(len(read_postgres(Conn(),q,t)['rows']),80)
        self.assertIn('REPEATABLE READ READ ONLY',c.calls[0][0])
        self.assertIn('provenance_minutes',c.calls[-1][0])

if __name__=='__main__':unittest.main()
