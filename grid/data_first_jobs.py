"""Grid-owned DataFirst requests. Cache writes never publish accepted results.
Source policy comes from CONTROL configuration, never request flags/telemetry.
"""
import copy,hashlib,json,math,re,uuid
KIND='stratt_data_first_v1'
SCHEMA='grid.stratt-data-first.v1'
STATES=frozenset(('SYNCING','PARTIAL','READY','RUNNING','COMPLETED','FAILED','BLOCKED','YIELDED'))

def need(ok):
 if not ok:raise ValueError('DATA_FIRST_REJECTED')

def canonical(value,limit=1048576):
 raw=json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
 need(len(raw)<=limit);return raw

def sha(value):return hashlib.sha256(canonical(value)).hexdigest()
def hexdigest(value,size=64):return type(value) is str and re.fullmatch('[a-f0-9]{'+str(size)+'}',value) is not None

def validate_request(value):
 need(type(value) is dict and set(value)=={'schema','source_commit','domain','resources'} and value['schema']==SCHEMA and hexdigest(value['source_commit'],40))
 d=value['domain'];r=value['resources'];need(type(d) is dict and set(d)=={'instrument','strategy_id','strategy_version','fingerprint','start_ms','end_ms','requirements','blockers','history_provenance','history_fingerprint','activity_basis'})
 i=d['instrument'];need(type(i) is dict and set(i)=={'category','symbol','status','launchTime','deliveryTime','fundingInterval','contractType','marketRegion','symbolId','baseCoin','quoteCoin'})
 need(i['category'] in ('linear','inverse','spot') and type(i['symbol']) is str and re.fullmatch('[A-Z0-9_.-]{1,80}',i['symbol']))
 need(i['status'] in ('Trading','Closed','Settled','Delivering'))
 need(all(x is None or type(x) in (str,int) and len(str(x))<=128 for x in i.values()))
 for k in ('strategy_id','strategy_version'):need(type(d[k]) is str and re.fullmatch('[A-Za-z0-9_.-]{1,128}',d[k]))
 need(hexdigest(d['fingerprint']) and type(d['start_ms']) is int and type(d['end_ms']) is int and 0<=d['start_ms']<d['end_ms']<2**63)
 need(d['blockers']==[] and d['activity_basis'] in ('EXPLICIT_ARCHIVE_INTERVALS','LAUNCH_DELIVERY_BOUNDS_ONLY'))
 need(all(d[k] is None or hexdigest(d[k]) for k in ('history_provenance','history_fingerprint')))
 need((d['history_provenance'] is None)==(d['history_fingerprint'] is None))
 need((d['activity_basis']=='EXPLICIT_ARCHIVE_INTERVALS')==(d['history_provenance'] is not None))
 need(type(d['requirements']) is list and 1<=len(d['requirements'])<=256)
 for q in d['requirements']:
  need(type(q) is dict and set(q)=={'symbol','dataset','timeframe','start_ms','end_ms','min_observations','required'})
  need(q['symbol']==i['symbol'] and q['dataset'] in ('candles','mark_price','index_price','premium_index','open_interest','long_short_ratio'))
  need(type(q['timeframe']) is str and re.fullmatch('[1-9][0-9]*[mhdw]',q['timeframe']))
  need(type(q['required']) is bool and type(q['min_observations']) is int and 1<=q['min_observations']<=1000000)
  need(type(q['start_ms']) is int and type(q['end_ms']) is int and 0<=q['start_ms']<=q['end_ms']<d['end_ms'])
 need(type(r) is dict and set(r)=={'cpu','ram_gb','scratch_gb','input_gb','gpu','data_locality'})
 need(all(type(r[k]) in (int,float) and math.isfinite(r[k]) and 0<=r[k]<=2**40 for k in ('cpu','ram_gb','scratch_gb','input_gb')) and r['gpu'] is False)
 need(r['data_locality'] is None or type(r['data_locality']) is str and re.fullmatch('[A-Za-z0-9_.:-]{1,128}',r['data_locality']))
 canonical(value);return copy.deepcopy(value)

def request_sha(value):return sha(validate_request(value))
def semantic_id(value):
 v=validate_request(value);return uuid.uuid5(uuid.NAMESPACE_URL,sha({k:v[k] for k in ('schema','source_commit','domain')}))

def admitted(value,policy):
 v=validate_request(value)
 return bool(type(policy) is dict and v['source_commit'] in policy and type(policy[v['source_commit']]) in (list,tuple) and v['domain']['fingerprint'] in policy[v['source_commit']])

def capable(node,value,policy):
 v=validate_request(value);runtime=node.get('data_first_runtime')
 return admitted(v,policy) and type(runtime) is dict and runtime=={'protocol':SCHEMA,'source_commit':v['source_commit']}

def decoded(value):return json.loads(value) if type(value) is str else value

async def enqueue(pool,value,policy):
 v=validate_request(value);need(admitted(v,policy));ident=semantic_id(v);payload=canonical(v).decode()
 async with pool.acquire() as c:
  async with c.transaction():
   await c.execute("""INSERT INTO ml_jobs(id,job_type,payload,dedupe_key) VALUES($1,$2,$3::jsonb,$4) ON CONFLICT DO NOTHING""",ident,KIND,payload,str(ident))
   row=await c.fetchrow('SELECT job_type,payload FROM ml_jobs WHERE id=$1 FOR UPDATE',ident)
   need(row is not None and row['job_type']==KIND and canonical(decoded(row['payload']))==canonical(v))
 return str(ident)

async def publish(pool,job_id,owner,generation,sequence,state,checkpoint,policy,*,request_pin):
 """Single authoritative transaction; identical receipts may be replayed.
 No distributed transaction with worker caches is implied. A stale writer can
 leave cache bytes but cannot commit a Grid checkpoint/result.
 """
 need(type(owner) is str and 1<=len(owner)<=128 and type(generation) is int and generation>=1 and type(sequence) is int and 1<=sequence<2**63 and state in STATES)
 body={'sequence':sequence,'state':state,'checkpoint':checkpoint};raw=canonical(body);digest=hashlib.sha256(raw).hexdigest()
 async with pool.acquire() as c:
  async with c.transaction():
   row=await c.fetchrow('SELECT * FROM ml_jobs WHERE id=$1 FOR UPDATE',uuid.UUID(str(job_id)))
   if row is None or row['job_type']!=KIND or row['lease_owner']!=owner or row['lease_generation']!=generation:return None
   v=decoded(row['payload']);need(admitted(v,policy) and hexdigest(request_pin) and request_sha(v)==request_pin);old=decoded(row.get('domain_state'))
   active=row['status']=='running' and await c.fetchval('SELECT lease_until>clock_timestamp() FROM ml_jobs WHERE id=$1',row['id'])
   if old and old['sequence']==sequence:
    if not (active or row['status']=='done' and old['state']=='COMPLETED' and state=='COMPLETED'):return None
    need(old['sha256']==digest);return {'accepted':True,'sha256':digest,'state':old['state'],'request_sha256':request_pin}
   if not active:return None
   need(sequence==(old['sequence']+1 if old else 1))
   need(not old or old['state']!='RUNNING' or state in ('RUNNING','COMPLETED','FAILED','BLOCKED'))
   if state=='YIELDED':
    need(type(checkpoint) is dict and set(checkpoint)=={'state','reason','progress'} and type(checkpoint['progress']) is dict)
    need((checkpoint['state']=='PARTIAL' and checkpoint['reason'] in ('CANCELLED_OR_RESOURCE_DEADLINE','REQUIRED_HISTORY_INCOMPLETE_OR_CANCELLED','SNAPSHOT_NOT_READY','CANCELLED')) or (checkpoint['state']=='READY' and checkpoint['reason']=='RESOURCE_ADMISSION_BLOCKED'))
    # Once strategy execution started, an interrupted/uncertain attempt must
    # terminate BLOCKED, never be silently resumed as a successful yield.
    need(not old or old['state']!='RUNNING')
   if state=='COMPLETED':
    need(old is not None and old['state']=='RUNNING' and type(old['checkpoint']) is dict and type(old['checkpoint'].get('progress')) is dict)
    need(old['checkpoint']['progress'].get('input_sha256')==checkpoint.get('input_sha256') if type(checkpoint) is dict else False)
    need(type(checkpoint) is dict and set(checkpoint)=={'strategy_id','strategy_version','fingerprint','output','input_sha256','instrument','requirements','activity_basis','history_provenance','trading','physical_g1'})
    d=v['domain'];need(all(checkpoint[k]==d[k] for k in ('strategy_id','strategy_version','fingerprint','instrument','requirements','activity_basis','history_provenance')) and hexdigest(checkpoint['input_sha256']) and checkpoint['trading']=='NO-GO' and checkpoint['physical_g1']=='NOT_AUTHORIZED')
   new={**body,'sha256':digest}
   # Conditional mutation rechecks expiry after result validation. All values
   # remain on this one locked row and same transaction/reservation authority.
   changed=await c.fetchval("""UPDATE ml_jobs SET domain_state=$4::jsonb,
    domain_result=CASE WHEN $5='COMPLETED' THEN $6::jsonb ELSE domain_result END,
    domain_result_sha256=CASE WHEN $5='COMPLETED' THEN $7 ELSE domain_result_sha256 END,
    status=CASE WHEN $5='COMPLETED' THEN 'done' WHEN $5 IN ('FAILED','BLOCKED') THEN 'failed' WHEN $5='YIELDED' THEN 'queued' ELSE status END,
    lease_owner=CASE WHEN $5='YIELDED' THEN NULL ELSE lease_owner END,
    lease_until=CASE WHEN $5='YIELDED' THEN NULL ELSE lease_until END,
    attempts=CASE WHEN $5='YIELDED' THEN GREATEST(0,attempts-1) ELSE attempts END,
    finished_at=CASE WHEN $5 IN ('COMPLETED','FAILED','BLOCKED') THEN clock_timestamp() ELSE finished_at END
    WHERE id=$1 AND lease_owner=$2 AND lease_generation=$3 AND status='running' AND lease_until>clock_timestamp() RETURNING id""",row['id'],owner,generation,canonical(new).decode(),state,canonical(checkpoint).decode(),sha(checkpoint))
   if not changed:return None
   if state in ('COMPLETED','FAILED','BLOCKED','YIELDED'):await c.execute('DELETE FROM ml_resource_reservations WHERE job_id=$1',row['id'])
   if not await c.fetchval('SELECT $1::timestamptz>clock_timestamp()',row['lease_until']):raise RuntimeError('DataFirst lease expired before commit')
 return {'accepted':True,'sha256':digest,'state':state,'request_sha256':request_pin}
