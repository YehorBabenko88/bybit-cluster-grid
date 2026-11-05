"""Virtual six-node, ten-symbol exercise. No real network/Windows observations."""
from .network_budget_model import BudgetModel,NODES

SYMBOLS=['BTCUSDT','ETHUSDT','SOLUSDT','XRPUSDT','BNBUSDT','DOGEUSDT','ADAUSDT','AVAXUSDT','LINKUSDT','DOTUSDT']

def _measurement(bad=False):
 return dict(dns_ms=2500 if bad else 10,dns_failed=False,gateway_ms=600 if bad else 10,
  https_ms=4000 if bad else 50,packet_loss_permille=200 if bad else 0,
  tcp_failed=bad,bybit_failed=False,interface_permille=950 if bad else 100)

def simulate():
 """Model 600,000 ms without sleeping; serialized restart is not actual storage."""
 budget=BudgetModel(now_ms=0);sequence={};history={node:set() for node in NODES}
 report=dict(qualification='SYNTHETIC_MODEL_ONLY_NOT_RUNTIME_ACCEPTANCE',virtual_duration_ms=600000,
  real_network_calls=0,nodes=list(NODES),symbols=list(SYMBOLS),max_pending=0,max_http=0,max_bulk=0,max_ws=0,
  reserved_bytes={'research':0,'high':0},byte_basis='RESERVED_CHARGED_SYNTHETIC_BYTES_NOT_OBSERVED_TRANSFER',
  actual_transfer_bound='NOT_PROVEN',open_p1=['DELAYED_FIRST_SPEND_CAN_ACCUMULATE_UNUSED_READ_CREDITS'],
  history_symbols_by_node={},phases={},restart_preserved_credit=False,
  windows_configuration_changes=[],state_bytes_max=0,http_attempts=0,ws_attempts=0)
 def enqueue(node,module,operation,now,connection=None,size=0):
  actor=node+'/'+module;seq=sequence.get(actor,0)+1
  try:
   if connection is None:budget.open(node,module,operation,seq,now_ms=now)
   else:budget.read(node,module,connection,size,seq,now_ms=now)
  except ValueError as error:
   if str(error)!='BACKPRESSURE':raise
   return False
  sequence[actor]=seq;return True
 def phase(now):
  if 120200<=now<180000:return 'degraded'
  if 210000<=now<270000:return 'ls5_down'
  if 330000<=now:return 'bybit_down'
  return 'normal_or_recovering'
 def pending_operation(state,node,module,operation):
  return any(x['node']==node and x['module']==module and x['operation']==operation and x['kind']=='OPEN' for x in state['pending'])
 for now in range(0,600001,100):
  label=phase(now);counter=report['phases'].setdefault(label,dict(research=0,high=0,live=0,http_opens=0,bybit_http_opens=0,ws_opens=0))
  if now==210000:budget.set_authority(False,now_ms=now)
  if now==270000:budget.set_authority(True,now_ms=now)
  if now==330000:
   budget.feedback(403,now_ms=now)
   for ident,held in budget.snapshot()['connections'].items():
    if held['protocol']=='WS':budget.close(ident,confirmed=True,now_ms=now)
  if now%1000==0:budget.observe(_measurement(120000<=now<180000),now_ms=now)
  if now in (120000,120100):budget.observe(_measurement(True),now_ms=now)
  if now==240000:
   before=budget.snapshot();raw=budget.dumps();budget=BudgetModel.restore(raw,now_ms=now)
   after=budget.snapshot();report['restart_preserved_credit']=all(before[k]==after[k] for k in ('research_units','high_units','http_units','ws_units','connections'))
  state=budget.snapshot()
  # Explicit modeled transport closure. Expiry alone never releases a slot.
  for ident,held in list(state['connections'].items()):
   request=held['request'];age=now-held['issued_ms']
   close=held['protocol']=='HTTP' and (request['priority']=='LOW' and age>=1000 or request['priority']=='HIGH' and age>=300)
   if close:budget.close(ident,confirmed=True,now_ms=now)
   elif not held['uncertain'] and held['deadline_ms']-now<=2000:
    budget.renew(ident,confirmed_open=True,now_ms=now)
  state=budget.snapshot();held=list(state['connections'].values())
  for node in NODES:
   if not any(x['request']['node']==node and x['request']['operation']=='history_get' for x in held) and not pending_operation(state,node,'grid','history_get'):
    enqueue(node,'grid','history_get',now)
  if not any(x['protocol']=='WS' for x in held) and not pending_operation(state,'LS5','grid','ws_connect'):
   enqueue('LS5','grid','ws_connect',now)
  if now%2000==0:
   for node in NODES:
    if not any(x['request']['node']==node and x['request']['operation']=='health' for x in held) and not pending_operation(state,node,'unified-system','health'):
     enqueue(node,'unified-system','health',now)
  state=budget.snapshot()
  for ident,connection in state['connections'].items():
   request=connection['request']
   if connection['uncertain'] or any(x['connection']==ident for x in state['pending']):continue
   size=2560 if connection['protocol']=='WS' else 65536 if request['priority']=='LOW' else 64
   enqueue(request['node'],request['module'],request['operation'],now,connection=ident,size=size)
  for _ in range(32):
   receipt=budget.grant(now_ms=now)
   if receipt is None:break
   if receipt['kind']=='OPEN':
    counter['ws_opens' if receipt['operation']=='ws_connect' else 'http_opens']+=1
    if receipt['operation'] in ('history_get','bybit_live_get'):counter['bybit_http_opens']+=1
    if receipt['operation']=='ws_connect' and now>=330000:
     # Synthetic upstream outage: the attempted handshake fails, its actual
     # modeled transport is confirmed drained, and no live payload is invented.
     budget.close(receipt['connection'],confirmed=True,now_ms=now)
   else:
    request=receipt['request'];lane='high' if request['priority']=='HIGH' else 'research'
    report['reserved_bytes'][lane]+=receipt['bytes'];counter[lane]+=receipt['bytes']
    if receipt['operation']=='ws_connect':counter['live']+=receipt['bytes']
    if lane=='research':
     node=request['node'];history[node].add(SYMBOLS[(request['sequence']-1)%10])
  state=budget.snapshot();connections=list(state['connections'].values());http=[x for x in connections if x['protocol']=='HTTP']
  report['max_pending']=max(report['max_pending'],len(state['pending']))
  report['max_http']=max(report['max_http'],len(http));report['max_bulk']=max(report['max_bulk'],sum(x['priority']=='LOW' for x in http))
  report['max_ws']=max(report['max_ws'],sum(x['protocol']=='WS' for x in connections))
  if now%10000==0:report['state_bytes_max']=max(report['state_bytes_max'],len(budget.dumps()))
 report['history_symbols_by_node']={node:[symbol for symbol in SYMBOLS if symbol in history[node]] for node in NODES}
 report['http_attempts']=state['attempts']['http'];report['ws_attempts']=state['attempts']['ws']
 report['final_pressure']=state['pressure'];report['final_http_cooldown_ms']=state['http_cooldown_ms']
 return report


if __name__=='__main__':
 import json
 print(json.dumps(simulate(),sort_keys=True,separators=(',',':')))
