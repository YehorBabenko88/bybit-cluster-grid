import copy,json,pytest
from s0_smoke.policy import validate_plan,load_json,public_url,outbound,forbidden_environment,import_allowed
H='a'*40

def plan():
 return dict(schema=1,profile='PHYSICAL_SMOKE_S0',head=H,run_id='11111111-1111-4111-8111-111111111111',duration_seconds=300,symbol='BTCUSDT',bybit_url='wss://stream.bybit.com/v5/public/linear',coordinator_ip='100.100.1.1',worker_ip='100.100.1.2',port=49441,hostnames={'LS5':'LS5','PC4':'PC4'},operator_sids={'LS5':'S-1-5-21-1-2-3-1001','PC4':'S-1-5-21-4-5-6-1001'})

def test_closed_plan(): assert validate_plan(plan(),H)['duration_seconds']==300
@pytest.mark.parametrize('field,value',[('schema',True),('duration_seconds',301),('duration_seconds',True),('duration_seconds',0),('symbol','ETHUSDT'),('bybit_url','wss://stream.bybit.com/v5/private'),('coordinator_ip','0.0.0.0'),('coordinator_ip','8.8.8.8'),('coordinator_ip','localhost'),('worker_ip','100.100.1.1'),('port',5432),('port',55432),('port',55433),('port',8765),('port',True),('head','b'*40),('run_id','../x'),('hostnames',{'LS5':'LS5','PC4':'LS5'}),('hostnames',{'LS5':'*','PC4':'PC4'}),('POSTGRES_DSN','x'),('api_key','x'),('trade',False)])
def test_unsafe_plan(field,value):
 v=plan();v[field]=value
 with pytest.raises(ValueError):validate_plan(v,H)
@pytest.mark.parametrize('url',['wss://stream.bybit.com/v5/private','wss://stream.bybit.com/v5/trade','wss://stream.bybit.com/v5/public/linear?x=1','wss://key@stream.bybit.com/v5/public/linear','https://api.bybit.com/v5/order/create','wss://stream.bybit.com.evil/v5/public/linear','wss://STREAM.BYBIT.COM/v5/public/linear','wss://stream.bybit.com:443/v5/public/linear'])
def test_public_url_exact(url):
 with pytest.raises(ValueError):public_url(url)
@pytest.mark.parametrize('name',['POSTGRES_DSN','DATABASE_URL','BYBIT_API_KEY','BYBIT_API_SECRET','TELEGRAM_BOT_TOKEN','GRID_SHARED_TOKEN','NODE_CREDENTIAL','PGPASSWORD','PYTHONPATH','HTTPS_PROXY'])
def test_secret_environment_refused(name):
 with pytest.raises(ValueError):forbidden_environment({name:'synthetic'})
def test_no_values_in_environment_error():
 with pytest.raises(ValueError) as e:forbidden_environment({'POSTGRES_DSN':'supersecret'})
 assert 'supersecret' not in str(e.value)
@pytest.mark.parametrize('raw',['{"a":1,"a":2}','NaN','1','[]','{"x":NaN}','{"x":1e9999}','{"x":'+ '['*30+'0'+']'*30+'}','{"x":"'+ 'x'*1048576+'"}'],ids=['duplicate','nonfinite','scalar','array','nan-field','infinite-float','deep','oversized'])
def test_bounded_json(raw):
 with pytest.raises(ValueError):load_json(raw)
@pytest.mark.parametrize('name',['grid','grid.trading','asyncpg','psycopg','dotenv','pybit','ccxt','telegram'])
def test_production_imports(name):assert not import_allowed(name)
def test_fixed_subscribe_only():
 assert outbound('subscribe')=={'op':'subscribe','args':['orderbook.1.BTCUSDT','publicTrade.BTCUSDT'],'req_id':'S0'}
 assert outbound('ping')=={'op':'ping','req_id':'S0'}
 for op in ['auth','order.create','trade','GET','subscribe.private']:
  with pytest.raises(ValueError):outbound(op)
