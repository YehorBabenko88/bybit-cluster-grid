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


def test_manifest_accepts_utf8_bom():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)/"grid"
        root.mkdir()
        (root/"a.py").write_text("ok",encoding="utf-8")
        h=hashlib.sha256(b"ok").hexdigest()

        manifest=Path(d)/"manifest.json"
        payload=json.dumps({"version":"bom-test","files":{"a.py":h}})
        manifest.write_bytes(b"\xef\xbb\xbf"+payload.encode("utf-8"))

        result=verify_manifest(root,manifest)

        assert result["ok"] is True
        assert result["bad"] == []
        assert result["missing"] == []
        assert result["version"] == "bom-test"


def test_runtime_python_caches_are_ignored_but_source_tampering_is_not():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)/"grid";root.mkdir()
        cache=root/"__pycache__";cache.mkdir()
        source=root/"worker.py";source.write_text("ok",encoding="utf-8")
        pyc=cache/"worker.cpython-312.pyc";pyc.write_bytes(b"build-time-cache")
        manifest=Path(d)/"manifest.json"
        manifest.write_text(json.dumps({"version":"cache-test","files":{
            "worker.py":hashlib.sha256(b"ok").hexdigest(),
            "__pycache__/worker.cpython-312.pyc":hashlib.sha256(b"build-time-cache").hexdigest(),
        }}),encoding="utf-8")

        pyc.write_bytes(b"runtime-rewritten-cache")
        result=verify_manifest(root,manifest)
        assert result["ok"] is True
        assert result["bad"] == []
        assert repair_plan({"bad":["__pycache__/worker.cpython-312.pyc"]}) == []

        source.write_text("tampered",encoding="utf-8")
        result=verify_manifest(root,manifest)
        assert result["ok"] is False
        assert result["bad"] == ["worker.py"]


def test_runtime_python_cache_missing_is_ignored_but_immutable_missing_is_not():
    with tempfile.TemporaryDirectory() as d:
        root=Path(d)/"grid";root.mkdir()
        manifest=Path(d)/"manifest.json"
        manifest.write_text(json.dumps({"version":"cache-missing","files":{
            "__pycache__/worker.cpython-312.pyc":"00",
            "worker.py":"00",
        }}),encoding="utf-8")
        result=verify_manifest(root,manifest)
        assert result["missing"] == ["worker.py"]
        assert repair_plan(result) == ["worker.py"]
