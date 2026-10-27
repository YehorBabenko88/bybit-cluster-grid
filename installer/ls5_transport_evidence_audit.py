"""Independent metadata-only Windows transport evidence audit; never grants authority."""
import re

class TransportEvidenceBlocked(ValueError):
    pass

def _need(condition, code):
    if not condition:
        raise TransportEvidenceBlocked(code)

def inspect_transport(parent, child, *, head, run, attempt):
    _need(type(parent) is dict and type(child) is list, "TRANSPORT_SHAPE")
    _need(set(parent) == {"schema", "head", "run_id", "attempt", "nonce", "parent_pid", "child_pid", "endpoints"}, "TRANSPORT_PARENT_FIELDS")
    _need(type(parent["schema"]) is int and parent["schema"] == 1, "TRANSPORT_SCHEMA")
    _need((parent["head"], parent["run_id"], parent["attempt"]) == (head, run, attempt), "TRANSPORT_CONTEXT")
    _need(type(parent["nonce"]) is str and re.fullmatch(r"[0-9a-f]{32}", parent["nonce"]) is not None, "TRANSPORT_NONCE")
    _need(all(type(parent[k]) is int and 0 < parent[k] < 2**32 for k in ("parent_pid", "child_pid"))
          and parent["parent_pid"] != parent["child_pid"], "TRANSPORT_PID")
    _need(type(parent["endpoints"]) is list and len(parent["endpoints"]) == len(child) == 4, "TRANSPORT_COUNT")
    seen = set()
    observations = []
    for endpoint, row, (family, mode) in zip(parent["endpoints"], child,
                                            ((4, "listener"), (4, "bound-not-listening"),
                                             (6, "listener"), (6, "bound-not-listening"))):
        host = "127.0.0.1" if family == 4 else "::1"
        _need(type(endpoint) is dict and set(endpoint) == {"family", "host", "port", "mode", "ready_utc_ms", "host_control"}, "TRANSPORT_ENDPOINT_FIELDS")
        _need(type(endpoint["family"]) is int and endpoint["family"] == family
              and endpoint["host"] == host and endpoint["mode"] == mode, "TRANSPORT_ENDPOINT_ID")
        port = endpoint["port"]
        _need(type(port) is int and 0 < port <= 65535 and (family, port) not in seen, "TRANSPORT_PORT")
        seen.add((family, port))
        _need(type(endpoint["ready_utc_ms"]) is int and 0 < endpoint["ready_utc_ms"] < 2**53, "TRANSPORT_READY")
        _need(endpoint["host_control"] == ("SUCCESS" if mode == "listener" else "WSA10061"), "TRANSPORT_HOST_CONTROL")
        _need(type(row) is dict and set(row) == {"nonce", "parent_pid", "pid", "family", "host", "port", "mode",
              "started_utc_ms", "deadline_ms", "elapsed_ns", "local_host", "local_port", "kind", "winerror", "errno"}, "TRANSPORT_CHILD_FIELDS")
        _need(row["nonce"] == parent["nonce"] and type(row["parent_pid"]) is int
              and row["parent_pid"] == parent["parent_pid"] and type(row["pid"]) is int
              and row["pid"] == parent["child_pid"], "TRANSPORT_CHILD_ID")
        _need(type(row["family"]) is int and row["family"] == family and row["host"] == host
              and type(row["port"]) is int and row["port"] == port and row["mode"] == mode, "TRANSPORT_CHILD_ENDPOINT")
        _need(type(row["started_utc_ms"]) is int
              and endpoint["ready_utc_ms"] <= row["started_utc_ms"] <= endpoint["ready_utc_ms"] + 120000, "TRANSPORT_CLOCK")
        _need(type(row["deadline_ms"]) is int and row["deadline_ms"] == 6000
              and type(row["elapsed_ns"]) is int and 0 <= row["elapsed_ns"] <= 11_000_000_000, "TRANSPORT_DEADLINE")
        _need(row["local_host"] in ((host, "0.0.0.0") if family == 4 else (host, "::"))
              and type(row["local_port"]) is int and 0 <= row["local_port"] <= 65535, "TRANSPORT_LOCAL")
        kind, winerror, errno = row["kind"], row["winerror"], row["errno"]
        _need(kind in ("SUCCESS", "TIMEOUT", "REFUSED", "PERMISSION", "OSERROR"), "TRANSPORT_KIND")
        _need(all(v is None or type(v) is int and -2**31 <= v < 2**32 for v in (winerror, errno)), "TRANSPORT_ERROR_TYPE")
        _need((kind != "SUCCESS" or winerror is None and errno is None)
              and (kind != "REFUSED" or winerror == errno == 10061)
              and (kind != "PERMISSION" or winerror == errno == 10013)
              and (kind != "TIMEOUT" or winerror is None and errno is None), "TRANSPORT_CONTRADICTORY_OUTCOME")
        observations.append({"family": family, "mode": mode, "kind": kind})
    return {"status": "BLOCKED", "assurance": "OBSERVED_NOT_ATTESTED",
            "policy_cause": "UNKNOWN", "host_verified": False,
            "execution_authorized": False, "physical_ready": False,
            "observations": observations}
