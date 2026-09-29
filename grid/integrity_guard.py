import hashlib,json
from pathlib import Path

def verify_manifest(root,manifest_path):
    root=Path(root).resolve(); manifest=json.loads(Path(manifest_path).read_text(encoding="utf-8-sig"))
    bad=[];missing=[]
    for rel,expected in manifest.get("files",{}).items():
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
    """Return only Grid-owned relative paths. Updater performs authenticated restore."""
    return sorted(set(report.get("bad",[])+report.get("missing",[])))
