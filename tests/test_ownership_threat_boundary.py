"""Pure evidence accounting regressions; no native calls or target paths."""
import xml.etree.ElementTree as E
import pytest
from installer.tests.verify_ownership_adversarial import assess, EXPECTED, OBSERVATIONS


def xml_report():
    root = E.Element('testsuite')
    for name in sorted(EXPECTED):
        case = E.SubElement(root, 'testcase', name=name)
        props = E.SubElement(case, 'properties')
        value = sorted(OBSERVATIONS[name])[0]
        E.SubElement(props, 'property', name='observed', value=value)
        if name == 'test_bounded_kernel_exhaustion_unproven':
            E.SubElement(case, 'skipped', message='BLOCKED_UNPROVEN: global exhaustion')
    return root


def test_kernel_exhaustion_must_not_be_promoted_to_pass():
    root = xml_report()
    case = next(t for t in root if t.get('name') == 'test_bounded_kernel_exhaustion_unproven')
    case.remove(case.find('skipped'))
    with pytest.raises(ValueError, match='EXHAUSTION_MUST_REMAIN_UNPROVEN'):
        assess(root, 'a' * 40)


@pytest.mark.parametrize('observed', ['ACL_ABA_UNDETECTED_LIMIT', 'ACL_ABA_DETECTED_THIS_RUN'])
def test_single_aba_observation_never_proves_aba_safety(observed):
    root = xml_report()
    case = next(t for t in root if t.get('name') == 'test_real_acl_replace_restore_aba_limit')
    case.find('./properties/property').set('value', observed)
    r = assess(root, 'a' * 40)
    assert r['readiness_passed'] is False and r['verified_safety_cases'] == 0
    assert set(r['unresolved_risks']) == {'ACL_NAMESPACE_ABA', 'GLOBAL_KERNEL_EXHAUSTION'}
    assert next(c for c in r['cases'] if c['case'] == case.get('name'))['security_outcome'] in {'LIMIT_REPRODUCED', 'UNPROVEN'}


@pytest.mark.parametrize('model', ['A', 'B'])
def test_threat_models_never_authorize_even_with_green_fixture_tests(model):
    from installer.ownership_threat_boundary import threat_boundary
    r = threat_boundary(model)
    assert r['status'] == 'BLOCKED' and r['evidence_only'] is True
    assert r['execution_authorized'] is False and r['physical_ready'] is False
    assert len(r['matrix']) == 7
    assert all(row['verification'] == 'BLOCKED' for row in r['matrix'])
    assert r['decision'] == ('STOP_OS_BOUNDARY_REQUIRED' if model == 'B' else 'BLOCKED_PROVISIONING_UNPROVEN')


@pytest.mark.parametrize('model', ['', 'admin', 'A_APPROVED', None, True, {}, ['A']])
def test_unknown_or_asserted_approval_cannot_select_a_threat_model(model):
    from installer.ownership_threat_boundary import threat_boundary
    with pytest.raises(ValueError):
        threat_boundary(model)
