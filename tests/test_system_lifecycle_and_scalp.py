import asyncio
import pytest
from grid.system_lifecycle import PHASES,phase_capabilities
from grid.historical_science_import import verify_bundle,canonical_payload
from grid.scalp_ontology import ScalpContext,validate_context
import hashlib,json

def test_phase_order_and_capabilities():
    assert PHASES[0]=="INFRASTRUCTURE" and PHASES[-1]=="PAPER_TRADING"
    assert not phase_capabilities("INFRASTRUCTURE")["paper"]
    assert phase_capabilities("PAPER_TRADING")["paper"]

def test_historical_bundle_rejects_fabricated_l2():
    b={"schema":1,"source":"strattester","created_at":1.0,
       "research_scope":"HISTORICAL_BOOTSTRAP_ONLY",
       "capabilities":{"candles":True,"open_interest":True,"public_trade_aggregates":True,
                       "true_l2_orderbook":True,"liquidations":False,"true_l2_absorption":False},
       "symbols":[]}
    b["sha256"]=hashlib.sha256(canonical_payload(b).encode()).hexdigest()
    ok,reason=verify_bundle(b)
    assert not ok and "fabricated" in reason

def test_historical_scalp_context_cannot_claim_live_only_fields():
    ctx=ScalpContext("BTC",1,"swing_high",100,1,"LEVEL_APPROACH",
                     {"book_imbalance":.5},{})
    ok,reason=validate_context(ctx,historical=True)
    assert not ok and "live-only" in reason

def test_telegram_has_three_sections():
    from pathlib import Path
    t=Path("grid/telegram_bot.py").read_text(encoding="utf-8")
    assert "УПРАВЛЕНИЕ" in t and "СИМУЛЯЦИЯ" in t and "НАУКА" in t
    assert "/simstatus" in t and "/sciencestatus" in t and "/phase" in t
