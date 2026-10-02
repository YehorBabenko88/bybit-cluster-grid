import hashlib,json
from pathlib import Path

def _runtime_generated(rel):
    """Files Python/runtime may legitimately create or rewrite after installation."""
    parts=Path(str(rel).replace("\\","/")).parts
    name=parts[-1].lower() if parts else ""
    return "__pycache__" in parts or name.endswith((".pyc",".pyo"))

def verify_manifest(root,manifest_path):
    root=Path(root).resolve(); manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    bad=[];missing=[]
    for rel,expected in manifest.get("files",{}).items():
        if _runtime_generated(rel):continue
        p=(root/rel).resolve()
        if root not in p.parents and p!=root: raise ValueError("manifest path escapes grid root")
        if not p.is_file():missing.append(rel);continue
        h=hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda:f.read(1024*1024),b""):h.update(chunk)
        if h.hexdigest().lower()!=str(expected).lower():bad.append(rel)
    return {"ok":not bad and not missing,"bad":bad,"missing":missing,
            "version":manifest.get("version")}

def repair_plan(report):
    """Return only immutable Grid-owned relative paths. Runtime caches are never repaired."""
    return sorted(set(
        rel for rel in report.get("bad",[])+report.get("missing",[])
        if not _runtime_generated(rel)
    ))
