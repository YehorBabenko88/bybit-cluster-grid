#!/usr/bin/env python3
"""Dedicated disposable Docker PG18 replication/PITR lab; never accepts a DSN.

Resources are retained under a unique mission3 label for evidence/review. No
existing container, database, network or volume is removed or reconfigured.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import time
import uuid

IMAGE='postgres@sha256:979bccfde35445db618c65107d27d08c6c21339d8dc3ad4c830c6633947be0e4'
ENV={k:v for k,v in os.environ.items() if k not in ('DOCKER_HOST','DOCKER_CONTEXT','DOCKER_TLS','DOCKER_TLS_VERIFY','DOCKER_CERT_PATH')}

def docker(*args, timeout=60, check=True):
    result=subprocess.run(['docker','--host=unix:///var/run/docker.sock',*args],env=ENV,text=True,capture_output=True,timeout=timeout)
    if check and result.returncode:raise RuntimeError('Docker lab operation failed: '+result.stderr[-2000:])
    return result

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--standbys',type=int,choices=(2,4),default=4);args=parser.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    prefix='mission3-ha-'+uuid.uuid4().hex[:10];net=prefix+'-net';volume=prefix+'-archive'
    standbys=['s'+str(i) for i in range(1,args.standbys+1)];required_sync=args.standbys//2
    names={role:prefix+'-'+role for role in ['primary',*standbys,'restore']}
    evidence={'schema':'grid.pg18.cloud-lab.v1','image':IMAGE,'prefix':prefix,'names':names,'physical':'NOT_RUN','production':'NO_GO','result':'INCOMPLETE','automatic_failover':'NOT_RUN_DCS_REQUIRED','synchronous_standbys':required_sync,'standby_count':args.standbys}
    def save(): (out/'evidence.json').write_text(json.dumps(evidence,indent=2))
    save()
    def sql(role, query, check=True):return docker('exec',names[role],'psql','-X','-A','-t','-v','ON_ERROR_STOP=1','-U','postgres','-d','postgres','-c',query,check=check).stdout.strip()
    def ready(role):
        for _ in range(120):
            result=docker('exec',names[role],'pg_isready','-h','127.0.0.1','-U','postgres',check=False)
            if result.returncode==0:return
            time.sleep(.25)
        raise RuntimeError('database not ready: '+role)
    def create(role, command=None):
        cmd=['run','-d','--name',names[role],'--label','codex.task=mission3-pg-ha','--label','codex.lab='+prefix,'--network',net,'--mount','type=volume,src='+volume+',dst=/archive','-e','PGDATA=/var/lib/postgresql/data/pgdata','-e','POSTGRES_HOST_AUTH_METHOD=trust',IMAGE]
        cmd.extend(command or ['postgres','-c','wal_level=replica','-c','max_wal_senders=10','-c','archive_mode=on','-c',"archive_command=test -f /archive/%f || cp %p /archive/%f",'-c','archive_timeout=1s'])
        docker(*cmd);ready(role)
    try:
        docker('image','inspect',IMAGE)
        docker('network','create','--internal','--label','codex.task=mission3-pg-ha',net)
        docker('volume','create','--label','codex.task=mission3-pg-ha',volume)
        create('primary')
        evidence['server_version']=sql('primary','SHOW server_version')
        if not evidence['server_version'].startswith('18.'):
            raise RuntimeError('PG18 image identity/version mismatch')
        docker('exec','-u','0',names['primary'],'sh','-c','chown postgres:postgres /archive && chmod 700 /archive')
        docker('exec','-u','postgres',names['primary'],'sh','-c',"echo 'host replication postgres 0.0.0.0/0 trust' >> \"$PGDATA/pg_hba.conf\"")
        sql('primary','SELECT pg_reload_conf()')
        for role in standbys:
            inner=('if [ ! -f "$PGDATA/PG_VERSION" ]; then pg_basebackup -h '+names['primary']+' -U postgres -D "$PGDATA" -R -X stream -c fast; '
                   +'echo "primary_conninfo = \'host='+names['primary']+' user=postgres application_name='+role+'\'" >> "$PGDATA/postgresql.auto.conf"; fi; exec postgres')
            bootstrap='mkdir -p "$PGDATA"; chown postgres:postgres "$PGDATA"; chmod 700 "$PGDATA"; exec gosu postgres bash -ec '+shlex.quote(inner)
            create(role,['bash','-ec',bootstrap])
        for _ in range(120):
            if sql('primary',"SELECT count(*) FROM pg_stat_replication WHERE state='streaming'")==str(args.standbys):break
            time.sleep(.25)
        else:raise RuntimeError('standbys did not stream')
        sql('primary',"ALTER SYSTEM SET synchronous_standby_names='ANY "+str(required_sync)+" ("+','.join(standbys)+")'")
        sql('primary',"ALTER SYSTEM SET synchronous_commit='remote_apply'");sql('primary','SELECT pg_reload_conf()')
        sql('primary','CREATE TABLE ha_probe(id integer PRIMARY KEY, value text); INSERT INTO ha_probe VALUES(1,\'baseline\')')
        evidence['replication']=json.loads(sql('primary',"SELECT json_agg(json_build_object('name',application_name,'state',state,'sync',sync_state,'lag_bytes',pg_wal_lsn_diff(pg_current_wal_lsn(),replay_lsn))) FROM pg_stat_replication"))
        docker('exec','-u','postgres',names['primary'],'pg_basebackup','-U','postgres','-D','/archive/base','-X','stream','-c','fast')
        verified=docker('exec','-u','postgres',names['primary'],'pg_verifybackup','/archive/base').stdout.strip();evidence['backup_verification']=verified;save()
        sql('primary',"INSERT INTO ha_probe VALUES(2,'before-target')")
        target=sql('primary',"SELECT pg_create_restore_point('mission3_restore_target')")
        sql('primary',"INSERT INTO ha_probe VALUES(3,'after-target')")
        sql('primary','SELECT pg_switch_wal()')
        for _ in range(120):
            count=sql('primary','SELECT archived_count FROM pg_stat_archiver')
            if int(count)>=2:break
            time.sleep(.25)
        restore='mkdir -p "$PGDATA"; cp -a /archive/base/. "$PGDATA/"; rm -f "$PGDATA/standby.signal"; touch "$PGDATA/recovery.signal"; chown -R postgres:postgres "$PGDATA"; chmod 700 "$PGDATA"; exec gosu postgres postgres -c restore_command="cp /archive/%f %p" -c recovery_target_name=mission3_restore_target -c recovery_target_action=promote -c archive_mode=off'
        create('restore',['bash','-ec',restore])
        rows=sql('restore','SELECT string_agg(id::text,\',\' ORDER BY id) FROM ha_probe')
        if rows!='1,2':raise RuntimeError('PITR application rows mismatch: '+rows)
        evidence['pitr']={'target_lsn':target,'restored_ids':rows,'after_target_absent':True,'in_recovery':sql('restore','SELECT pg_is_in_recovery()')};save()
        for lost,role in enumerate(reversed(standbys),1):
            docker('stop','-t','5',names[role])
            if len(standbys)-lost >= required_sync:
                sql('primary',"SET statement_timeout='5s'; INSERT INTO ha_probe VALUES("+str(10+lost)+",'standby-loss')")
                evidence['loss_'+str(lost)+'_standbys']='COMMIT_CONFIRMED'
            else:
                blocked=docker('exec',names['primary'],'timeout','4','psql','-X','-v','ON_ERROR_STOP=1','-U','postgres','-c',"SET statement_timeout='1500ms'; INSERT INTO ha_probe VALUES(20,'unacknowledged')",check=False)
                if blocked.returncode!=124:raise RuntimeError('insufficient synchronous standbys did not block commit')
                evidence['loss_'+str(lost)+'_standbys']='ACK_BLOCKED_TRANSACTION_OUTCOME_UNKNOWN_UNTIL_RECONCILED'
                break
        for role in standbys:
            docker('start',names[role]);ready(role)
        sql('primary',"SET statement_timeout='5s'; INSERT INTO ha_probe VALUES(30,'recovered')")
        evidence['recovery_after_standby_loss']='COMMIT_CONFIRMED'
        evidence['archive_files']=docker('exec',names['primary'],'find','/archive','-maxdepth','1','-type','f','-printf','%f\n').stdout.splitlines()
        evidence['result']='PASS_REPLICATION_PITR_STANDBY_LOSS';save()
    except Exception as exc:
        evidence['error']=str(exc);save();raise
    print(json.dumps(evidence,indent=2))

if __name__=='__main__':main()
