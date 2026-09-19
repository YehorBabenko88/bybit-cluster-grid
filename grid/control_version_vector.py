def vector_from_state(state):
    return {k:int((v or {}).get("_version",0)) for k,v in (state or {}).items()}

def compare_vectors(a,b):
    """1 if a dominates b, -1 if b dominates a, 0 equal, None concurrent/conflicting."""
    keys=set(a)|set(b);ge=all(a.get(k,0)>=b.get(k,0) for k in keys);le=all(a.get(k,0)<=b.get(k,0) for k in keys)
    if ge and le:return 0
    if ge:return 1
    if le:return -1
    return None

def freshest_dominating(replicas):
    if not replicas:return None
    best=replicas[0]
    for r in replicas[1:]:
        c=compare_vectors(vector_from_state(r.get("state")),vector_from_state(best.get("state")))
        if c==1:best=r
        elif c is None:raise ValueError("concurrent control replicas require reconciliation")
    for r in replicas:
        c=compare_vectors(vector_from_state(best.get("state")),vector_from_state(r.get("state")))
        if c not in (0,1):raise ValueError("no single dominating control replica")
    return best
