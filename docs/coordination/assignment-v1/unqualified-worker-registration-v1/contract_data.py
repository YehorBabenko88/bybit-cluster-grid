"""PROPOSED pure registration DATA codec. No client, RPC, issuer or permission."""
import hashlib,json,re,uuid
from pathlib import Path
from grid.authority_runtime_v1 import canonical
from grid.authority_assignment_v1 import _decode,_uuid

INTENT_SCHEMA='unified.authority.unqualified-worker-registration-intent.v1-review1'
RECORD_SCHEMA='unified.authority.unqualified-worker-registration.v1-review1'
IDENTITIES=('cluster_id','cluster_generation','realm_id','node_id','worker_inventory_incarnation_id','original_registration_request_id')
BOUND=IDENTITIES+('worker_module_sha256',)
INTENT_FIELDS=frozenset(('schema','operation')+BOUND)
RECORD_FIELDS=frozenset(('schema','original_registration_intent_sha256','native_session_id','registration_state','admitted_fields','resources_reserved','effect_permitted')+BOUND)

def _sha(value):
    if type(value) is not str or re.fullmatch('[0-9a-f]{64}',value) is None:raise ValueError('SHA256')

def parse_intent(raw):
    value=_decode(raw)
    if set(value)!=INTENT_FIELDS or value['schema']!=INTENT_SCHEMA or value['operation']!='COMMISSION_UNQUALIFIED_WORKER':
        raise ValueError('CLOSED_REGISTRATION_INTENT')
    for field in IDENTITIES:_uuid(value[field])
    _sha(value['worker_module_sha256'])
    return value

def intent_digest(raw):
    parse_intent(raw)
    return hashlib.sha256(raw).hexdigest()

def parse_record(raw,*,original_intent_bytes):
    original=parse_intent(original_intent_bytes);value=_decode(raw)
    if set(value)!=RECORD_FIELDS or value['schema']!=RECORD_SCHEMA:raise ValueError('CLOSED_REGISTRATION_RECORD')
    if any(value[field]!=original[field] for field in BOUND):raise ValueError('ORIGINAL_REGISTRATION_BINDING')
    if value['original_registration_intent_sha256']!=intent_digest(original_intent_bytes):raise ValueError('ORIGINAL_REGISTRATION_DIGEST')
    sid=value['native_session_id']
    if type(sid) is not str:raise ValueError('NATIVE_SESSION')
    try:valid=str(uuid.UUID(sid))==sid
    except ValueError:valid=False
    if not valid:raise ValueError('NATIVE_SESSION')
    if (value['registration_state']!='UNQUALIFIED' or type(value['admitted_fields']) is not list
            or value['admitted_fields'] or value['resources_reserved'] is not False or value['effect_permitted'] is not False):
        raise ValueError('NO_REGISTRATION_UPGRADE_OR_GRANT')
    return value

def registration_keys(original_intent_bytes):
    value=parse_intent(original_intent_bytes)
    key='unified/'+value['cluster_id']+'/runtime-v1/research-lab-v1/'+value['realm_id']+'/workers/'+value['node_id']+'/registration-v1'
    return key,key+'/lock'

UUID4={'type':'string','minLength':36,'maxLength':36,'pattern':'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$(?![\\s\\S])'}
NATIVE_UUID={'type':'string','minLength':36,'maxLength':36,'pattern':'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$(?![\\s\\S])'}
SHA={'type':'string','minLength':64,'maxLength':64,'pattern':'^[0-9a-f]{64}$(?![\\s\\S])'}

def schemas():
    bound={field:UUID4 for field in IDENTITIES};bound['worker_module_sha256']=SHA
    intent=dict(bound,schema={'const':INTENT_SCHEMA},operation={'const':'COMMISSION_UNQUALIFIED_WORKER'})
    record=dict(bound,schema={'const':RECORD_SCHEMA},original_registration_intent_sha256=SHA,
        native_session_id=NATIVE_UUID,registration_state={'const':'UNQUALIFIED'},
        admitted_fields={'type':'array','maxItems':0},resources_reserved={'type':'boolean','const':False},effect_permitted={'type':'boolean','const':False})
    return {name:{'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object','additionalProperties':False,
                  'properties':props,'required':sorted(props)} for name,props in (('intent.schema.json',intent),('record.schema.json',record))}

if __name__=='__main__':
    for name,value in schemas().items():
        (Path(__file__).parent/name).write_bytes(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode('ascii')+b'\n')
