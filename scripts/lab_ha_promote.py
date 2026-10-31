#!/usr/bin/env python3
"""Promotion experiment only against previously labeled owned-cloud PG/Consul labs."""
import argparse
import asyncio
import json
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from grid.coordination import ConsulConfig, ConsulSessionAuthority
from grid.postgres_ha import PromotionController, HAError, lsn_bytes
from lab_ha_postgres import docker, IMAGE

async def main():
    parser=argparse.ArgumentParser();parser.add_argument('--postgres-evidence',required=True);parser.add_argument('--consul-manifest',required=True);parser.add_argument('--output',required=True);args=parser.parse_args()
    p=json.loads(Path(args.postgres_evidence).read_text());c=json.loads(Path(args.consul_manifest).read_text())
    if p.get('result')!='PASS_REPLICATION_PITR_STANDBY_LOSS' or p.get('standby_count')!=4 or p.get('image')!=IMAGE:
        raise RuntimeError('qualified five-role owned lab required')
    names=p['names'];prefix=p['prefix'];out=Path(args.output);out.mkdir(exist_ok=False,parents=True)
    # Endpoint manifest must bind each address to the actual labeled container.
    for v in c['voters']:
        facts=json.loads(docker('inspect',v['name']).stdout)[0]
        if facts['Id']!=v['id'] or facts['Config']['Labels'].get('grid.lab')!=c['label'] or facts['Config']['Image']!=c['image'] or facts['NetworkSettings']['Networks'][c['network']]['IPAddress']!=v['ip'] or v['endpoint']!='http://'+v['ip']+':8500':
            raise RuntimeError('Consul resource identity mismatch')
    containers={}
    for role,name in names.items():
        facts=json.loads(docker('inspect',name).stdout)[0]
        if facts['Config']['Labels'].get('codex.lab')!=prefix or facts['Config']['Image']!=IMAGE:
            raise RuntimeError('PG resource identity mismatch')
        containers[role]=facts['Id']
    def sql(role,query):
        return docker('exec',names[role],'timeout','15','psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U','postgres','-c',query).stdout.strip()
    client=httpx.AsyncClient(trust_env=False,follow_redirects=False)
    authority=ConsulSessionAuthority(ConsulConfig(endpoints=tuple(v['endpoint'] for v in c['voters']),namespace='lab-grid/pg-ha-'+prefix,isolated_lab=True,ttl_seconds=120),client=client)
    evidence={'schema':'grid.pg18.consul.cloud-promotion.v1','pg_prefix':prefix,'physical':'NOT_RUN','production':'NO_GO','result':'INCOMPLETE'}
    def save(): (out/'evidence.json').write_text(json.dumps(evidence,indent=2))
    save();lease=None
    try:
        lease=await authority.acquire('s1')
        if lease is None:raise RuntimeError('DCS lease not acquired')
        cluster=sql('primary','SELECT system_identifier::text FROM pg_control_system()')
        sql('primary',"INSERT INTO ha_probe VALUES(40,'durable-before-primary-loss')")
        required=sql('primary','SELECT pg_current_wal_lsn()::text')
        for _ in range(60):
            if lsn_bytes(sql('s1','SELECT pg_last_wal_replay_lsn()::text'))>=lsn_bytes(required):break
            await asyncio.sleep(.1)
        else:raise RuntimeError('candidate not caught up')
        await authority.write_control(lease,'acknowledged_lsn',{'lsn':required,'system_identifier':cluster,'old_primary_id':containers['primary'],'candidate_id':containers['s1']})
        async def current(owner,epoch):
            return owner==lease.owner and epoch==lease.token and await authority.validate(lease)
        async def acknowledged(owner,epoch):
            if not await current(owner,epoch):raise HAError('DCS unavailable')
            record=await authority.read_control('acknowledged_lsn')
            if not record or any(record[k]!=getattr(lease,k) for k in ('owner','token','session_id')):raise HAError('checkpoint lease mismatch')
            value=record['payload']
            if value['system_identifier']!=cluster or value['candidate_id']!=containers['s1'] or value['old_primary_id']!=containers['primary']:raise HAError('checkpoint cluster mismatch')
            return value['lsn']
        async def fenced(old,epoch):
            if old!='primary' or epoch!=lease.token:return False
            facts=json.loads(docker('inspect',names['primary']).stdout)[0]
            return (facts['Id']==containers['primary'] and facts['State']['Running'] is False
                    and facts['HostConfig']['RestartPolicy']['Name']=='no'
                    and facts['Config']['Labels'].get('codex.lab')==prefix)
        class PG:
            async def recovery(self):return sql('s1','SELECT pg_is_in_recovery()')=='t'
            async def replay_lsn(self):return sql('s1','SELECT pg_last_wal_replay_lsn()::text')
            async def promote(self):return sql('s1','SELECT pg_promote(true,10)')=='t'
        async def fence_candidate(owner,epoch):
            if owner!='s1' or epoch!=lease.token:return False
            docker('stop','-t','5',names['s1'])
            return json.loads(docker('inspect',names['s1']).stdout)[0]['State']['Running'] is False
        controller=PromotionController(PG(),current,fenced,acknowledged_lsn=acknowledged,fence_candidate=fence_candidate)
        try:await controller.promote('s1','primary',lease.token,required)
        except HAError:evidence['unfenced_primary_denied']=True
        else:raise RuntimeError('unfenced promotion allowed')
        docker('stop','-t','5',names['s4']);docker('stop','-t','5',names['primary'])
        evidence['two_node_loss']=['primary','s4'];evidence['durable_required_lsn']=required;evidence['dcs_token']=lease.token
        evidence['promotion']=await controller.promote('s1','primary',lease.token,required)
        for role in ('s2','s3'):
            sql(role,"ALTER SYSTEM SET primary_conninfo='host="+names['s1']+" user=postgres application_name="+role+"'")
            sql(role,'SELECT pg_reload_conf()')
        sql('s1',"ALTER SYSTEM SET synchronous_standby_names='ANY 2 (s2,s3)'");sql('s1','SELECT pg_reload_conf()')
        for _ in range(100):
            if sql('s1',"SELECT count(*) FROM pg_stat_replication WHERE state='streaming'")=='2':break
            await asyncio.sleep(.1)
        else:raise RuntimeError('survivors did not follow promoted writer')
        sql('s1',"INSERT INTO ha_probe VALUES(41,'two-node-loss-recovered')")
        evidence['application_rows']=sql('s1','SELECT string_agg(id::text,\',\' ORDER BY id) FROM ha_probe')
        evidence['fence_still_valid']=await fenced('primary',lease.token)
        evidence['dcs_still_valid']=await current('s1',lease.token)
        await authority.release(lease)
        try:await controller.supervise_writer('s1',lease.token,asyncio.Event(),interval=.05)
        except HAError:evidence['released_lease_fenced_writer']=json.loads(docker('inspect',names['s1']).stdout)[0]['State']['Running'] is False
        else:raise RuntimeError('writer survived DCS lease release')
        evidence['system_identifier']=cluster;evidence['result']='PASS_OWNED_CLOUD_GUARDED_PROMOTION_TWO_NODE_LOSS'
        save()
    except Exception as exc:
        evidence['error']=str(exc);save();raise
    finally:
        if lease is not None:
            # End disposable experiment with no writer depending on a released lease.
            docker('stop','-t','5',names['s1'])
            await authority.release(lease)
        await client.aclose()
    print(json.dumps(evidence,indent=2))

if __name__=='__main__':asyncio.run(main())
