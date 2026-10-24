"""Synthetic negative tests. No host, Windows API, ACL, process or network access."""
import copy
import json
import pytest
from installer.trusted_bootstrap import assess, VERSION

ROOT = r"C:\GridTrusted"
EXEC = r"C:\GridExecutable"
FILES = [
    EXEC + r"\runtime\python.exe",
    EXEC + r"\runtime\pyvenv.cfg",
    EXEC + r"\runtime\site-packages\sitecustomize.py",
    EXEC + r"\runtime\site-packages\grid.pth",
    EXEC + r"\releases\" + VERSION + r"\grid\coordinator.py",
    EXEC + r"\runtime\python311.dll",
]
def sample():
    inventory = {f: ("%064x" % (i+1)) for i, f in enumerate(FILES)}
    policy = dict(schema="grid-ls5-bootstrap-policy-1", head="e25197b169ef0e5f37b5bd0030ee4a97b13965e2",
                  active_release=VERSION, trusted_root=ROOT, executable_root=EXEC, inventory=inventory)
    files = [dict(path=f, sha256=d, kind="FILE", owner_trusted=True,
                  acl_custody_trusted=True, ancestors_trusted=True, reparse=False, hardlinks=1)
             for f, d in inventory.items()]
    observation = dict(schema="grid-ls5-bootstrap-observation-1", head=policy["head"],
                       active_release=VERSION, trusted_root=ROOT, executable_root=EXEC, files=files,
                       runtime=dict(python_exe=FILES[0], pyvenv_cfg=FILES[1],
                                    site_packages=FILES[2], dll_search_paths=[EXEC+r"\runtime"],
                                    imports_closed=True),
                       environment=dict(variables={}, path_entries=[EXEC+r"\runtime"],
                                        cwd_trusted=True, user_site_disabled=True, isolated_python=True),
                       custody=dict(source_independently_authenticated=True, no_preexisting_writers=True,
                                    handles_stable=True, after_acl_rebuild=True, fresh_rebuilt_runtime=True),
                       tasks=dict(grid_disabled=True, unrelated_tasks_classified=True,
                                  recovery_disabled=True))
    return policy, observation

def check(p, o):
    return assess(json.dumps(p), json.dumps(o))

def test_synthetic_pass_never_authorizes():
    p,o=sample(); r=check(p,o)
    assert r["model_status"]=="OFFLINE_MODEL_PASS"
    assert r["status"]=="BLOCKED" and r["host_verified"] is False
    assert not r["execute_authorized"] and not r["deployment_authorized"]

@pytest.mark.parametrize("attack", [
    "release","hash","missing","duplicate","hardlink","reparse","owner",
    "ancestor","writable","untrusted_source","old_runtime","writer",
    "pyvenv","sitepackages","pythonpath","pythonhome","path","cwd",
    "dll","imports","user_site","isolated","task","recovery","unrelated"])
def test_attacks_fail_closed(attack):
    p,o=sample()
    if attack=="release":o["active_release"]="0"*40
    elif attack=="hash":o["files"][0]["sha256"]="f"*64
    elif attack=="missing":o["files"].pop()
    elif attack=="duplicate":o["files"][1]["path"]=o["files"][0]["path"]
    elif attack=="hardlink":o["files"][0]["hardlinks"]=2
    elif attack=="reparse":o["files"][0]["reparse"]=True
    elif attack=="owner":o["files"][0]["owner_trusted"]=False
    elif attack=="ancestor":o["files"][0]["ancestors_trusted"]=False
    elif attack=="writable":o["files"][0]["acl_custody_trusted"]=False
    elif attack=="untrusted_source":o["custody"]["source_independently_authenticated"]=False
    elif attack=="old_runtime":o["custody"]["fresh_rebuilt_runtime"]=False
    elif attack=="writer":o["custody"]["no_preexisting_writers"]=False
    elif attack=="pyvenv":o["runtime"]["pyvenv_cfg"]=EXEC+r"\other\pyvenv.cfg"
    elif attack=="sitepackages":o["runtime"]["site_packages"]=EXEC+r"\other\site.py"
    elif attack=="pythonpath":o["environment"]["variables"]["PYTHONPATH"]=r"C:\Users\Public"
    elif attack=="pythonhome":o["environment"]["variables"]["PYTHONHOME"]=r"C:\Users\Public"
    elif attack=="path":o["environment"]["path_entries"]=[r"C:\Users\Public"]
    elif attack=="cwd":o["environment"]["cwd_trusted"]=False
    elif attack=="dll":o["runtime"]["dll_search_paths"]=[r"C:\Users\Public"]
    elif attack=="imports":o["runtime"]["imports_closed"]=False
    elif attack=="user_site":o["environment"]["user_site_disabled"]=False
    elif attack=="isolated":o["environment"]["isolated_python"]=False
    elif attack=="task":o["tasks"]["grid_disabled"]=False
    elif attack=="recovery":o["tasks"]["recovery_disabled"]=False
    elif attack=="unrelated":o["tasks"]["unrelated_tasks_classified"]=False
    r=check(p,o)
    assert r["model_status"]=="FAIL" and r["status"]=="BLOCKED"
    assert not r["execute_authorized"]

@pytest.mark.parametrize("raw", ['{}','[]','null','{"a":1,"a":2}','NaN','x'*1048577])
def test_malformed_policy(raw):
    _,o=sample()
    r=assess(raw,json.dumps(o))
    assert r["model_status"]=="FAIL" and not r["execute_authorized"]

def test_forged_consistent_claims_are_only_model_pass():
    p,o=sample()
    p["inventory"][FILES[0]]="f"*64
    o["files"][0]["sha256"]="f"*64
    r=check(p,o)
    assert r["model_status"]=="OFFLINE_MODEL_PASS"
    assert not r["host_verified"] and not r["execute_authorized"]

def test_unknown_field_is_rejected():
    p,o=sample();o["physical_authorized"]=True
    assert check(p,o)["model_status"]=="FAIL"
