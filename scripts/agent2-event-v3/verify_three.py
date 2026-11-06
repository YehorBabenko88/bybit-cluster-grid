"""Real ephemeral Linux3-voter scenario. Never run against physical services."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import uuid

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'lab/consul'))
import httpx
from provision import IMAGE, docker
from grid.coordination import ConsulConfig, ConsulSessionAuthority
from grid.coordination_event_v3 import EventAuthority


class SyntheticProvider:
    async def require_current(self, context, action, assignment):
        if context!='SYNTHETIC_ONLY':
            raise ValueError('fixture context required')
        return SimpleNamespace(actor_id='operator',grant_revision=1,capabilities=frozenset({'authority.lifecycle'}))


async def verify(output):
    if sys.platform!='linux' or os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted':
        raise RuntimeError('EPHEMERAL_GITHUB_HOSTED_LINUX_REQUIRED')
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    label='agent2-event-v3-'+uuid.uuid4().hex[:12];network=label+'-net'
    nodes=[];network_created=False;observer_created=False;observer=label+'-observer'
    evidence=dict(schema='grid.event-v3.three.evidence.v1',result='RUNNING',image=IMAGE,
        qualification='REAL_CONSUL_SYNTHETIC_PRINCIPAL_LIFECYCLE_ONLY',production='NO_GO',
        windows_physical='NOT_RUN',tls_acl_identity='NOT_QUALIFIED',publication='UNWIRED',events=[],nodes=nodes)

    def record(name,**fields):
        evidence['events'].append(dict(scenario=name,**fields));save()

    def save():
        (output/'evidence.json').write_text(json.dumps(evidence,indent=2)+'\n')

    def inspect(node):
        info=json.loads(docker('inspect',node['id']))[0]
        if (info['Id']!=node['id'] or info['Config']['Image']!=IMAGE
                or info['Config']['Labels'].get('grid.lab')!=label
                or info['HostConfig']['RestartPolicy']['Name']!='no'
                or not any(m.get('Name')==node['volume'] and m['Destination']=='/consul/data' for m in info['Mounts'])):
            raise RuntimeError('OWNED_CONTAINER_IDENTITY_MISMATCH')
        return info

    def endpoint(node):
        info=inspect(node);ip=info['NetworkSettings']['Networks'].get(network,{}).get('IPAddress')
        if not ip:raise RuntimeError('OWNED_ENDPOINT_UNAVAILABLE')
        node['ip']=ip
        return 'http://'+ip+':8500'

    def act(verb,node):
        inspect(node);return docker(verb,node['id'])

    async def healthy(http,live):
        until=time.monotonic()+60
        while time.monotonic()<until:
            try:
                for node in live:
                    r=await http.get(endpoint(node)+'/v1/operator/raft/configuration');r.raise_for_status()
                    servers=r.json()['Servers']
                    assert len(servers)==3 and all(s['Voter'] is True for s in servers)
                    assert len({s['ID'] for s in servers})==3 and sum(s['Leader'] is True for s in servers)==1
                    assert {s['Node'] for s in servers}=={n['name'] for n in nodes}
                return servers
            except (httpx.HTTPError,AssertionError,KeyError):await asyncio.sleep(.25)
        raise RuntimeError('THREE_VOTER_CONFIGURATION_TIMEOUT')

    try:
        image=json.loads(docker('image','inspect',IMAGE))[0]
        assert IMAGE in image['RepoDigests']
        version=docker('run','--rm','--network=none','--entrypoint=consul',IMAGE,'version')
        assert 'Consul v2.1.0' in version and '881572b4' in version
        record('image_source_checked',version=version,image_id=image['Id'])
        docker('network','create','--internal','--label','grid.lab='+label,network);network_created=True
        net=json.loads(docker('network','inspect',network))[0]
        assert net['Internal'] is True and net['Labels']['grid.lab']==label
        names=[label+'-'+n for n in ('ls5','pc4','pc3')]
        for name in names:
            volume=name+'-data';docker('volume','create','--label','grid.lab='+label,volume)
            node=dict(name=name,volume=volume);nodes.append(node)
            node['id']=docker('run','-d','--name',name,'--hostname',name,'--network',network,
                '--label','grid.lab='+label,'--restart=no','--memory=256m','--cpus=.5',
                '--mount','type=volume,source='+volume+',target=/consul/data',
                '-e','CONSUL_LOCAL_CONFIG='+json.dumps({'leave_on_terminate':False,'autopilot':{'cleanup_dead_servers':False}}),
                IMAGE,'agent','-server','-bootstrap-expect=3','-node='+name,'-client=0.0.0.0','-bind=0.0.0.0',
                '-data-dir=/consul/data','-retry-interval=1s',*['-retry-join='+p for p in names if p!=name])
            inspect(node)
        async with httpx.AsyncClient(trust_env=False,timeout=2) as http:
            servers=await healthy(http,nodes);record('three_real_voters',servers=servers)
            generation,assignment,incarnation=[str(uuid.uuid4()) for _ in range(3)]
            namespace='event-v3-'+uuid.uuid4().hex
            def authority(live):
                return ConsulSessionAuthority(ConsulConfig(endpoints=tuple(endpoint(n) for n in live),
                    namespace=namespace,isolated_lab=True,ttl_seconds=60),client=http)
            a=authority(nodes);v=EventAuthority(a,generation,principal_provider=SyntheticProvider())
            for suffix,value in [('generation',{'generation':generation}),
                ('principals/operator',{'actor_id':'operator','grant_revision':'1','state':'ADMITTED','capabilities':['authority.lifecycle']}),
                ('workers/worker',{'worker_id':'worker','incarnation':incarnation,'state':'ADMITTED'})]:
                r=await http.put(endpoint(nodes[0])+'/v1/kv/'+(v.generation_key if suffix=='generation' else v.prefix+suffix),json=value);r.raise_for_status()
            leader=await a.acquire('LS5');assert leader
            session=await v.prepare_session(leader,'SYNTHETIC_ONLY',assignment)
            def command(action,revision,request):
                return dict(schema='unified.authority.lifecycle.v3',request_id=request,generation=generation,
                    actor_id='operator',assignment_id=assignment,worker_id='worker',worker_incarnation=incarnation,
                    lease_session_id=session,action=action,expected_revision=str(revision))
            grant=command('GRANT',0,'grant')
            receipt=await v.submit(leader,grant,'SYNTHETIC_ONLY');assert receipt['status']=='COMMITTED'
            assert await v.submit(leader,grant,'SYNTHETIC_ONLY')==receipt
            record('grant_and_idempotent_receipt',receipt=receipt)
            actual=next(n for n in nodes if n['name']==next(s['Node'] for s in servers if s['Leader']))
            act('kill',actual);live=[n for n in nodes if n!=actual]
            await healthy(http,live)
            a2=authority(live);v2=EventAuthority(a2,generation,principal_provider=SyntheticProvider())
            assert await v2.submit(leader,grant,'SYNTHETIC_ONLY')==receipt
            record('raft_leader_crash_receipt_survives')
            # Logical owner deliberately changes through existing authority session.
            r=await http.put(endpoint(live[0])+'/v1/session/destroy/'+leader.session_id);r.raise_for_status()
            successor=await a2.acquire('PC4');assert successor and successor.token>leader.token
            assert (await v2.submit(leader,command('RENEW',1,'stale-owner'),'SYNTHETIC_ONLY'))['status']=='REJECTED'
            assert (await v2.submit(successor,command('RENEW',1,'renew'),'SYNTHETIC_ONLY'))['status']=='COMMITTED'
            record('successor_renews_old_leader_rejected',old_token=leader.token,new_token=successor.token)
            r=await http.put(endpoint(live[0])+'/v1/session/destroy/'+session);r.raise_for_status()
            assert (await v2.submit(successor,command('RENEW',2,'expired'),'SYNTHETIC_ONLY'))['status']=='REJECTED'
            assert (await v2.submit(successor,command('REVOKE',2,'revoke'),'SYNTHETIC_ONLY'))['status']=='COMMITTED'
            record('lease_invalidation_no_successor_rejected_terminal_reconciled')
            act('kill',live[1]);single=authority([live[0]])
            single_v=EventAuthority(single,generation,principal_provider=SyntheticProvider())
            assert (await single_v.submit(successor,command('COMPLETE',3,'minority'),'SYNTHETIC_ONLY'))['status']=='UNKNOWN'
            record('two_voter_loss_no_new_mutation')
            for node in nodes:
                if inspect(node)['State']['Running']:act('kill',node)
            for node in nodes:act('start',node)
            await healthy(http,nodes)
            restarted=EventAuthority(authority(nodes),generation,principal_provider=SyntheticProvider())
            assert await restarted.submit(successor,grant,'SYNTHETIC_ONLY')==receipt
            record('simultaneous_restart_durable_receipt')
            # Real 1/2 isolation, not a boolean quorum model.
            minority=nodes[0];inspect(minority)
            docker('network','create','--internal','--label','grid.lab='+label,observer);observer_created=True
            docker('network','connect',observer,minority['id'])
            observer_ip=inspect(minority)['NetworkSettings']['Networks'][observer]['IPAddress']
            isolated_endpoint='http://'+observer_ip+':8500'
            docker('network','disconnect',network,minority['id'])
            majority=nodes[1:];await healthy(http,majority)
            majority_a=authority(majority);majority_v=EventAuthority(majority_a,generation,principal_provider=SyntheticProvider())
            assert await majority_v.submit(successor,grant,'SYNTHETIC_ONLY')==receipt
            r=await http.put(endpoint(majority[0])+'/v1/session/destroy/'+successor.session_id);r.raise_for_status()
            majority_owner=await majority_a.acquire('PC3');assert majority_owner
            assignment=str(uuid.uuid4())
            session=await majority_v.prepare_session(majority_owner,'SYNTHETIC_ONLY',assignment)
            partition_intent=command('GRANT',0,'partition-grant')
            partition_receipt=await majority_v.submit(majority_owner,partition_intent,'SYNTHETIC_ONLY')
            assert partition_receipt['status']=='COMMITTED'
            # Reachable HTTP minority, isolated from Raft majority: not just dead endpoint.
            alive=await http.get(isolated_endpoint+'/v1/status/peers');alive.raise_for_status()
            isolated_a=ConsulSessionAuthority(ConsulConfig(endpoints=(isolated_endpoint,),namespace=namespace,
                isolated_lab=True,ttl_seconds=60,request_timeout=1),client=http)
            isolated_v=EventAuthority(isolated_a,generation,principal_provider=SyntheticProvider())
            assert (await isolated_v.submit(majority_owner,dict(partition_intent,request_id='minority'),'SYNTHETIC_ONLY'))['status']=='UNKNOWN'
            record('one_two_partition_majority_commits_reachable_minority_denied',receipt=partition_receipt)
            record('one_two_partition_majority_consistent_receipt')
            docker('network','connect','--alias',minority['name'],network,minority['id'])
            await healthy(http,nodes)
            assert await majority_v.submit(majority_owner,partition_intent,'SYNTHETIC_ONLY')==partition_receipt
            record('partition_heal_reconciled')
            evidence['result']='PASS';save()
    except BaseException as exc:
        evidence['result']='FAIL';record('failure',error_type=type(exc).__name__,error=str(exc));raise
    finally:
        failures=[]
        for node in reversed(nodes):
            try:
                if 'id' in node:inspect(node);docker('rm','-f',node['id'])
                vol=json.loads(docker('volume','inspect',node['volume']))[0]
                if vol['Name']!=node['volume'] or vol.get('Labels',{}).get('grid.lab')!=label:raise RuntimeError('OWNED_VOLUME_REQUIRED')
                docker('volume','rm',node['volume'])
            except Exception as exc:failures.append(str(exc))
        for name,created in ((network,network_created),(observer,observer_created)):
            if created:
                try:
                    net=json.loads(docker('network','inspect',name))[0]
                    if net['Name']!=name or net['Labels'].get('grid.lab')!=label:raise RuntimeError('OWNED_NETWORK_REQUIRED')
                    docker('network','rm',name)
                except Exception as exc:failures.append(str(exc))
        if failures:evidence['result']='FAIL';record('cleanup_failure',errors=failures)
        save()
        if failures:raise RuntimeError('OWNED_CLEANUP_FAILED')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-ephemeral-hosted-linux',action='store_true',required=True)
    parser.add_argument('--output',required=True)
    args=parser.parse_args();asyncio.run(verify(args.output))
