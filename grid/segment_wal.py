import asyncio, json, os, pathlib, time, zlib

class SegmentWAL:
    """Bounded append-only crash-recovery WAL for pending DB writes."""
    def __init__(self,root,max_bytes=2*1024**3,segment_bytes=16*1024**2):
        self.root=pathlib.Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.max_bytes=int(max_bytes); self.segment_bytes=int(segment_bytes)
        self.checkpoint=self.root/"checkpoint"
        self.checkpoint_backup=self.root/"checkpoint.bak"
        self._lock=asyncio.Lock()
        self._next_id=self._discover_next_id()

    def _segments(self):
        return sorted(self.root.glob("wal-*.seg"))

    def _discover_next_id(self):
        high=self._checkpoint_id()
        for _,rid,_ in self._iter_records():
            high=max(high,rid)
        return high+1

    def _read_checkpoint(self,path):
        try:
            value=int(path.read_text(encoding="ascii").strip() or "0")
            return value if value>=0 else None
        except (OSError,ValueError):
            return None

    def _checkpoint_id(self):
        # Keep a second durable generation. A torn/corrupt primary checkpoint
        # must not force replay of the entire historical WAL after a power loss.
        primary=self._read_checkpoint(self.checkpoint)
        backup=self._read_checkpoint(self.checkpoint_backup)
        values=[x for x in (primary,backup) if x is not None]
        return max(values) if values else 0

    def bytes_used(self):
        total=0
        for p in self._segments():
            try: total+=p.stat().st_size
            except OSError: pass
        return total

    def ratio(self):
        return min(1.0,self.bytes_used()/max(1,self.max_bytes))

    def _active(self):
        segs=self._segments()
        if segs:
            p=segs[-1]
            try:
                if p.stat().st_size<self.segment_bytes: return p
            except OSError: pass
        return self.root/f"wal-{time.time_ns():020d}.seg"

    async def append(self,payload):
        body=json.dumps(payload,separators=(",",":"),ensure_ascii=False).encode("utf-8")
        async with self._lock:
            rid=self._next_id
            record=json.dumps({"id":rid,"crc32":zlib.crc32(body)&0xffffffff,"payload":payload},
                              separators=(",",":"),ensure_ascii=False).encode("utf-8")+b"\n"
            if self.bytes_used()+len(record)>self.max_bytes:
                raise BufferError("Grid WAL capacity exceeded")
            p=self._active()
            with open(p,"ab") as f:
                f.write(record); f.flush(); os.fsync(f.fileno())
            self._next_id+=1
            return rid

    def _iter_records(self):
        for p in self._segments():
            try:
                with open(p,"rb") as f:
                    for raw in f:
                        try:
                            obj=json.loads(raw)
                            body=json.dumps(obj["payload"],separators=(",",":"),ensure_ascii=False).encode("utf-8")
                            if (zlib.crc32(body)&0xffffffff)!=int(obj["crc32"]): continue
                            yield p,int(obj["id"]),obj["payload"]
                        except (ValueError,KeyError,TypeError,json.JSONDecodeError):
                            continue
            except OSError:
                continue

    def recover(self):
        checkpoint=self._checkpoint_id()
        return [(rid,payload) for _,rid,payload in self._iter_records() if rid>checkpoint]

    async def ack(self,record_id):
        async with self._lock:
            current=self._checkpoint_id()
            if record_id<=current: return
            tmp=self.checkpoint.with_suffix(".tmp")
            with open(tmp,"w",encoding="ascii") as f:
                f.write(str(record_id)); f.flush(); os.fsync(f.fileno())
            # Preserve the previous known-good generation before publishing the
            # new primary. Recovery chooses the highest valid generation.
            if self.checkpoint.exists():
                backup_tmp=self.checkpoint_backup.with_suffix(".tmp")
                try:
                    data=self.checkpoint.read_text(encoding="ascii")
                    int(data.strip() or "0")
                    with open(backup_tmp,"w",encoding="ascii") as f:
                        f.write(data); f.flush(); os.fsync(f.fileno())
                    os.replace(backup_tmp,self.checkpoint_backup)
                except (OSError,ValueError):
                    try: backup_tmp.unlink()
                    except OSError: pass
            os.replace(tmp,self.checkpoint)
            self._compact(record_id)

    def _compact(self,checkpoint):
        segs=self._segments()
        for p in segs[:-1]:
            max_id=0
            for rp,rid,_ in self._iter_records():
                if rp==p: max_id=max(max_id,rid)
            if max_id and max_id<=checkpoint:
                try: p.unlink()
                except OSError: pass
