"""Offline-only PostgreSQL physical-readiness regressions."""
from installer.pgdata_physical_readiness_offline import (
    CONTRACT, FIELDS, FLAGS, evaluate,
)


def packet():
    return {
        "contract": CONTRACT,
        "source_commit": "4d0569d64763eba358c58d47211c5bb0165f78cb",
        "requested_action": "OFFLINE_REVIEW_ONLY",
        "evidence": {name: {"state": "UNKNOWN", "sha256": None} for name in FIELDS},
    }


def assert_no_go(result):
    assert result["status"] == "BLOCKED"
    assert all(result[name] is False for name in FLAGS)
    assert result["guest_vm_cases"] == "12 NOT_RUN"
    assert result["pc4_sid_acl_cases"] == "10 NOT_RUN"
    for blocker in (
        "PHYSICAL_OWNERSHIP_UNVERIFIED",
        "SCHEMA1_ADAPTER_MAPPING_BLOCKED",
        "EXISTING_CLUSTER_EXCLUSION_UNVERIFIED",
        "BACKUP_RESTORE_NOT_PROVEN",
    ):
        assert blocker in result["blockers"]


def test_empty_valid_packet_never_authorizes():
    result = evaluate(packet())
    assert result["metadata_valid"] is True
    assert_no_go(result)


def test_forged_full_evidence_never_authorizes():
    value = packet()
    for item in value["evidence"].values():
        item.update(state="EVIDENCE_PROPOSED", sha256="a" * 64)
    result = evaluate(value)
    assert result["metadata_valid"] is True
    assert_no_go(result)


def test_all_malformed_packets_fail_closed():
    bad = [None, [], "yes", {}, {"status": "PASS"}, {"contract": CONTRACT}]
    for value in bad:
        result = evaluate(value)
        assert result["metadata_valid"] is False
        assert_no_go(result)


def test_unknown_fields_and_missing_fields_rejected():
    value = packet()
    value["evidence"]["unreviewed"] = {"state": "EVIDENCE_PROPOSED", "sha256": "a" * 64}
    assert evaluate(value)["errors"] == ["EVIDENCE_SCHEMA_INVALID"]
    assert_no_go(evaluate(value))
    value = packet()
    del value["evidence"]["isolated_restore_review"]
    assert evaluate(value)["errors"] == ["EVIDENCE_SCHEMA_INVALID"]


def test_false_or_unbound_claims_rejected():
    value = packet()
    value["evidence"]["full_sid_token_acl_review"] = {"state": "PASS", "sha256": "a" * 64}
    result = evaluate(value)
    assert "EVIDENCE_STATE_INVALID:full_sid_token_acl_review" in result["errors"]
    assert_no_go(result)
    value = packet()
    value["evidence"]["isolated_restore_review"] = {"state": "EVIDENCE_PROPOSED", "sha256": None}
    result = evaluate(value)
    assert "EVIDENCE_DIGEST_MISSING:isolated_restore_review" in result["errors"]
    assert_no_go(result)


def test_execution_and_schema_activation_requests_rejected():
    for action in ("INITDB", "DEPLOY", "SCHEMA2_ENABLE", True, None):
        value = packet()
        value["requested_action"] = action
        result = evaluate(value)
        assert "ACTION_NOT_AUTHORIZED" in result["errors"]
        assert_no_go(result)


def test_evidence_object_shape_and_digest_are_strict():
    for invalid in ([], None, "PASS", {"state": "UNKNOWN"}, {"state": "UNKNOWN", "sha256": None, "extra": True}):
        value = packet()
        value["evidence"]["backup_wal_retention_review"] = invalid
        result = evaluate(value)
        assert "EVIDENCE_ITEM_INVALID:backup_wal_retention_review" in result["errors"]
        assert_no_go(result)
    for invalid in (True, 0, "0" * 64, "A" * 64, "x" * 64):
        value = packet()
        value["evidence"]["off_host_copy_review"]["sha256"] = invalid
        result = evaluate(value)
        assert "EVIDENCE_DIGEST_INVALID:off_host_copy_review" in result["errors"]
        assert_no_go(result)
