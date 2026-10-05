import hashlib
import os
import pathlib
import tempfile
import uuid


class LocalArtifactStore:
    """Owned immutable local artifacts. Only artifact://local URIs are deletable here."""
    scheme="artifact://local/"

    def __init__(self,root):
        self.root=pathlib.Path(root).resolve()
        self.root.mkdir(parents=True,exist_ok=True)

    def _path(self,artifact_id):
        aid=str(artifact_id)
        if not aid or any(ch not in "0123456789abcdef-" for ch in aid.lower()):
            raise ValueError("invalid artifact id")
        return self.root/(aid+".bin")

    def put_bytes(self,data):
        data=bytes(data);aid=uuid.uuid4();target=self._path(aid)
        fd,tmp=tempfile.mkstemp(prefix=aid.hex+".",suffix=".tmp",dir=str(self.root))
        try:
            with os.fdopen(fd,"wb") as f:
                f.write(data);f.flush();os.fsync(f.fileno())
            os.replace(tmp,target)
        finally:
            try:os.unlink(tmp)
            except FileNotFoundError:pass
        return {"id":aid,"storage_uri":self.scheme+str(aid),
                "bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}

    def adopt_temp(self,temp_path,size,sha256):
        temp=pathlib.Path(temp_path).resolve()
        if os.path.commonpath([str(temp),str(self.root)])!=str(self.root):
            raise ValueError("temp artifact escaped owned root")
        aid=uuid.uuid4();target=self._path(aid)
        os.replace(temp,target)
        return {"id":aid,"storage_uri":self.scheme+str(aid),
                "bytes":int(size),"sha256":str(sha256)}

    def delete_uri(self,uri):
        if not str(uri).startswith(self.scheme):
            raise ValueError("refusing to delete non-local artifact URI")
        aid=str(uri)[len(self.scheme):]
        p=self._path(aid).resolve()
        if os.path.commonpath([str(p),str(self.root)])!=str(self.root):
            raise ValueError("artifact path escaped owned root")
        try:p.unlink();return True
        except FileNotFoundError:return False
