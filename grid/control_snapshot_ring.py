import hashlib,json
from pathlib import Path
from .local_control_journal import LocalControlJournal

class ControlSnapshotRing:
    def __init__(self,directory,keep=5):
        self.dir=Path(directory);self.dir.mkdir(parents=True,exist_ok=True);self.keep=max(2,int(keep))
    def store(self,version,state):
        p=self.dir/f"control-{int(version):020d}.json"
        LocalControlJournal(p).apply(int(version),state)
        files=sorted(self.dir.glob("control-*.json"))
        for old in files[:-self.keep]:
            try:old.unlink()
            except OSError:pass
        return p
    def newest(self):
        for p in reversed(sorted(self.dir.glob("control-*.json"))):
            try:return LocalControlJournal(p).load()
            except Exception:continue
        return {"version":0,"state":{}}

def replica_meta(journal):
    x=journal.load()
    body=json.dumps({"version":x["version"],"state":x["state"]},sort_keys=True,separators=(",",":")).encode()
    return {"control_generation":x["version"],"control_checksum":hashlib.sha256(body).hexdigest()}

def choose_replica(candidates):
    """Highest valid generation wins; conflicting checksum at same generation is unsafe."""
    valid=[c for c in candidates if int(c.get("control_generation",0))>=0 and c.get("control_checksum")]
    if not valid:return None
    top=max(int(c["control_generation"]) for c in valid)
    peers=[c for c in valid if int(c["control_generation"])==top]
    sums={c["control_checksum"] for c in peers}
    if len(sums)!=1:raise ValueError("control replica conflict at same generation")
    return sorted(peers,key=lambda c:str(c.get("node_id","")))[0]
