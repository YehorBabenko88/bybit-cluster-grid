"""Independent synthetic ACL review; no host access and no physical attestation."""
from copy import deepcopy

import pytest

from tools.s0_ancestor_acl_review import review_snapshot

USER = 'S-1-5-21-1-2-3-1002'
CAP = 'S-1-15-3-2968813833-811790644-2202111208-3784096404-1081847329-2708967783-1438471679'


def ace(sid=CAP, mask=0x1F01FF, flags=0, kind=0):
    return dict(sid=sid, mask=mask, flags=flags, kind=kind)


def snapshot(*extra):
    return dict(schema=1, operator_sid=USER, ancestors=[
        dict(identity='volume:1', owner=USER, dacl_present=True,
             reparse=False, complete=True, aces=[ace(USER), *extra]),
        dict(identity='volume:2', owner=USER, dacl_present=True,
             reparse=False, complete=True, aces=[ace(USER)]),
    ])


def test_safe_model_never_grants_host_or_execution_authority():
    result = review_snapshot(snapshot())
    assert result['model'] == 'OFFLINE_MODEL_PASS'
    assert result['host'] == 'BLOCKED'
    assert result['execute'] is False and result['cleanup'] is False


@pytest.mark.parametrize('flags', [0, 16])
def test_effective_full_control_not_neutralized_by_inherit_only_sibling(flags):
    result = review_snapshot(snapshot(ace(flags=flags), ace(mask=0x10000000, flags=27)))
    assert result['model'] == 'BLOCKED'
    assert 'UNTRUSTED_EFFECTIVE_MUTATION' in result['findings']
    assert 'UNTRUSTED_INHERITABLE_MUTATION' in result['findings']


@pytest.mark.parametrize('flags', [11, 27])
def test_inherit_only_is_not_current_grant_but_unprotected_children_are_at_risk(flags):
    result = review_snapshot(snapshot(ace(mask=0x10000000, flags=flags)))
    assert result['model'] == 'BLOCKED'
    assert 'UNTRUSTED_EFFECTIVE_MUTATION' not in result['findings']
    assert 'UNTRUSTED_INHERITABLE_MUTATION' in result['findings']


def test_raw_object_inherit_bit_is_not_dotnet_propagation_inherit_only():
    result = review_snapshot(snapshot(ace(mask=0x40000, flags=2)))
    assert 'UNTRUSTED_EFFECTIVE_MUTATION' in result['findings']


@pytest.mark.parametrize('mask', [0x40, 0x10000, 0x40000, 0x80000, 0x10000000, 0x40000000])
def test_parent_replacement_control_bits_block_even_with_clean_descendant(mask):
    result = review_snapshot(snapshot(ace(mask=mask)))
    assert result['model'] == 'BLOCKED'


def test_capability_prefix_is_not_a_trust_rule():
    assert review_snapshot(snapshot(ace()))['model'] == 'BLOCKED'


def test_allow_order_and_inheritance_mapping_do_not_redeem_effective_rights():
    for entries in ((ace(flags=16), ace(mask=0x10000000, flags=27)),
                    (ace(mask=0x10000000, flags=27), ace(flags=16))):
        assert review_snapshot(snapshot(*entries))['model'] == 'BLOCKED'


def test_untrusted_local_group_with_mutation_rights_is_not_a_user():
    assert review_snapshot(snapshot(ace(sid='S-1-5-32-545')))['model'] == 'BLOCKED'


def test_deny_ace_does_not_establish_effective_access_or_cancel_conservative_risk():
    assert review_snapshot(snapshot(ace(kind=1), ace()))['model'] == 'BLOCKED'


@pytest.mark.parametrize('sid', ['S-1-15-3-x', 'S-1-15-3-01', 'S-1-15-3-4294967296',
                             'S-1-15-3-1\n', 's-1-15-3-1', '', None])
def test_sid_parse_errors_fail_closed(sid):
    assert review_snapshot(snapshot(ace(sid=sid)))['model'] == 'BLOCKED'


@pytest.mark.parametrize('field,value', [('mask', True), ('mask', -1), ('mask', 2**32),
                                      ('flags', 32), ('flags', True), ('kind', 9),
                                      ('kind', True)])
def test_unknown_ace_or_invalid_numeric_representation_blocks(field, value):
    entry = ace(); entry[field] = value
    assert review_snapshot(snapshot(entry))['model'] == 'BLOCKED'


@pytest.mark.parametrize('field,value', [('owner', CAP), ('owner', None),
                                      ('dacl_present', False), ('dacl_present', 1),
                                      ('reparse', True), ('reparse', None),
                                      ('complete', False), ('complete', 1),
                                      ('identity', ''), ('aces', None)])
def test_incomplete_ancestor_custody_cannot_pass(field, value):
    data = snapshot(); data['ancestors'][0][field] = value
    assert review_snapshot(data)['model'] == 'BLOCKED'


def test_duplicate_identity_or_missing_ancestry_blocks():
    data = snapshot(); data['ancestors'][1] = deepcopy(data['ancestors'][0])
    assert review_snapshot(data)['model'] == 'BLOCKED'
    data['ancestors'] = []
    assert review_snapshot(data)['model'] == 'BLOCKED'


def test_no_parent_name_or_extra_producer_claim_can_create_a_pass():
    data = snapshot(); data['host_verified'] = True
    assert review_snapshot(data)['model'] == 'BLOCKED'
    data = snapshot(); data['ancestors'][0]['known_folder'] = 'UserProfile'
    assert review_snapshot(data)['model'] == 'BLOCKED'


def test_model_does_not_accept_group_identity_in_place_of_operator():
    data = snapshot(); data['operator_sid'] = 'S-1-5-32-544'
    assert review_snapshot(data)['model'] == 'BLOCKED'


def test_read_only_unknown_ace_is_not_silently_an_enabled_token_membership_proof():
    result = review_snapshot(snapshot(ace(mask=0x1200A9)))
    assert result['model'] == 'OFFLINE_MODEL_PASS'
    assert result['host'] == 'BLOCKED'
    assert result['effective_access'] == 'NOT_EVALUATED'


@pytest.mark.parametrize('mask', [0x200, 0x04000000, 0x08000000, 0x01000000, 0x02000000])
@pytest.mark.parametrize('sid,kind', [(CAP, 0), (CAP, 1), (USER, 0)])
def test_unsupported_access_mask_bits_block_even_for_trusted_or_deny_ace(mask, sid, kind):
    assert review_snapshot(snapshot(ace(sid=sid, mask=mask, kind=kind)))['model'] == 'BLOCKED'


@pytest.mark.parametrize('flags', [0, 3, 16, 19])
def test_effective_generic_all_blocks(flags):
    assert review_snapshot(snapshot(ace(mask=0x10000000, flags=flags)))['model'] == 'BLOCKED'


@pytest.mark.parametrize('schema', [True, 1.0, '1', None])
def test_schema_types_are_not_coerced(schema):
    data = snapshot(); data['schema'] = schema
    assert review_snapshot(data)['model'] == 'BLOCKED'
