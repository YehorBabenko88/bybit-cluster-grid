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
        return p.is_file() and sha256_file(p)==str(digest).lower()

    def put(self,source,expected_sha256=None):
        source=Path(source)
        digest=sha256_file(source)
        if expected_sha256 and digest!=str(expected_sha256).lower():
            raise ValueError("cache source sha256 mismatch")
        dest=self.path_for(digest);dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.exists():
            if sha256_file(dest)!=digest:
                raise ValueError("content-addressed cache corruption")
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
        finally:
            try:os.remove(tmp)
            except FileNotFoundError:pass
        return str(destination)
