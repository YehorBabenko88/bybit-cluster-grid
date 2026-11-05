"""Synthetic actors, clocks and transport state; no sockets or durable DB."""
import importlib,json
import pytest

def model(now=0):
 from grid.network_budget_model import BudgetModel
 return BudgetModel(now_ms=now)

def opened(b,*,node="PC1",op="history_get",seq=1,now=1000):
 b.open(node,"grid",op,seq,now_ms=0)
 result=None
 for at in range(1000,now+1,1000):result=b.grant(now_ms=at)
 assert result and result["kind"]=="OPEN"
 return result["connection"]

def test_open_spends_attempt_but_each_chunk_spends_only_bytes():
 b=model();conn=opened(b)
 assert b.snapshot()["attempts"]["http"]==1
 for seq in (2,3):
  b.read("PC1","grid",conn,65536,seq,now_ms=1000)
  permit=b.grant(now_ms=1000);assert permit["kind"]=="READ" and permit["bytes"]==65536
 assert b.snapshot()["attempts"]["http"]==1
 assert b.snapshot()["charged"]["research"]==131072
 assert len(b.snapshot()["connections"])==1

def test_cluster_http_four_and_bulk_two_without_automatic_expiry_reuse():
 b=model()
 for node in ("PC1","PC2","PC3"):b.open(node,"grid","history_get",1,now_ms=0)
 first=b.grant(now_ms=1000);second=b.grant(now_ms=2000)
 assert first and second and b.grant(now_ms=3000) is None
 for node in ("PC4","LS7"):b.open(node,"grid","bybit_live_get",1,now_ms=3000)
 assert b.grant(now_ms=4000) and b.grant(now_ms=5000)
 assert b.grant(now_ms=6000) is None and len(b.snapshot()["connections"])==4
 b.close(first["connection"],confirmed=False,now_ms=100000)
 reopened=type(b).restore(b.dumps(),now_ms=200000)
 assert reopened.grant(now_ms=201000) is None
 reopened.close(first["connection"],confirmed=True,now_ms=201000)
 assert reopened.grant(now_ms=202000)["operation"]=="history_get"

def test_websocket_attempts_shared_paced_and_max_three_aggregate_ls5_connections():
 b=model()
 for seq in range(1,5):b.open("LS5","grid","ws_connect",seq,now_ms=0)
 assert b.grant(now_ms=0) is None
 accepted=[]
 for t in range(1000,16001,1000):
  result=b.grant(now_ms=t)
  if result:accepted.append(t);b.renew(result["connection"],confirmed_open=True,now_ms=t)
 assert accepted==[3000,6000,9000]
 assert len(b.snapshot()["connections"])==3 and b.snapshot()["attempts"]["ws"]==3
 with pytest.raises(ValueError):b.open("PC1","grid","ws_connect",1,now_ms=16000)

def test_cold_restore_rollback_and_actor_replay_cannot_mint_or_duplicate():
 b=model();ticket=b.open("PC1","grid","history_get",1,now_ms=0)
 assert b.open("PC1","grid","history_get",1,now_ms=0)==ticket
 assert b.grant(now_ms=0) is None
 conn=b.grant(now_ms=1000)["connection"]
 b.read("PC1","grid",conn,1000,2,now_ms=1000);receipt=b.grant(now_ms=1000)
 assert b.read("PC1","grid",conn,1000,2,now_ms=1000)==receipt["ticket"]
 assert b.grant(now_ms=1000) is None
 before=b.snapshot();reopened=type(b).restore(b.dumps(),now_ms=900000)
 assert reopened.snapshot()["research_units"]==before["research_units"]
 assert reopened.snapshot()["http_units"]==before["http_units"]
 assert reopened.grant(now_ms=899999) is None and reopened.snapshot()["clock_fault"]
 assert reopened.grant(now_ms=900001) is None
 with pytest.raises(ValueError):b.read("PC1","grid",conn,1001,2,now_ms=1000)
 b.close(conn,confirmed=True,now_ms=1000)
 with pytest.raises(ValueError):b.open("PC1","grid","history_get",1,now_ms=1000)

def test_priority_and_ownership_are_closed_not_caller_high_string():
 b=model();low=b.open("PC1","grid","history_get",1,now_ms=0)
 high=b.open("PC2","grid","bybit_live_get",1,now_ms=0)
 assert b.grant(now_ms=1000)["ticket"]==high
 assert b.grant(now_ms=1200)["ticket"]==low
 for node,module,op in (("ADMINIT","grid","history_get"),("PC1","strattester","ws_connect"),("PC1","grid","HIGH"),("PC1","grid","place_order")):
  with pytest.raises(ValueError):b.open(node,module,op,3,now_ms=1200)
 conn=next(iter(b.snapshot()["connections"]))
 with pytest.raises(ValueError):b.read("PC3","grid",conn,1024,1,now_ms=1200)

def test_bounded_queue_backpressure_does_not_consume_sequence():
 b=model()
 for seq in range(1,17):b.open("PC1","grid","history_get",seq,now_ms=0)
 with pytest.raises(ValueError,match="BACKPRESSURE"):b.open("PC1","grid","history_get",17,now_ms=0)
 assert b.snapshot()["sequences"]["PC1/grid"]==16
 high=b.open("PC1","grid","bybit_live_get",17,now_ms=0)
 assert b.grant(now_ms=1000)["ticket"]==high

def test_ls5_outage_no_new_bulk_or_connections_and_only_preallocated_high_bytes():
 b=model();conn=opened(b,node="LS5",op="ws_connect",now=3000)
 b.set_authority(False,now_ms=4000)
 b.read("LS5","grid",conn,65536,2,now_ms=4000)
 assert b.grant(now_ms=4000)["kind"]=="READ"
 b.read("LS5","grid",conn,1,3,now_ms=4000)
 assert b.grant(now_ms=5000) is None
 b.open("PC1","grid","history_get",1,now_ms=5000)
 assert b.grant(now_ms=6000) is None
 reopened=type(b).restore(b.dumps(),now_ms=900000)
 assert reopened.grant(now_ms=901000) is None

def test_cooldowns_persist_and_cannot_be_shortened():
 b=model();b.open("PC1","grid","history_get",1,now_ms=0);b.feedback(403,now_ms=0)
 b.feedback(429,now_ms=1000,retry_after_ms=1000)
 assert b.snapshot()["http_cooldown_ms"]>=600000
 assert b.grant(now_ms=599000) is None
 reopened=type(b).restore(b.dumps(),now_ms=599999)
 assert reopened.grant(now_ms=599999) is None
 assert reopened.grant(now_ms=600001)["kind"]=="OPEN"

def test_global_http_block_stops_new_chunk_debits_on_existing_streams():
 b=model();conn=opened(b)
 b.read('PC1','grid',conn,1024,2,now_ms=1000)
 b.feedback(403,now_ms=1000)
 assert b.grant(now_ms=1000) is None
 assert b.snapshot()['charged']['research']==0

def test_bybit_block_retains_uncertain_sessions_but_preserves_local_health():
 b=model();conn=opened(b)
 b.feedback(403,now_ms=1000)
 assert b.snapshot()['connections'][conn]['uncertain'] is True
 b.open('PC2','unified-system','health',1,now_ms=1000)
 assert b.grant(now_ms=1200)['operation']=='health'

def measurement(bad=False):
 return dict(dns_ms=3000 if bad else 10,dns_failed=False,gateway_ms=10,https_ms=20,packet_loss_permille=200 if bad else 0,tcp_failed=False,bybit_failed=False,interface_permille=950 if bad else 100)

def test_pressure_hysteresis_and_bounded_observations_survive_reopen():
 b=model()
 for t in range(3):b.observe(measurement(True),now_ms=t)
 assert b.snapshot()["pressure"]=="DEGRADED"
 b.open("PC1","grid","history_get",1,now_ms=2);assert b.grant(now_ms=1000) is None
 for t in range(1001,1011):b.observe(measurement(),now_ms=t)
 assert b.snapshot()["pressure"]=="RECOVERING"
 for t in range(1011,1021):b.observe(measurement(),now_ms=t)
 assert b.snapshot()["pressure"]=="NORMAL"
 reopened=type(b).restore(b.dumps(),now_ms=2000)
 assert reopened.snapshot()["observations"]==b.snapshot()["observations"]
 for t in range(2001,2101):reopened.observe(measurement(),now_ms=t)
 assert len(reopened.snapshot()["observations"])==64

def test_serialization_bounds_and_counter_tampering_rejected():
 b=model();original=b.dumps();assert len(original)<=131072
 for change in ("negative","extra","oversize","bool"):
  state=json.loads(original)
  if change=="negative":state["research_units"]=-1
  elif change=="extra":state["arbitrary"]="HIGH"
  elif change=="bool":state["research_units"]=True
  candidate=b"x"*131073 if change=="oversize" else json.dumps(state).encode()
  with pytest.raises(ValueError):type(b).restore(candidate,now_ms=0)

@pytest.mark.parametrize('kind',['duplicate_pending','duplicate_open','priority','actor','receipt_connection','deadline','float_clock','bool_deadline'])
def test_restore_rejects_identity_category_and_lease_corruption(kind):
 import copy
 b=model();conn=opened(b);b.read('PC1','grid',conn,1000,2,now_ms=1000);b.grant(now_ms=1000)
 b.read('PC1','grid',conn,1000,3,now_ms=1000);s=b.snapshot()
 if kind=='duplicate_pending':s['pending'].append(copy.deepcopy(s['pending'][0]))
 elif kind=='duplicate_open':
  second=copy.deepcopy(s['connections'][conn]);second['id']='connection/2';s['connections']['connection/2']=second;s['permit_sequence']=2;s['attempts']['http']=2
 elif kind=='priority':s['connections'][conn]['priority']='HIGH'
 elif kind=='actor':s['connections'][conn]['request']['module']='strattester'
 elif kind=='receipt_connection':s['receipts']['PC1/grid']['connection']='connection/999'
 elif kind=='deadline':s['connections'][conn]['deadline_ms']=6001
 elif kind=='float_clock':s['clock_ms']=1000.0
 else:s['connections'][conn]['deadline_ms']=True
 with pytest.raises(ValueError):type(b).restore(json.dumps(s).encode(),now_ms=1000)

@pytest.mark.parametrize('node',['PC1','PC2','PC3','PC4','LS7'])
@pytest.mark.parametrize('operation',['ssh_control','github_fetch','module_update'])
def test_only_ls5_can_initiate_control_and_shared_external_fetch(node,operation):
 b=model()
 with pytest.raises(ValueError):b.open(node,'unified-system',operation,1,now_ms=0)
 assert b.snapshot()['pending']==[] and b.snapshot()['sequences']=={}

@pytest.mark.parametrize('operation',['ssh_control','github_fetch','module_update'])
def test_ls5_retains_closed_control_and_fetch_operations(operation):
 b=model();b.open('LS5','unified-system',operation,1,now_ms=0)
 assert b.grant(now_ms=200)['operation']==operation

@pytest.mark.parametrize('node',['PC1','PC2','PC3','PC4','LS7'])
def test_restore_cannot_move_ls5_control_capability_to_worker(node):
 b=model();b.open('LS5','unified-system','ssh_control',1,now_ms=0);b.grant(now_ms=200)
 s=b.snapshot();s['sequences']={node+'/unified-system':1}
 held=s['connections']['connection/1']['request'];held['node']=node;held['id']=node+'/unified-system/1'
 receipt=s['receipts'].pop('LS5/unified-system');receipt['request']['node']=node;receipt['request']['id']=held['id'];receipt['ticket']=held['id'];s['receipts'][node+'/unified-system']=receipt
 with pytest.raises(ValueError):type(b).restore(json.dumps(s).encode(),now_ms=200)

def test_open_p1_delayed_first_spend_counterexample_is_not_a_transfer_bound():
 # Intentional known limitation, NOT a proof that actual bandwidth is safe.
 # These are never spent on real I/O. Seventy single-use but unused receipts
 # could later be first-spent together, exceeding a one-second+burst envelope.
 b=model();conn=opened(b);unused=[]
 for index in range(70):
  now=1000+index*1000;b.renew(conn,confirmed_open=True,now_ms=now)
  b.read('PC1','grid',conn,65536,index+2,now_ms=now)
  unused.append(b.grant(now_ms=now))
 assert all(receipt and receipt['kind']=='READ' and 'expires_ms' not in receipt for receipt in unused)
 assert sum(receipt['bytes'] for receipt in unused)>3*1048576
 assert b.snapshot()['charged']['research']==70*65536
