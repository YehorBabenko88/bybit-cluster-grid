"""Offline-only LS5 network policy validator. No sockets, subprocess or host reads."""
import ipaddress
import json

NODES = ("LS5", "LS7", "PC1", "PC2", "PC3", "PC4")
KNOWN = {"LS5": "100.103.160.110", "LS7": "100.112.25.75", "PC4": "100.91.48.20"}
REQUIRED = {("LS5", "PC4", 22)}
FORBIDDEN_PORTS = {55432}
MAX_POLICY_BYTES = 65536
RESULT = {"status": "BLOCKED", "physical_ready": False, "execution_authorized": False,
          "physical_tests": "0/10 NOT_RUN", "host_verified": False}

def evaluate(raw):
    out = dict(RESULT, policy_valid=False, findings=[])
    try:
        _require(type(raw) is str and len(raw.encode("utf-8")) <= MAX_POLICY_BYTES, "POLICY_SIZE_OR_TYPE")
        obj = json.loads(raw, object_pairs_hook=_unique, parse_constant=_reject_constant)
        _keys(obj, {"schema", "nodes", "listeners", "flows", "security"})
        _require(obj["schema"] == "grid-network-offline-1", "SCHEMA")
        _require(type(obj["nodes"]) is dict and set(obj["nodes"]) == set(NODES), "NODES")
        for node, address in obj["nodes"].items():
            if address is None:
                _require(node not in KNOWN, "KNOWN_ADDRESS_MISSING")
                continue
            _require(type(address) is str, "ADDRESS_TYPE")
            ip = ipaddress.ip_address(address)
            _require(ip.version == 4 and ip in ipaddress.ip_network("100.64.0.0/10"), "TAILNET_ADDRESS")
            if node in KNOWN:
                _require(address == KNOWN[node], "KNOWN_ADDRESS_MISMATCH")
        addresses = [x for x in obj["nodes"].values() if x is not None]
        _require(len(addresses) == len(set(addresses)), "DUPLICATE_IP")
        _require(type(obj["listeners"]) is list and len(obj["listeners"]) == 2, "LISTENERS")
        observed = set()
        for listener in obj["listeners"]:
            _keys(listener, {"node", "service", "bind", "port", "exposure"})
            _require(listener["node"] == "LS5", "LISTENER_NODE")
            _require(listener["service"] in ("coordinator", "postgres"), "LISTENER_SERVICE")
            _require(type(listener["bind"]) is str and listener["bind"] in ("127.0.0.1", KNOWN["LS5"]), "UNSAFE_BIND")
            if listener["service"] == "postgres":
                _require(listener["bind"] == "127.0.0.1", "POSTGRES_LOOPBACK_ONLY")
            _require(type(listener["port"]) is int, "PORT_TYPE")
            _require(listener["port"] == {"coordinator": 8765, "postgres": 55432}[listener["service"]], "PORT")
            _require(listener["exposure"] == "PRIVATE_ONLY", "EXPOSURE")
            _require(listener["service"] not in observed, "DUPLICATE_LISTENER")
            observed.add(listener["service"])
        _require(observed == {"coordinator", "postgres"}, "MISSING_LISTENER")
        _keys(obj["security"], {"tls_remote", "api_auth", "ssh_keys_only", "tailscale_acl_default_deny", "firewall_default_deny", "secrets_external", "cert_identity_verified"})
        for k, value in obj["security"].items():
            _require(type(value) is bool and value is True, "SECURITY_" + k.upper())
        _require(type(obj["flows"]) is list and len(obj["flows"]) <= 30, "FLOWS")
        flows = set()
        for flow in obj["flows"]:
            _keys(flow, {"src", "dst", "port", "transport", "purpose"})
            _require(type(flow["src"]) is str and type(flow["dst"]) is str, "FLOW_ENDPOINT_TYPE")
            _require(flow["src"] in NODES and flow["dst"] in NODES and flow["src"] != flow["dst"], "FLOW_ENDPOINT")
            _require(obj["nodes"][flow["src"]] is not None and obj["nodes"][flow["dst"]] is not None, "FLOW_UNKNOWN_PEER")
            _require(type(flow["port"]) is int and flow["port"] in (22, 8765), "FLOW_PORT")
            _require(type(flow["transport"]) is str and flow["transport"] == "tailscale", "FLOW_TRANSPORT")
            _require(type(flow["purpose"]) is str and flow["purpose"] == ("ssh" if flow["port"] == 22 else "agent_api"), "FLOW_PURPOSE")
            if flow["port"] == 8765:
                _require(flow["dst"] == "LS5" and flow["src"] != "LS5", "FLOW_API_DIRECTION")
            else:
                _require((flow["src"], flow["dst"]) in {("LS5", "PC4"), ("PC4", "LS5")}, "FLOW_SSH_DIRECTION")
            item = (flow["src"], flow["dst"], flow["port"])
            _require(item not in flows, "DUPLICATE_FLOW")
            flows.add(item)
        _require(REQUIRED.issubset(flows), "SSH_BASELINE_MISSING")
        out["policy_valid"] = True
        out["findings"] = ["STATIC_POLICY_ONLY", "LIVE_LISTENERS_UNVERIFIED", "FIREWALL_UNVERIFIED",
                           "TAILSCALE_ACL_UNVERIFIED", "TLS_AUTH_UNVERIFIED", "SSH_IDENTITY_UNVERIFIED"]
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        out["findings"] = ["INVALID_POLICY"]
    return out

def _require(condition, code):
    if not condition:
        raise ValueError(code)

def _keys(obj, expected):
    _require(type(obj) is dict and set(obj) == expected, "FIELDS")

def _unique(pairs):
    out = {}
    for key, value in pairs:
        _require(key not in out, "DUPLICATE_JSON_KEY")
        out[key] = value
    return out

def _reject_constant(value):
    raise ValueError("NONFINITE_NUMBER")
