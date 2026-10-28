"""Pure closed S0 policy. These application checks are not an OS sandbox."""
import ipaddress,json,math,re,uuid
PUBLIC_URL='wss://stream.bybit.com/v5/public/linear'
TOPICS=['orderbook.1.BTCUSDT','publicTrade.BTCUSDT']
MAX_JSON=1048576

def need(ok,code='S0_POLICY_BLOCKED'):
 if not ok:raise ValueError(code)

def canonical(value):return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False).encode('ascii')

def load_json(raw):
 need(type(raw) in (str,bytes) and 0<len(raw)<=MAX_JSON)
 try:
  text=raw.decode('utf-8') if type(raw) is bytes else raw
  depth=0;quoted=False;escape=False
  for c in text:
   if quoted:
    if escape:escape=False
    elif c=='\\':escape=True
    elif c=='"':quoted=False
   elif c=='"':quoted=True
   elif c in '[{':depth+=1;need(depth<=20)
   elif c in ']}':depth-=1;need(depth>=0)
  def pairs(rows):
   out={}
   for k,v in rows:need(k not in out);out[k]=v
   return out
  def number(s):need(len(s)<=24);return int(s)
  def floating(s):raise ValueError('S0_FLOAT_JSON_BLOCKED')
  v=json.loads(text,object_pairs_hook=pairs,parse_int=number,parse_float=floating,parse_constant=floating)
  need(type(v) is dict);return v
 except (UnicodeError,RecursionError,OverflowError,json.JSONDecodeError):raise ValueError('S0_JSON_BLOCKED') from None

def public_url(url):need(url==PUBLIC_URL);return PUBLIC_URL

def outbound(op):
 need(op in ('subscribe','ping'))
 return dict(op=op,args=list(TOPICS),req_id='S0') if op=='subscribe' else dict(op='ping',req_id='S0')

def import_allowed(name):
 return name.split('.')[0] not in {'grid','asyncpg','psycopg','psycopg2','dotenv','pybit','ccxt','telegram','run_coordinator','run_worker'}

def forbidden_environment(env):
 fixed={'DATABASE_URL','NODE_CREDENTIAL','PGPASSWORD','PYTHONPATH','PYTHONHOME','PYTHONSTARTUP','PYTHONINSPECT','OPENSSL_CONF','OPENSSL_MODULES','SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE','CURL_CA_BUNDLE','SSLKEYLOGFILE','HTTP_PROXY','HTTPS_PROXY','ALL_PROXY'}
 allowed={'SYSTEMROOT','WINDIR','USERPROFILE','LOCALAPPDATA','USERNAME','COMPUTERNAME','TEMP','TMP','PATH'}
 for key in env:
  upper=key.upper();need(upper in allowed,'S0_ENVIRONMENT_NOT_CLOSED')
  need(upper not in fixed and not upper.startswith(('POSTGRES','PGHOST','PGPORT','PGUSER','PGDATABASE','PGSERVICE','BYBIT','BINANCE','TELEGRAM','GRID_')),'S0_INHERITED_CONFIGURATION_BLOCKED')

def sid(value):
 need(type(value) is str and len(value)<=200 and re.fullmatch(r'S-1-5-21(?:-(?:0|[1-9][0-9]{0,9})){4}',value))
 need(all(int(n)<2**32 for n in value.split('-')[4:]));return value

def literal(value):
 need(type(value) is str)
 try:p=ipaddress.IPv4Address(value)
 except ipaddress.AddressValueError:raise ValueError('S0_LITERAL_IP_REQUIRED') from None
 allowed=any(p in ipaddress.ip_network(n) for n in ('100.64.0.0/10','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))
 need(allowed and str(p)==value);return value

def validate_plan(v,head):
 fields={'schema','profile','head','run_id','duration_seconds','symbol','bybit_url','coordinator_ip','worker_ip','port','operator_sids','hostnames'}
 need(type(v) is dict and set(v)==fields)
 need(type(v['schema']) is int and v['schema']==1 and v['profile']=='PHYSICAL_SMOKE_S0')
 need(type(head) is str and re.fullmatch('[0-9a-f]{40}',head) and v['head']==head)
 need(type(v['duration_seconds']) is int and v['duration_seconds']==300 and v['symbol']=='BTCUSDT');public_url(v['bybit_url'])
 need(type(v['run_id']) is str and re.fullmatch('[0-9a-f-]{36}',v['run_id']))
 try:u=uuid.UUID(v['run_id']);need(u.version==4 and str(u)==v['run_id'])
 except (ValueError,AttributeError):raise ValueError('S0_RUN_ID_BLOCKED') from None
 literal(v['coordinator_ip']);literal(v['worker_ip']);need(v['coordinator_ip']!=v['worker_ip'])
 need(type(v['port']) is int and 49152<=v['port']<=65535 and v['port'] not in (55432,55433))
 names=v['hostnames'];need(type(names) is dict and set(names)=={'LS5','PC4'} and len(set(names.values()))==2)
 for n in names.values():need(type(n) is str and re.fullmatch('[A-Z0-9](?:[A-Z0-9-]{0,13}[A-Z0-9])?',n))
 ids=v['operator_sids'];need(type(ids) is dict and set(ids)=={'LS5','PC4'});sid(ids['LS5']);sid(ids['PC4']);need(ids['LS5']!=ids['PC4'])
 return v
