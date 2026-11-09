"""Local custody contract DATA only. Never Root ownership or native proof."""
import base64,hashlib,importlib.util,json,stat,uuid
from pathlib import Path
from grid.authority_assignment_v1 import _decode,_uuid

spec=importlib.util.spec_from_file_location('registration_data_dependency',Path(__file__).with_name('contract_data.py'))
registration=importlib.util.module_from_spec(spec);spec.loader.exec_module(registration)
MAX_ORIGINAL_BYTES=2048
MAX_RECEIPT_BYTES=4096
MAX_DB_BYTES=1048576
MAX_ROWS=64
SCHEMA='unified.authority.unqualified-worker-registration-custody.v1-review1'
FIELDS={'schema','original_registration_request_id','original_registration_intent_sha256','original_registration_intent_base64',
        'event','rpc_kind','rpc_attempt_id','native_session_id','endpoint_sha256','outcome','resources_reserved','effect_permitted'}
RPCS={'SESSION_CREATE','SESSION_INFO','REGISTRATION_TXN','CONSISTENT_READ','SESSION_DESTROY'}
MUTATIONS={'SESSION_CREATE','REGISTRATION_TXN','SESSION_DESTROY'}

def preflight_path(path):
    """Conservative local bounds, NOT evidence of exclusive ownership/custody."""
    path=Path(path).absolute()
    for item in (path,*path.parents):
        info=item.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&0x400:raise ValueError('REPARSE_OR_SYMLINK')
    info=path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or not 0<info.st_size<=MAX_DB_BYTES:raise ValueError('JOURNAL_FILE_BOUND')
    if any(path.with_name(path.name+suffix).exists() for suffix in ('-wal','-shm','-journal')):raise ValueError('JOURNAL_SIDECAR_REQUIRES_OWNER_RECOVERY')

def parse_receipt(raw,*,original_intent_bytes):
    if type(raw) is not bytes or len(raw)>MAX_RECEIPT_BYTES:raise ValueError('CUSTODY_RECEIPT_BOUND')
    if type(original_intent_bytes) is not bytes or len(original_intent_bytes)>MAX_ORIGINAL_BYTES:raise ValueError('CUSTODY_ORIGINAL_BOUND')
    intent=registration.parse_intent(original_intent_bytes);value=_decode(raw)
    if set(value)!=FIELDS or value['schema']!=SCHEMA:raise ValueError('FOREIGN_OR_OPEN_CUSTODY_RECORD')
    if (value['original_registration_request_id']!=intent['original_registration_request_id']
            or value['original_registration_intent_sha256']!=hashlib.sha256(original_intent_bytes).hexdigest()
            or value['original_registration_intent_base64']!=base64.b64encode(original_intent_bytes).decode('ascii')):
        raise ValueError('CUSTODY_ORIGINAL_BINDING')
    if value['resources_reserved'] is not False or value['effect_permitted'] is not False:raise ValueError('NO_CUSTODY_PERMISSION')
    sid=value['native_session_id']
    if sid is not None:
        if type(sid) is not str:raise ValueError('NATIVE_SESSION')
        try:valid=str(uuid.UUID(sid))==sid
        except ValueError:valid=False
        if not valid:raise ValueError('NATIVE_SESSION')
    if value['event']=='ORIGINAL_RETAINED':
        if (value['rpc_kind']!='NONE' or value['outcome']!='NOT_SENT'
                or any(value[field] is not None for field in ('rpc_attempt_id','native_session_id','endpoint_sha256'))):
            raise ValueError('ORIGINAL_PRE_SESSION_ONLY')
    else:
        if value['event'] not in ('RPC_ATTEMPTED','RPC_RESULT') or value['rpc_kind'] not in RPCS:raise ValueError('CUSTODY_EVENT')
        _uuid(value['rpc_attempt_id']);registration._sha(value['endpoint_sha256'])
        if value['event']=='RPC_ATTEMPTED' and value['outcome']!='ATTEMPTED':raise ValueError('ATTEMPT_BEFORE_RPC')
        if value['event']=='RPC_RESULT' and value['outcome'] not in ('CONFIRMED','REJECTED','UNKNOWN'):raise ValueError('RPC_OUTCOME')
        if value['rpc_kind']=='SESSION_CREATE':
            confirmed=value['event']=='RPC_RESULT' and value['outcome']=='CONFIRMED'
            if (sid is not None)!=confirmed:raise ValueError('SESSION_CREATION_OWNERSHIP_UNKNOWN')
        elif value['rpc_kind']!='CONSISTENT_READ' and sid is None:raise ValueError('KNOWN_NATIVE_SESSION_REQUIRED')
    return value

def outer_state(value):
    return 'OBSERVING' if value['event']=='ORIGINAL_RETAINED' or value['outcome']=='CONFIRMED' else 'BLOCKED'

def replay(records,*,original_intent_bytes):
    """Call only AFTER actual pinned Journal.read verifies its hash chain.

    Public dictionaries/output are local DATA and cannot authorize any RPC.
    """
    from grid.authority_runtime_v1 import canonical
    if type(records) is not list or not 1<=len(records)<=MAX_ROWS:raise ValueError('CUSTODY_ROW_BOUND')
    attempts={};results={};seen_mutations=set();known_sid=None;transaction='NONE'
    for sequence,row in enumerate(records,1):
        if type(row) is not dict or set(row)!={'sequence','state','receipt','previous_hash'} or type(row['sequence']) is not int or row['sequence']!=sequence:
            raise ValueError('JOURNAL_ROW')
        value=parse_receipt(canonical(row['receipt']),original_intent_bytes=original_intent_bytes)
        if row['state']!=outer_state(value):raise ValueError('CUSTODY_OUTER_STATE')
        if sequence==1:
            if value['event']!='ORIGINAL_RETAINED':raise ValueError('ORIGINAL_MUST_BE_FIRST')
            continue
        if value['event']=='ORIGINAL_RETAINED':raise ValueError('ONE_ORIGINAL_PER_JOURNAL')
        attempt=value['rpc_attempt_id'];kind=value['rpc_kind'];sid=value['native_session_id']
        if kind!='SESSION_CREATE' and sid is not None and sid!=known_sid:raise ValueError('NO_SESSION_ADOPTION')
        if value['event']=='RPC_ATTEMPTED':
            if attempt in attempts:raise ValueError('RPC_ATTEMPT_REUSE')
            if kind in MUTATIONS:
                if kind in seen_mutations:raise ValueError('NO_AUTOMATIC_MUTATION_RETRY')
                if kind=='REGISTRATION_TXN' and 'SESSION_DESTROY' in seen_mutations:raise ValueError('NO_REGISTRATION_AFTER_CLEANUP')
                if any(attempts[key]['rpc_kind'] in MUTATIONS and (key not in results or results[key]['outcome']=='UNKNOWN') for key in attempts):
                    raise ValueError('UNRESOLVED_MUTATION_NO_NEW_MUTATION')
                if kind!='SESSION_CREATE' and (known_sid is None or sid!=known_sid):raise ValueError('NO_SESSION_ADOPTION')
                if kind=='SESSION_DESTROY' and 'REGISTRATION_TXN' in seen_mutations and transaction!='REJECTED':raise ValueError('NO_INVALIDATION_AS_ROLLBACK')
                seen_mutations.add(kind)
            if kind=='REGISTRATION_TXN':transaction='UNKNOWN'
            if kind=='SESSION_CREATE' and known_sid is not None:raise ValueError('NO_NEW_SESSION')
            attempts[attempt]=value
        else:
            prior=attempts.get(attempt)
            if prior is None or attempt in results or prior['rpc_kind']!=kind or prior['endpoint_sha256']!=value['endpoint_sha256']:
                raise ValueError('RPC_RESULT_WITHOUT_EXACT_ATTEMPT')
            if kind!='SESSION_CREATE' and prior['native_session_id']!=sid:raise ValueError('RPC_SESSION_BINDING')
            results[attempt]=value
            if kind=='SESSION_CREATE' and value['outcome']=='CONFIRMED':known_sid=sid
            if kind=='REGISTRATION_TXN':transaction=value['outcome']
    return dict(local_transaction_report=transaction,native_session_id=known_sid,
        unresolved_rpc_attempts=[key for key in attempts if key not in results or results[key]['outcome']=='UNKNOWN'],
        resources_reserved=False,effect_permitted=False)

def receipt_schema():
    nullable=lambda value:{'anyOf':[value,{'type':'null'}]}
    props=dict(schema={'const':SCHEMA},original_registration_request_id=registration.UUID4,
        original_registration_intent_sha256=registration.SHA,
        original_registration_intent_base64={'type':'string','maxLength':2732,'pattern':'^[A-Za-z0-9+/]+={0,2}$(?![\\s\\S])'},
        event={'enum':['ORIGINAL_RETAINED','RPC_ATTEMPTED','RPC_RESULT']},rpc_kind={'enum':['NONE']+sorted(RPCS)},
        rpc_attempt_id=nullable(registration.UUID4),native_session_id=nullable(registration.NATIVE_UUID),
        endpoint_sha256=nullable(registration.SHA),outcome={'enum':['NOT_SENT','ATTEMPTED','CONFIRMED','REJECTED','UNKNOWN']},
        resources_reserved={'type':'boolean','const':False},effect_permitted={'type':'boolean','const':False})
    return {'$schema':'https://json-schema.org/draft/2020-12/schema','type':'object','additionalProperties':False,
        'properties':props,'required':sorted(FIELDS),'allOf':[
            {'if':{'properties':{'event':{'const':'ORIGINAL_RETAINED'}}},'then':{'properties':{
                'rpc_kind':{'const':'NONE'},'outcome':{'const':'NOT_SENT'},'rpc_attempt_id':{'type':'null'},
                'native_session_id':{'type':'null'},'endpoint_sha256':{'type':'null'}}},
             'else':{'properties':{'rpc_kind':{'enum':sorted(RPCS)},'rpc_attempt_id':registration.UUID4,'endpoint_sha256':registration.SHA}}},
            {'if':{'properties':{'event':{'const':'RPC_ATTEMPTED'}}},'then':{'properties':{'outcome':{'const':'ATTEMPTED'}}}},
            {'if':{'properties':{'event':{'const':'RPC_RESULT'}}},'then':{'properties':{'outcome':{'enum':['CONFIRMED','REJECTED','UNKNOWN']}}}},
            {'if':{'properties':{'rpc_kind':{'const':'SESSION_CREATE'}}},'then':{'if':{'properties':{
                'event':{'const':'RPC_RESULT'},'outcome':{'const':'CONFIRMED'}}},'then':{'properties':{'native_session_id':registration.NATIVE_UUID}},
                'else':{'properties':{'native_session_id':{'type':'null'}}}}},
            {'if':{'properties':{'rpc_kind':{'enum':['SESSION_INFO','REGISTRATION_TXN','SESSION_DESTROY']}}},
             'then':{'properties':{'native_session_id':registration.NATIVE_UUID}}}]}

if __name__=='__main__':
    Path(__file__).with_name('custody-receipt.schema.json').write_bytes(json.dumps(receipt_schema(),sort_keys=True,separators=(',',':')).encode('ascii')+b'\n')
