"""Offline correlation of measured endpoints, never a WFP or owner attestation."""
import re

def need(value):
    if not value:raise ValueError('TRANSPORT_PROVENANCE_REFUSED')

def integer(value,low,high):return type(value) is int and low<=value<=high

def validate_transport(parent,child,head,run,attempt):
    need(type(parent) is dict and set(parent)=={'schema','head','run_id','attempt','nonce','parent_pid','child_pid','endpoints'})
    need(type(parent['schema']) is int and parent['schema']==1 and (parent['head'],parent['run_id'],parent['attempt'])==(head,run,attempt))
    need(type(parent['nonce']) is str and re.fullmatch('[0-9a-f]{32}',parent['nonce']))
    need(integer(parent['parent_pid'],1,2**32-1) and integer(parent['child_pid'],1,2**32-1) and parent['parent_pid']!=parent['child_pid'])
    need(type(parent['endpoints']) is list and len(parent['endpoints'])==4 and type(child) is list and len(child)==4)
    ports=set()
    for endpoint,row,(family,mode) in zip(parent['endpoints'],child,[(f,m) for f in (4,6) for m in ('listener','bound-not-listening')]):
        host='127.0.0.1' if family==4 else '::1'
        need(type(endpoint) is dict and set(endpoint)=={'family','host','port','mode','ready_utc_ms','host_control'})
        need(type(endpoint['family']) is int and endpoint['family']==family and endpoint['host']==host and endpoint['mode']==mode)
        need(integer(endpoint['port'],1,65535) and (family,endpoint['port']) not in ports);ports.add((family,endpoint['port']))
        need(integer(endpoint['ready_utc_ms'],1,2**53) and endpoint['host_control']==('SUCCESS' if mode=='listener' else 'WSA10061'))
        need(type(row) is dict and set(row)=={'nonce','parent_pid','pid','family','host','port','mode','started_utc_ms','elapsed_ns','local_host','local_port','kind','winerror','errno'})
        need(row['nonce']==parent['nonce'] and integer(row['parent_pid'],1,2**32-1) and row['parent_pid']==parent['parent_pid'] and integer(row['pid'],1,2**32-1) and row['pid']==parent['child_pid'])
        need(type(row['family']) is int and row['family']==family and integer(row['port'],1,65535) and row['port']==endpoint['port'] and row['host']==host and row['mode']==mode)
        need(integer(row['started_utc_ms'],endpoint['ready_utc_ms'],endpoint['ready_utc_ms']+120000) and integer(row['elapsed_ns'],0,10000000000))
        need(row['local_host'] in (host,'0.0.0.0' if family==4 else '::') and integer(row['local_port'],0,65535))
        need(row['kind'] in ('SUCCESS','TIMEOUT','REFUSED','PERMISSION','OSERROR'))
        for key in ('winerror','errno'):need(row[key] is None or integer(row[key],-2**31,2**32-1))
        if row['kind']=='SUCCESS':need(row['winerror'] is None and row['errno'] is None)
    return dict(status='OBSERVED_NOT_ATTESTED',policy_cause='UNKNOWN',host_verified=False,execute_authorized=False,cleanup_authorized=False)
