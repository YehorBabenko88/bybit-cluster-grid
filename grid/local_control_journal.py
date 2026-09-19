import hashlib,json,os,tempfile
from pathlib import Path

class LocalControlJournal:
    """Small crash-safe replica of critical control state, never bulk market data."""
    def __init__(self,path):
        self.path=Path(path); self.path.parent.mkdir(parents=True,exist_ok=True)

    def load(self):
        if not self.path.exists():return {"version":0,"state":{}}
        obj=json.loads(self.path.read_text(encoding="utf-8"))
        body=json.dumps({"version":obj["version"],"state":obj["state"]},
                        sort_keys=True,separators=(",",":")).encode()
        if hashlib.sha256(body).hexdigest()!=obj.get("checksum"):
            raise ValueError("control journal checksum mismatch")
        return {"version":int(obj["version"]),"state":obj["state"]}

    def apply(self,version,state):
        current=self.load()
        if int(version)<=current["version"]:return False
        body_obj={"version":int(version),"state":state}
        body=json.dumps(body_obj,sort_keys=True,separators=(",",":")).encode()
        obj={**body_obj,"checksum":hashlib.sha256(body).hexdigest()}
        fd,tmp=tempfile.mkstemp(prefix=self.path.name+".",dir=str(self.path.parent))
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                json.dump(obj,f,sort_keys=True,separators=(",",":"));f.flush();os.fsync(f.fileno())
            os.replace(tmp,self.path)
            return True
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
