"""Closed v1.2 turnover declarations and literal snapshot policy; no IO."""
import json,re
from decimal import Decimal
TURNOVER_BASIS='EXECUTED_TRADE_PRICE_TIMES_QUANTITY_SUM'
AVAILABILITY_BASIS='CALLER_DECLARED_NOT_COMMIT_OR_PIT'
FINANCIAL_ENCODING='FINITE_BINARY64_DTO_FROM_EXACT_DECIMAL_ACCUMULATION'

def _snapshot_json(value,*,max_bytes=8388608):
    remaining=max_bytes;nodes=0
    def charge(size):
        nonlocal remaining
        remaining-=size
        if remaining<0:raise ValueError('TURNOVER_HISTORY_BYTE_BUDGET')
    def copy(item,depth):
        nonlocal nodes
        nodes+=1
        if nodes>250000 or depth>16:raise ValueError('TURNOVER_HISTORY_GRAPH_BUDGET')
        kind=type(item)
        if item is None or kind is bool or kind is int or kind is float or kind is str:
            if kind is int and item.bit_length()>1024:raise ValueError('TURNOVER_HISTORY_INTEGER_BUDGET')
            if kind is str and len(item)>max_bytes:raise ValueError('TURNOVER_HISTORY_STRING_BUDGET')
            try:raw=json.dumps(item,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')
            except (ValueError,TypeError,OverflowError):raise ValueError('TURNOVER_HISTORY_LITERAL_VALUE_REQUIRED') from None
            charge(len(raw));return item
        if kind is list or kind is tuple:
            if len(item)>250000:raise ValueError('TURNOVER_HISTORY_GRAPH_BUDGET')
            charge(2+max(0,len(item)-1));out=[copy(child,depth+1) for child in item]
            return tuple(out) if kind is tuple else out
        if kind is dict:
            if len(item)>250000:raise ValueError('TURNOVER_HISTORY_GRAPH_BUDGET')
            if any(type(key) is not str or not 1<=len(key)<=128 for key in item):raise ValueError('TURNOVER_HISTORY_LITERAL_KEY_REQUIRED')
            charge(2+max(0,len(item)-1)+len(item));out={}
            for key,child in item.items():
                charge(len(json.dumps(key,ensure_ascii=True).encode('ascii')));out[key]=copy(child,depth+1)
            return out
        raise ValueError('TURNOVER_HISTORY_LITERAL_VALUE_REQUIRED')
    return copy(value,0)

def _clock(value):
    if type(value) is not int or not 0<=value<=2**53-1:raise ValueError('TURNOVER_HISTORY_LITERAL_CLOCK_REQUIRED')
    return value

def _units(value):
    if type(value) is not dict or len(value)!=3 or any(type(k) is not str or k not in ('price','volume','turnover') for k in value):raise ValueError('TURNOVER_HISTORY_EXPLICIT_QUOTE_UNITS_REQUIRED')
    if any(type(value[k]) is not str or re.fullmatch('[A-Z0-9][A-Z0-9_.-]{0,31}',value[k]) is None for k in ('volume','turnover')):raise ValueError('TURNOVER_HISTORY_LITERAL_UNIT_REQUIRED')
    if type(value['price']) is not str or value['price']!=value['turnover']+'/'+value['volume']:raise ValueError('TURNOVER_HISTORY_UNIT_RELATION_REQUIRED')
    return dict(value)

def _version(value):
    if type(value) is not dict or len(value)!=2 or any(type(k) is not str or k not in ('major','minor') for k in value):raise ValueError('TURNOVER_HISTORY_RECORD_VERSION_REQUIRED')
    if type(value['major']) is not int or type(value['minor']) is not int or value['major']!=1 or value['minor']!=2:raise ValueError('TURNOVER_HISTORY_RECORD_VERSION_REQUIRED')

def _number(value):
    if type(value) is not int and type(value) is not float:raise ValueError('TURNOVER_HISTORY_LITERAL_AMOUNT_REQUIRED')
    from market_math import lossless_nonnegative_binary64_valid
    if lossless_nonnegative_binary64_valid(value) is not True:raise ValueError('TURNOVER_HISTORY_LITERAL_AMOUNT_REQUIRED')
    return value

def _candle(candle):
    from market_math import candle_ohlcv_turnover_valid,executed_notional_consistent
    from .numeric_dto import volume_total
    values=tuple(_number(candle[k]) for k in ('open','high','low','close','buy_volume','sell_volume','turnover'))
    volume=volume_total(values[4:6])
    if executed_notional_consistent(values[6],volume) is not True:raise ValueError('TURNOVER_HISTORY_EXECUTED_NOTIONAL_CONSISTENCY')
    if candle_ohlcv_turnover_valid(*(Decimal(str(v)) for v in values[:4]),Decimal(str(volume)),turnover=Decimal(str(values[6]))) is not True:raise ValueError('TURNOVER_HISTORY_OHLCV_DOMAIN')

def _record(value):
    for key,expected in (('producer','market_data'),('timeframe','1m'),('representation','historical_aggregate')):
        if type(value[key]) is not str or value[key]!=expected:raise ValueError('TURNOVER_HISTORY_RECORD_FAMILY_REQUIRED')
    _version(value['api_version']);_units(value['units'])
    start=_clock(value['start_ms']);end=_clock(value['end_ms']);known=_clock(value['available_at_ms'])
    source_start=_clock(value['source_event_start_ms']);source_end=_clock(value['source_event_end_ms']);ingestion=_clock(value['ingestion_ms'])
    if start%60000 or end!=start+59999 or not start<=source_start<=source_end<=end or ingestion<source_end:raise ValueError('TURNOVER_HISTORY_RECORD_CLOCKS_REQUIRED')
    if known<end+1:raise ValueError('TURNOVER_HISTORY_AVAILABILITY_REQUIRED')
    for key,expected in (('turnover_basis',TURNOVER_BASIS),('availability_basis',AVAILABILITY_BASIS),('financial_encoding',FINANCIAL_ENCODING),('source_authentication','NOT_EVALUATED')):
        if type(value[key]) is not str or value[key]!=expected:raise ValueError('TURNOVER_HISTORY_DECLARATION_REQUIRED')
    if value['execution_authority'] is not False or value['trading_authorized'] is not False:raise ValueError('TURNOVER_HISTORY_NOT_AUTHORITY')
    _candle(value['candle'])
