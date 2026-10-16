"""PUBLIC deterministic TEST seeds; never an attestor, authority or secret store."""
import copy
import json
from pathlib import Path
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from installer.vm_lab_evidence import draft
from installer.vm_lab_json import canonical

DOMAIN='GRID_VM_LAB_TEST_ATTESTATION_V1'
OBSERVER='55555555-5555-4555-8555-555555555555'
APPROVER='66666666-6666-4666-8666-666666666666'
NOW='2026-10-16T20:00:10Z'
# Deliberately PUBLIC test bytes. No production key or signing authority exists.
SEEDS=(bytes(range(32)),bytes(range(32,64)))


def signed(plan,payload=None):
    challenge={'session_id':'77777777-7777-4777-8777-777777777777','nonce':'8'*64,
               'sequence':1,'code_sha256':'d'*64,'artifact_sha256':'e'*64}
    if payload is None:
        payload={'draft':draft(plan,OBSERVER),'challenge':copy.deepcopy(challenge),
                 'observer_id':OBSERVER,'approval_id':APPROVER,
                 'issued_at':'2026-10-16T20:00:00Z','expires_at':'2026-10-16T20:04:00Z'}
    envelope={'schema':1,'domain':DOMAIN,'canonicalization':'GRID_JSON_INTEGER_V1',
              'payload':copy.deepcopy(payload),'signatures':[]}
    for i,role in enumerate(('observer','approval')):
        header={'key_id':'test-'+role+'-v1','role':role,'algorithm':'Ed25519'}
        message=DOMAIN.encode()+b'\x00'+canonical({k:envelope[k] for k in ('schema','domain','canonicalization')}|{'payload':envelope['payload'],'signer':header})
        signature=Ed25519PrivateKey.from_private_bytes(SEEDS[i]).sign(message).hex()
        envelope['signatures'].append(header|{'signature':signature})
    return envelope,challenge


def example_plan():
    return json.loads((Path(__file__).parent/'vm-lab-plan.example.json').read_text(encoding='utf-8'))
