"""Offline-only negative G0 admission tests: no sockets or physical providers."""
import copy
import json
import pytest
from installer.ls5_pc4_network_g0_offline import evaluate

def fixture():
    node = {"tailnet_ip": None, "identity_verified": None, "listeners_complete": None,
            "firewall_effective_verified": None, "tailscale_policy_verified": None,
            "ssh_identity_verified": None, "tls_identity_verified": None,
            "source_custody_verified": None}
    return {"schema": "ls5-pc4-network-g0-offline-1", "head": "a"*40,
            "run_id": "1234567890abcdef",
            "nodes": {"LS5": dict(node), "PC4": dict(node)},
            "controls": {"worker_has_pg_dsn": None, "worker_has_control_token": None,
                         "external_ingress_detected": None, "production_endpoint_detected": None}}

def check(raw, valid):
    r=evaluate(raw)
    assert r["observation_valid"] is valid
    assert r["status"]=="BLOCKED" and r["network_physical_readiness"]=="BLOCKED"
    assert r["host_verified"] is False and r["execution_authorized"] is False
    assert r["cleanup_authorized"] is False and r["physical_tests"]=="0/10 NOT_RUN"
    return r

def test_unknown_observation_is_blocked(): check(json.dumps(fixture()),True)

def test_all_asserted_true_is_still_blocked():
    x=fixture()
    for node in x["nodes"].values():
        for k in node:
            if k!="tailnet_ip": node[k]=True
    check(json.dumps(x),True)

@pytest.mark.parametrize("field",["worker_has_pg_dsn","worker_has_control_token","external_ingress_detected","production_endpoint_detected"])
def test_declared_unsafe_control(field):
    x=fixture(); x["controls"][field]=True
    assert "UNSAFE_NETWORK_CONTROL_DECLARED" in check(json.dumps(x),True)["findings"]

@pytest.mark.parametrize("field",["identity_verified","listeners_complete","firewall_effective_verified","tailscale_policy_verified","ssh_identity_verified","tls_identity_verified","source_custody_verified"])
@pytest.mark.parametrize("value",["true",1,[],{}])
def test_spoofed_proof_types(field,value):
    x=fixture();x["nodes"]["PC4"][field]=value
    check(json.dumps(x),False)

@pytest.mark.parametrize("value",["0.0.0.0","8.8.8.8","::1","100.103.160.110/32",True,[],{}])
def test_unsafe_ip(value):
    x=fixture();x["nodes"]["PC4"]["tailnet_ip"]=value
    check(json.dumps(x),False)

@pytest.mark.parametrize("value",[1,"yes",{},[],False])
def test_invalid_control_types(value):
    x=fixture();x["controls"]["worker_has_pg_dsn"]=value
    if value is False: check(json.dumps(x),True)
    else: check(json.dumps(x),False)

@pytest.mark.parametrize("raw",[None,b"{}",'{"a":1,"a":2}',"NaN","\ud800","["*1200+"0"+"]"*1200," "*65537])
def test_malformed_input(raw): check(raw,False)

def test_missing_evidence_and_authority_injection():
    x=fixture();del x["nodes"]["LS5"]["firewall_effective_verified"]
    check(json.dumps(x),False)
    x=fixture();x["execution_authorized"]=True
    check(json.dumps(x),False)

def test_run_and_head_binding_types():
    x=fixture();x["head"]="A"*40;check(json.dumps(x),False)
    x=fixture();x["run_id"]="x";check(json.dumps(x),False)

def test_unbound_observation_cannot_claim_replay_protection():
    result=check(json.dumps(fixture()),True)
    assert "REPLAY_BINDING_UNVERIFIED" in result["findings"]

def test_correct_independent_head_run_binding_is_still_not_physical_pass():
    x=fixture()
    result=evaluate(json.dumps(x),expected_head=x["head"],expected_run_id=x["run_id"])
    assert result["observation_valid"] is True
    assert "REPLAY_BINDING_UNVERIFIED" not in result["findings"]
    assert result["status"]=="BLOCKED" and result["host_verified"] is False
    assert result["execution_authorized"] is False

@pytest.mark.parametrize("field,value,expected_code",[
    ("expected_head","b"*40,"HEAD_BINDING_MISMATCH"),
    ("expected_head",True,"HEAD_BINDING_MISMATCH"),
    ("expected_run_id","ffffffffffffffff","RUN_BINDING_MISMATCH"),
    ("expected_run_id",123,"RUN_BINDING_MISMATCH"),
])
def test_replayed_or_spoofed_binding_rejected(field,value,expected_code):
    x=fixture()
    kwargs={"expected_head":x["head"],"expected_run_id":x["run_id"]}
    kwargs[field]=value
    result=evaluate(json.dumps(x),**kwargs)
    assert result["observation_valid"] is False
    assert result["findings"]==[expected_code]
    assert result["status"]=="BLOCKED"
    assert result["execution_authorized"] is False

def test_replay_from_another_run_fails_even_when_document_is_self_consistent():
    old=fixture()
    replay=json.dumps(old)
    result=evaluate(replay,expected_head=old["head"],expected_run_id="1234567890abcdefNEW")
    assert result["observation_valid"] is False
    assert result["findings"]==["RUN_BINDING_MISMATCH"]
