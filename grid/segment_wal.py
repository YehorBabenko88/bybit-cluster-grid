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
                data=f.read()
                if not data or data.endswith(b"\n"):return
                cut=data.rfind(b"\n")
                tail=data[cut+1:]
                # A complete final JSON record is valid even without a newline
                # (tests/import tools may create one). Only truncate a tail that
                # cannot be parsed and CRC-validated as a full WAL record.
                try:
                    obj=json.loads(tail)
                    body=json.dumps(obj["payload"],separators=(",",":"),ensure_ascii=False).encode("utf-8")
                    valid=(zlib.crc32(body)&0xffffffff)==int(obj["crc32"]) and int(obj["id"])>=0
                except (ValueError,KeyError,TypeError,json.JSONDecodeError):
                    valid=False
                if valid:
                    # A fully persisted record without a final newline must
                    # be delimited before the next append, or both records
                    # become one invalid JSON line after restart.
                    f.seek(0,os.SEEK_END)
                    f.write(bytes((10,)))
                    f.flush();os.fsync(f.fileno())
                    return
                # Preserve the damaged bytes for forensic recovery. Only the
                # incomplete final record may be truncated, never earlier rows.
                damaged=self.root/(p.name+".torn-tail")
                with open(damaged,"wb") as copy:
                    copy.write(tail);copy.flush();os.fsync(copy.fileno())
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
        for p in list(self._segments())+list(self.root.glob("*.torn-tail")):
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
                            if (zlib.crc32(body)&0xffffffff)!=int(obj["crc32"]):
                                raise ValueError("WAL CRC mismatch")
                            rid=int(obj["id"])
                            if rid<0:
                                raise ValueError("negative WAL record id")
                            yield p,rid,obj["payload"]
                        except (ValueError,KeyError,TypeError,UnicodeError,json.JSONDecodeError) as exc:
                            # Silent skipping plus a later checkpoint can permanently
                            # discard a corrupt but unacknowledged record. Fail closed.
                            raise ValueError(f"Corrupt WAL record in {p.name}") from exc
            except OSError as exc:
                raise OSError(f"Unable to read WAL segment {p.name}") from exc

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
            current=self._checkpoint_id()
            if record_id<=current: return
            tmp=self.root/"checkpoint.next"
            with open(tmp,"w",encoding="ascii") as f:
                f.write(str(record_id)); f.flush(); os.fsync(f.fileno())
            # Preserve the previous known-good generation before publishing the
            # new primary. Recovery chooses the highest valid generation.
            if self.checkpoint.exists():
                backup_tmp=self.root/"checkpoint.backup.next"
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
        if len(segs)<=1:return
        maxima={}
        for rp,rid,_ in self._iter_records():
            maxima[rp]=max(maxima.get(rp,0),rid)
        for p in segs[:-1]:
            max_id=maxima.get(p,0)
            if max_id and max_id<=checkpoint:
                try:p.unlink()
                except OSError:pass
