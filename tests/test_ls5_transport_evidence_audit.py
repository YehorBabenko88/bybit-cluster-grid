import copy
import unittest
from installer.ls5_transport_evidence_audit import inspect_transport, TransportEvidenceBlocked

HEAD = "a" * 40

def fixture():
    parent = dict(schema=1, head=HEAD, run_id="40547110334", attempt="1",
                  nonce="b"*32, parent_pid=6832, child_pid=6508, endpoints=[])
    child = []
    for family, mode, port, kind in ((4, "listener", 63504, "TIMEOUT"),
                                    (4, "bound-not-listening", 63502, "REFUSED"),
                                    (6, "listener", 63508, "TIMEOUT"),
                                    (6, "bound-not-listening", 63503, "REFUSED")):
        host = "127.0.0.1" if family == 4 else "::1"
        parent["endpoints"].append(dict(family=family, host=host, port=port, mode=mode,
             ready_utc_ms=1793120837000, host_control="SUCCESS" if mode=="listener" else "WSA10061"))
        child.append(dict(nonce=parent["nonce"], parent_pid=6832, pid=6508, family=family,
             host=host, port=port, mode=mode, started_utc_ms=1793120837574,
             deadline_ms=6000, elapsed_ns=6001496700 if kind=="TIMEOUT" else 2003276800,
             local_host="0.0.0.0" if family==4 else "::", local_port=63530,
             kind=kind, winerror=10061 if kind=="REFUSED" else None,
             errno=10061 if kind=="REFUSED" else None))
    return parent, child

class IndependentTransportAuditTests(unittest.TestCase):
    def inspect(self, parent, child):
        return inspect_transport(parent, child, head=HEAD, run="40547110334", attempt="1")

    def test_valid_observations_never_authorize(self):
        p, c = fixture()
        result = self.inspect(p, c)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["physical_ready"])
        self.assertEqual(result["policy_cause"], "UNKNOWN")

    def test_forged_and_contradictory_records(self):
        for target, key, value in (
            ("parent", "nonce", "0"*32), ("child", "nonce", "0"*32),
            ("child", "pid", 1234), ("child", "parent_pid", 1234),
            ("child", "port", 5555), ("child", "deadline_ms", 2000),
            ("child", "kind", "PERMISSION"), ("child", "winerror", 10013),
            ("child", "errno", 10013), ("child", "started_utc_ms", 1),
            ("child", "family", 6), ("child", "mode", "listener-forged"),
            ("parent", "host_control", "SUCCESS"),
        ):
            p, c = fixture()
            if target == "parent":
                if key == "nonce": p[key] = value
                else: p["endpoints"][1][key] = value
            else: c[1][key] = value
            with self.subTest(target=target,key=key,value=value), self.assertRaises(TransportEvidenceBlocked):
                self.inspect(p, c)

    def test_duplicate_and_out_of_order(self):
        p,c=fixture()
        for change in ("duplicate", "reorder", "extra", "wrong_context", "bool_pid"):
            pp,cc=copy.deepcopy((p,c))
            if change=="duplicate": cc[1]=copy.deepcopy(cc[0])
            if change=="reorder": cc[0],cc[1]=cc[1],cc[0]
            if change=="extra": cc.append(copy.deepcopy(cc[-1]))
            if change=="wrong_context": pp["head"]="f"*40
            if change=="bool_pid": pp["child_pid"]=True
            with self.subTest(change=change), self.assertRaises(TransportEvidenceBlocked):
                self.inspect(pp,cc)

if __name__ == "__main__":
    unittest.main()
