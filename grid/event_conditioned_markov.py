from collections import defaultdict,Counter

class EventConditionedMarkov:
    """P(state_to | symbol, setup, state_from) learned from causal event outcomes at a fixed horizon."""
    def __init__(self,min_transitions=30,alpha=1.0):
        self.min_transitions=int(min_transitions);self.alpha=float(alpha)
        self.counts=defaultdict(Counter);self.totals=Counter();self.states=set()
    def fit(self,rows):
        for r in rows:
            a=r.get("market_state") or r.get("regime");b=r.get("state_to")
            if not a or not b:continue
            sym=str(r.get("symbol","*"));setup=str(r.get("setup_type","*"))
            self.states.update((a,b))
            for key in ((sym,setup,a),(sym,"*",a),("*",setup,a),("*","*",a)):
                self.counts[key][b]+=1;self.totals[key]+=1
        return self
    def _key(self,symbol,setup,state):
        for k in ((str(symbol),str(setup),state),(str(symbol),"*",state),("*",str(setup),state),("*","*",state)):
            if self.totals.get(k,0)>=self.min_transitions or (k[0]=="*" and k[1]=="*" and self.totals.get(k,0)>0):
                return k
        return ("*","*",state)
    def probabilities(self,symbol,setup,state):
        key=self._key(symbol,setup,state);states=sorted(self.states)
        if not states or self.totals.get(key,0)==0:return {},{"scope":key,"transitions":0}
        row=self.counts[key];den=sum(row.values())+self.alpha*len(states)
        return {s:(row.get(s,0)+self.alpha)/den for s in states},{"scope":key,"transitions":self.totals[key]}
