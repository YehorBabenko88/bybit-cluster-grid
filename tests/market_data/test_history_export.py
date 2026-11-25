import copy
import unittest
from market_data.provenance import digest
from market_data.history_export import export_records, read_postgres


def fixture(n=80):
    rows=[]; receipts={}
    for i in range(n):
        r={'symbol':'BTCUSDT','start_ms':i*60000,'end_ms':i*60000+59999,
           'source_event_start_ms':i*60000+1,'source_event_end_ms':i*60000+59998,
           'source':{'identity':'fixture','source_revision':'a'*40,'epoch':'fixture-epoch','market_type':'linear'},
           'representation':'historical_aggregate','status':'PARTIAL',
           'candle':{'open':100+i*.1,'high':102+i*.1,'low':99+i*.1,'close':101+i*.1,'buy_volume':2.,'sell_volume':1.}}
        r['dataset_fingerprint']=digest(r); rows.append(r)
        receipts[r['dataset_fingerprint']]={'fingerprint':r['dataset_fingerprint'], 'venue':'bybit',
            'available_at_ms':(i+1)*60000,'complete':True,'watermark_ms':(i+1)*60000,
            'units':{'price':'USDT/BTC','volume':'BTC'},'evidence_class':'SYNTHETIC'}
    req={'schema':'market_data.history.request.v1','venue':'bybit','market_type':'linear','symbol':'BTCUSDT',
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
        self.assertEqual(a['schema'],'market_data.history.v1')
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

        _assert_historical_numeric_delegate_contract(self)

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



def _assert_historical_numeric_delegate_contract(case):
    # Isolated downstream NUMERIC seam: bypass only integrity serialization in
    # this test. Real Decimal/nonfinite canonical rejection is preserved below.
    from decimal import Decimal, localcontext
    from unittest.mock import patch
    import market_data.history_export as owner
    class Truthy:
        def __bool__(self):raise AssertionError('FOREIGN_BOOL_CALLBACK')
    def seam(values, response=True):
        rows,request,trust=fixture(1);row=rows[0]
        old=row['dataset_fingerprint'];receipt=trust['receipts'].pop(old)
        row['dataset_fingerprint']='sealed';receipt['fingerprint']='sealed'
        trust['receipts']={'sealed':receipt};trust['receipt_pins']={'sealed':'sealed'}
        row['candle'].update(zip(('open','high','low','close','buy_volume','sell_volume'),values))
        with patch.object(owner,'canonical',return_value=b'[]'),patch.object(owner,'digest',return_value='sealed'),patch.object(owner,'historical_ohlc_directional_volume_valid',return_value=response) as delegated:
            try:result=owner.export_records(rows,request,trust)
            except ValueError as error:return str(error),delegated.call_count
            return result,delegated.call_count
    for bad in (True,'1',Decimal('1'),float('inf'),float('nan')):
        error,calls=seam((bad,2,1,2,2,1))
        case.assertEqual((error,calls),('NUMERIC',0))
    error,calls=seam((10**1000,2,1,2,2,1))
    case.assertEqual((error,calls),('HISTORY_UNAVAILABLE',0))
    for response in (False,1,Truthy()):
        error,calls=seam((1,2,1,2,2,1),response)
        case.assertEqual((error,calls),('OHLCV',1))
    # Full export with ordinary integrity preflight: patch the actual imported
    # binding and reject nonliteral success without calling foreign __bool__.
    for response in (False,1,Truthy()):
        rows,request,trust=fixture(1);before=copy.deepcopy((rows,request,trust))
        with patch.object(owner,'historical_ohlc_directional_volume_valid',return_value=response) as delegated:
            with case.assertRaisesRegex(ValueError,'^OHLCV$'):owner.export_records(rows,request,trust)
            case.assertEqual(delegated.call_count,1)
        case.assertEqual(before,(rows,request,trust))
    # Isolated seam plus direct real Math preserve the historical numeric domain.
    real=owner.historical_ohlc_directional_volume_valid
    for values in ((1,2,1,2,2,1),(2**53+1,2**53+1,2**53+1,2**53+1,0,0),(5e-324,5e-324,5e-324,5e-324,5e-324,0),(1e308,1e308,1e308,1e308,-0.0,0)):
        with localcontext() as context:
            context.prec=1
            for signal in context.traps:context.traps[signal]=True
            before=dict(context.flags)
            result,calls=seam(values,True)
            case.assertIsInstance(result,dict);case.assertEqual(calls,1)
            case.assertIs(real(*values),True);case.assertEqual(before,dict(context.flags))
    for values in ((1,2,0,2,2,1),(1,2,1,3,2,1),(1,2,1,2,-1,1)):
        case.assertIs(real(*values),False)
    for bad in (Decimal('1'),float('nan')):
        rows,request,trust=fixture(1);rows[0]['candle']['open']=bad
        with patch.object(owner,'historical_ohlc_directional_volume_valid') as delegated:
            with case.assertRaises(ValueError) as raised:owner.export_records(rows,request,trust)
            if type(bad) is Decimal:case.assertEqual(str(raised.exception),'HISTORY_UNAVAILABLE')
            else:case.assertTrue(str(raised.exception).startswith('Out of range float values are not JSON compliant'))
            delegated.assert_not_called()

if __name__=='__main__':unittest.main()
