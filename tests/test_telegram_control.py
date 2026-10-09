import time
from grid.telegram_bot import _healthy_canary
from grid.config import settings

def node(cpu=10,ram=20,disk_gb=100,age=0):
    return {"last_seen":time.time()-age,"cpu_pct":cpu,"ram_pct":ram,
            "disk_free":disk_gb*1024**3,"agent_version":"1.0"}

def test_canary_rejects_offline_and_pressure():
    nodes={
      "offline":node(age=settings.heartbeat_seconds*4),
      "cpu":node(cpu=settings.resource_cpu_limit+1),
      "ram":node(ram=settings.resource_ram_limit+1),
      "disk":node(disk_gb=max(0,settings.resource_disk_free_gb-1)),
      "good":node(cpu=15,ram=25,disk_gb=settings.resource_disk_free_gb+50),
    }
    assert _healthy_canary(nodes)=="good"

def test_canary_prefers_lower_pressure_deterministically():
    nodes={"b":node(cpu=20,ram=20),"a":node(cpu=10,ram=10)}
    assert _healthy_canary(nodes)=="a"

def test_no_healthy_canary():
    assert _healthy_canary({"x":node(cpu=99)}) is None


def test_telegram_authorization_requires_private_chat_and_same_sender(monkeypatch):
    from grid.telegram_bot import authorized_sender
    monkeypatch.setattr(settings,"telegram_allowed_chat_ids","123")
    assert authorized_sender(123,"private",123)
    assert not authorized_sender(123,"group",123)
    assert not authorized_sender(123,"supergroup",123)
    assert not authorized_sender(123,"private",456)
    assert not authorized_sender(456,"private",456)
    assert not authorized_sender(123,"private",None)
