"""Offline VM lab design validator. Metadata only; never creates or inspects resources."""
import json
import re
import sys
import uuid
from pathlib import PureWindowsPath

CASES = (
    ('write', 'Different adversary token denied file/data/child writes.'),
    ('delete', 'Different adversary token denied delete and delete-child rights.'),
    ('write_dac', 'Different adversary token denied WRITE_DAC.'),
    ('write_owner', 'Different adversary token denied WRITE_OWNER.'),
    ('acl_mutation', 'Attempt DACL mutation from adversary token; verifier must refuse on uncertainty.'),
    ('acl_aba', 'Attempt change/restore schedule; never infer safety from a sampled absence.'),
    ('inherited_acl', 'Unexpected inherited ACE must block; do not repair permissions automatically.'),
    ('junction', 'Attempt junction/reparse substitution inside the future disposable guest fixture.'),
    ('ancestor', 'Attempt owned ancestor rename/substitution before and during pinned session.'),
    ('existing_mapping', 'Pre-existing writable mapping/handle remains an explicit exclusion to attest.'),
    ('privileges', 'Check actual effective token/elevation/groups; privileged token must block. No exploit.'),
    ('distinct_token', 'Attest distinct effective token user SIDs for owner/verifier/adversary, not names.'),
)


def _need(ok, code):
    if not ok:
        raise ValueError(code)


def _shape(value, names):
    _need(type(value) is dict and set(value) == set(names.split()), 'VM_PLAN_SCHEMA_INVALID')


def _guid(value):
    _need(type(value) is str and len(value) == 36, 'VM_ID_INVALID')
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise ValueError('VM_ID_INVALID') from None
    _need(str(parsed) == value and parsed.version == 4, 'VM_ID_INVALID')
    return value


def _sid(value):
    _need(type(value) is str and re.fullmatch(r'S-1-5-21-(?:[1-9][0-9]{0,9}-){3}[1-9][0-9]{0,9}', value), 'VM_SID_INVALID')
    _need(all(int(n) <= 4294967295 for n in value.split('-')[4:]), 'VM_SID_INVALID')
    return value


def _path(value):
    _need(type(value) is str and len(value) <= 220 and re.fullmatch(r'[A-Z]:\\[A-Za-z0-9_.\\-]+', value), 'VM_PATH_INVALID')
    parts = value[3:].split('\\')
    _need(all(p and p not in ('.', '..') and not p.endswith('.') and
              not re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', p)
              for p in parts), 'VM_PATH_INVALID')
    return PureWindowsPath(value)


def _digest(value):
    _need(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) and len(set(value)) > 0, 'VM_EVIDENCE_INVALID')


def validate_vm_lab_plan(plan):
    """Validate declarations only. An approved field is NOT independent attestation."""
    _shape(plan, 'schema mode threat_model lab_id vm_id host storage image network integration accounts approval quotas teardown schema2 imported_credentials')
    _need(type(plan['schema']) is int and plan['schema'] == 1, 'VM_PLAN_VERSION_INVALID')
    _need(plan['mode'] == 'PlanOnly' and plan['threat_model'] == 'A', 'VM_PLAN_MODE_BLOCKED')
    _need(plan['schema2'] is False and plan['imported_credentials'] is False and plan['teardown'] == 'PreserveOnly', 'VM_EXECUTION_FORBIDDEN')
    lab = _guid(plan['lab_id']); vm = _guid(plan['vm_id'])
    host = plan['host']; _shape(host, 'id aliases trusted_admin hypervisor inventory_complete protected_paths')
    _need(type(host['id']) is str and host['id'].startswith('LAB-HOST-'), 'VM_HOST_INVALID')
    host_guid = _guid(host['id'][9:])
    _need(host['trusted_admin'] is True and host['inventory_complete'] is True and host['hypervisor'] == 'Hyper-V', 'VM_HOST_TRUST_UNPROVEN')
    _need(type(host['aliases']) is list and 1 <= len(host['aliases']) <= 16, 'VM_HOST_ALIASES_REQUIRED')
    for alias in host['aliases']:
        _need(type(alias) is str and re.fullmatch('[A-Za-z0-9_.-]{1,100}', alias), 'VM_HOST_ALIAS_INVALID')
        _need(re.sub('[-_]', '', alias.split('.')[0]).upper() not in ('LS5', 'LS7'), 'VM_PROTECTED_HOST')
    storage = plan['storage']; _shape(storage, 'root disk_id fresh_disk existing_disk shared_mounts host_folders passthrough')
    root = _path(storage['root']); disk = _guid(storage['disk_id'])
    _need(len({lab, vm, host_guid, disk}) == 4, 'VM_ID_REUSED')
    _need(root.parts[1:] == ('GridVmLab', lab), 'VM_STORAGE_NOT_EXCLUSIVE_LAYOUT')
    _need(type(host['protected_paths']) is list and 1 <= len(host['protected_paths']) <= 128, 'VM_PROTECTED_INVENTORY_REQUIRED')
    for value in host['protected_paths']:
        protected = _path(value)
        _need(root != protected and root not in protected.parents and protected not in root.parents, 'VM_STORAGE_OVERLAP')
    _need(storage['fresh_disk'] is True and storage['existing_disk'] is False and storage['passthrough'] is False, 'VM_DISK_REUSE_OR_PASSTHROUGH')
    _need(storage['shared_mounts'] == [] and type(storage['shared_mounts']) is list and
          storage['host_folders'] == [] and type(storage['host_folders']) is list, 'VM_HOST_SHARING_FORBIDDEN')
    image = plan['image']; _shape(image, 'sha256 immutable trusted_source provenance_sha256 publisher')
    _digest(image['sha256']); _digest(image['provenance_sha256'])
    _need(image['immutable'] is True and image['trusted_source'] is True and
          type(image['publisher']) is str and re.fullmatch('[A-Z0-9-]{1,64}', image['publisher']), 'VM_IMAGE_UNTRUSTED')
    network = plan['network']; _shape(network, 'mode adapters tailscale ssh')
    _need(network['mode'] == 'Disconnected' and type(network['adapters']) is list and network['adapters'] == [] and
          network['tailscale'] is False and network['ssh'] is False, 'VM_NETWORK_FORBIDDEN')
    integration = plan['integration']
    _shape(integration, 'clipboard drag_drop enhanced_session guest_services device_passthrough')
    _need(all(value is False for value in integration.values()), 'VM_HOST_INTEGRATION_FORBIDDEN')
    accounts = plan['accounts']
    _need(type(accounts) is list and len(accounts) == 3, 'VM_PRINCIPALS_INVALID')
    roles = []; sids = []
    for account in accounts:
        _shape(account, 'role sid token_sid elevated administrator enabled_privileges credential_origin')
        _need(type(account['role']) is str, 'VM_PRINCIPALS_INVALID')
        roles.append(account['role']); sids.append(_sid(account['sid']))
        _need(int(account['sid'].split('-')[-1]) >= 1000, 'VM_GUEST_BUILTIN_IDENTITY')
        _need(_sid(account['token_sid']) == account['sid'], 'VM_TOKEN_MISMATCH')
        _need(account['elevated'] is False and account['administrator'] is False and
              type(account['enabled_privileges']) is list and account['enabled_privileges'] == [] and
              account['credential_origin'] == 'FreshGuestOnly', 'VM_PRINCIPAL_PRIVILEGED_OR_IMPORTED')
    _need(set(roles) == {'owner', 'verifier', 'adversary'} and len(set(sids)) == 3, 'VM_PRINCIPALS_NOT_INDEPENDENT')
    approval = plan['approval']; _shape(approval, 'approved requester_sid approver_sid plan_review_id')
    _need(approval['approved'] is True, 'VM_APPROVAL_REQUIRED')
    requester = _sid(approval['requester_sid']); approver = _sid(approval['approver_sid'])
    _need(requester != approver and requester not in sids and approver not in sids, 'VM_APPROVAL_NOT_INDEPENDENT')
    _digest(approval['plan_review_id'])
    quotas = plan['quotas']; _shape(quotas, 'cpu memory_mib disk_gib duration_minutes')
    for key, low, high in [('cpu',1,4), ('memory_mib',1024,8192), ('disk_gib',8,80), ('duration_minutes',1,120)]:
        _need(type(quotas[key]) is int and low <= quotas[key] <= high, 'VM_QUOTA_INVALID')
    return {'schema':1, 'mode':'PlanOnly', 'status':'BLOCKED', 'assurance':'STATIC_METADATA_ONLY',
            'plan_validation':'VALID_METADATA_ONLY', 'execution_authorized':False,
            'physical_ready':False, 'readiness_passed':False, 'verified_safety_cases':0,
            'negative_cases':[{'case':case, 'objective':objective, 'execution':'NOT_RUN',
                               'assurance':'BLOCKED_UNPROVEN'} for case, objective in CASES],
            'blockers':['NO_EXECUTOR', 'HOST_AND_IMAGE_ATTESTATION_REQUIRED', 'INDEPENDENT_APPROVAL_NOT_AUTHENTICATED',
                        'PATH_ALIAS_AND_STORAGE_OWNERSHIP_UNPROVEN', 'ACTUAL_TOKEN_SEPARATION_NOT_ATTESTED',
                        'NETWORK_AND_SHARED_DEVICE_ISOLATION_NOT_ATTESTED', 'ACL_NAMESPACE_ABA',
                        'GLOBAL_KERNEL_EXHAUSTION', 'ALL_GUEST_NEGATIVE_CASES_NOT_RUN']}


def parse_vm_lab_plan(raw):
    _need(type(raw) is str and len(raw.encode('utf-8')) <= 65536, 'VM_JSON_SIZE_INVALID')
    def pairs(items):
        result = {}
        for key, value in items:
            _need(key not in result, 'VM_JSON_DUPLICATE_KEY')
            result[key] = value
        return result
    def constant(_):
        raise ValueError('VM_JSON_NONFINITE')
    try:
        return validate_vm_lab_plan(json.loads(raw, object_pairs_hook=pairs, parse_constant=constant))
    except (RecursionError, json.JSONDecodeError):
        raise ValueError('VM_JSON_INVALID') from None


if __name__ == '__main__':
    try:
        print(json.dumps(parse_vm_lab_plan(sys.stdin.read(65537)), sort_keys=True))
    except ValueError as exc:
        # Only fixed validator codes, never input/credentials or exception payloads.
        code = str(exc)
        if not re.fullmatch('VM_[A-Z_]{1,64}', code): code = 'VM_PLAN_INVALID'
        print(json.dumps({'status':'BLOCKED', 'error':'VM_PLAN_REJECTED',
                          'reason':code, 'execution_authorized':False}))
        sys.exit(2)
