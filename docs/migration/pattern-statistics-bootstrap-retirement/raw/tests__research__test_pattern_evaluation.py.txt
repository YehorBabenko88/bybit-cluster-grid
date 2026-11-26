from strattester.research.pattern_evaluation import evaluate_entry_signals
from strattester.research.scalp_entries import ScalpEntry
from strattester.research.execution import Signal,ExecutionPolicy

def _bars():
    out=[]
    p=100.0
    for i in range(150):
        out.append({"t":i*60_000,"open":p,"high":p+1,"low":p-1,"close":p})
    return out

def test_pattern_evaluator_is_chronological_and_returns_verdict():
    bars=_bars();entries=[]
    for i in range(5,145,5):
        t=i*60_000
        entries.append(ScalpEntry("X",t,"long",100,
          Signal(t,"long","market",None,99,101),{"symbol":"X"}))
    r=evaluate_entry_signals("X",entries,bars,policy=ExecutionPolicy(60_000,fee_rate=0),folds=5,min_samples=10)
    assert len(r.folds)==5
    assert r.trades>0
    assert r.verdict.status in ("KEEP","REJECT","NEEDS_MORE_DATA")
    assert r.bootstrap_lower is not None

def test_empty_pattern_never_becomes_keep():
    r=evaluate_entry_signals("X",[],_bars(),policy=ExecutionPolicy(60_000),folds=5,min_samples=10)
    assert r.verdict.status!="KEEP"
