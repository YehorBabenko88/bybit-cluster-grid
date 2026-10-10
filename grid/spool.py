import asyncio, json, os, pathlib, time, uuid

class DiskSpool:
    """Small crash-recovery journal for pending DB writes; not a market-data archive."""
    def __init__(self,root,max_bytes=2*1024**3):
        self.root=pathlib.Path(root)
        self.pending=self.root/"pending"
        self.quarantine=self.root/"quarantine"
        self.max_bytes=int(max_bytes)
        self._lock=asyncio.Lock()
        self.pending.mkdir(parents=True,exist_ok=True)
        self.quarantine.mkdir(parents=True,exist_ok=True)

    def _files(self):
        return sorted(self.pending.glob("*.json"))

    def bytes_used(self):
        total=0
        for p in list(self._files())+list(self.quarantine.glob("*.json")):
            try: total+=p.stat().st_size
            except OSError: pass
        return total

    def ratio(self):
        return min(1.0,self.bytes_used()/max(1,self.max_bytes))

    async def append(self,payload):
        raw=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        async with self._lock:
            if self.bytes_used()+len(raw)>self.max_bytes:
                raise BufferError("Grid disk spool capacity exceeded")
            name=f"{time.time_ns():020d}-{uuid.uuid4().hex}.json"
            tmp=self.pending/(name+".tmp")
            final=self.pending/name
            with open(tmp,"wb") as f:
                f.write(raw); f.flush(); os.fsync(f.fileno())
            os.replace(tmp,final)
            return str(final)

    async def ack(self,path):
        target=pathlib.Path(path)
        if target.parent.resolve()!=self.pending.resolve() or target.suffix!=".json":
            raise ValueError("spool acknowledgement must reference a pending JSON entry")
        try: target.unlink()
        except FileNotFoundError: pass

    def recover(self):
        out=[]
        for p in self._files():
            try:
                out.append((str(p),json.loads(p.read_text(encoding="utf-8"))))
            except (OSError,UnicodeError,json.JSONDecodeError):
                # Preserve corrupt entries for inspection, but prevent endless
                # reprocessing and include them in the spool capacity budget.
                try: os.replace(p,self.quarantine/p.name)
                except OSError: pass
                continue
        return out
