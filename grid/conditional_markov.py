from collections import defaultdict
from .markov_regime import MarkovRegimeModel

class ConditionalMarkov:
    """Hierarchical causal Markov: symbol+setup -> symbol -> setup -> global."""
    def __init__(self,min_transitions=30,alpha=1.0):
        self.min_transitions=int(min_transitions);self.alpha=float(alpha)
        self.models={};self.sizes={}
    def fit(self,rows,state_key="market_state"):
        buckets=defaultdict(list)
        ordered=sorted(rows,key=lambda r:r["event_ts"])
        for r in ordered:
            s=r.get(state_key)
            if not s:continue
            sym=str(r.get("symbol","*"));setup=str(r.get("setup_type","*"))
            for key in (("*","*"),(sym,"*"),("*",setup),(sym,setup)):
                buckets[key].append(s)
        for key,states in buckets.items():
            self.models[key]=MarkovRegimeModel(self.alpha).fit(states)
            self.sizes[key]=max(0,len(states)-1)
        return self
    def _key(self,symbol,setup):
        for key in ((str(symbol),str(setup)),(str(symbol),"*"),("*",str(setup)),("*","*")):
            if key in self.models and (self.sizes.get(key,0)>=self.min_transitions or key==("*","*")):
                return key
        return ("*","*")
    def probabilities(self,symbol,setup,state):
        key=self._key(symbol,setup)
        m=self.models.get(key)
        return (m.probabilities(state) if m else {}),{"scope":key,"transitions":self.sizes.get(key,0)}
