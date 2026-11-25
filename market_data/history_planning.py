"""Caller-declared history query windows; no availability, writer or provider client.

Original planning roles: Strattester13998 readiness.py. Math alone aligns grids.
"""
from dataclasses import dataclass,field
import re
from .timestamp_codec import epoch_milliseconds

_FIELDS=frozenset(('symbol','launchTime','deliveryTime','delistTime','fundingInterval','supportsOpenInterest','supportsFunding','supportsLongShortRatio'))
_DATASETS=frozenset(('candles','mark_price','index_price','premium_index','open_interest','funding','long_short_ratio'))
_MAX_CADENCE=2**53-1 # Representation budget, never a provider interval policy.

def _symbol(value):
    if type(value) is not str or not 2<=len(value)<=30 or re.fullmatch('[A-Z0-9]+',value) is None:raise ValueError('bounded declared instrument symbol required')
    return value

def _strict_clock(value):
    if type(value) is not int:raise ValueError('literal declared clock required')
    return epoch_milliseconds(value)

def _minutes(value):
    if type(value) is str:
        if not 1<=len(value)<=16 or re.fullmatch('[1-9][0-9]{0,15}',value) is None:raise ValueError('canonical cadence minutes required')
        value=int(value)
    if type(value) is not int or not 1<=value<=_MAX_CADENCE:raise ValueError('bounded literal cadence minutes required')
    return value

@dataclass(frozen=True)
class HistoryInstrumentDeclaration:
    symbol:str
    launch_ms:int=0
    delivery_ms:int|None=None
    funding_interval_minutes:int|None=None
    open_interest:bool|None=None
    funding:bool|None=None
    long_short_ratio:bool|None=None
    declared_fields:tuple=()
    schema:str=field(default='market_data.history-instrument-declaration.v1',init=False)
    source_authenticity:str=field(default='NOT_EVALUATED',init=False)
    def __post_init__(self):
        _symbol(self.symbol);_strict_clock(self.launch_ms)
        if self.delivery_ms is not None:_strict_clock(self.delivery_ms)
        if self.funding_interval_minutes is not None:
            if type(self.funding_interval_minutes) is not int:raise ValueError('literal typed cadence required')
            _minutes(self.funding_interval_minutes)
        if any(value is not None and type(value) is not bool for value in (self.open_interest,self.funding,self.long_short_ratio)):raise ValueError('explicit boolean or unknown dataset declarations required')
        if type(self.declared_fields) is not tuple or len(self.declared_fields)>len(_FIELDS) or any(type(key) is not str or len(key)>64 or key not in _FIELDS for key in self.declared_fields) or len(set(self.declared_fields))!=len(self.declared_fields):raise ValueError('bounded declaration field roster required')

def declare_history_instrument(metadata):
    if type(metadata) is not dict or not 1<=len(metadata)<=len(_FIELDS):raise ValueError('closed history instrument declaration required')
    data=metadata.copy()
    if len(data)>len(_FIELDS) or any(type(key) is not str or len(key)>64 or key not in _FIELDS for key in data) or 'symbol' not in data:raise ValueError('closed history instrument declaration required')
    def clock(key,default):
        value=data.get(key)
        return default if value is None or type(value) is str and value=='' else epoch_milliseconds(value)
    launch=clock('launchTime',0);delivery=clock('deliveryTime',None);delist=clock('delistTime',None)
    if delivery==0:delivery=None
    if delist==0:delist=None
    if delivery is not None and delist is not None and delivery!=delist:raise ValueError('conflicting declared lifetime bounds')
    if delivery is None:delivery=delist
    funding=data.get('fundingInterval')
    funding=None if funding is None or type(funding) is str and funding=='' else _minutes(funding)
    return HistoryInstrumentDeclaration(_symbol(data['symbol']),launch,delivery,funding,
        data.get('supportsOpenInterest'),data.get('supportsFunding'),data.get('supportsLongShortRatio'),tuple(sorted(data)))

def declared_dataset_requests(instrument):
    if type(instrument) is not HistoryInstrumentDeclaration:raise ValueError('canonical history instrument declaration required')
    instrument.__post_init__()
    requested={'candles','mark_price','index_price','premium_index'}
    # Unknown support means a request policy, never provider capability evidence.
    if instrument.open_interest is not False:requested.add('open_interest')
    if instrument.funding is True or instrument.funding is None and instrument.funding_interval_minutes is not None:requested.add('funding')
    if instrument.long_short_ratio is not False:requested.add('long_short_ratio')
    return frozenset(requested)

@dataclass(frozen=True)
class HistoryRequest:
    symbol:str
    dataset:str
    timeframe:str
    start_ms:int
    end_ms:int
    coverage:str=field(default='UNKNOWN',init=False)
    readiness:str=field(default='NOT_EVALUATED',init=False)
    def __post_init__(self):
        _symbol(self.symbol)
        if type(self.dataset) is not str or len(self.dataset)>32 or self.dataset not in _DATASETS:raise ValueError('declared dataset required')
        if type(self.timeframe) is not str or not 2<=len(self.timeframe)<=17 or not self.timeframe.endswith('m'):raise ValueError('declared minute timeframe required')
        _minutes(self.timeframe[:-1]);_strict_clock(self.start_ms);_strict_clock(self.end_ms)
        if self.start_ms>self.end_ms:raise ValueError('ordered declared request window required')

@dataclass(frozen=True)
class DeclaredHistoryPlan:
    instrument:HistoryInstrumentDeclaration
    requested_end_ms:int
    effective_end_ms:int
    requests:tuple
    unplanned:tuple
    schema:str=field(default='market_data.history-request-plan.v1',init=False)
    coverage:str=field(default='UNKNOWN',init=False)
    source_authenticity:str=field(default='NOT_EVALUATED',init=False)
    point_in_time_availability:str=field(default='UNKNOWN',init=False)
    readiness:str=field(default='NOT_EVALUATED',init=False)
    execution_authority:bool=field(default=False,init=False)
    trading_authorized:bool=field(default=False,init=False)
    def __post_init__(self):
        if type(self.instrument) is not HistoryInstrumentDeclaration:raise ValueError('canonical instrument declaration required')
        _strict_clock(self.requested_end_ms);_strict_clock(self.effective_end_ms)
        if self.effective_end_ms>self.requested_end_ms:raise ValueError('declared lifetime cannot extend requested horizon')
        if type(self.requests) is not tuple or len(self.requests)>7 or any(type(item) is not HistoryRequest for item in self.requests):raise ValueError('bounded immutable requests required')
        if type(self.unplanned) is not tuple or len(self.unplanned)>7 or any(type(item) is not tuple or len(item)!=2 or type(item[0]) is not str or len(item[0])>32 or item[0] not in _DATASETS or type(item[1]) is not str or len(item[1])>64 or item[1] not in ('CADENCE_UNKNOWN','NO_GRID_SAMPLES_IN_DECLARED_LIFETIME') for item in self.unplanned):raise ValueError('bounded unplanned request reasons required')

def plan_history_requests(instrument,*,end_ms):
    requested=declared_dataset_requests(instrument);end_ms=_strict_clock(end_ms);requested_end_ms=end_ms
    try:from market_math import history_window_ms
    except ImportError:raise RuntimeError('MATH_HISTORY_WINDOW_CAPABILITY_REQUIRED') from None
    if instrument.delivery_ms is not None:end_ms=min(end_ms,instrument.delivery_ms)
    specs=(('candles',1),('mark_price',1),('index_price',1),('premium_index',1),('open_interest',5),('funding',instrument.funding_interval_minutes),('long_short_ratio',5))
    requests=[];unplanned=[]
    for dataset,cadence in specs:
        if dataset not in requested:continue
        if cadence is None:unplanned.append((dataset,'CADENCE_UNKNOWN'));continue
        window=history_window_ms(instrument.launch_ms,end_ms,cadence_minutes=cadence)
        if window is None:unplanned.append((dataset,'NO_GRID_SAMPLES_IN_DECLARED_LIFETIME'));continue
        if type(window) is not tuple or len(window)!=2:raise RuntimeError('MATH_HISTORY_WINDOW_RESULT_INVALID')
        requests.append(HistoryRequest(instrument.symbol,dataset,str(cadence)+'m',window[0],window[1]))
    return DeclaredHistoryPlan(instrument,requested_end_ms,end_ms,tuple(requests),tuple(unplanned))
