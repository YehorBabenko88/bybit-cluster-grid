"""Deterministic LAB reservation/attempt model, NOT a runtime grant or store.

No imports create sockets, files, timers, tasks or database connections. Actors,
clock, transport closure and measurements are modeled inputs. A future reviewed
adapter must supply existing Grid authority/authentication and durable debits.
Reservation issuance does not prove actual transfer bandwidth: delayed FIRST
spend of previously unused receipts is an open P1, not solved by single use.
"""
import copy,json

NODES=('LS5','PC1','PC2','PC3','PC4','LS7')
MIB=1024*1024
CAPABILITIES={
 'grid':frozenset(('history_get','dataset_transfer','peer_sync','bybit_live_get','ws_connect','heartbeat')),
 'unified-system':frozenset(('health','ssh_control','github_fetch','module_update','peer_sync')),
 'strattester':frozenset(('dataset_transfer',)),
 'math':frozenset(('dataset_transfer',)),
 'meta_analyse':frozenset(('dataset_transfer',)),
 'terminan':frozenset(('health',)),
}
HIGH=frozenset(('bybit_live_get','ws_connect','heartbeat','health','ssh_control'))
HTTP=frozenset(('history_get','bybit_live_get'))
CENTRAL_ONLY=frozenset(('ssh_control','github_fetch','module_update'))
MEASURES=frozenset(('dns_ms','dns_failed','gateway_ms','https_ms','packet_loss_permille','tcp_failed','bybit_failed','interface_permille'))
SCHEMA='grid.lab.network-budget-model.v1'

def need(ok,reason='NETWORK_BUDGET_MODEL_REJECTED'):
 if not ok:raise ValueError(reason)

def integer(value,minimum=0,maximum=2**53-1):return type(value) is int and minimum<=value<=maximum

def _operation(node,module,operation):
 need(type(node) is str and node in NODES and type(module) is str and module in CAPABILITIES)
 need(type(operation) is str and operation in CAPABILITIES[module])
 need(operation!='ws_connect' or node=='LS5')
 need(operation not in CENTRAL_ONLY or node=='LS5')
 return 'HIGH' if operation in HIGH else 'LOW'

def _measurement(value):
 need(type(value) is dict and set(value)==MEASURES)
 for key in ('dns_failed','tcp_failed','bybit_failed'):need(type(value[key]) is bool)
 for key in ('dns_ms','gateway_ms','https_ms'):need(integer(value[key],0,600000))
 for key in ('packet_loss_permille','interface_permille'):need(integer(value[key],0,1000))
 return (value['dns_failed'] or value['tcp_failed'] or value['bybit_failed']
  or value['dns_ms']>=2000 or value['gateway_ms']>=500 or value['https_ms']>=3000
  or value['packet_loss_permille']>=100 or value['interface_permille']>=900)


class BudgetModel:
 def __init__(self,*,now_ms=0):
  need(integer(now_ms))
  self._s=dict(schema=SCHEMA,clock_ms=now_ms,clock_fault=False,authority=True,
   research_units=0,http_units=0,ws_units=0,high_units={node:0 for node in NODES},
   http_cooldown_ms=0,pressure='NORMAL',bad_count=0,good_count=0,
   sequences={},pending=[],connections={},receipts={},permit_sequence=0,
   attempts={'http':0,'ws':0},charged={'research':0,'high':0},observations=[])

 def _advance(self,now_ms):
  need(integer(now_ms));s=self._s
  if now_ms<s['clock_ms']:s['clock_fault']=True
  if s['clock_fault']:return False
  elapsed=min(now_ms-s['clock_ms'],1000);s['clock_ms']=now_ms
  if s['authority']:
   rate=MIB if s['pressure']=='NORMAL' else MIB//4 if s['pressure']=='RECOVERING' else 0
   s['research_units']=min(2*MIB*1000,s['research_units']+elapsed*rate)
   s['http_units']=min(1000,s['http_units']+elapsed*5)
   s['ws_units']=min(60000,s['ws_units']+elapsed*20)
   for node in NODES:s['high_units'][node]=min(65536*1000,s['high_units'][node]+elapsed*65536)
  for permit in s['connections'].values():
   if now_ms>=permit['deadline_ms']:permit['uncertain']=True
  return True

 def _ticket(self,item,now_ms):
  need(self._advance(now_ms),'CLOCK_FAULT');s=self._s
  actor=item['node']+'/'+item['module'];ticket=actor+'/'+str(item['sequence']);item=dict(item,id=ticket)
  candidates=[*s['pending'],*(x['request'] for x in s['connections'].values()),*(x['request'] for x in s['receipts'].values())]
  old=next((x for x in candidates if x['id']==ticket),None)
  if old is not None:need(old==item,'REPLAY_MISMATCH');return ticket
  need(item['sequence']==s['sequences'].get(actor,0)+1,'SEQUENCE_REJECTED')
  priority=item['priority'];node=item['node']
  need(len(s['pending'])<128,'BACKPRESSURE')
  need(sum(x['priority']=='LOW' for x in s['pending'])<96 or priority=='HIGH','BACKPRESSURE')
  need(sum(x['node']==node and x['priority']==priority for x in s['pending'])<(8 if priority=='HIGH' else 16),'BACKPRESSURE')
  s['pending'].append(item);s['sequences'][actor]=item['sequence'];return ticket

 def open(self,node,module,operation,sequence,*,now_ms):
  priority=_operation(node,module,operation);need(integer(sequence,1))
  return self._ticket(dict(node=node,module=module,operation=operation,bytes=0,sequence=sequence,
   priority=priority,kind='OPEN',connection=None),now_ms)

 def read(self,node,module,connection,requested_bytes,sequence,*,now_ms):
  need(type(connection) is str and connection in self._s['connections'])
  owner=self._s['connections'][connection]['request'];need((node,module)==(owner['node'],owner['module']))
  need(integer(requested_bytes,1,65536) and integer(sequence,1))
  return self._ticket(dict(node=node,module=module,operation=owner['operation'],bytes=requested_bytes,
   sequence=sequence,priority=owner['priority'],kind='READ',connection=connection),now_ms)

 def grant(self,*,now_ms):
  if not self._advance(now_ms):return None
  s=self._s
  for item in sorted(s['pending'],key=lambda x:x['priority']!='HIGH'):
   high=item['priority']=='HIGH';operation=item['operation'];node=item['node'];size=item['bytes']
   if not high and (not s['authority'] or s['pressure']=='DEGRADED'):continue
   if item['kind']=='OPEN':
    if not s['authority']:continue
    protocol='WS' if operation=='ws_connect' else 'HTTP'
    active=[x for x in s['connections'].values() if x['protocol']==protocol]
    if protocol=='WS':
     if len(active)>=3 or s['ws_units']<60000:continue
    else:
     if len(active)>=4 or not high and sum(x['priority']=='LOW' for x in active)>=2:continue
     if (operation in HTTP and now_ms<s['http_cooldown_ms']) or s['http_units']<1000:continue
    if protocol=='WS':s['ws_units']-=60000;s['attempts']['ws']+=1
    else:s['http_units']-=1000;s['attempts']['http']+=1
    s['permit_sequence']+=1;connection='connection/'+str(s['permit_sequence'])
    s['connections'][connection]=dict(id=connection,protocol=protocol,priority=item['priority'],
     issued_ms=now_ms,deadline_ms=now_ms+5000,uncertain=False,request=copy.deepcopy(item))
   else:
    connection=item['connection'];held=s['connections'].get(connection)
    if held is None or held['uncertain']:continue
    if operation in HTTP and now_ms<s['http_cooldown_ms']:continue
    units=s['high_units'][node] if high else s['research_units']
    if units<size*1000:continue
    if high:s['high_units'][node]-=size*1000;s['charged']['high']+=size
    else:s['research_units']-=size*1000;s['charged']['research']+=size
   receipt=dict(ticket=item['id'],connection=connection,kind=item['kind'],operation=operation,
    bytes=size,issued_ms=now_ms,request=copy.deepcopy(item))
   s['receipts'][node+'/'+item['module']]=receipt;s['pending'].remove(item)
   return copy.deepcopy(receipt)
  return None

 def close(self,connection,*,confirmed,now_ms):
  need(type(connection) is str and type(confirmed) is bool);self._advance(now_ms)
  need(connection in self._s['connections'])
  if confirmed:
   del self._s['connections'][connection]
   self._s['pending']=[x for x in self._s['pending'] if x['connection']!=connection]
  else:self._s['connections'][connection]['uncertain']=True

 def renew(self,connection,*,confirmed_open,now_ms):
  need(type(confirmed_open) is bool);self._advance(now_ms)
  need(connection in self._s['connections']);held=self._s['connections'][connection]
  need(not held['uncertain'] and confirmed_open is True,'TRANSPORT_UNCERTAIN')
  held['deadline_ms']=now_ms+5000

 def set_authority(self,available,*,now_ms):
  need(type(available) is bool);self._advance(now_ms);s=self._s
  if available and not s['authority']:
   s.update(pressure='RECOVERING',good_count=0,bad_count=0,research_units=0,http_units=0,ws_units=0)
   s['high_units']={node:0 for node in NODES}
  s['authority']=available

 def feedback(self,status,*,now_ms,retry_after_ms=0,reset_ms=None):
  need(type(status) is int and status in (403,429));need(integer(retry_after_ms,0,86400000))
  need(reset_ms is None or integer(reset_ms,now_ms,now_ms+86400000))
  self._advance(now_ms);duration=600000 if status==403 else max(60000,retry_after_ms)
  self._s['http_cooldown_ms']=max(self._s['http_cooldown_ms'],now_ms+duration,reset_ms or 0)
  self._s['http_units']=0
  if status==403:
   # The future adapter must terminate these actual owned HTTP transports.
   # Merely observing a block never proves closure or frees a connection slot.
   for held in self._s['connections'].values():
    if held['request']['operation'] in HTTP:held['uncertain']=True

 def observe(self,value,*,now_ms):
  bad=_measurement(value);self._advance(now_ms);s=self._s
  s['observations'].append(dict(at_ms=now_ms,measurement=copy.deepcopy(value),bad=bad,
   queued=len(s['pending']),active_bulk=sum(p['priority']=='LOW' for p in s['connections'].values())))
  s['observations']=s['observations'][-64:]
  if bad:
   s['bad_count']=min(3,s['bad_count']+1);s['good_count']=0
   if s['bad_count']>=3 or s['pressure']!='NORMAL':s.update(pressure='DEGRADED',research_units=0)
  else:
   s['bad_count']=0;s['good_count']=min(10,s['good_count']+1)
   if s['good_count']==10 and s['pressure']=='DEGRADED':s.update(pressure='RECOVERING',good_count=0)
   elif s['good_count']==10 and s['pressure']=='RECOVERING':s.update(pressure='NORMAL',good_count=0)

 def snapshot(self):return copy.deepcopy(self._s)

 def dumps(self):
  self._validate(self._s)
  raw=json.dumps(self._s,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
  need(len(raw)<=131072);return raw

 @classmethod
 def restore(cls,raw,*,now_ms):
  need(type(raw) is bytes and len(raw)<=131072 and integer(now_ms))
  def unique(pairs):
   result={}
   for key,value in pairs:need(key not in result);result[key]=value
   return result
  try:value=json.loads(raw,object_pairs_hook=unique)
  except (ValueError,RecursionError):raise ValueError('NETWORK_BUDGET_MODEL_REJECTED') from None
  try:cls._validate(value)
  except (KeyError,TypeError,AttributeError,RecursionError,OverflowError):raise ValueError('NETWORK_BUDGET_MODEL_REJECTED') from None
  result=cls(now_ms=now_ms);result._s=value
  # Deserialization is not earning elapsed time. Existing credit remains bounded.
  if now_ms<value['clock_ms']:value['clock_fault']=True
  else:value['clock_ms']=now_ms
  return result

 @staticmethod
 def _validate(s):
  template=BudgetModel()._s;need(type(s) is dict and set(s)==set(template) and s['schema']==SCHEMA)
  for key in ('clock_ms','http_cooldown_ms','permit_sequence'):need(integer(s[key]))
  for key in ('clock_fault','authority'):need(type(s[key]) is bool)
  for key,cap in (('research_units',2*MIB*1000),('http_units',1000),('ws_units',60000),('bad_count',3),('good_count',10)):need(integer(s[key],0,cap))
  need(s['pressure'] in ('NORMAL','DEGRADED','RECOVERING'))
  need(type(s['high_units']) is dict and set(s['high_units'])==set(NODES) and all(integer(x,0,65536*1000) for x in s['high_units'].values()))
  for key in ('attempts','charged'):
   need(type(s[key]) is dict and set(s[key])==set(template[key]) and all(integer(x) for x in s[key].values()))
  need(type(s['sequences']) is dict and len(s['sequences'])<=len(NODES)*len(CAPABILITIES))
  for actor,seq in s['sequences'].items():
   need(type(actor) is str and len(actor)<=64 and actor.count('/')==1)
   node,module=actor.split('/');need(node in NODES and module in CAPABILITIES and integer(seq,1))
  need(type(s['pending']) is list and len(s['pending'])<=128 and type(s['connections']) is dict and len(s['connections'])<=7)
  need(type(s['receipts']) is dict and len(s['receipts'])<=len(NODES)*len(CAPABILITIES))
  def request(item):
   need(type(item) is dict and set(item)=={'id','node','module','operation','bytes','sequence','priority','kind','connection'})
   priority=_operation(item['node'],item['module'],item['operation']);need(item['priority']==priority)
   actor=item['node']+'/'+item['module'];need(integer(item['sequence'],1) and item['sequence']<=s['sequences'].get(actor,0))
   need(item['id']==actor+'/'+str(item['sequence']))
   need(item['kind'] in ('OPEN','READ'))
   if item['kind']=='OPEN':need(item['bytes']==0 and type(item['bytes']) is int and item['connection'] is None)
   else:need(integer(item['bytes'],1,65536) and type(item['connection']) is str and item['connection'].startswith('connection/'))
  ids=[]
  for item in s['pending']:
   request(item);need(item['id'] not in ids);ids.append(item['id'])
   if item['kind']=='READ':
    held=s['connections'].get(item['connection']);need(type(held) is dict and type(held.get('request')) is dict)
    owner=held['request'];need(all(item[k]==owner[k] for k in ('node','module','operation','priority')))
  opened=[]
  for ident,p in s['connections'].items():
   need(type(p) is dict and set(p)=={'id','protocol','priority','issued_ms','deadline_ms','uncertain','request'})
   need(type(ident) is str and ident.startswith('connection/') and ident[11:].isascii() and ident[11:].isdigit())
   need(integer(int(ident[11:]),1,s['permit_sequence']) and ident=='connection/'+str(int(ident[11:])) and p['id']==ident)
   request(p['request']);need(p['request']['kind']=='OPEN' and p['priority']==p['request']['priority'])
   need(p['request']['id'] not in opened and p['request']['id'] not in ids);opened.append(p['request']['id'])
   need(p['protocol']==('WS' if p['request']['operation']=='ws_connect' else 'HTTP'))
   need(integer(p['issued_ms']) and integer(p['deadline_ms'],p['issued_ms']+1,s['clock_ms']+5000) and p['issued_ms']<=s['clock_ms'] and type(p['uncertain']) is bool)
  for actor,receipt in s['receipts'].items():
   need(type(receipt) is dict and set(receipt)=={'ticket','connection','kind','operation','bytes','issued_ms','request'})
   request(receipt['request']);item=receipt['request'];need(actor==item['node']+'/'+item['module'])
   need(item['id'] not in ids)
   need(receipt['ticket']==item['id'] and all(receipt[k]==item[k] for k in ('kind','operation','bytes')))
   need(type(receipt['connection']) is str and receipt['connection'].startswith('connection/') and integer(receipt['issued_ms'],0,s['clock_ms']))
   if item['kind']=='READ':need(receipt['connection']==item['connection'])
   elif receipt['connection'] in s['connections']:need(s['connections'][receipt['connection']]['request']==item)
  http=[x for x in s['connections'].values() if x['protocol']=='HTTP']
  need(len(http)<=4 and sum(x['priority']=='LOW' for x in http)<=2)
  need(sum(x['protocol']=='WS' for x in s['connections'].values())<=3)
  need(s['permit_sequence']==s['attempts']['http']+s['attempts']['ws'])
  need(s['attempts']['http']>=len(http) and s['attempts']['ws']>=sum(x['protocol']=='WS' for x in s['connections'].values()))
  need(sum(x['priority']=='LOW' for x in s['pending'])<=96)
  for node in NODES:
   for priority,cap in (('HIGH',8),('LOW',16)):need(sum(x['node']==node and x['priority']==priority for x in s['pending'])<=cap)
  need(type(s['observations']) is list and len(s['observations'])<=64)
  for item in s['observations']:
   need(type(item) is dict and set(item)=={'at_ms','measurement','bad','queued','active_bulk'})
   need(integer(item['at_ms']) and item['at_ms']<=s['clock_ms'] and type(item['bad']) is bool and item['bad']==_measurement(item['measurement']))
   need(integer(item['queued'],0,128) and integer(item['active_bulk'],0,2))
