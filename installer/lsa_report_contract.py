"""Offline admissibility of untrusted LSA JSON; never an execution gate.

No host queries, native API, file writes, subprocesses or physical harness imports.
Even accepted reports have unknown provenance and cannot establish effective rights.
"""
import json
import re
import sys

from installer.vm_lab_json import load

TOP = frozenset(('schema', 'mode', 'readiness', 'effective_rights',
                 'execution_authorized', 'physical_tests', 'records', 'errors',
                 'group_completeness', 'actor_token_observed'))
RECORD = frozenset(('principal', 'relation', 'state', 'code', 'ntstatus', 'win32',
                    'cleanup_failed', 'direct_allow', 'direct_deny'))
ACCOUNTS = frozenset(('GridLabCollector', 'GridLabStorage'))
CONDITIONAL = frozenset(('Everyone', 'AuthenticatedUsers', 'LocalAccount',
    'LocalAccountAdmin', 'Users', 'Administrators', 'Network', 'Batch',
    'Interactive', 'Service', 'RemoteInteractive', 'ThisOrganization', 'Local', 'ConsoleLogon'))
ALLOW = frozenset(('SeBatchLogonRight', 'SeInteractiveLogonRight', 'SeServiceLogonRight',
                  'SeNetworkLogonRight', 'SeRemoteInteractiveLogonRight'))
DENY = frozenset(('SeDenyBatchLogonRight', 'SeDenyInteractiveLogonRight', 'SeDenyServiceLogonRight',
                 'SeDenyNetworkLogonRight', 'SeDenyRemoteInteractiveLogonRight'))


def _need(condition):
    if not condition:
        raise ValueError('LSA_CONTRACT_REJECTED')


def _rights(value, allowed):
    _need(type(value) is list and len(value) <= 5)
    _need(all(type(v) is str and v in allowed for v in value))
    _need(len(set(value)) == len(value))


def validate(raw):
    """Accept bounded JSON text for diagnostic review only; fixed safe output.

    contract_valid means this strict consumption profile admits the document.
    Error/partial reports may be legitimate producer output but are not admitted.
    A well-formed mock is indistinguishable from a real report without external
    provenance; both receive exactly the same BLOCKED, unauthenticated result.
    """
    out = dict(schema='grid-lsa-contract-review-1', status='BLOCKED',
               contract_valid=False, code='LSA_CONTRACT_REJECTED',
               evidence_class='UNAUTHENTICATED_DIAGNOSTIC_ONLY',
               effective_rights='UNKNOWN', execution_authorized=False,
               readiness_passed=False, physical_attestation=False,
               physical_tests='0/10 NOT_RUN', physical_passes=0)
    try:
        data = load(raw)
        _need(type(data) is dict and set(data) == TOP)
        _need(data['schema'] == 'grid-lsa-readonly-1')
        _need(data['mode'] in ('PlanOnly', 'CollectLocalReadOnly'))
        _need(data['readiness'] == 'BLOCKED' and data['effective_rights'] == 'UNKNOWN')
        _need(data['execution_authorized'] is False and data['actor_token_observed'] is False)
        _need(data['physical_tests'] == '0/10 NOT_RUN' and data['group_completeness'] == 'UNKNOWN')
        _need(type(data['errors']) is list and not data['errors'])
        rows = data['records']
        _need(type(rows) is list)
        if data['mode'] == 'PlanOnly':
            _need(not rows)
        else:
            # Producer includes two accounts and fourteen known SID candidates.
            # A direct group may replace a conditional alias for the same SID.
            # Redaction prevents verifying that mapping or actual completeness.
            _need(16 <= len(rows) <= 256)
            seen = set()
            accounts = set()
            for row in rows:
                _need(type(row) is dict and set(row) == RECORD)
                name, relation = row['principal'], row['relation']
                _need(type(name) is str and name not in seen)
                seen.add(name)
                if relation == 'LOCAL_ACCOUNT':
                    _need(name in ACCOUNTS)
                    accounts.add(name)
                elif relation == 'CONDITIONAL_CANDIDATE':
                    _need(name in CONDITIONAL)
                else:
                    _need(relation == 'DIRECT_LOCAL_GROUP')
                    _need(re.fullmatch(r'local_group_[1-9][0-9]*', name) is not None
                          and int(name.rsplit('_', 1)[1]) >= 2)
                _need(row['state'] == 'DIRECT_ONLY' and row['cleanup_failed'] is False)
                _need(type(row['win32']) is int and 0 <= row['win32'] <= 0xFFFFFFFF)
                _rights(row['direct_allow'], ALLOW)
                _rights(row['direct_deny'], DENY)
                if row['code'] == 'ENUMERATED':
                    _need(row['ntstatus'] == '0x00000000' and row['win32'] == 0)
                    # Empty relevant arrays can represent unrelated native privileges.
                else:
                    _need(row['code'] == 'NO_DIRECT_ASSIGNMENTS')
                    _need(row['ntstatus'] == '0xC0000034' and row['win32'] == 2)
                    _need(not row['direct_allow'] and not row['direct_deny'])
            _need(accounts == ACCOUNTS)
        out.update(contract_valid=True, code='LSA_DIAGNOSTIC_ONLY')
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        pass
    return out


def main():
    # Read at most the existing JSON helper's UTF-8 byte budget plus one sentinel.
    try:
        raw = sys.stdin.buffer.read(65537).decode('utf-8')
    except UnicodeError:
        raw = ''
    result = validate(raw)
    print(json.dumps(result, sort_keys=True))
    return 0 if result['contract_valid'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
