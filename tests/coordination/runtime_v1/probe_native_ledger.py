"""Actual Consul operation-plan probe with UNTRUSTED synthetic domain records.
Not commit_storage, an issued assignment, native identity or publication evidence.
"""
import argparse,asyncio,base64,hashlib,json,subprocess,sys,types,uuid
from pathlib import Path
sys.dont_write_bytecode=True
ROOT=Path(__file__).absolute().parents[3];sys.path.insert(0,str(ROOT))
from grid.authority_runtime_v1 import PartitionIdentity,RuntimeLayout,canonical,measure_native_plan
from grid.coordination import ConsulConfig,ConsulSessionAuthority,CoordinationLost

def check(key,index):return {'KV':dict(Verb='check-index',Key=key,Index=index)}
def cas(key,index,raw):return {'KV':dict(Verb='cas',Key=key,Index=index,Value=base64.b64encode(raw).decode())}

def main():
 p=argparse.ArgumentParser();p.add_argument('--unified-source',required=True);p.add_argument('--binary',required=True);p.add_argument('--scratch',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 labraw=subprocess.check_output(['git','--no-replace-objects','-C',a.unified_source,'show','1c3b8ad57afb4de56d512c28876a9e5e40969f6d:tests/control_mux/consul_lab.py'])
 m=types.ModuleType('pinned_owned_loopback_fixture');exec(compile(labraw,'<pinned-loopback-fixture>','exec'),m.__dict__)
 report=dict(schema='agent2.runtime-v1.native-operation-probe.review1',qualification='REAL_CONSUL_PLAN_WITH_UNTRUSTED_DOMAIN_RECORDS_ONLY',producer_implemented=False,publication_qualified=False,native_identity=False,production='NO_GO',events=[])
 with m.ConsulLab(a.binary,a.scratch) as lab:
  async def run():
   ids=[str(uuid.uuid4()) for _ in range(20)];cluster,dataset,worker,logicallease,owner,request,receipt=ids[:7]
   layout=RuntimeLayout(PartitionIdentity(cluster,dataset,'source.v1','partition.0'));n=layout.namespace
   authority=ConsulSessionAuthority(ConsulConfig(endpoints=tuple(lab.nodes),namespace=n,isolated_lab=True,ttl_seconds=15,request_timeout=2))
   try:
    gen=str(uuid.uuid4());generation=n+'/commands/generation';await authority._request('PUT','/v1/kv/'+generation,content=canonical({'generation':gen}));leader=await authority.acquire('native-plan-fixture');assert leader
    session=(await authority._request('PUT','/v1/session/create',json=dict(Name='owned-runtime-plan-worker',TTL='15s',Behavior='release',LockDelay='0s',NodeChecks=[])))['ID']
    lock=layout.lease(logicallease,'lock');await authority._request('PUT','/v1/txn',json=[{'KV':dict(Verb='check-session',Key=authority.key,Session=leader.session_id)},check(authority.key,leader.token),{'KV':dict(Verb='lock',Key=lock,Session=session,Value=base64.b64encode(canonical({'schema':'UNTRUSTED_NATIVE_PLAN_LEASE','lease_id':logicallease})).decode())}])
    keyhash=hashlib.sha256(b'UNTRUSTED_ORIGINAL_COMMAND').hexdigest();keys=layout.original(request,keyhash,receipt)
    families=[]
    def add(family,key,verb='check',owner='A2'):families.append((family,key,verb,owner))
    for family,path in [('native-principal','principals/'+ids[7]),('native-session','sessions/'+ids[8]),('native-enrollment','enrollments/'+ids[9]),('native-policy','policies/'+ids[10])]:add(family,n+'/security/v1/'+path)
    for family in ('registration','policy','observation-current','resource-ledger'):add('node-'+family,layout.node(worker,family),'check','A5')
    add('issued-resource-reservation',layout.resource_reservation(ids[19]),'check','A5')
    add('current-capacity-observation',layout.observation(str(uuid.uuid4())),'check','A5')
    add('actual-execution-attempt',layout.execution_attempt(worker,str(uuid.uuid4())),'check','A2/Root')
    freshness=layout.node(worker,'freshness')
    await authority._request('PUT','/v1/txn',json=[{'KV':dict(Verb='lock',Key=freshness,Session=session,Value=base64.b64encode(canonical({'schema':'UNTRUSTED_FRESHNESS_SESSION'})).decode())}])
    add('current-assignment',layout.assignment,'check','A5');add('durable-counters',layout.counters)
    add('logical-lease-binding',layout.lease(logicallease,'binding'))
    for i in range(2):
     node,volume,instance=ids[11+i*3:14+i*3]
     for family in ('budget','drain','allocation','reservation'):
      add('storage-'+family,layout.storage(node,volume,instance,family,ids[17+i] if family=='reservation' else None),'cas' if family in ('budget','allocation') else 'check','A4')
    for i in range(8):add('replica-eligibility',layout.prefix+'replicas/'+hashlib.sha256(('replica'+str(i)).encode()).hexdigest(),'check','A4')
    for i in range(4):add('direct-hold',layout.prefix+'holds/'+str(uuid.uuid4()),'check','A4')
    add('source-policy',layout.source_policy,'check','A3/A4');add('coverage',layout.coverage,'cas','A4');add('dataset-head',layout.dataset_head,'cas','A4');add('checkpoint-head',layout.checkpoint,'cas','A3/A4')
    for family in ('publication','outbox','receipt'):add(family,keys[family],'cas0','A2/A4')
    add('original-command',keys['command'],'cas')
    add('global-request-binding',keys['common_request'])
    add('global-key-binding',layout.common_key(owner,owner,'intent1'))
    add('pending-intent-ledger',layout.prefix+'intent-ledgers/'+owner,'cas')
    for family,key,verb,_ in families:
     if verb!='cas0':await authority._request('PUT','/v1/kv/'+key,content=canonical(dict(schema='UNTRUSTED_NATIVE_PLAN_RECORD',family=family,revision='1')))
    async def row(key):
     rows=await authority._request('GET','/v1/kv/'+key,params={'consistent':''},missing_ok=True)
     if rows is None:return 0,None
     assert len(rows)==1 and rows[0]['Key']==key and type(rows[0]['ModifyIndex']) is int
     return rows[0]['ModifyIndex'],base64.b64decode(rows[0]['Value'])
    async def plan():
     g,_=await row(generation);li,_=await row(lock);fi,_=await row(freshness)
     ops=[{'KV':dict(Verb='check-session',Key=authority.key,Session=leader.session_id)},check(authority.key,leader.token),check(generation,g),{'KV':dict(Verb='check-session',Key=lock,Session=session)},check(lock,li),{'KV':dict(Verb='check-session',Key=freshness,Session=session)},check(freshness,fi)]
     ledger=[dict(ordinal=i+1,family=family,owner='A2',key=op['KV']['Key'],verb=op['KV']['Verb'],precondition='ACTUAL_NATIVE_SESSION_OR_INDEX') for i,(family,op) in enumerate(zip(('current-leader-session','current-leader-index','generation','worker-lease-session','worker-lease-index','native-freshness-session','native-freshness-index'),ops))]
     for family,key,verb,owner_name in families:
      index,_=await row(key)
      if verb=='check':assert index>0;op=check(key,index)
      elif verb=='cas0':assert index==0;op=cas(key,0,canonical(dict(schema='UNTRUSTED_NATIVE_PLAN_RESULT',family=family,request_id=request,revision='2')))
      else:assert index>0;op=cas(key,index,canonical(dict(schema='UNTRUSTED_NATIVE_PLAN_RESULT',family=family,request_id=request,revision='2')))
      ops.append(op);ledger.append(dict(ordinal=len(ops),family=family,owner=owner_name,key=key,verb=op['KV']['Verb'],precondition='CAPTURED_ACTUAL_INDEX_OR_ABSENCE',actual_native_index=index))
     for entry,op in zip(ledger,ops):
      entry['operation_encoded_bytes']=len(json.dumps(op,separators=(',',':')).encode());entry['value_bytes']=len(base64.b64decode(op['KV'].get('Value','')))
     return ops,ledger
    operations,ledger=await plan();measure=measure_native_plan(operations)
    report['rejected_plan_measure']=dict(operations=measure.operations,encoded_bytes=measure.encoded_bytes,encoded_sha256=measure.encoded_sha256)
    assert measure.operations<=64 and measure.encoded_bytes<=32768
    # Supersession wins first: SAME current assignment key changed, old plan rejects atomically.
    ai,_=await row(layout.assignment);await authority._request('PUT','/v1/txn',json=[cas(layout.assignment,ai,canonical({'schema':'UNTRUSTED_SUPERSESSION','revision':'2'}))])
    try:await authority._request('PUT','/v1/txn',json=operations)
    except CoordinationLost:pass
    else:raise AssertionError('STALE_ASSIGNMENT_PLAN_COMMITTED')
    assert (await row(keys['receipt']))[0]==0 and (await row(keys['publication']))[0]==0
    report['events'].append('SUPERSESSION_FIRST_REJECTS_SAME_ASSIGNMENT_KEY_PLAN')
    # A fresh plan over current fixture state wins before later supersession.
    operations,ledger=await plan();measure=measure_native_plan(operations)
    await authority._request('PUT','/v1/txn',json=operations)
    report.update(operation_count=measure.operations,encoded_request_bytes=measure.encoded_bytes,encoded_request_sha256=measure.encoded_sha256,ledger=ledger)
    index,value=await row(keys['receipt']);assert index>0
    ai,_=await row(layout.assignment);await authority._request('PUT','/v1/txn',json=[cas(layout.assignment,ai,canonical({'schema':'UNTRUSTED_LATER_SUPERSESSION','revision':'3'}))])
    assert await row(keys['receipt'])==(index,value)
    report['actual_probe_receipt_modify_index']=index;report['events'].append('PLAN_FIRST_PRESERVES_IMMUTABLE_PROBE_RECEIPT')
    # Native64-operation boundary with unique, actual existing check rows.
    extras=[]
    for i in range(64):
     key=layout.prefix+'probe-only/operation-boundary/'+str(i);await authority._request('PUT','/v1/kv/'+key,content=b'fixture');idx,_=await row(key);extras.append(check(key,idx))
    measure_native_plan(extras);await authority._request('PUT','/v1/txn',json=extras,params={'consistent':''})
    try:measure_native_plan(extras+[extras[0]])
    except ValueError:pass
    else:raise AssertionError('65_OPERATIONS_ACCEPTED')
    report['events'].append('64_NATIVE_OPERATIONS_ACCEPT_65_PREFLIGHT_DENY')
    # Exact configured request-byte boundary; not a domain-record size approval.
    native=None
    for suffix in range(4):
     key=layout.prefix+'probe-only/byte-boundary'+'x'*suffix
     overhead=len(json.dumps([cas(key,0,b'')],separators=(',',':')).encode())
     delta=32768-overhead
     if delta%4==0:
      native=[cas(key,0,b'x'*(delta//4*3))];break
    assert native and measure_native_plan(native).encoded_bytes==32768
    await authority._request('PUT','/v1/txn',json=native)
    oversized=json.loads(json.dumps(native));oversized[0]['KV']['Key']+='x'
    try:measure_native_plan(oversized)
    except ValueError:pass
    else:raise AssertionError('32769_BYTES_ACCEPTED')
    report['events'].append('32768_NATIVE_BYTES_ACCEPT_32769_PREFLIGHT_DENY')
    await authority._request('PUT','/v1/session/destroy/'+session)
    await authority.release(leader)
   finally:await authority.close()
  asyncio.run(run())
 report['owned_processes_stopped']=all(p.poll() is not None for p in lab.processes);report['result']='PASS_NATIVE_PLAN_ONLY_NOT_PUBLICATION'
 a.output.write_bytes((json.dumps(report,indent=2)+'\n').encode());print(json.dumps({k:v for k,v in report.items() if k!='ledger'}))
if __name__=='__main__':main()
