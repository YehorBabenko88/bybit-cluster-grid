"""Pure L0 design-metadata checker. No discovery, authority or infrastructure API."""
import json,re,sys,uuid
from installer.vm_lab_json import check_value,load
from installer.vm_lab_plan import CASES
from vm_principal_lab.sid_validation import valid_sid
RC='83c7c034668d02ce833e4f9750409b74641b9070'
RESOURCES=('host','guests','network','principals','storage','services','trust','time','anti_rollback','retention')
FLAGS=('authorized','readiness','execution_authorized','readiness_passed','physical_ready','schema2_enabled')
ROLES=('operator','observer_a','observer_b','owner','verifier','adversary','host_admin')
def need(ok,code='LAB_MANIFEST_INVALID'):
    if not ok:raise ValueError(code)
def shape(obj,keys):need(type(obj) is dict and set(obj)==set(keys),'LAB_SHAPE_INVALID')
def fixed(obj,values):
    for k,v in values.items():need(type(obj[k]) is type(v) and obj[k]==v,'LAB_UNSAFE_PROPOSAL')
def guid(v):
    need(type(v) is str and re.fullmatch('[0-9a-f-]{36}',v),'LAB_ID_INVALID')
    x=uuid.UUID(v);need(str(x)==v and x.version==4,'LAB_ID_INVALID');return v
def resource(m,k):
    x=m[k];shape(x,('evidence_status','proposal'));fixed(x,{'evidence_status':'UNVERIFIED'});return x['proposal']
def check(m):
    check_value(m)
    shape(m,('schema','kind','mode','offline_rc','gates','negative_cases',*FLAGS,*RESOURCES))
    fixed(m,dict(schema=1,kind='WINDOWS_LAB_L0_DRAFT',mode='PlanOnly',**dict.fromkeys(FLAGS,False)))
    shape(m['offline_rc'],('sha','status','run_id'));fixed(m['offline_rc'],dict(sha=RC,status='VERIFIED_OFFLINE_ONLY',run_id=39436629147))
    h=resource(m,'host');shape(h,('id','label','dedicated','os_build','hypervisor','hypervisor_version','hardware_provenance','production_member'))
    fixed(h,dict(dedicated=True,hypervisor='Hyper-V',production_member=False))
    need(type(h['label']) is str and re.fullmatch('LAB-HOST-[A-Z0-9-]{1,40}',h['label']),'LAB_HOST_INVALID')
    for k in ('os_build','hypervisor_version','hardware_provenance'):need(type(h[k]) is str and 0<len(h[k])<=128,'LAB_HOST_INVALID')
    ids=[guid(h['id'])];nodes=[]
    guests=resource(m,'guests');need(type(guests)is list and len(guests)==2,'LAB_GUESTS_INVALID')
    for g,role in zip(guests,('CONTROL','WORKER')):
        shape(g,('id','node_id','role','os_build','image_sha256','provisioned','powered_on'));ids.append(guid(g['id']))
        fixed(g,dict(role=role,provisioned=False,powered_on=False))
        need(type(g['node_id'])is str and re.fullmatch('LAB[A-Z0-9_-]{1,12}',g['node_id']),'LAB_NODE_INVALID');nodes.append(g['node_id'])
        need(type(g['os_build'])is str and 0<len(g['os_build'])<=128,'LAB_OS_INVALID')
        need(g['image_sha256'] is None or type(g['image_sha256'])is str and re.fullmatch('[0-9a-f]{64}',g['image_sha256']),'LAB_IMAGE_INVALID')
    need(len(set(ids))==3 and len(set(nodes))==2,'LAB_ID_REUSE')
    n=resource(m,'network');expected=dict(switch_type='PRIVATE',address_plan='UNASSIGNED',routes=[],default_gateway=None,dns_forwarders=[])
    expected.update(dict.fromkeys(('production_access','tailscale','nat','bridge','host_management_access','internet_access','dual_homed_guests','file_sharing','clipboard','enhanced_session'),False))
    shape(n,expected);fixed(n,expected)
    principals=resource(m,'principals');need(type(principals)is list and len(principals)==len(ROLES),'LAB_PRINCIPALS_INVALID')
    domains=[];sids=[]
    for p,role in zip(principals,ROLES):
        shape(p,('role','custody_domain','sid','token_attestation'));fixed(p,dict(role=role,token_attestation=None))
        need(type(p['custody_domain'])is str and re.fullmatch('[A-Z][A-Z0-9-]{1,63}',p['custody_domain']),'LAB_CUSTODY_INVALID');domains.append(p['custody_domain'])
        if p['sid'] is not None:
            need(valid_sid(p['sid']) and p['sid'].startswith('S-1-5-21-'),'LAB_SID_INVALID');sids.append(p['sid'])
    need(len(set(domains))==len(domains) and len(set(sids))==len(sids),'LAB_PRINCIPAL_REUSE')
    s=resource(m,'storage');expected=dict(scope='GUEST_ONLY',volume_identity='UNASSIGNED',placeholder_run=True,pg_mapping='PROPOSAL_ONLY_NO_RUNTIME_MAPPING',legacy_pg_plan='{parent}\\{run_id}\\{node_id}\\pgdata',legacy_adapter='{parent}\\{run_id}_{node_id}\\postgres\\data',proposed_contract='LAB_PGDATA_INTENT_V1_DRAFT',shared_host_mounts=False,ownership_verified=False)
    shape(s,(*expected,'parent','run_id'));fixed(s,expected)
    need(type(s['parent'])is str and re.fullmatch(r'[D-Z]:\\GridLab',s['parent']),'LAB_PATH_INVALID')
    need(type(s['run_id'])is str and re.fullmatch('[0-9a-f]{32}',s['run_id']) and s['run_id']!='0'*32,'LAB_RUN_INVALID')
    service=resource(m,'services');expected=dict(postgres_major=16,postgres_listen='127.0.0.1',task_prefix='BybitClusterGridLab_',registered_tasks=[],installed_services=[],startup_authorized=False,trading=False,telegram=False,postgres_started=False)
    shape(service,(*expected,'postgres_port','coordinator_port'));fixed(service,expected)
    ports=[service[k] for k in ('postgres_port','coordinator_port')]
    need(all(type(v)is int and 20000<=v<=49999 for v in ports) and len(set(ports))==2,'LAB_PORT_INVALID')
    for name,expected in (
      ('trust',dict(operator_root=None,observer_a_root=None,observer_b_root=None,live_keys='NOT_PROVISIONED',test_keys_allowed=False,authority_verified=False)),
      ('time',dict(scheme='OUT_OF_BAND_NONCE_BOUND_TIMESTAMP',max_uncertainty_seconds=2,implementation='NOT_IMPLEMENTED',source_endpoint=None,verified=False)),
      ('anti_rollback',dict(scheme='TWO_INDEPENDENT_DURABLE_WITNESSES',ack_policy='2_OF_2',storage='EXTERNAL_TO_LAB_HOST',implementation='NOT_IMPLEMENTED',anchor_endpoint=None,correlated_rollback_resistance='UNPROVEN',verified=False))):
        p=resource(m,name);shape(p,expected);fixed(p,expected)
    retention=resource(m,'retention');expected=dict(archive='UNPROVISIONED',append_only_verified=False,automatic_delete=False,cleanup_policy='SEPARATE_APPROVAL_AND_PROVEN_OWNERSHIP',teardown_owner='operator',preserve_on_failure=True)
    shape(retention,(*expected,'planned_days','planned_max_runs'));fixed(retention,expected)
    need(type(retention['planned_days'])is int and 1<=retention['planned_days']<=365 and type(retention['planned_max_runs'])is int and 1<=retention['planned_max_runs']<=100,'LAB_RETENTION_INVALID')
    gates=m['gates'];need(type(gates)is list and len(gates)==6,'LAB_GATES_INVALID')
    for i,(g,owner) in enumerate(zip(gates,('operator','observer_a','operator','observer_b','operator','operator'))):
        expected=dict(level='L'+str(i),owner=owner,source_sha=RC,evidence_digest=None,authorized=False,status='PROPOSED' if i<2 else 'NOT_RUN',rollback='PRESERVE_ONLY')
        shape(g,expected);fixed(g,expected)
    cases=m['negative_cases'];need(type(cases)is list and len(cases)==12,'LAB_CASES_INVALID')
    for i,(case,(name,_)) in enumerate(zip(cases,CASES),1):
        expected=dict(id=f'VM-NEG-{i:02}',case=name,execution='NOT_RUN',expected='STOP_BLOCKED',evidence_digest=None)
        shape(case,expected);fixed(case,expected)
def result(errors):
    return dict(schema=1,status='BLOCKED',manifest_valid=not errors,errors=errors,physical_deployment='NO-GO',
        native_evidence='UNVERIFIED',durable_anti_rollback='NOT_IMPLEMENTED',guest_cases='12 NOT_RUN',
        assurance='OFFLINE_DESIGN_METADATA_ONLY',verified_safety_cases=0,**dict.fromkeys(FLAGS,False))
def validate_manifest(m):
    try:check(m)
    except (ValueError,TypeError,KeyError,OverflowError,RecursionError):return result(['LAB_MANIFEST_INVALID'])
    return result([])
def validate_text(raw):
    try:return validate_manifest(load(raw))
    except (ValueError,TypeError,OverflowError,RecursionError):return result(['LAB_JSON_INVALID'])
def main():
    try:r=validate_text(sys.stdin.buffer.read(65537).decode('utf-8',errors='strict'))
    except UnicodeError:r=result(['LAB_JSON_INVALID'])
    print(json.dumps(r,sort_keys=True));return 0 if r['manifest_valid'] else 2
if __name__=='__main__':raise SystemExit(main())
