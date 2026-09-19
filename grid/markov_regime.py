from collections import defaultdict,Counter

class MarkovRegimeModel:
    """Causal first-order regime transition model with additive smoothing."""
    def __init__(self,alpha=1.0):
        self.alpha=float(alpha);self.counts=defaultdict(Counter);self.states=set()
    def fit(self,states):
        self.counts=defaultdict(Counter);self.states=set(states)
        for a,b in zip(states,states[1:]):self.counts[a][b]+=1
        return self
    def probabilities(self,state):
        states=sorted(self.states)
        if not states:return {}
        row=self.counts.get(state,{})
        den=sum(row.values())+self.alpha*len(states)
        return {s:(row.get(s,0)+self.alpha)/den for s in states}
    def transition_probability(self,a,b):
        return self.probabilities(a).get(b,0.0)

def fit_fold_markov(train_rows,state_key="market_state"):
    ordered=sorted(train_rows,key=lambda r:r["event_ts"])
    states=[r.get(state_key) for r in ordered if r.get(state_key)]
    return MarkovRegimeModel().fit(states)

def attach_markov_features(model,rows,state_key="market_state"):
    out=[]
    for r in rows:
        x=dict(r);p=model.probabilities(x.get(state_key))
        x["markov_next_probabilities"]=p
        x["markov_p_stay"]=p.get(x.get(state_key),0.0)
        x["markov_p_high_vol"]=sum(v for k,v in p.items() if k in ("HIGH_VOL","IMPULSE"))
        out.append(x)
    return out
