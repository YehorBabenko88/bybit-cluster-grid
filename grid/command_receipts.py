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
        except FileNotFoundError:
            return {}
        except (OSError,ValueError,TypeError) as exc:
            raise RuntimeError("command receipt journal is unreadable; refusing command execution") from exc
        if not isinstance(raw,dict):
            raise RuntimeError("command receipt journal has invalid format; refusing command execution")
        return raw

    def get(self,command_id):
        if not command_id:
            return None
        rows=self._load()
        key=str(command_id)
        if key not in rows:
            return None
        row=rows[key]
        if not isinstance(row,dict) or not isinstance(row.get("ok"),bool):
            raise RuntimeError("command receipt entry is invalid; refusing command execution")
        return row

    def ensure_capacity(self,command_id):
        """Refuse a new command before execution if its receipt cannot fit."""
        rows=self._load()
        if str(command_id) not in rows and len(rows)>=self.max_entries:
            raise RuntimeError("command receipt journal capacity reached; refusing command execution")

    def put(self,command_id,ok,result=None,error=None):
        if not command_id:
            return
        rows=self._load()
        rows[str(command_id)]={
            "ok":bool(ok),"result":result,"error":error,"completed_at":time.time()
        }
        if len(rows)>self.max_entries:
            # Dropping a receipt solely because newer commands arrived can
            # allow a still-deliverable CONTROL command to execute twice.
            # Fail closed until CONTROL/Worker agree on safe pruning.
            raise RuntimeError("command receipt journal capacity reached; refusing unsafe eviction")
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
