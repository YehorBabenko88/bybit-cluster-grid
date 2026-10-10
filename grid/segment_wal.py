import asyncio, json, os, pathlib, time, zlib

class SegmentWAL:
    """Bounded append-only crash-recovery WAL for pending DB writes."""
    def __init__(self,root,max_bytes=2*1024**3,segment_bytes=16*1024**2):
        self.root=pathlib.Path(root); self.root.mkdir(parents=True,exist_ok=True)
        self.max_bytes=int(max_bytes); self.segment_bytes=int(segment_bytes)
        self.checkpoint=self.root/"checkpoint"
        self.checkpoint_backup=self.root/"checkpoint.bak"
        self._lock=asyncio.Lock()
        self._repair_trailing_partial()
        self._cleanup_staging_files()
        self._next_id=self._discover_next_id()

    def _segments(self):
        return sorted(self.root.glob("wal-*.seg"))

    def _repair_trailing_partial(self):
        # A power loss can leave the active segment without its final newline.
        # Appending to those torn bytes would corrupt the next valid record too.
        segs=self._segments()
        if not segs:return
        p=segs[-1]
        try:
            with open(p,"rb+") as f:
                # Only the final line can be torn. Avoid loading an entire
                # multi-megabyte segment into RAM during startup.
                f.seek(0,os.SEEK_END)
                end=f.tell()
                if not end:return
                f.seek(end-1)
                if f.read(1)==b"\n":return
                block_size=65536
                cursor=end
                cut=-1
                while cursor>0:
                    start=max(0,cursor-block_size)
                    f.seek(start)
                    block=f.read(cursor-start)
                    idx=block.rfind(b"\n")
                    if idx>=0:
                        cut=start+idx
                        break
                    cursor=start
                f.seek(cut+1)
                tail=f.read(end-cut-1)
                # A complete final JSON record is valid even without a newline
                # (tests/import tools may create one). Only truncate a tail that
                # cannot be parsed and CRC-validated as a full WAL record.
                try:
                    obj=json.loads(tail)
                    body=json.dumps(obj["payload"],separators=(",",":"),ensure_ascii=False).encode("utf-8")
                    valid=(type(obj["crc32"]) is int and type(obj["id"]) is int
                           and obj["id"]>=0 and (zlib.crc32(body)&0xffffffff)==obj["crc32"])
                except (ValueError,KeyError,TypeError,json.JSONDecodeError):
                    valid=False
                if valid:
                    # Normalize a valid unterminated record before the next
                    # append; otherwise two JSON objects would share one line.
                    f.seek(0,os.SEEK_END)
                    f.write(bytes([10]))
                    f.flush();os.fsync(f.fileno())
                    return
                f.truncate(0 if cut<0 else cut+1)
                f.flush();os.fsync(f.fileno())
        except OSError:
            pass

    def _cleanup_staging_files(self):
        for name in ("checkpoint.next","checkpoint.backup.next"):
            try:(self.root/name).unlink()
            except FileNotFoundError:pass
            except OSError:pass

    def _discover_next_id(self):
        high=self._checkpoint_id()
        for _,rid,_ in self._iter_records():
            high=max(high,rid)
        return high+1

    def _read_checkpoint(self,path):
        try:
            raw=path.read_text(encoding="ascii").strip()
            # A torn write can leave a valid-looking integer prefix. A
            # checkpoint is accepted only if the whole file is a single
            # canonical decimal number, with no leading/trailing junk.
            if not raw or not raw.isascii() or not raw.isdecimal():
                return None
            value=int(raw)
            return value if value>=0 else None
        except (OSError,ValueError,UnicodeError):
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
                            crc=obj["crc32"]
                            rid=obj["id"]
                            if type(crc) is not int or not 0<=crc<=0xffffffff:
                                raise ValueError("invalid WAL CRC field")
                            if type(rid) is not int or rid<0:
                                raise ValueError("invalid WAL record id")
                            if (zlib.crc32(body)&0xffffffff)!=crc:
                                raise ValueError("WAL CRC mismatch")
                            yield p,rid,obj["payload"]
                        except (ValueError,KeyError,TypeError,UnicodeError) as exc:
                            # Silently skipping a corrupted middle record lets
                            # a later ACK advance past permanently lost data.
                            raise RuntimeError(f"corrupt WAL record in {p}") from exc
            except OSError as exc:
                # An unreadable segment is not an empty segment. Skipping it
                # can let recovery ACK records after a missing WAL range.
                raise RuntimeError(f"cannot read WAL segment {p}") from exc

    def iter_recover(self):
        """Stream pending records so a large outage backlog is never materialized in RAM."""
        checkpoint=self._checkpoint_id()
        for _,rid,payload in self._iter_records():
            if rid>checkpoint:
                yield rid,payload

    def recover(self):
        # Compatibility helper for small callers/tests. Runtime replay must use iter_recover().
        return list(self.iter_recover())

    async def ack(self,record_id):
        async with self._lock:
            # A checkpoint beyond the last allocated record would cause future
            # WAL entries to be skipped during crash recovery.
            if not isinstance(record_id,int) or isinstance(record_id,bool) or record_id<0 or record_id>=self._next_id:
                raise ValueError("WAL ACK id is outside the allocated record range")
            current=self._checkpoint_id()
            if record_id<=current: return
            # A caller must not ACK past an earlier pending record: doing so
            # would make that earlier write unrecoverable after a crash.
            pending=next(self.iter_recover(),None)
            if pending is None or pending[0]!=record_id:
                raise ValueError("WAL ACK must target the oldest pending record")
            tmp=self.root/"checkpoint.next"
            with open(tmp,"w",encoding="ascii") as f:
                f.write(str(record_id)); f.flush(); os.fsync(f.fileno())
            # Preserve the previous known-good generation before publishing the
            # new primary. Recovery chooses the highest valid generation.
            previous=self._read_checkpoint(self.checkpoint)
            if previous is not None:
                backup_tmp=self.root/"checkpoint.backup.next"
                try:
                    with open(backup_tmp,"w",encoding="ascii") as f:
                        f.write(str(previous)); f.flush(); os.fsync(f.fileno())
                    os.replace(backup_tmp,self.checkpoint_backup)
                except OSError:
                    try: backup_tmp.unlink()
                    except OSError: pass
            os.replace(tmp,self.checkpoint)
            self._compact(record_id)

    def _compact(self,checkpoint):
        segs=self._segments()
        if len(segs)<=1:return
        maxima={}
        for rp,rid,_ in self._iter_records():
            maxima[rp]=max(maxima.get(rp,0),rid)
        for p in segs[:-1]:
            max_id=maxima.get(p,0)
            if max_id and max_id<=checkpoint:
                try:p.unlink()
                except OSError:pass
