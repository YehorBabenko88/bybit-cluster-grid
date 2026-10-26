"""Pure offline G0 network observation admission. Never grants physical authority."""
import ipaddress
import json

MAX_BYTES = 65536
RESULT = {"status": "BLOCKED", "network_physical_readiness": "BLOCKED",
          "host_verified": False, "execution_authorized": False,
          "cleanup_authorized": False, "physical_tests": "0/10 NOT_RUN"}

def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate key")
        out[key] = value
    return out

def _reject_constant(value):
    raise ValueError("nonfinite")

def evaluate(raw):
    out = dict(RESULT, observation_valid=False, findings=["INVALID_OBSERVATION"])
    try:
        if type(raw) is not str or len(raw.encode("utf-8")) > MAX_BYTES:
            return out
        x = json.loads(raw, object_pairs_hook=_unique, parse_constant=_reject_constant)
        if type(x) is not dict or set(x) != {"schema", "head", "run_id", "nodes", "controls"}:
            return out
        if x["schema"] != "ls5-pc4-network-g0-offline-1":
            return out
        if type(x["head"]) is not str or len(x["head"]) != 40 or any(c not in "0123456789abcdef" for c in x["head"]):
            return out
        if type(x["run_id"]) is not str or not (16 <= len(x["run_id"]) <= 64) or not x["run_id"].isascii() or not x["run_id"].isalnum():
            return out
        if type(x["nodes"]) is not dict or set(x["nodes"]) != {"LS5", "PC4"}:
            return out
        for name, node in x["nodes"].items():
            if type(node) is not dict or set(node) != {"tailnet_ip", "identity_verified", "listeners_complete", "firewall_effective_verified", "tailscale_policy_verified", "ssh_identity_verified", "tls_identity_verified", "source_custody_verified"}:
                return out
            addr = node["tailnet_ip"]
            if addr is not None:
                if type(addr) is not str:
                    return out
                ip = ipaddress.ip_address(addr)
                if ip.version != 4 or ip not in ipaddress.ip_network("100.64.0.0/10"):
                    return out
            for field in set(node) - {"tailnet_ip"}:
                if node[field] is not None and type(node[field]) is not bool:
                    return out
        if type(x["controls"]) is not dict or set(x["controls"]) != {"worker_has_pg_dsn", "worker_has_control_token", "external_ingress_detected", "production_endpoint_detected"}:
            return out
        for value in x["controls"].values():
            if value is not None and type(value) is not bool:
                return out
        out["observation_valid"] = True
        out["findings"] = ["STATIC_OBSERVATION_ONLY", "NATIVE_PROVENANCE_UNVERIFIED"]
        if any(x["controls"][k] is True for k in x["controls"]):
            out["findings"].append("UNSAFE_NETWORK_CONTROL_DECLARED")
        if any(node[k] is not True for node in x["nodes"].values() for k in ("identity_verified", "listeners_complete", "firewall_effective_verified", "tailscale_policy_verified", "ssh_identity_verified", "tls_identity_verified", "source_custody_verified")):
            out["findings"].append("MISSING_NATIVE_PROOF")
    except (ValueError, TypeError, KeyError, AttributeError, UnicodeError, RecursionError):
        pass
    return out
