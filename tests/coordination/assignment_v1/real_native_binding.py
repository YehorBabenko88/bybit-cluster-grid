"""Owned real Consul guard/CAS substrate contract, NOT an issued grant.
Explicit lab-source is hash pinned; no native identity/provider is invented.
"""
import argparse,asyncio,hashlib,importlib.util,json,sys,uuid
from pathlib import Path

def main():
    p=argparse.ArgumentParser();p.add_argument('--binary',required=True);p.add_argument('--lab-source',required=True,type=Path);p.add_argument('--scratch',required=True);p.add_argument('--output',required=True,type=Path);a=p.parse_args()
    root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root))
    raw=a.lab_source.read_bytes();assert hashlib.sha256(raw).hexdigest()=='367e57bb130cc52298048aeee53f73ac39f6c0899c5d2a5ac39b9cd0065d1b9e'
    module=importlib.util.module_from_spec(importlib.util.spec_from_loader('a2_owned_native_consul_lab',loader=None));exec(compile(raw,str(a.lab_source),'exec'),module.__dict__)
    from grid.coordination import ConsulConfig,ConsulSessionAuthority,CoordinationLost,CoordinationUnavailable
    from grid.authority_runtime_v1 import PartitionIdentity,canonical
    from grid.authority_assignment_v1 import AssignmentAuthority,AssignmentLayout,AssignmentUnavailable,_check,_cas
    report=dict(scope='RAW_NATIVE_CONSUL_BINDING_ONLY_NOT_ASSIGNMENT_OR_NATIVE_SECURITY',native_identity=False,issued_assignment=False,production='NO_GO',events=[])
    with module.ConsulLab(a.binary,a.scratch) as lab:
        async def run():
            cluster,generation,dataset=[str(uuid.uuid4()) for _ in range(3)]
            authority=ConsulSessionAuthority(ConsulConfig(endpoints=tuple(lab.nodes),namespace='unified/'+cluster,isolated_lab=True,ttl_seconds=60,request_timeout=2))
            try:
                genkey=authority.config.namespace+'/commands/generation'
                await authority._request('PUT','/v1/kv/'+genkey,content=canonical({'generation':generation}))
                lease=await authority.acquire('assignment-native-binding-owned');assert lease is not None
                backend=AssignmentAuthority(authority,generation);layout=AssignmentLayout(PartitionIdentity(cluster,dataset,'offline','partition'))
                try:await backend.execute(b'{}',context=object(),leader=lease)
                except AssignmentUnavailable:pass
                else:raise AssertionError('ABSENT_NATIVE_PROVIDER_ISSUED_GRANT')
                report['events'].append('PUBLIC_ASSIGNMENT_DEFAULT_NATIVE_ABSENCE_DENIED')
                record={'schema':'untrusted.native-binding-probe.v1','revision':'1'}
                await authority._request('PUT','/v1/kv/'+layout.assignment,content=canonical(record))
                current=await backend._read(layout.assignment);fence=await backend._leader_fence(lease)
                receipt_key=layout.prefix+'probe-only/receipts/'+str(uuid.uuid4())
                await backend._transaction(fence+[_check(current),_cas(receipt_key,0,dict(schema='untrusted.probe-receipt.v1',result='CAPTURED'))])
                receipt=await backend._read(receipt_key);assert receipt.index>0
                report['events'].append('ACTUAL_CHECKED_NATIVE_RECEIPT_RAW_PROBE_COMMIT')
                old_fence=await backend._leader_fence(lease)
                await authority.release(lease);lease=await authority.acquire('assignment-native-binding-successor');assert lease is not None
                stale_key=layout.prefix+'probe-only/stale-leader'
                try:await backend._transaction(old_fence+[_cas(stale_key,0,{'never':'commit'})])
                except CoordinationLost:pass
                else:raise AssertionError('STALE_NATIVE_LEADER_COMMITTED')
                assert not(await backend._read(stale_key)).index
                report['events'].append('ACTUAL_STALE_LEADER_NATIVE409_NO_EFFECT')
                old_fence=await backend._leader_fence(lease)
                await authority._request('PUT','/v1/kv/'+genkey,content=canonical({'generation':str(uuid.uuid4())}))
                stale_gen_key=layout.prefix+'probe-only/stale-generation'
                try:await backend._transaction(old_fence+[_cas(stale_gen_key,0,{'never':'commit'})])
                except CoordinationLost:pass
                else:raise AssertionError('STALE_GENERATION_COMMITTED')
                assert not(await backend._read(stale_gen_key)).index
                report['events'].append('ACTUAL_STALE_GENERATION_NATIVE409_NO_EFFECT')
                await authority._request('PUT','/v1/kv/'+genkey,content=canonical({'generation':generation}))
                fence=await backend._leader_fence(lease);current=await backend._read(layout.assignment)
                superseded=dict(record,revision='2')
                await backend._transaction(fence+[_cas(layout.assignment,current.index,superseded)])
                publication_key=layout.prefix+'probe-only/publications/'+str(uuid.uuid4())
                try:await backend._transaction(fence+[_check(current),_cas(publication_key,0,{'never':'stale-publication'})])
                except CoordinationLost:pass
                else:raise AssertionError('SUPERSEDED_NATIVE_ASSIGNMENT_KEY_PUBLISHED')
                assert not(await backend._read(publication_key)).index
                report['events'].append('ACTUAL_SUPERSESSION_FIRST_REJECTS_PUBLICATION_SAME_KEY')
                current=await backend._read(layout.assignment);first_key=layout.prefix+'probe-only/publications/'+str(uuid.uuid4())
                await backend._transaction(fence+[_check(current),_cas(first_key,0,{'schema':'untrusted.probe-publication.v1','original':'immutable'})])
                committed=await backend._read(first_key)
                await backend._transaction(fence+[_cas(layout.assignment,current.index,dict(record,revision='3'))])
                assert await backend._read(first_key)==committed
                report['events'].append('ACTUAL_PUBLICATION_FIRST_RECEIPT_RETAINED_AFTER_SUPERSESSION')
                lab.restart_all();await asyncio.to_thread(lab.wait_quorum)
                assert await backend._read(receipt_key)==receipt and await backend._read(first_key)==committed
                lease=await authority.acquire('assignment-native-binding-restart')
                if lease is None:
                    # Existing owned session may survive restart; history alone
                    # never becomes new leader permission. No new effect needed.
                    pass
                report['events'].append('ACTUAL_SIMULTANEOUS_RESTART_DURABLE_NATIVE_RECEIPT_INDEX')
                for index in (0,1):lab.stop_node(index)
                try:await backend._read(receipt_key)
                except CoordinationUnavailable:pass
                else:raise AssertionError('ONE_OF_THREE_CONSISTENT_READ_SUCCEEDED')
                report['events'].append('ACTUAL_ONE_OF_THREE_NO_QUORUM_NO_CACHE_SUCCESS')
                report['receipt_index']=receipt.index;report['receipt_sha256']=hashlib.sha256(receipt.raw).hexdigest()
            finally:await authority.close()
        asyncio.run(asyncio.wait_for(run(),timeout=90))
    report['owned_processes_stopped']=all(p.poll() is not None for p in lab.all_processes);report['result']='PASS'
    a.output.write_bytes((json.dumps(report,indent=2)+chr(10)).encode());print(json.dumps(report))
if __name__=='__main__':main()
