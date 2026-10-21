"""Future PGDATA PowerShell-layout intent. Pure metadata; never native authority.

Does not import/call installer, producer, adapter, filesystem or Windows APIs.
Caller history is untrusted input, not a persistent replay ledger.
"""
import hashlib
import json
import re
import uuid
from installer.vm_lab_json import canonical, check_value, load
from vm_principal_lab.sid_validation import valid_sid

BASE = '272ea6c1d011779a83a5d89478e237a6427f66e9'
CONTRACT = 'PGDATA_POWERSHELL_INTENT_V1_DRAFT'
ROLES = ('resource_custodian', 'windows_object_owner', 'future_postgres_writer',
         'observer_a', 'observer_b', 'stop_authority')
NATIVE = ('reparse', 'symlink', 'ancestor', 'volume', 'file_identity', 'acl', 'tokens', 'handles')
FLAGS = ('execution_authorized', 'readiness_passed', 'physical_ready', 'schema2_enabled')

def _need(ok):
    if not ok: raise ValueError('PGDATA_INTENT_INVALID')

def _shape(obj, keys):
    _need(type(obj) is dict and set(obj) == set(keys))

def _hex(value, size):
    return type(value) is str and re.fullmatch('[0-9a-f]{'+str(size)+'}', value) is not None and value != '0'*size

def _uid(value):
    if type(value) is not str or len(value) != 36: return False
    try: return str(uuid.UUID(value)) == value and uuid.UUID(value).version == 4
    except ValueError: return False

def _sha(raw):
    return hashlib.sha256(raw).hexdigest()

def _intent(i):
    _shape(i, ('contract', 'parent', 'root', 'pgdata', 'run_id', 'node_id',
               'candidate_sha', 'phase', 'scope', 'root_provenance', 'native', 'roles', *FLAGS))
    _need(i['contract'] == CONTRACT and i['scope'] == 'EMPTY_FIXTURE_ONLY')
    _need(type(i['phase']) is str and i['phase'] in ('PREPARED', 'COMMITTED', 'RETIRED'))
    _need(all(i[k] is False for k in FLAGS))
    _need(type(i['parent']) is str and re.fullmatch(r'[D-Z]:\\GridLab', i['parent']) is not None)
    _need(_hex(i['run_id'], 32) and _hex(i['candidate_sha'], 40))
    node = i['node_id']
    _need(type(node) is str and re.fullmatch(r'[A-Z][A-Z0-9_-]{0,14}', node) is not None)
    _need(node not in ('LS5', 'LS7', 'CON', 'PRN', 'AUX', 'NUL') and re.fullmatch(r'(COM|LPT)[1-9]', node) is None)
    _need(i['root'] == i['parent']+'\\'+i['run_id']+'_'+node)
    _need(i['pgdata'] == i['root']+'\\postgres\\data')
    _need(canonical(i['root_provenance']) == canonical({
        'source_commit': BASE, 'producer_path': 'installer/isolated-deployment-core.ps1',
        'status': 'UNVERIFIED'}))
    _need(canonical(i['native']) == canonical({k: 'UNVERIFIED' for k in NATIVE}))
    _need(type(i['roles']) is list and len(i['roles']) == len(ROLES))
    principals = set(); custody = set(); sids = set()
    for role, r in zip(ROLES, i['roles']):
        _shape(r, ('role', 'principal_id', 'custody_domain', 'proposed_sid', 'status'))
        _need(r['role'] == role and r['status'] == 'UNVERIFIED')
        _need(_uid(r['principal_id']) and r['principal_id'] not in principals)
        _need(type(r['custody_domain']) is str and re.fullmatch('[A-Z][A-Z0-9_]{0,31}', r['custody_domain']) is not None and r['custody_domain'] not in custody)
        principals.add(r['principal_id']); custody.add(r['custody_domain'])
        sid = r['proposed_sid']
        _need(sid is None or (valid_sid(sid) and sid not in sids))
        if sid is not None: sids.add(sid)

def _producer(raw, i):
    """Conservative ASCII fixture byte profile of frozen producer; not provenance.

    Preserve given bytes. Never use Python reserialization to reinterpret a
    historical PS plan. Unsupported serializer representations are refused.
    """
    _need(type(raw) is str and len(raw) <= 8192 and raw.isascii())
    p = load(raw)
    _need(type(p) is dict)
    keys = ('schema','kind','parent','root','run_id','node_id','role','version','branch',
            'postgres_port','coordinator_port','database','tasks','activation_authorized',
            'database_initialization_authorized','tasks_registered','staging_policy',
            'rollback','blockers','plan_sha256')
    _need(tuple(p) == keys and type(p['schema']) is int and p['schema'] == 1)
    for k in ('parent', 'root', 'run_id', 'node_id'): _need(p[k] == i[k])
    _need(p['version'] == i['candidate_sha'] and p['kind'] == 'ISOLATED_PREPARATION')
    _need(type(p['role']) is str and p['role'] in ('CONTROL', 'WORKER'))
    _need(type(p['branch']) is str and len(p['branch']) <= 128 and (p['branch'] == 'main' or re.fullmatch('audit/codex-[a-z0-9-]+', p['branch']) is not None))
    ports = [p['postgres_port'], p['coordinator_port']]
    _need(all(type(n) is int and 20000 <= n <= 49999 for n in ports) and ports[0] != ports[1])
    prefix = 'BybitClusterGridLab_'+i['run_id']+'_'+i['node_id']
    _need(p['database'] == 'grid_lab_'+i['run_id']+'_'+i['node_id'].lower())
    _need(p['tasks'] == [prefix+s for s in ('_Agent','_Coordinator','_ArchivePipeline')])
    _need(all(p[k] is False for k in ('activation_authorized','database_initialization_authorized','tasks_registered')))
    _need(p['staging_policy'] == 'installer/stage-github-release.ps1' and p['rollback'] == 'RETIRE_AND_PRESERVE')
    _need(p['blockers'] == ['DATABASE_INITIALIZATION_REQUIRES_SEPARATE_REVIEW',
        'RELEASE_STAGING_AND_MANIFEST_PREFLIGHT_REQUIRED', 'TASK_REGISTRATION_AND_ACTIVATION_NOT_IMPLEMENTED',
        'FRESH_PHYSICAL_EVIDENCE_AND_OPERATOR_APPROVAL_REQUIRED'])
    # Profile exact compact ASCII bytes, ordered as the frozen producer. Unknown
    # formatting is rejected, never repaired. This is not a general PS serializer.
    _need(raw == json.dumps(p, separators=(',', ':'), ensure_ascii=True))
    declared = p.pop('plan_sha256')
    preimage = json.dumps(p, separators=(',', ':'), ensure_ascii=True).encode('ascii')
    _need(_hex(declared, 64) and declared == _sha(preimage))
    return declared

def _validate(b, seen):
    check_value(b)
    _shape(b, ('intent', 'intent_sha256', 'producer_plan_utf8', 'journal_utf8',
               'journal_sha256', 'receipt_utf8', 'receipt_sha256'))
    i = b['intent']; _intent(i)
    ih = _sha(canonical(i)); _need(_hex(b['intent_sha256'],64) and b['intent_sha256'] == ih)
    ph = _producer(b['producer_plan_utf8'], i)
    states = {'PREPARED': ['PREPARED'], 'COMMITTED': ['PREPARED','COMMITTED'],
              'RETIRED': ['PREPARED','COMMITTED','RETIRED']}[i['phase']]
    journal = ''.join('{"schema":1,"plan_sha256":"'+ph+'","state":"'+s+'"}\n' for s in states)
    _need(b['journal_utf8'] == journal)
    jh = _sha(journal.encode('ascii'))
    _need(_hex(b['journal_sha256'],64) and b['journal_sha256'] == jh)
    raw = b['receipt_utf8']; _need(type(raw) is str and len(raw) <= 8192)
    receipt = load(raw); _need(type(receipt) is dict)
    rid = receipt.get('receipt_id'); _need(_uid(rid))
    expected = {'kind': 'PGDATA_INTENT_DIAGNOSTIC_V1', 'receipt_id': rid,
                'intent_sha256': ih, 'producer_plan_sha256': ph, 'journal_sha256': jh,
                **{k: i[k] for k in ('root','pgdata','run_id','node_id','phase','scope')},
                'status': 'BLOCKED', **{k: False for k in FLAGS}}
    _need(canonical(receipt) == canonical(expected) and raw == canonical(expected).decode('ascii')+'\n')
    _need(_hex(b['receipt_sha256'],64) and b['receipt_sha256'] == _sha(raw.encode('ascii')))
    _need(type(seen) in (tuple, list) and len(seen) <= 256)
    _need(all(_uid(x) for x in seen) and len(set(seen)) == len(seen))
    _need(rid not in seen)

def validate_bundle(bundle, *, seen_receipt_ids=()):
    """No receipt acceptance or history mutation. Missing native proof => BLOCKED."""
    try:
        _validate(bundle, seen_receipt_ids); valid = True
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        valid = False
    return {'status': 'BLOCKED', 'metadata_valid': valid, 'l1': 'NO-GO', 'l2': 'NO-GO',
            **{k: False for k in FLAGS}, 'ownership_verified': False,
            'guest_cases': '12 NOT_RUN', 'replay_protection': 'CALLER_HISTORY_ONLY_NOT_DURABLE',
            'anti_rollback': 'NOT_IMPLEMENTED',
            'errors': [] if valid else ['PGDATA_INTENT_INVALID'],
            'blockers': ['NATIVE_EVIDENCE_MISSING', 'PRODUCER_PROVENANCE_UNVERIFIED',
                         'STAGING_POLICY_NOT_EVALUATED', 'DURABLE_REPLAY_NOT_IMPLEMENTED',
                         'TWO_HUMAN_REVIEWS_REQUIRED', 'NO_PHYSICAL_AUTHORIZATION']}

def validate_text(raw, *, seen_receipt_ids=()):
    try: return validate_bundle(load(raw), seen_receipt_ids=seen_receipt_ids)
    except (ValueError, TypeError, RecursionError): return validate_bundle(None)
