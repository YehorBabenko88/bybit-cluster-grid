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


