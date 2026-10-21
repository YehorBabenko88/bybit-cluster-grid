"""Inert, closed Air-gap A proposal contract; no executor or evidence verifier."""
from installer.vm_lab_json import canonical, check_value, load
from installer.vm_lab_plan import CASES

BASE = '612a9daac26360886e0571ec9fe55c3a557c5da3'

def template():
    """Public symbolic proposal only. Values are not allocated resource identities."""
    return {
        'schema': 1, 'planning_base': BASE, 'variant': 'A',
        'owner_direction': 'PROVISIONAL', 'mode': 'OFFLINE_DESIGN_ONLY',
        'authorized': False, 'execution_authorized': False, 'readiness': False,
        'physical_ready': False, 'schema2_enabled': False, 'execution': 'NOT_RUN',
        'topology': {**{k: False for k in (
            'wifi', 'bluetooth', 'routing', 'nat', 'bridged_nic', 'tailscale',
            'production', 'internet', 'shared_clipboard', 'shared_folders', 'host_mounts')},
            'switch': 'PRIVATE_PROPOSED', 'routes': [], 'hardware': 'OWNER_UNVERIFIED'},
        'roles': [
            {'role': 'operator', 'custody': 'OPERATOR_DOMAIN', 'status': 'UNVERIFIED'},
            {'role': 'observer_a', 'custody': 'OBSERVER_A_DOMAIN', 'status': 'UNVERIFIED'},
            {'role': 'observer_b', 'custody': 'OBSERVER_B_DOMAIN', 'status': 'UNVERIFIED'},
            {'role': 'stop_custodian', 'custody': 'STOP_DOMAIN', 'status': 'UNVERIFIED'}],
        'reviews': [{'reviewer': 'HUMAN_ARCHITECTURE_REQUIRED', 'decision': 'NOT_REVIEWED'},
                    {'reviewer': 'HUMAN_SECURITY_REQUIRED', 'decision': 'NOT_REVIEWED'}],
        'transfer': {'direction': 'OUTBOUND_EVIDENCE_ONLY', 'inbound_receipts': False,
                     'autorun': False, 'custody': 'UNVERIFIED', 'freshness': 'UNVERIFIED',
                     'hash_proves_freshness': False, 'approval': 'NOT_GRANTED'},
        'trusted_time': 'UNVERIFIED', 'anti_rollback': 'NOT_IMPLEMENTED',
        'epoch_continuity': 'UNVERIFIED', 'native_evidence': 'UNVERIFIED',
        'pgdata_mapping': 'UNRESOLVED_SCHEMA1_MISMATCH',
        'cases': [{'case': c, 'execution': 'NOT_RUN'} for c, _ in CASES],
    }

def validate_manifest(value):
    try:
        check_value(value)
        valid = type(value) is dict and canonical(value) == canonical(template())
    except (ValueError, TypeError, RecursionError):
        valid = False
    return {
        'manifest_valid': valid, 'status': 'BLOCKED', 'l1': 'NO-GO', 'l2': 'NO-GO',
        'authorized': False, 'execution_authorized': False, 'readiness': False,
        'physical_ready': False, 'schema2_enabled': False, 'guest_cases': '12 NOT_RUN',
        'assurance': 'OFFLINE_SHAPE_ONLY',
        'errors': [] if valid else ['AIRGAP_CONTRACT_INVALID'],
        'blockers': ['TWO_INDEPENDENT_HUMAN_REVIEWS_REQUIRED', 'HARDWARE_UNVERIFIED',
                     'TIME_AND_CUSTODY_UNVERIFIED', 'DURABLE_ANTI_ROLLBACK_NOT_IMPLEMENTED',
                     'PGDATA_MAPPING_UNRESOLVED', 'NO_L2_AUTHORIZATION'],
    }

def validate_text(raw):
    try:
        return validate_manifest(load(raw))
    except (ValueError, TypeError, RecursionError):
        return validate_manifest(None)
