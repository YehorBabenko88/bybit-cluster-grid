"""Coordinator health must belong to the supervised process, not a stale server."""
import io
import json
import urllib.error
from grid.release_supervisor import _ready


class FakeProcess:
    pid=4321


class FakeResponse:
    status=200
    def __init__(self,payload):self.payload=payload
    def __enter__(self):return self
    def __exit__(self,*args):return False
    def read(self,*args):return self.payload.read(*args)


def test_coordinator_readiness_rejects_other_process(monkeypatch):
    def probe(*args,**kwargs):
        return FakeResponse(io.BytesIO(json.dumps({"ok":True,"pid":9999}).encode()))
    monkeypatch.setattr("grid.release_supervisor.urllib.request.urlopen",probe)
    assert not _ready("coordinator",FakeProcess(),None)


def test_coordinator_readiness_accepts_own_process(monkeypatch):
    def probe(*args,**kwargs):
        return FakeResponse(io.BytesIO(json.dumps({"ok":True,"pid":4321}).encode()))
    monkeypatch.setattr("grid.release_supervisor.urllib.request.urlopen",probe)
    assert _ready("coordinator",FakeProcess(),None)
