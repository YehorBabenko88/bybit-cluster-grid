import asyncio
from grid.control_candidate import ControlCandidate
class BadPool:
    def acquire(self): raise RuntimeError("db down")
class J:
    def load(self): return {"version":0,"state":{}}
    def apply(self,*a): return False
def test_candidate_never_grants_mutations_without_db_fencing():
    c=ControlCandidate(BadPool(),"PC2",J(),lambda:[])
    r=asyncio.run(c.tick())
    assert r["mode"]=="ISOLATED_LAST_NODE"
    assert r["telegram"] is True
    assert r["mutations"] is False
    assert r["leader"] is False
