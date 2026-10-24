"""Pure negative fixtures; never open network connections."""
import copy
import json
import pytest
from installer.ls5_network_offline import evaluate

def baseline():
    return {"schema":"grid-network-offline-1",
      "nodes":{"LS5":"100.103.160.110","LS7":"100.112.25.75","PC1":None,"PC2":None,"PC3":None,"PC4":"100.91.48.20"},
      "listeners":[{"node":"LS5","service":"coordinator","bind":"100.103.160.110","port":8765,"exposure":"PRIVATE_ONLY"},
                   {"node":"LS5","service":"postgres","bind":"127.0.0.1","port":55432,"exposure":"PRIVATE_ONLY"}],
      "flows":[{"src":"PC4","dst":"LS5","port":22,"transport":"tailscale","purpose":"ssh"},
               {"src":"LS5","dst":"PC4","port":22,"transport":"tailscale","purpose":"ssh"},
               {"src":"PC4","dst":"LS5","port":8765,"transport":"tailscale","purpose":"agent_api"}],
      "security":dict.fromkeys(("tls_remote","api_auth","ssh_keys_only","tailscale_acl_default_deny","firewall_default_deny","secrets_external","cert_identity_verified"),True)}

def check(x, expected):
    r=evaluate(json.dumps(x))
    assert r["policy_valid"] is expected
    assert r["status"]=="BLOCKED" and r["host_verified"] is False
    assert r["execution_authorized"] is False and r["physical_ready"] is False
    assert r["physical_tests"]=="0/10 NOT_RUN"

def test_valid_model_still_blocked(): check(baseline(),True)

@pytest.mark.parametrize("field,value",[
 ("bind","0.0.0.0"),("bind","::"),("bind","100.91.48.20"),
 ("port",55432),("port",True),("exposure","PUBLIC")])
def test_unsafe_coordinator_listener(field,value):
    x=baseline();x["listeners"][0][field]=value;check(x,False)

@pytest.mark.parametrize("field",["tls_remote","api_auth","ssh_keys_only","tailscale_acl_default_deny","firewall_default_deny","secrets_external","cert_identity_verified"])
@pytest.mark.parametrize("value",[False,None,1,"true"])
def test_missing_security_guarantee(field,value):
    x=baseline();x["security"][field]=value;check(x,False)

@pytest.mark.parametrize("flow",[
 {"src":"PC4","dst":"LS5","port":55432,"transport":"tailscale","purpose":"agent_api"},
 {"src":"PC3","dst":"PC2","port":22,"transport":"tailscale","purpose":"ssh"},
 {"src":"PC4","dst":"LS5","port":8765,"transport":"internet","purpose":"agent_api"},
 {"src":"PC4","dst":"LS5","port":8765,"transport":"tailscale","purpose":"ssh"},
])
def test_forbidden_flow(flow):
    x=baseline();x["flows"].append(flow);check(x,False)

def test_duplicate_flow(): x=baseline();x["flows"].append(copy.deepcopy(x["flows"][0]));check(x,False)
def test_missing_ssh_baseline():
    x=baseline()
    x["flows"]=[f for f in x["flows"] if not (f["src"]=="LS5" and f["dst"]=="PC4" and f["port"]==22)]
    check(x,False)
def test_wrong_known_ip(): x=baseline();x["nodes"]["LS5"]="100.64.1.1";check(x,False)
def test_duplicate_ip(): x=baseline();x["nodes"]["PC1"]=x["nodes"]["PC4"];check(x,False)
def test_unknown_ip_public(): x=baseline();x["nodes"]["PC1"]="8.8.8.8";check(x,False)
def test_extra_field(): x=baseline();x["authorized"]=True;check(x,False)
def test_duplicate_json_key():
    raw=json.dumps(baseline()).replace('"schema":', '"schema":"forged","schema":',1)
    assert evaluate(raw)["policy_valid"] is False
@pytest.mark.parametrize("raw",['NaN','[]','null','{','{"schema":1,"schema":2}'])
def test_invalid_json(raw): assert evaluate(raw)["policy_valid"] is False


def test_reverse_ssh_is_optional():
    x=baseline()
    x["flows"]=[f for f in x["flows"] if not (f["src"]=="PC4" and f["dst"]=="LS5" and f["port"]==22)]
    check(x,True)

@pytest.mark.parametrize("node",["PC1","PC2","PC3"])
def test_unknown_peer_cannot_be_granted_flow(node):
    x=baseline()
    x["flows"].append({"src":node,"dst":"LS5","port":8765,"transport":"tailscale","purpose":"agent_api"})
    check(x,False)

@pytest.mark.parametrize("field,value", [("src",["PC4"]),("dst",{"node":"LS5"}),("transport",["tailscale"]),("purpose",["ssh"])])
def test_nested_type_spoofing(field,value):
    x=baseline()
    x["flows"][0][field]=value
    check(x,False)

@pytest.mark.parametrize("src,dst,port,purpose",[
 ("LS7","PC4",22,"ssh"),
 ("PC4","LS7",22,"ssh"),
 ("LS5","LS7",22,"ssh"),
 ("LS5","PC4",8765,"agent_api"),
])
def test_lateral_or_wrong_direction_blocked(src,dst,port,purpose):
    x=baseline()
    if src=="LS7" or dst=="LS7":
        assert x["nodes"]["LS7"] is not None
    x["flows"].append({"src":src,"dst":dst,"port":port,"transport":"tailscale","purpose":purpose})
    check(x,False)

@pytest.mark.parametrize("service,field,value",[
 ("coordinator","node","PC4"),
 ("postgres","bind","0.0.0.0"),
 ("postgres","bind","100.103.160.110"),
 ("postgres","port",8765),
 ("postgres","exposure","TAILNET"),
])
def test_listener_isolation(service,field,value):
    x=baseline()
    listener=next(z for z in x["listeners"] if z["service"]==service)
    listener[field]=value
    check(x,False)

def test_missing_listener():
    x=baseline(); x["listeners"].pop(); check(x,False)

def test_duplicate_listener():
    x=baseline(); x["listeners"][1]=copy.deepcopy(x["listeners"][0]); check(x,False)

def test_schema_only_cannot_authorize():
    x=baseline(); check(x,True)
    r=evaluate(json.dumps(x))
    assert r["status"]=="BLOCKED" and r["host_verified"] is False
    assert r["physical_ready"] is False and r["execution_authorized"] is False

@pytest.mark.parametrize("value",[True,False,0,1,None,{},[]])
def test_authority_field_injection_rejected(value):
    x=baseline(); x["execution_authorized"]=value; check(x,False)


@pytest.mark.parametrize("raw", ["[" * 1500 + "]" * 1500, '{"x":' * 1200 + "0" + "}" * 1200])
def test_deep_json_fails_closed_without_exception(raw):
    # Payload is within the byte budget but may exceed json.loads recursion depth.
    r = evaluate(raw)
    assert r["policy_valid"] is False
    assert r["physical_ready"] is False
    assert r["execution_authorized"] is False
    assert r["status"] == "BLOCKED"
