from vm_principal_lab.evidence_consistency import EvidenceClaim, detect_evidence_conflicts

def claim(source, **overrides):
    values = dict(principal="guest-a", source=source, observed_sid="S-1-5-21-1",
                  token_sid="S-1-5-21-1", elevation="limited",
                  group_sids=("S-1-5-32-545",), acl_digest="sha256:example")
    values.update(overrides)
    return EvidenceClaim(**values)

def test_independent_matching_sources_have_no_conflicts():
    assert detect_evidence_conflicts({"one": claim("source-1"), "two": claim("source-2")}) == ()

def test_disagreement_is_detected():
    issues = detect_evidence_conflicts({
        "one": claim("source-1"),
        "two": claim("source-2", observed_sid="S-1-5-21-2", acl_digest="different"),
    })
    assert "guest-a:OBSERVED_SID_CONFLICT" in issues
    assert "guest-a:ACL_DIGEST_CONFLICT" in issues
    assert "two:SID_TOKEN_CONFLICT" in issues

def test_duplicate_provenance_is_detected():
    assert "guest-a:DUPLICATE_SOURCE" in detect_evidence_conflicts({
        "one": claim("same"), "two": claim("same")
    })

def test_missing_evidence_fails_closed():
    issues = detect_evidence_conflicts({"one": claim("", acl_digest="", elevation="unknown")})
    assert "INSUFFICIENT_INDEPENDENT_SOURCES" in issues
    assert "one:MISSING_PROVENANCE" in issues
    assert "one:ACL_EVIDENCE_MISSING" in issues
    assert "one:ELEVATION_UNKNOWN" in issues

def test_two_claims_for_different_guests_do_not_count_as_independent():
    issues = detect_evidence_conflicts({
        "one": claim("source-1", principal="guest-a"),
        "two": claim("source-2", principal="guest-b", observed_sid="S-1-5-21-2", token_sid="S-1-5-21-2"),
    })
    assert "guest-a:INSUFFICIENT_INDEPENDENT_SOURCES" in issues
    assert "guest-b:INSUFFICIENT_INDEPENDENT_SOURCES" in issues

def test_source_id_reuse_across_guests_is_detected():
    issues = detect_evidence_conflicts({
        "one": claim("shared-source", principal="guest-a"),
        "two": claim("shared-source", principal="guest-b", observed_sid="S-1-5-21-2", token_sid="S-1-5-21-2"),
    })
    assert "two:SOURCE_REUSED_ACROSS_PRINCIPALS" in issues

def test_observed_sid_reuse_across_guests_is_detected():
    issues = detect_evidence_conflicts({
        "one": claim("source-1", principal="guest-a"),
        "two": claim("source-2", principal="guest-b"),
    })
    assert "two:OBSERVED_SID_REUSED_ACROSS_PRINCIPALS" in issues

def test_independent_sources_per_each_guest_are_accepted_as_consistent():
    issues = detect_evidence_conflicts({
        "a1": claim("a1"), "a2": claim("a2"),
        "b1": claim("b1", principal="guest-b", observed_sid="S-1-5-21-2", token_sid="S-1-5-21-2"),
        "b2": claim("b2", principal="guest-b", observed_sid="S-1-5-21-2", token_sid="S-1-5-21-2"),
    })
    assert issues == ()

def test_token_sid_reuse_across_guests_detected_even_with_distinct_observed_sids():
    issues = detect_evidence_conflicts({
        "one": claim("source-1", principal="guest-a"),
        "two": claim("source-2", principal="guest-b", observed_sid="S-1-5-21-2"),
    })
    assert "two:TOKEN_SID_REUSED_ACROSS_PRINCIPALS" in issues
    assert "two:SID_TOKEN_CONFLICT" in issues

def test_distinct_guest_token_sids_do_not_trigger_reuse():
    issues = detect_evidence_conflicts({
        "a1": claim("a1"), "a2": claim("a2"),
        "b1": claim("b1", principal="guest-b", observed_sid="S-1-5-21-2", token_sid="S-1-5-21-2"),
        "b2": claim("b2", principal="guest-b", observed_sid="S-1-5-21-2", token_sid="S-1-5-21-2"),
    })
    assert not any("TOKEN_SID_REUSED" in issue for issue in issues)

def test_p2_r4_consistency_rejects_overflow_sid():
    errors = detect_evidence_conflicts({
        "one": claim("source-1", observed_sid="S-1-5-4294967296",
                     token_sid="S-1-5-4294967296"),
        "two": claim("source-2"),
    })
    assert "one:INVALID_SID" in errors
    assert errors


def test_p2_r5_consistency_rejects_fake_group_membership():
    errors = detect_evidence_conflicts({
        "one": claim("source-1", group_sids=("NOT-A-SID",)),
        "two": claim("source-2"),
    })
    assert "one:INVALID_GROUP_SIDS" in errors


def test_p2_r5_consistency_rejects_wrong_claim_type():
    errors = detect_evidence_conflicts({"one": "forged", "two": claim("source-2")})
    assert "one:INVALID_CLAIM" in errors
