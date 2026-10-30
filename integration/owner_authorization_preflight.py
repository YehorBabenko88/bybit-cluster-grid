"""Offline preparation metadata only. No owner verifier, store, or executor."""
import re

from installer.vm_lab_json import canonical, load
from installer.vm_lab_plan import _digest, _guid, _need, _shape


def _scope(value):
    _shape(value, 'head_sha artifact_sha256 owner_key_sha256 host_id session_id boot_id action')
    _need(type(value['head_sha']) is str and re.fullmatch('[0-9a-f]{40}', value['head_sha']),
          'OWNER_PREPARATION_SHA')
    for name in ('artifact_sha256', 'owner_key_sha256'):
        _digest(value[name])
    for name in ('host_id', 'session_id', 'boot_id'):
        _guid(value[name])
    _need(type(value['action']) is str and value['action'] in ('execute', 'cleanup'),
          'OWNER_PREPARATION_ACTION')


def assess_preparation(raw, expected_scope):
    """Compare untrusted declarations with caller metadata; always deny effects.

    Neither input is an authenticated identity, signature, measured boot fact,
    trusted handle, ledger, or external monotonic anchor. No I/O is performed.
    """
    report = dict(schema=1, status='BLOCKED', mode='OFFLINE_PREPARATION_ONLY',
                  metadata_matches=False, authentication='NOT_IMPLEMENTED',
                  durable_replay='NOT_IMPLEMENTED', execution_authorized=False,
                  cleanup_authorized=False, readiness_passed=False,
                  physical_ready=False, host_verified=False, verified_safety_cases=0,
                  automatic_resume=False, recovery_disposition='RETAIN_FOR_REVIEW',
                  blockers=['OWNER_TRUST_ENROLLMENT_UNIMPLEMENTED',
                            'OWNER_SIGNATURE_VALIDATION_UNIMPLEMENTED',
                            'DURABLE_REPLAY_LEDGER_UNIMPLEMENTED',
                            'EXTERNAL_NONROLLBACK_ANCHOR_UNIMPLEMENTED',
                            'TRUSTED_CLOCK_AND_REVOCATION_UNIMPLEMENTED',
                            'FRESH_OWNER_AUTHORIZATION_REQUIRED',
                            'HANDLE_REACQUISITION_UNIMPLEMENTED',
                            'HANDLE_BOUND_CLEANUP_NOT_AUTHORIZED'])
    try:
        # Reuse existing bounded, duplicate-key rejecting JSON handling.
        data = load(raw)
        expected = load(canonical(expected_scope).decode('ascii'))
        _shape(data, 'schema scope recovery')
        _need(type(data['schema']) is int and data['schema'] == 1, 'OWNER_PREPARATION_SCHEMA')
        _scope(data['scope']); _scope(expected)
        if data['scope'] != expected:
            report['blockers'].append('SCOPE_MISMATCH')
            return report
        recovery = data['recovery']
        _shape(recovery, 'previous_boot_id current_boot_id handles_lost journal_sha256 anchor_sha256')
        for name in ('previous_boot_id', 'current_boot_id'):
            _guid(recovery[name])
        _need(type(recovery['handles_lost']) is bool, 'OWNER_PREPARATION_HANDLES')
        for name in ('journal_sha256', 'anchor_sha256'):
            if recovery[name] is not None:
                _digest(recovery[name])
        _need(recovery['current_boot_id'] == data['scope']['boot_id'], 'OWNER_PREPARATION_BOOT')
    except (ValueError, TypeError, KeyError, RuntimeError, RecursionError):
        report['blockers'].append('INVALID_PREPARATION_INPUT')
        return report
    report['metadata_matches'] = True
    if (recovery['previous_boot_id'] == recovery['current_boot_id']
            and not recovery['handles_lost']):
        report['recovery_disposition'] = 'NO_AUTOMATIC_ACTION'
    # Even matching journal/anchor hashes prove no durable or nonrollback state.
    return report
