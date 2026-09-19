from .conditional_markov import ConditionalMarkov
from .markov_strategy_context import markov_context

REGIME_ALLOWED={
 "POC":{"HIGH_VOL","IMPULSE"},
 "BREAKOUT":{"EXPANDING","HIGH_VOL","IMPULSE"},
 "FALSE_BREAK":{"HIGH_VOL","IMPULSE","DECAY"},
 "VOLATILITY_CAPTURE":{"EXPANDING","HIGH_VOL","IMPULSE"},
}
MARKOV_TARGETS={
 "POC":{"DECAY","QUIET"},
 "BREAKOUT":{"HIGH_VOL","IMPULSE"},
 "FALSE_BREAK":{"DECAY","QUIET"},
 "VOLATILITY_CAPTURE":{"HIGH_VOL","IMPULSE"},
}

def chronological_folds(rows,min_train=100,folds=4):
    x=sorted(rows,key=lambda r:r["event_ts"])
    n=len(x)
    if n<=min_train:return []
    remain=n-min_train;step=max(1,remain//max(1,int(folds)))
    out=[]
    start=min_train
    for fold in range(1,int(folds)+1):
        end=n if fold==int(folds) else min(n,start+step)
        if start>=end:break
        out.append((fold,x[:start],x[start:end]))
        start=end
    return out

def select_validation(variant,setup,train,validation,markov_threshold=.55,ml_threshold=.5,min_transitions=30):
    model=ConditionalMarkov(min_transitions=min_transitions).fit(train)
    selected=[];missing_ml=False
    for row in validation:
        x=dict(row)
        ctx=markov_context(model,x);x.update(ctx)
        state=x.get("market_state") or x.get("regime")
        regime_ok=state in REGIME_ALLOWED.get(setup,set())
        targets=MARKOV_TARGETS.get(setup,set())
        p_target=sum(float(ctx["markov_next"].get(s,0)) for s in targets)
        x["markov_target_probability"]=p_target
        markov_ok=p_target>=float(markov_threshold)
        ml_score=x.get("ml_score")
        if variant in ("ML","ML_MARKOV") and ml_score is None:
            missing_ml=True;continue
        ml_ok=(float(ml_score)>=float(ml_threshold)) if ml_score is not None else False
        keep={"BASE":True,"REGIME":regime_ok,"MARKOV":markov_ok,
              "REGIME_MARKOV":regime_ok and markov_ok,
              "ML":ml_ok,"ML_MARKOV":ml_ok and markov_ok}[variant]
        if keep:selected.append(x)
    return selected,{"missing_ml_score":missing_ml,"validation":len(validation),"selected":len(selected)}
