"""Static, evidence-only threat boundary. No probes, paths, privileges or executor."""
import json

# Contract descriptions are conditional API semantics, NOT verified ownership.
_ROWS = (
    ('handles_sharing', 'Conditional kernel sharing contract',
     'Incompatible normal data-write/delete opens are refused while compatible handles remain open.',
     'Not WRITE_DAC, namespace-wide exclusion, process protection or pre-existing mappings.'),
    ('acl', 'Conditional discretionary access control',
     'Independently provisioned ACL can restrict different unprivileged SIDs.',
     'No effective-token/policy attestation; owner/same-SID writer can change DACL; no admin boundary.'),
    ('file_identity', 'Observed volume serial plus 64-bit file index',
     'Compares identity of currently opened fixture objects.',
     'No universal uniqueness, durable provenance, trusted volume attestation or alias exclusion.'),
    ('junction_reparse', 'Observed fixture rejection/sharing denial',
     'Checks fixture reparse/type and identity at sampled boundaries.',
     'OPEN_REPARSE_POINT does not validate all ancestors; no global path capability.'),
    ('ancestors_namespace', 'Observed pinned-owned-ancestor denial',
     'Owned root/data/postgres renames denied in recorded Windows fixture runs.',
     'Ancestors outside fixture, other aliases and transient namespace ABA remain unproven.'),
    ('privileged_writer', 'STOP: outside in-process discretionary boundary',
     'Model A excludes elevated admins, hostile same-SID code and privileged writers.',
     'Model B may control ACLs, processes and verifier; requires a stronger trusted OS boundary.'),
    ('aba_exhaustion', 'Reproduced limitation and unproven failure mode',
     'ACL replace/restore was undetected on both baseline runners; bounded quota cleanup observed.',
     'No atomic ACL/namespace snapshot; global kernel exhaustion never tested.'),
)


def threat_boundary(model):
    """Return descriptions only. Selecting A asserts no provisioning/approval facts."""
    if type(model) is not str or model not in ('A', 'B'):
        raise ValueError('THREAT_MODEL_UNKNOWN')
    return {
        'schema': 1, 'status': 'BLOCKED', 'assurance': 'EVIDENCE_ONLY',
        'evidence_only': True, 'execution_authorized': False, 'physical_ready': False,
        'model': model,
        'decision': 'STOP_OS_BOUNDARY_REQUIRED' if model == 'B' else 'BLOCKED_PROVISIONING_UNPROVEN',
        'matrix': [dict(property=key, basis=basis, conditional_property=prop,
                        limitation=limit, verification='BLOCKED')
                   for key, basis, prop, limit in _ROWS],
    }


if __name__ == '__main__':
    print(json.dumps([threat_boundary('A'), threat_boundary('B')], sort_keys=True))
