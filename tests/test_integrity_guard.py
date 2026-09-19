import hashlib,json,tempfile
from pathlib import Path
from grid.integrity_guard import verify_manifest,repair_plan

def test_integrity_guard_detects_missing_and_modified_grid_files():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)/"grid";root.mkdir()
        (root/"a.py").write_text("ok",encoding="utf8")
        h=hashlib.sha256(b"ok").hexdigest()
        m=Path(d)/"manifest.json";m.write_text(json.dumps({"version":"1","files":{"a.py":h,"b.py":h}}))
        x=verify_manifest(root,m)
        assert x["missing"]==["b.py"] and repair_plan(x)==["b.py"]
        (root/"a.py").write_text("changed",encoding="utf8")
        x=verify_manifest(root,m)
        assert "a.py" in x["bad"] and "b.py" in x["missing"]

def test_manifest_cannot_escape_grid_root():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)/"grid";root.mkdir()
        m=Path(d)/"manifest.json";m.write_text(json.dumps({"files":{"../x":"00"}}))
        try:verify_manifest(root,m);assert False
        except ValueError:pass
