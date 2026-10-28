"""Offline consistency of S0 evidence; hashes do not independently attest a host."""
import hashlib,io,json,re,zipfile
import xml.etree.ElementTree as E
from pathlib import Path
from .policy import need,canonical,load_json
from .storage import read_small,write_new
from .protocol import MarketState
from .wire import validate_summary
PUBLIC={'events.jsonl','market.jsonl','claim.json','summary.json','results.xml','prepared.json'}

def verify_chain(raw,context):
 need(type(raw) is bytes and len(raw)<=67108864 and raw.endswith(b'\n') and raw,'S0_JOURNAL_INTERRUPTED')
 previous='0'*64;rows=[]
 for seq,line in enumerate(raw.splitlines(),1):
  need(seq<=1000000)
  row=load_json(line);need(set(row)=={'seq','previous','payload','sha256'} and type(row['seq']) is int and row['seq']==seq and row['previous']==previous)
  need(row['sha256']==hashlib.sha256(canonical({k:row[k] for k in ('seq','previous','payload')})).hexdigest())
  p=row['payload'];need(type(p) is dict and set(p)==set(context)|{'kind','utc_ms','value'} and all(p[k]==v for k,v in context.items()) and type(p['utc_ms']) is int and type(p['kind']) is str and len(p['kind'])<=80 and type(p['value']) is dict)
  previous=row['sha256'];rows.append(p)
 return rows

def verify_evidence(root,context,pin):
 idx=load_json(read_small(root,'sha256.json'));need(set(idx)=={'schema',*context,'package_sha256','files','g1_execute','cleanup_authorized'})
 need(type(idx['schema']) is int and idx['schema']==1 and all(idx[k]==v for k,v in context.items()) and idx['package_sha256']==pin and idx['g1_execute'] is False and idx['cleanup_authorized'] is False)
 files=idx['files'];need(type(files) is dict and {'events.jsonl','claim.json','summary.json','results.xml'}<=set(files)<=PUBLIC)
 for n,h in files.items():need(hashlib.sha256(read_small(root,n,67108864)).hexdigest()==h,'S0_EVIDENCE_HASH_BLOCKED')
 summary=load_json(read_small(root,'summary.json'));need(all(summary[k]==v for k,v in context.items()) and summary['package_sha256']==pin and summary['scope']=='S0_PUBLIC_ONLY_NOT_GRID_ACCEPTANCE' and summary['g1_execute'] is False and summary['cleanup_authorized'] is False and summary['physical_sid_acl']=='0/10 NOT_RUN' and summary['deployment']=='NO-GO')
 events=verify_chain(read_small(root,'events.jsonl',8388608),context);need(events[0]['kind']=='started' and events[-1]['kind']=='finished')
 result=summary['result'];need(events[-1]['value']==dict(result=result,error=summary['error']))
 stats=result.get('stats')
 if stats:validate_summary(stats)
 if context['role']=='PC4':
  need('market.jsonl' in files);state=MarketState();connected=0
  market_raw=read_small(root,'market.jsonl',67108864);need(market_raw or summary['status']=='BLOCKED_OR_PARTIAL')
  for row in (verify_chain(market_raw,context) if market_raw else []):
   if row['kind']=='connection':
    connected+=1;need(row['value']=={'index':connected})
    if connected>1:state.reconnect()
   else:need(row['kind']=='bybit-public' and connected>0);state.ingest(row['value'],row['utc_ms'])
  if stats is not None:need(stats==state.summary(),'S0_COUNTER_REPLAY_MISMATCH')
  else:need(summary['status']=='BLOCKED_OR_PARTIAL' and summary['error'] is not None)
 accepted=summary['status']=='PUBLIC_SMOKE_OBSERVED'
 need(summary['status'] in ('PUBLIC_SMOKE_OBSERVED','BLOCKED_OR_PARTIAL'))
 if accepted:need(summary['error'] is None and result.get('reason')=='WINDOW_COMPLETE' and result.get('elapsed_ms',0)>=240000 and result.get('registered') is True and result.get('final') is True and result.get('heartbeats',0)>=3 and stats['trade_count']>0 and stats['book_updates']>0)
 xml=read_small(root,'results.xml');need(b'<!DOCTYPE' not in xml.upper() and b'<!ENTITY' not in xml.upper())
 suite=E.fromstring(xml);need(suite.tag=='testsuite' and suite.get('head')==context['head'] and suite.get('run_id')==context['run_id'] and suite.get('tests')=='1' and suite.get('errors')=='0' and suite.get('skipped')=='0' and suite.get('failures')==('0' if accepted else '1'))
 need(len(list(suite.iter('testcase')))==1 and len(list(suite.iter('failure')))==(0 if accepted else 1))
 return dict(status='S0_EVIDENCE_CONSISTENT_NOT_ATTESTED',observation=summary['status'],**context,files=sorted(files),g1_execute=False,cleanup=False)

def archive_evidence(root,context,pin):
 result=verify_evidence(root,context,pin);index=load_json(read_small(root,'sha256.json'));buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,'w',compression=zipfile.ZIP_DEFLATED) as z:
  for n in sorted(set(index['files'])|{'sha256.json'}):
   need(n in PUBLIC|{'sha256.json'});z.writestr(n,read_small(root,n,67108864))
 raw=buffer.getvalue();need(len(raw)<=67108864);write_new_archive(root,raw)
 return dict(result,archive='s0-evidence.zip',sha256=hashlib.sha256(raw).hexdigest())

def write_new_archive(root,raw):
 # Evidence export only, never replacement or removal. Keys/config never included.
 import os
 fd=os.open(Path(root)/'s0-evidence.zip',os.O_CREAT|os.O_EXCL|os.O_WRONLY|getattr(os,'O_BINARY',0),0o600)
 with os.fdopen(fd,'wb') as f:need(f.write(raw)==len(raw));f.flush();os.fsync(f.fileno())
