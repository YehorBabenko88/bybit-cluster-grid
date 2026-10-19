"""Pure offline negative tests for PGDATA cross-contract checks."""
import copy
from installer.pgdata_cross_contract import check_pgdata_contract

RUN = "a" * 32
ROOT = "C:\\GridLab\\" + RUN + "\\LAB01\\pgdata"

def fixtures():
    plan = dict(schema=1, run_id=RUN, node_id="LAB01", data_root=ROOT,
                port=25432, postgres_major=16, listen_address="127.0.0.1",
                existing_cluster=False, runtime_stopped=True, operator_approved=True)
    adapter = dict(run_id=RUN, node_id="LAB01", postgres_port=25432,
                   root="C:\\GridLab\\" + RUN + "\\LAB01")
    journal = dict(status="BLOCKED", execution_authorized=False,
                   readiness_passed=False, run_id=RUN, node_id="LAB01", pgdata=ROOT)
    return plan, adapter, journal

def assert_blocked(result):
    assert result["status"] == "BLOCKED"
    assert result["readiness_passed"] is False
    assert result["execution_authorized"] is False
    assert result["physical_ready"] is False
    assert result["ownership_verified"] is False
    assert result["schema2_enabled"] is False

def test_normal_metadata_still_blocked():
    p, a, j = fixtures()
    original = copy.deepcopy((p, a, j))
    r = check_pgdata_contract(p, a, j)
    assert_blocked(r)
    assert "PGDATA_LAYOUT_MISMATCH" in r["blockers"]
    assert (p, a, j) == original

def test_missing_or_forged_inputs_fail_closed():
    p, a, j = fixtures()
    for args in [(None, a, j), (p, None, j), (p, a, None),
                 (dict(p, postgres_major=17), a, j),
                 (p, dict(a, postgres_port=True), j),
                 (p, a, dict(j, execution_authorized=True)),
                 (p, a, dict(j, readiness_passed=True)),
                 (p, a, dict(j, status="READY")),
                 (p, a, dict(j, pgdata="C:\\other")),
                 (p, a, dict(j, node_id="LS5"))]:
        assert_blocked(check_pgdata_contract(*args))

def test_no_side_effects(monkeypatch):
    import socket
    import subprocess
    from pathlib import Path
    def forbidden(*args, **kwargs):
        raise AssertionError("SIDE_EFFECT")
    with monkeypatch.context() as m:
        m.setattr(Path, "open", forbidden)
        m.setattr(subprocess, "Popen", forbidden)
        m.setattr(socket.socket, "connect", forbidden)
        assert_blocked(check_pgdata_contract(*fixtures()))

def test_specific_blocker_codes_and_immutable_inputs():
    cases = [
        (lambda p,a,j: (None,a,j), "PLAN_INVALID"),
        (lambda p,a,j: (p,None,j), "ADAPTER_MISSING"),
        (lambda p,a,j: (p,a,None), "JOURNAL_MISSING"),
        (lambda p,a,j: (dict(p,postgres_major=17),a,j), "PLAN_INVALID"),
        (lambda p,a,j: (p,dict(a,postgres_port=True),j), "ADAPTER_IDENTITY_MISMATCH"),
        (lambda p,a,j: (p,a,dict(j,execution_authorized=True)), "JOURNAL_AUTHORIZATION_FORBIDDEN"),
        (lambda p,a,j: (p,a,dict(j,readiness_passed=True)), "JOURNAL_AUTHORIZATION_FORBIDDEN"),
        (lambda p,a,j: (p,a,dict(j,status="READY")), "JOURNAL_STATUS_UNSAFE"),
        (lambda p,a,j: (p,a,dict(j,pgdata="C:\\\\other")), "JOURNAL_PGDATA_MISMATCH"),
        (lambda p,a,j: (p,a,dict(j,node_id="LS5")), "JOURNAL_IDENTITY_MISMATCH"),
    ]
    for transform, expected in cases:
        args = transform(*fixtures())
        saved = copy.deepcopy(args)
        r = check_pgdata_contract(*args)
        assert_blocked(r)
        assert expected in r["blockers"], (expected, r)
        assert args == saved

def test_behavioral_journal_objects_never_compared():
    class Hostile:
        def __eq__(self, other):
            raise RuntimeError("UNSAFE_EQ")
        def __ne__(self, other):
            raise RuntimeError("UNSAFE_NE")
    for field in ("status", "run_id", "node_id", "pgdata"):
        p, a, j = fixtures()
        j[field] = Hostile()
        r = check_pgdata_contract(p, a, j)
        assert_blocked(r)
        assert "JOURNAL_FIELD_TYPE_INVALID" in r["blockers"]

def test_all_journal_scalar_fields_reject_non_strings():
    for field in ("status", "run_id", "node_id", "pgdata"):
        for invalid in (None, True, False, 0, 1, 1.5, [], {}, b"BLOCKED"):
            p, a, j = fixtures()
            j[field] = invalid
            before = copy.deepcopy((p, a, j))
            result = check_pgdata_contract(p, a, j)
            assert_blocked(result)
            assert "JOURNAL_FIELD_TYPE_INVALID" in result["blockers"], (field, invalid, result)
            assert (p, a, j) == before

def test_adapter_identity_mismatch_codes():
    for field, value in (("run_id", "b" * 32), ("node_id", "LS5"),
                         ("postgres_port", True), ("postgres_port", 25433)):
        p, a, j = fixtures()
        a[field] = value
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        assert "ADAPTER_IDENTITY_MISMATCH" in result["blockers"]

def test_schema2_is_never_accepted():
    p, a, j = fixtures()
    p["schema"] = 2
    result = check_pgdata_contract(p, a, j)
    assert_blocked(result)
    assert result["blockers"] == ["PLAN_INVALID"]

def test_hostile_journal_cannot_mutate_plan_through_comparison():
    class Mutator:
        def __init__(self, plan):
            self.plan = plan
        def __ne__(self, other):
            self.plan["port"] = 25433
            return False
        def __eq__(self, other):
            self.plan["port"] = 25433
            return True

    for field in ("status", "run_id", "node_id", "pgdata"):
        p, a, j = fixtures()
        original = copy.deepcopy(p)
        j[field] = Mutator(p)
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        assert "JOURNAL_FIELD_TYPE_INVALID" in result["blockers"]
        assert p == original, field

def test_string_subclasses_not_accepted_as_journal_claims():
    class SpoofedString(str):
        def __ne__(self, other):
            raise AssertionError("comparison must not be invoked")
    for field in ("status", "run_id", "node_id", "pgdata"):
        p, a, j = fixtures()
        j[field] = SpoofedString(j[field])
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        assert "JOURNAL_FIELD_TYPE_INVALID" in result["blockers"]

def test_protected_nodes_and_unsafe_path_aliases_remain_blocked():
    for node in ("LS5", "LS7"):
        p, a, j = fixtures()
        p["node_id"] = node
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        assert result["blockers"] == ["PLAN_INVALID"]
    for root in (
        "c:\\\\GridLab\\\\" + RUN + "\\\\LAB01\\\\pgdata",
        "C:/GridLab/" + RUN + "/LAB01/pgdata",
        "C:\\\\GridLab\\\\" + RUN + "\\\\LAB01\\\\..\\\\pgdata",
        "\\\\\\\\server\\\\share\\\\pgdata",
    ):
        p, a, j = fixtures()
        p["data_root"] = root
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        assert "PLAN_INVALID" in result["blockers"], root

def test_missing_adapter_root_cannot_suppress_layout_blocker():
    for root in (None, "", 0, True, [], {}):
        p, a, j = fixtures()
        a["root"] = root
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        assert "PGDATA_LAYOUT_MISMATCH" in result["blockers"]
        assert "PHYSICAL_OWNERSHIP_UNVERIFIED" in result["blockers"]
        assert "SCHEMA1_ADAPTER_MAPPING_BLOCKED" in result["blockers"]

def test_metadata_matching_cannot_claim_ownership_or_authorize():
    p, a, j = fixtures()
    # Even a synthetic adapter path matching the requested PGDATA is
    # metadata only, never native identity or ownership evidence.
    a["root"] = "C:\\\\GridLab\\\\" + RUN + "\\\\LAB01\\\\pgdata"
    j.update(status="BLOCKED", execution_authorized=False, readiness_passed=False)
    result = check_pgdata_contract(p, a, j)
    assert_blocked(result)
    assert "PHYSICAL_OWNERSHIP_UNVERIFIED" in result["blockers"]
    assert "SCHEMA1_ADAPTER_MAPPING_BLOCKED" in result["blockers"]
    assert result["blockers"] == sorted(set(result["blockers"]))

def test_all_missing_journal_fields_fail_closed():
    for field in ("status", "execution_authorized", "readiness_passed",
                  "run_id", "node_id", "pgdata"):
        p, a, j = fixtures()
        del j[field]
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        if field in ("execution_authorized", "readiness_passed"):
            expected = "JOURNAL_AUTHORIZATION_FORBIDDEN"
        else:
            expected = "JOURNAL_FIELD_TYPE_INVALID"
        assert expected in result["blockers"], (field, result)

def test_missing_adapter_identity_fields_fail_closed():
    for field in ("run_id", "node_id", "postgres_port"):
        p, a, j = fixtures()
        del a[field]
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        assert "ADAPTER_IDENTITY_MISMATCH" in result["blockers"]

def test_behavioral_adapter_fields_never_compared():
    class Hostile:
        def __eq__(self, other):
            raise AssertionError("adapter comparison invoked")
        def __ne__(self, other):
            raise AssertionError("adapter comparison invoked")
        def __str__(self):
            raise AssertionError("adapter stringification invoked")
    for field in ("run_id", "node_id", "postgres_port", "root"):
        p, a, j = fixtures()
        a[field] = Hostile()
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        expected = "PGDATA_LAYOUT_MISMATCH" if field == "root" else "ADAPTER_IDENTITY_MISMATCH"
        assert expected in result["blockers"], (field, result)

def test_repeated_calls_are_deterministic_and_do_not_accumulate_blockers():
    p, a, j = fixtures()
    first = check_pgdata_contract(p, a, j)
    second = check_pgdata_contract(p, a, j)
    assert first == second
    assert first is not second
    assert first["blockers"] is not second["blockers"]
    assert first["blockers"] == sorted(set(first["blockers"]))
    assert_blocked(first)

def test_result_mutation_cannot_affect_future_checks():
    p, a, j = fixtures()
    first = check_pgdata_contract(p, a, j)
    first["blockers"].clear()
    first["status"] = "READY"
    first["execution_authorized"] = True
    second = check_pgdata_contract(p, a, j)
    assert_blocked(second)
    assert "PHYSICAL_OWNERSHIP_UNVERIFIED" in second["blockers"]
    assert "SCHEMA1_ADAPTER_MAPPING_BLOCKED" in second["blockers"]

def test_plan_malformed_shape_never_calls_adapter_or_journal_objects():
    class Hostile:
        def __eq__(self, other):
            raise AssertionError("unsafe equality")
        def __str__(self):
            raise AssertionError("unsafe string conversion")
    p, a, j = fixtures()
    p["schema"] = 2
    a["root"] = Hostile()
    j["status"] = Hostile()
    result = check_pgdata_contract(p, a, j)
    assert_blocked(result)
    assert result["blockers"] == ["PLAN_INVALID"]

def test_invalid_plan_fields_are_rejected_without_execution():
    mutations = (
        ("port", True), ("port", 19999), ("port", 50000),
        ("postgres_major", 17), ("listen_address", "0.0.0.0"),
        ("existing_cluster", True), ("runtime_stopped", False),
        ("operator_approved", False), ("schema", True),
        ("run_id", "not-a-run-id"), ("node_id", "LS5"),
    )
    for field, value in mutations:
        p, a, j = fixtures()
        p[field] = value
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        assert result["blockers"] == ["PLAN_INVALID"], (field, value, result)

def test_non_dictionary_journal_and_adapter_are_rejected():
    for value in (None, False, 0, "", [], (), set()):
        p, a, j = fixtures()
        adapter_result = check_pgdata_contract(p, value, j)
        journal_result = check_pgdata_contract(p, a, value)
        assert_blocked(adapter_result)
        assert_blocked(journal_result)
        assert "ADAPTER_MISSING" in adapter_result["blockers"]
        assert "JOURNAL_MISSING" in journal_result["blockers"]

def test_journal_boolean_authorization_flags_use_exact_false():
    for field in ("execution_authorized", "readiness_passed"):
        for unsafe in (None, True, 0, 1, "", "false", [], {}):
            p, a, j = fixtures()
            j[field] = unsafe
            result = check_pgdata_contract(p, a, j)
            assert_blocked(result)
            assert "JOURNAL_AUTHORIZATION_FORBIDDEN" in result["blockers"], (field, unsafe, result)

def test_journal_mismatches_report_specific_blockers():
    cases = (
        ("status", "READY", "JOURNAL_STATUS_UNSAFE"),
        ("run_id", "b" * 32, "JOURNAL_IDENTITY_MISMATCH"),
        ("node_id", "OTHER", "JOURNAL_IDENTITY_MISMATCH"),
        ("pgdata", "C:\\\\Other\\\\pgdata", "JOURNAL_PGDATA_MISMATCH"),
    )
    for field, value, blocker in cases:
        p, a, j = fixtures()
        j[field] = value
        result = check_pgdata_contract(p, a, j)
        assert_blocked(result)
        assert blocker in result["blockers"], (field, result)
        assert "PHYSICAL_OWNERSHIP_UNVERIFIED" in result["blockers"]
