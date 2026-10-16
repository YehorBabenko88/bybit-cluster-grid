"""VM lab metadata regressions only; no VM/native/SQL/process operations."""
import copy
import pytest


def plan():
    return {
        'schema': 1, 'mode': 'PlanOnly', 'threat_model': 'A',
        'lab_id': '11111111-1111-4111-8111-111111111111',
        'vm_id': '22222222-2222-4222-8222-222222222222',
        'host': {'id': 'LAB-HOST-33333333-3333-4333-8333-333333333333',
                 'aliases': ['DISPOSABLE-LAB-HOST'], 'trusted_admin': True,
                 'hypervisor': 'Hyper-V', 'inventory_complete': True,
                 'protected_paths': [r'C:\BybitClusterGrid', r'D:\InstalledGrid']},
        'storage': {'root': r'D:\GridVmLab\11111111-1111-4111-8111-111111111111',
                    'disk_id': '44444444-4444-4444-8444-444444444444',
                    'fresh_disk': True, 'existing_disk': False, 'shared_mounts': [],
                    'host_folders': [], 'passthrough': False},
        'image': {'sha256': 'a'*64, 'immutable': True, 'trusted_source': True,
                  'provenance_sha256': 'b'*64, 'publisher': 'APPROVED-LAB-IMAGE'},
        'network': {'mode': 'Disconnected', 'adapters': [], 'tailscale': False, 'ssh': False},
        'integration': {'clipboard': False, 'drag_drop': False, 'enhanced_session': False,
                        'guest_services': False, 'device_passthrough': False},
        'accounts': [
            {'role': role, 'sid': f'S-1-5-21-100-200-300-{rid}', 'token_sid': f'S-1-5-21-100-200-300-{rid}',
             'elevated': False, 'administrator': False, 'enabled_privileges': [],
             'credential_origin': 'FreshGuestOnly'}
            for role, rid in [('owner',1001), ('verifier',1002), ('adversary',1003)]],
        'approval': {'approved': True, 'requester_sid': 'S-1-5-21-400-500-600-1001',
                     'approver_sid': 'S-1-5-21-400-500-600-1002', 'plan_review_id': 'c'*64},
        'quotas': {'cpu': 2, 'memory_mib': 4096, 'disk_gib': 40, 'duration_minutes': 60},
        'teardown': 'PreserveOnly', 'schema2': False, 'imported_credentials': False,
    }


def validate(p):
    from installer.vm_lab_plan import validate_vm_lab_plan
    return validate_vm_lab_plan(p)


def test_valid_metadata_is_never_readiness_or_execution_authorization():
    r = validate(plan())
    assert r['status'] == 'BLOCKED' and r['plan_validation'] == 'VALID_METADATA_ONLY'
    assert r['execution_authorized'] is False and r['physical_ready'] is False
    assert r['readiness_passed'] is False and r['verified_safety_cases'] == 0
    assert len(r['negative_cases']) == 12
    assert all(c['execution'] == 'NOT_RUN' and c['assurance'] == 'BLOCKED_UNPROVEN' for c in r['negative_cases'])


@pytest.mark.parametrize('path,value', [
    (('schema',), True), (('mode',), 'Execute'), (('schema2',), True), (('threat_model',), 'B'),
    (('host','aliases'), ['LS5']), (('host','aliases'), ['ls-7.example.local']),
    (('host','id'), 'LS5'), (('host','trusted_admin'), False), (('host','inventory_complete'), False),
    (('host','protected_paths'), []), (('host','protected_paths'), [r'D:\GridVmLab']),
    (('storage','root'), r'D:\GridVmLab\11111111-1111-4111-8111-111111111111\..\InstalledGrid'),
    (('storage','root'), r'\\LS5\share'), (('storage','root'), r'C:\ProgramData\Grid'),
    (('storage','root'), r'D:\GRIDVM~1\11111111-1111-4111-8111-111111111111'),
    (('storage','fresh_disk'), False), (('storage','existing_disk'), True),
    (('storage','shared_mounts'), ['D:\\host']), (('storage','host_folders'), ['C:\\']),
    (('storage','passthrough'), True), (('network','mode'), 'Bridge'),
    (('network','adapters'), ['production']), (('network','tailscale'), True), (('network','ssh'), True),
    (('image','sha256'), 'untrusted'), (('image','trusted_source'), False),
    (('image','immutable'), False), (('image','provenance_sha256'), ''),
    (('approval','approved'), False), (('approval','plan_review_id'), ''),
    (('quotas','cpu'), True), (('quotas','memory_mib'), 999999),
    (('quotas','disk_gib'), 0), (('quotas','duration_minutes'), 0),
    (('teardown',), 'Delete'), (('imported_credentials',), True),
    (('vm_id',), '11111111-1111-4111-8111-111111111111'),
])
def test_unsafe_metadata_is_rejected(path, value):
    p = plan()
    target = p
    for key in path[:-1]: target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError): validate(p)


@pytest.mark.parametrize('mutation', ['same_sid', 'same_token', 'admin', 'elevated', 'privileges',
                                      'credential', 'self_approval', 'guest_approver', 'unknown', 'missing'])
def test_principal_and_schema_confusion_rejected(mutation):
    p = plan()
    if mutation == 'same_sid': p['accounts'][2]['sid'] = p['accounts'][0]['sid']
    elif mutation == 'same_token': p['accounts'][2]['token_sid'] = p['accounts'][0]['token_sid']
    elif mutation == 'admin': p['accounts'][2]['administrator'] = True
    elif mutation == 'elevated': p['accounts'][2]['elevated'] = True
    elif mutation == 'privileges': p['accounts'][2]['enabled_privileges'] = ['SeTakeOwnershipPrivilege']
    elif mutation == 'credential': p['accounts'][2]['credential_origin'] = 'ProductionSSH'
    elif mutation == 'self_approval': p['approval']['approver_sid'] = p['approval']['requester_sid']
    elif mutation == 'guest_approver': p['approval']['approver_sid'] = p['accounts'][0]['sid']
    elif mutation == 'unknown': p['execution_authorized'] = True
    elif mutation == 'missing': del p['network']
    with pytest.raises(ValueError): validate(p)


def test_input_not_modified_and_results_not_shared():
    p = plan(); before = copy.deepcopy(p)
    r = validate(p); r['negative_cases'][0]['execution'] = 'PASS'
    assert p == before
    assert validate(p)['negative_cases'][0]['execution'] == 'NOT_RUN'


@pytest.mark.parametrize('raw', ['{}', '{"schema":1,"schema":1}', '{"schema":NaN}', '[]', 'x'*65537], ids=['empty','duplicate','nan','array','oversize'])
def test_json_fail_closed(raw):
    from installer.vm_lab_plan import parse_vm_lab_plan
    with pytest.raises(ValueError): parse_vm_lab_plan(raw)



@pytest.mark.parametrize('capability', ['clipboard','drag_drop','enhanced_session','guest_services','device_passthrough'])
def test_host_integration_forbidden(capability):
    p = plan(); p['integration'][capability] = True
    with pytest.raises(ValueError): validate(p)


def test_required_case_set_cannot_be_caller_supplied():
    p = plan(); p['negative_cases'] = [{'execution':'PASS'}]
    with pytest.raises(ValueError): validate(p)


def test_nested_unknown_fields_cannot_smuggle_executor_configuration():
    for section in ('host','storage','image','network','approval','quotas','integration'):
        p = plan(); p[section]['execute'] = True
        with pytest.raises(ValueError): validate(p)


def test_invalid_account_role_types_fail_closed():
    p = plan(); p['accounts'][0]['role'] = []
    with pytest.raises(ValueError): validate(p)


@pytest.mark.parametrize('rid', [500,501,502,999])
def test_builtin_or_reserved_guest_identity_contradicts_nonadmin_plan(rid):
    p = plan(); sid = f'S-1-5-21-100-200-300-{rid}'
    p['accounts'][2]['sid'] = sid; p['accounts'][2]['token_sid'] = sid
    with pytest.raises(ValueError): validate(p)
