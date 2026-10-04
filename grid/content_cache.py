from __future__ import annotations
import hashlib,os,shutil,tempfile
from pathlib import Path


def sha256_file(path,chunk_size=1024*1024):
    h=hashlib.sha256()
    with open(path,"rb") as f:
        while True:
            chunk=f.read(int(chunk_size))
            if not chunk:break
            h.update(chunk)
    return h.hexdigest()


class ContentAddressedCache:
    """Local immutable cache keyed by sha256. Atomic publish; readers verify bytes."""
    def __init__(self,root):
        self.root=Path(root)
        self.objects=self.root/"objects"
        self.objects.mkdir(parents=True,exist_ok=True)

    def path_for(self,digest):
        digest=str(digest).lower()
        if len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("invalid sha256")
        return self.objects/digest[:2]/digest[2:]

    def has(self,digest):
        p=self.path_for(digest)
        if not p.is_file() or sha256_file(p)!=str(digest).lower():return False
        try:os.utime(p,None)
        except OSError:pass
        return True

    def put(self,source,expected_sha256=None):
        source=Path(source)
        digest=sha256_file(source)
        if expected_sha256 and digest!=str(expected_sha256).lower():
            raise ValueError("cache source sha256 mismatch")
        dest=self.path_for(digest);dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            if sha256_file(dest)!=digest:
                raise ValueError("content-addressed cache corruption")
            try:os.utime(dest,None)
            except OSError:pass
            return {"path":str(dest),"sha256":digest,"bytes":dest.stat().st_size,"created":False}
        fd,tmp=tempfile.mkstemp(prefix=".publish-",dir=dest.parent);os.close(fd)
        try:
            shutil.copyfile(source,tmp)
            if sha256_file(tmp)!=digest:raise ValueError("cache publish verification failed")
            os.replace(tmp,dest)
        finally:
            try:os.remove(tmp)
            except FileNotFoundError:pass
        return {"path":str(dest),"sha256":digest,"bytes":dest.stat().st_size,"created":True}

    def materialize(self,digest,destination):
        source=self.path_for(digest)
        if not source.is_file() or sha256_file(source)!=str(digest).lower():
            raise FileNotFoundError("verified cache object not found")
        destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix=".materialize-",dir=destination.parent);os.close(fd)
        try:
            shutil.copyfile(source,tmp)
            if sha256_file(tmp)!=str(digest).lower():raise ValueError("materialized cache hash mismatch")
            os.replace(tmp,destination)
            try:os.utime(source,None)
            except OSError:pass
        finally:
            try:os.remove(tmp)
            except FileNotFoundError:pass
        return str(destination)


    def gc(self,max_bytes,ttl_seconds,protected=()):
        import time
        protected={str(x).lower() for x in protected}
        now=time.time();items=[]
        for prefix in self.objects.iterdir() if self.objects.exists() else []:
            if not prefix.is_dir():continue
            for p in prefix.iterdir():
                if not p.is_file():continue
                digest=prefix.name+p.name
                try:st=p.stat()
                except FileNotFoundError:continue
                items.append((st.st_mtime,st.st_size,digest,p))
        total=sum(x[1] for x in items);deleted=bytes_deleted=0
        for mtime,size,digest,p in sorted(items):
            expired=(now-mtime)>=float(ttl_seconds)
            over=total>int(max_bytes)
            if digest in protected or (not expired and not over):continue
            try:
                p.unlink();deleted+=1;bytes_deleted+=size;total-=size
                try:
                    if not any(p.parent.iterdir()):p.parent.rmdir()
                except (FileNotFoundError,OSError):pass
            except FileNotFoundError:pass
        return {"deleted":deleted,"bytes_deleted":bytes_deleted,"bytes_remaining":total}
