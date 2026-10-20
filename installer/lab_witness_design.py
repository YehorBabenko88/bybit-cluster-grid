"""Closed, inert L1 proposal schema. Never verifies or authorizes infrastructure.

No paths, endpoints, commands, secrets, approval tokens or native identities are
accepted. Symbolic custody domains are proposals, not proof of independence.
"""
from installer.vm_lab_json import check_value, load

BASE = '2552cf8568a21d4a57a2aacc57ccdbc9861ea5c4'

def template():
    return {
        'schema': 1, 'planning_base': BASE, 'mode': 'OFFLINE_DESIGN_ONLY',
        'choice': 'UNSELECTED', 'authorized': False, 'readiness': False,
        'schema2_enabled': False, 'execution_authorized': False,
        'A': {'transfer_enabled': False, 'live_freshness': 'UNVERIFIED',
              'transport': 'SUPERVISED_MEDIA_PROPOSAL'},
        'B': {'enabled': False, 'routes': [], 'transport': 'RESTRICTED_GATEWAY_PROPOSAL',
              'gateway_is_witness': False, 'default_deny': True},
        'witnesses': [
            {'owner': 'EXTERNAL_OWNER_A', 'anchor_domain': 'EXTERNAL_ANCHOR_A',
             'key_custody': 'EXTERNAL_KEY_A', 'status': 'UNVERIFIED'},
            {'owner': 'EXTERNAL_OWNER_B', 'anchor_domain': 'EXTERNAL_ANCHOR_B',
             'key_custody': 'EXTERNAL_KEY_B', 'status': 'UNVERIFIED'}],
        'reviews': ['NOT_REVIEWED', 'NOT_REVIEWED'],
        'trusted_time': 'UNVERIFIED', 'durable_anchor': 'NOT_IMPLEMENTED',
        'correlated_rollback': 'UNRESOLVED', 'native_evidence': 'UNVERIFIED',
        'pgdata_mapping': 'UNRESOLVED_SCHEMA1_MISMATCH',
        'cases': ['NOT_RUN'] * 12,
    }

def validate_manifest(value):
    valid = False
    choice = 'UNSELECTED'
    try:
        check_value(value)
        if type(value) is not dict:
            raise ValueError('SHAPE')
        choice = value.get('choice')
        if type(choice) is not str or choice not in ('UNSELECTED', 'A', 'B'):
            raise ValueError('CHOICE')
        expected = template(); expected['choice'] = choice
        # Canonical JSON distinguishes bool from int throughout the closed schema.
        from installer.vm_lab_json import canonical
        valid = canonical(value) == canonical(expected)
    except (ValueError, TypeError, RecursionError):
        valid = False
    blockers = ['TWO_OWNER_REVIEW_REQUIRED', 'TRUST_ASSUMPTIONS_UNVERIFIED',
                'TIME_AND_ANCHORS_UNVERIFIED', 'PGDATA_MAPPING_UNRESOLVED',
                'NO_PHYSICAL_AUTHORIZATION']
    if choice == 'UNSELECTED': blockers.insert(0, 'CHOICE_REQUIRED')
    if not valid: blockers.insert(0, 'CONTRACT_INVALID')
    return {'manifest_valid': valid, 'status': 'BLOCKED', 'l1': 'NO-GO',
            'physical_deployment': 'NO-GO', 'guest_cases': '12 NOT_RUN',
            'authorized': False, 'readiness': False, 'execution_authorized': False,
            'schema2_enabled': False, 'blockers': blockers,
            'assurance': 'OFFLINE_SHAPE_ONLY'}

def validate_text(raw):
    try:
        return validate_manifest(load(raw))
    except (ValueError, TypeError, RecursionError):
        return validate_manifest(None)
