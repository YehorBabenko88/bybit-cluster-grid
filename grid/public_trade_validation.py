"""Admission bounds for the existing public-trade collector; no feed engine."""
import json
import math

from .models import Trade

MAX_FRAME_BYTES=1024*1024
MAX_BATCH_TRADES=1024
MAX_ACK_FRAMES=2000
MAX_ACK_BYTES=4*1024*1024
MAX_OPEN_MINUTES=1024
PERSIST_TIMEOUT_SECONDS=20


def decode_frame(raw):
    if not isinstance(raw,(str,bytes)):
        raise ValueError('invalid public trade frame')
    if len(raw)>MAX_FRAME_BYTES:raise ValueError('public trade frame byte limit')
    size=len(raw.encode('utf-8')) if isinstance(raw,str) else len(raw)
    if size>MAX_FRAME_BYTES:raise ValueError('public trade frame byte limit')
    def nonfinite(_):raise ValueError('nonfinite public JSON')
    try:message=json.loads(raw,parse_constant=nonfinite)
    except (ValueError,UnicodeError,RecursionError) as exc:raise ValueError('invalid public trade JSON') from exc
    if not isinstance(message,dict):raise ValueError('invalid public trade envelope')
    return message,size


def parse_trades(message,symbol,now_ms):
    """Validate the complete batch before any continuity/aggregate mutation."""
    if message.get('topic')!='publicTrade.'+symbol:raise ValueError('unsubscribed trade topic')
    batch=message.get('data')
    if not isinstance(batch,list) or len(batch)>MAX_BATCH_TRADES:raise ValueError('invalid public trade batch')
    trades=[]
    for item in batch:
        if not isinstance(item,dict) or ('s' in item and item['s']!=symbol):raise ValueError('invalid public trade symbol')
        stamp=item.get('T')
        if isinstance(stamp,str) and 0<len(stamp)<=20 and stamp.isascii() and stamp.isdecimal():stamp=int(stamp)
        if type(stamp) is not int or stamp<=0 or stamp>now_ms+300000:raise ValueError('invalid public trade timestamp')
        values=[]
        for key in ('p','v'):
            value=item.get(key)
            if isinstance(value,bool) or not isinstance(value,(int,float,str)) or (isinstance(value,str) and len(value)>64):raise ValueError('invalid public trade numeric')
            try:value=float(value)
            except (ValueError,TypeError,OverflowError) as exc:raise ValueError('invalid public trade numeric') from exc
            if not math.isfinite(value) or value<=0:raise ValueError('invalid public trade numeric')
            values.append(value)
        side=item.get('S');trade_id=item.get('i')
        if side not in ('Buy','Sell') or not isinstance(trade_id,str) or not 0<len(trade_id)<=128:raise ValueError('invalid public trade side or identity')
        trades.append(Trade(symbol,stamp,values[0],values[1],side,trade_id))
    return trades


def validated_tick(value):
    if isinstance(value,bool):raise ValueError('invalid public trade tick')
    try:value=float(value)
    except (ValueError,TypeError,OverflowError) as exc:raise ValueError('invalid public trade tick') from exc
    if not math.isfinite(value) or value<=0:raise ValueError('invalid public trade tick')
    return value


def preflight_footprint(trades,builder):
    """Simulate finite arithmetic without mutating buckets, IDs or continuity."""
    tick=validated_tick(builder.tick_size);states={};batch_volume=0.;accepted=[]
    for trade in trades:
        start=(trade.ts_ms//builder.interval_ms)*builder.interval_ms
        if start<=builder.finalized_through_ms.get(trade.symbol,-1):continue
        old=builder.buckets.get((trade.symbol,start))
        if old is not None and trade.trade_id in old['seen_trade_ids']:continue
        state=states.setdefault((trade.symbol,start),{'buy':old['buy'] if old else 0.,
            'sell':old['sell'] if old else 0.,'ids':set(),'levels':{}})
        if trade.trade_id in state['ids']:continue
        state['ids'].add(trade.trade_id)
        batch_volume+=trade.qty
        if not math.isfinite(batch_volume):raise ValueError('public trade batch volume overflow')
        try:
            quotient=trade.price/tick
            if not math.isfinite(quotient):raise ValueError('public trade price/tick overflow')
            key=round(quotient);price=key*tick
            if not math.isfinite(price) or price<=0:raise ValueError('public trade rounded price overflow')
        except (OverflowError,ZeroDivisionError) as exc:raise ValueError('public trade price/tick overflow') from exc
        if key not in state['levels']:
            level=old['levels'].get(key) if old else None
            state['levels'][key]=[level.buy_qty if level else 0.,level.sell_qty if level else 0.]
        index=0 if trade.side=='Buy' else 1
        side='buy' if index==0 else 'sell'
        state[side]+=trade.qty;state['levels'][key][index]+=trade.qty
        values=(state['buy'],state['sell'],state['buy']+state['sell'],*state['levels'][key],sum(state['levels'][key]))
        if not all(math.isfinite(value) for value in values):raise ValueError('public trade aggregate volume overflow')
        accepted.append(trade)
    return accepted


_TAPE_BUCKET_KEYS=frozenset(('start_ms','open','high','low','close','buy_volume','sell_volume','buy_count','sell_count','trade_count'))
_TAPE_DERIVED_KEYS=frozenset(('delta','cvd','range','aggressor_imbalance'))


def _finite(value):
    if type(value) not in (int,float):return False
    try:return math.isfinite(value)
    except OverflowError:return False


def _tape_bucket(row,bucket_ms):
    # Inspect the fixed ten-field kernel record before copying any values.
    if type(row) is not dict or len(row)!=len(_TAPE_BUCKET_KEYS) or set(row)!=_TAPE_BUCKET_KEYS:
        raise ValueError('unknown public tape state')
    for key in ('start_ms','buy_count','sell_count','trade_count'):
        value=row[key]
        if type(value) is not int or value<0 or value.bit_length()>63:raise ValueError('invalid public tape integer')
    if row['start_ms']%bucket_ms or row['trade_count']!=row['buy_count']+row['sell_count']:raise ValueError('invalid public tape state')
    if not all(_finite(row[key]) for key in ('open','high','low','close','buy_volume','sell_volume')):raise ValueError('nonfinite public tape state')
    if not 0<row['low']<=min(row['open'],row['close'])<=max(row['open'],row['close'])<=row['high']:raise ValueError('invalid public tape prices')
    if min(row['buy_volume'],row['sell_volume'])<0:raise ValueError('invalid public tape volume')
    if not _finite(row['buy_volume']+row['sell_volume']):raise ValueError('public tape volume overflow')


def _tape_output(row,bucket_ms):
    if type(row) is not dict or len(row)!=14 or set(row)!=_TAPE_BUCKET_KEYS|_TAPE_DERIVED_KEYS:raise ValueError('unknown public tape output')
    _tape_bucket({key:row[key] for key in _TAPE_BUCKET_KEYS},bucket_ms)
    if not all(_finite(row[key]) for key in _TAPE_DERIVED_KEYS):raise ValueError('nonfinite public tape output')


def preflight_tape(trades,tape,symbol):
    """Reuse the actual kernel on only this symbol's bounded isolated state."""
    from .micro_tape import MicroTapeAggregator
    if type(tape) is not MicroTapeAggregator or type(tape.state) is not dict or type(tape.cvd) is not dict:
        raise ValueError('unknown public tape kernel')
    if type(trades) is not list or len(trades)>MAX_BATCH_TRADES:raise ValueError('public tape batch limit')
    bucket=tape.bucket_ms
    if type(bucket) is not int or bucket<50 or bucket.bit_length()>63:raise ValueError('invalid public tape bucket')
    cvd=tape.cvd.get(symbol,0.)
    if not _finite(cvd):raise ValueError('nonfinite public tape CVD')
    shadow=MicroTapeAggregator(bucket);shadow.cvd[symbol]=cvd
    row=tape.state.get(symbol)
    if row is not None:
        _tape_bucket(row,bucket);shadow.state[symbol]=row.copy()

    def prospective_flush():
        current=shadow.state.get(symbol)
        if current is None:return
        _tape_bucket(current,bucket)
        probe=MicroTapeAggregator(bucket)
        probe.state[symbol]=current.copy();probe.cvd[symbol]=shadow.cvd.get(symbol,0.)
        # Reuse _finalize via flush: no separate CVD formula or silent clamp.
        _tape_output(probe.flush(symbol),bucket)

    prospective_flush()
    for trade in trades:
        output=shadow.add(trade)
        if output is not None:_tape_output(output,bucket)
        if not _finite(shadow.cvd.get(symbol,0.)):raise ValueError('nonfinite public tape CVD')
        prospective_flush()
