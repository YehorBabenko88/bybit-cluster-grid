import json
import os
import pathlib
import tempfile
import time


class CommandReceiptStore:
    """Small durable idempotency journal for CONTROL commands executed by an agent."""
    def __init__(self,path=None,max_entries=1000):
        root=pathlib.Path(os.environ.get("ProgramData",os.getcwd()))/"BybitClusterGrid"
        self.path=pathlib.Path(path) if path else root/"command-receipts.json"
        self.max_entries=max(100,int(max_entries))

    def _load(self):
        try:
            raw=json.loads(self.path.read_text(encoding="utf-8"))
            return raw if isinstance(raw,dict) else {}
        except (OSError,ValueError,TypeError):
            return {}

    def get(self,command_id):
        if not command_id:
            return None
        row=self._load().get(str(command_id))
        return row if isinstance(row,dict) else None

    def put(self,command_id,ok,result=None,error=None):
        if not command_id:
            return
        rows=self._load()
        rows[str(command_id)]={
            "ok":bool(ok),"result":result,"error":error,"completed_at":time.time()
        }
        if len(rows)>self.max_entries:
            ordered=sorted(rows.items(),key=lambda kv:float(kv[1].get("completed_at",0)),reverse=True)
            rows=dict(ordered[:self.max_entries])
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix=self.path.name+".",suffix=".tmp",dir=str(self.path.parent))
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                json.dump(rows,f,separators=(",",":"),ensure_ascii=False)
                f.flush(); os.fsync(f.fileno())
            os.replace(tmp,self.path)
        finally:
            try: os.unlink(tmp)
            except FileNotFoundError: pass
