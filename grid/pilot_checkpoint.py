from __future__ import annotations
import json,os,time
from pathlib import Path

STAGES=("INVENTORY","REPAIR","VERIFY_REPAIR","RESEARCH","IMPORT","LIVE_CANARY","COMPLETE")

class PilotCheckpoint:
    def __init__(self,path):
        self.path=Path(path)
    def load(self):
        if not self.path.exists():return {}
        return json.loads(self.path.read_text(encoding="utf-8"))
    def save(self,state):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        tmp=self.path.with_suffix(self.path.suffix+".tmp")
        tmp.write_text(json.dumps(state,indent=2,sort_keys=True),encoding="utf-8")
        with open(tmp,"rb") as f:os.fsync(f.fileno())
        os.replace(tmp,self.path)
        return state
    def initialize(self,source_path):
        x=self.load()
        if x:return x
        cutoff=((int(time.time()*1000)//60000)-1)*60000
        return self.save({"schema":1,"source_path":str(Path(source_path).resolve()),
                          "research_cutoff_ms":cutoff,"stage":"INVENTORY",
                          "completed_symbols":[],"created_at":int(time.time())})
    def advance(self,stage,**fields):
        if stage not in STAGES:raise ValueError(stage)
        x=self.load();x.update(fields);x["stage"]=stage;x["updated_at"]=int(time.time())
        return self.save(x)
