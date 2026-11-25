from __future__ import annotations
from dataclasses import dataclass, field

@dataclass(frozen=True)
class ExecutionPolicy:
    bar_ms:int
    fee_rate:float=.00055
    slippage_bps:float=0.0
    ambiguous_policy:str='SL_FIRST'
    position_usd:float=100.0

@dataclass(frozen=True)
class Signal:
    decision_time:int
    side:str
    entry_kind:str
    entry_price:float|None
    stop_loss:float
    take_profit:float

@dataclass(frozen=True)
class ResearchTrade:
    side:str
    entry_time:int
    entry_price:float
    exit_time:int
    exit_price:float
    exit_reason:str
    gross_pnl:float
    fees:float
    net_pnl:float
    metadata:dict=field(default_factory=dict)

def _adverse(price:float,side:str,bps:float,entry:bool)->float:
    k=bps/10000.0
    if side=='long':
        return price*(1+k if entry else 1-k)
    return price*(1-k if entry else 1+k)

def simulate_trade(signal:Signal,bars,policy:ExecutionPolicy,metadata=None)->ResearchTrade:
    if signal.side not in ('long','short'): raise ValueError('side')
    if signal.entry_kind not in ('market','limit'): raise ValueError('entry_kind')
    rows=list(bars)
    entry_idx=None; raw_entry=None; entry_at_open=True
    for i,b in enumerate(rows):
        earliest = signal.decision_time if signal.entry_kind=='market' else signal.decision_time + policy.bar_ms
        if b['t'] < earliest: continue
        if signal.entry_kind=='market':
            entry_idx=i; raw_entry=float(b['open']); break
        p=float(signal.entry_price)
        o=float(b['open']); h=float(b['high']); l=float(b['low'])
        if signal.side=='long':
            if o<=p:
                entry_idx=i; raw_entry=o; break
            if l<=p<=h:
                entry_idx=i; raw_entry=p; entry_at_open=False; break
        else:
            if o>=p:
                entry_idx=i; raw_entry=o; break
            if l<=p<=h:
                entry_idx=i; raw_entry=p; entry_at_open=False; break
    if entry_idx is None: raise ValueError('entry not filled')
    entry=_adverse(raw_entry,signal.side,policy.slippage_bps,True)
    exit_time=None; raw_exit=None; reason=None
    for i,b in enumerate(rows[entry_idx:],start=entry_idx):
        o=float(b['open']); h=float(b['high']); l=float(b['low'])
        # The opening price precedes an intrabar limit fill. Only positions
        # already filled at this bar's open can experience an opening gap.
        opening_gap=i>entry_idx or entry_at_open
        if signal.side=='long':
            if opening_gap and o <= signal.stop_loss:
                raw_exit=o; reason='SL_GAP'
            elif opening_gap and o >= signal.take_profit:
                raw_exit=signal.take_profit; reason='TP_GAP'
            else:
                hit_sl=l <= signal.stop_loss
                hit_tp=h >= signal.take_profit
                if hit_sl and hit_tp:
                    raw_exit=signal.stop_loss if policy.ambiguous_policy=='SL_FIRST' else signal.take_profit
                    reason='SL' if policy.ambiguous_policy=='SL_FIRST' else 'TP'
                elif hit_sl:
                    raw_exit=signal.stop_loss; reason='SL'
                elif hit_tp:
                    raw_exit=signal.take_profit; reason='TP'
        else:
            if opening_gap and o >= signal.stop_loss:
                raw_exit=o; reason='SL_GAP'
            elif opening_gap and o <= signal.take_profit:
                raw_exit=signal.take_profit; reason='TP_GAP'
            else:
                hit_sl=h >= signal.stop_loss
                hit_tp=l <= signal.take_profit
                if hit_sl and hit_tp:
                    raw_exit=signal.stop_loss if policy.ambiguous_policy=='SL_FIRST' else signal.take_profit
                    reason='SL' if policy.ambiguous_policy=='SL_FIRST' else 'TP'
                elif hit_sl:
                    raw_exit=signal.stop_loss; reason='SL'
                elif hit_tp:
                    raw_exit=signal.take_profit; reason='TP'
        if reason:
            exit_time=b['t']; break
    if reason is None:
        b=rows[-1]; raw_exit=float(b['close']); exit_time=b['t']; reason='EOD'
    exit_price=_adverse(float(raw_exit),signal.side,policy.slippage_bps,False)
    qty=policy.position_usd/entry if entry else 0.0
    gross=(exit_price-entry)*qty if signal.side=='long' else (entry-exit_price)*qty
    fees=(entry+exit_price)*qty*policy.fee_rate
    return ResearchTrade(signal.side,rows[entry_idx]['t'],entry,exit_time,exit_price,reason,gross,fees,gross-fees,dict(metadata or {}))


@dataclass(frozen=True)
class ScaleSignal:
    decision_time:int
    side:str
    entries:tuple[tuple[float,float],...]
    stop_loss:float
    take_profits:tuple[tuple[float,float],...]
    move_stop_to_entry_after_tp1:bool=False

@dataclass(frozen=True)
class ExecutionFill:
    time:int
    price:float
    quantity:float
    fraction:float

@dataclass(frozen=True)
class ExecutionExit:
    time:int
    price:float
    quantity:float
    reason:str

@dataclass(frozen=True)
class ScaleTrade:
    side:str
    fills:tuple[ExecutionFill,...]
    exits:tuple[ExecutionExit,...]
    gross_pnl:float
    fees:float
    net_pnl:float

def simulate_scale_trade(signal:ScaleSignal,bars,policy:ExecutionPolicy)->ScaleTrade:
    if signal.side not in ('long','short'): raise ValueError('side')
    if not signal.entries or abs(sum(x[1] for x in signal.entries)-1.0)>1e-9: raise ValueError('entry fractions')
    if not signal.take_profits or abs(sum(x[1] for x in signal.take_profits)-1.0)>1e-9: raise ValueError('target fractions')
    rows=list(bars); fills=[]; exits=[]; pending=list(enumerate(signal.entries))
    target_idx=0; remaining_qty=0.0; first_allowed=signal.decision_time+policy.bar_ms; active_stop=float(signal.stop_loss)
    for b in rows:
        if b['t']<first_allowed: continue
        o=float(b['open']); h=float(b['high']); l=float(b['low']); filled_now=False
        still=[]
        for leg,(price,fraction) in pending:
            hit=(o<=price or l<=price<=h) if signal.side=='long' else (o>=price or l<=price<=h)
            if not hit:
                still.append((leg,(price,fraction))); continue
            raw=o if ((signal.side=='long' and o<=price) or (signal.side=='short' and o>=price)) else float(price)
            px=_adverse(raw,signal.side,policy.slippage_bps,True)
            qty=(policy.position_usd*fraction)/px
            fills.append(ExecutionFill(b['t'],px,qty,fraction)); remaining_qty+=qty; filled_now=True
        pending=still
        # With OHLC data the path inside a fill bar is unknowable. Do not grant
        # optimistic survival: evaluate the stop on the fill bar (SL-first).
        if remaining_qty<=0: continue
        stop_gap=(o<=active_stop) if signal.side=='long' else (o>=active_stop)
        stop_hit=(l<=active_stop) if signal.side=='long' else (h>=active_stop)
        if stop_gap or stop_hit:
            raw=o if stop_gap else active_stop
            px=_adverse(float(raw),signal.side,policy.slippage_bps,False)
            exits.append(ExecutionExit(b['t'],px,remaining_qty,'SL')); remaining_qty=0.0
            break
        if target_idx<len(signal.take_profits):
            target,fraction=signal.take_profits[target_idx]
            target_hit=(o>=target or h>=target) if signal.side=='long' else (o<=target or l<=target)
            if target_hit:
                total_filled=sum(x.quantity for x in fills)
                q=min(remaining_qty,total_filled*fraction)
                px=_adverse(float(target),signal.side,policy.slippage_bps,False)
                exits.append(ExecutionExit(b['t'],px,q,f'TP{target_idx+1}')); remaining_qty-=q; target_idx+=1
                if signal.move_stop_to_entry_after_tp1 and target_idx==1 and remaining_qty>0:
                    active_stop=sum(x.price*x.quantity for x in fills)/sum(x.quantity for x in fills)
    if remaining_qty>1e-12:
        b=rows[-1]; px=_adverse(float(b['close']),signal.side,policy.slippage_bps,False)
        exits.append(ExecutionExit(b['t'],px,remaining_qty,'EOD'))
    if not fills: raise ValueError('entry not filled')
    total_qty=sum(x.quantity for x in fills)
    avg_entry=sum(x.price*x.quantity for x in fills)/total_qty
    gross=sum((x.price-avg_entry)*x.quantity if signal.side=='long' else (avg_entry-x.price)*x.quantity for x in exits)
    fees=(sum(x.price*x.quantity for x in fills)+sum(x.price*x.quantity for x in exits))*policy.fee_rate
    return ScaleTrade(signal.side,tuple(fills),tuple(exits),gross,fees,gross-fees)

