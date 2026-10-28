"""Narrow S0 components. TLS/public-only application policy, not a hostile-code sandbox."""
import asyncio,hashlib,socket,ssl,time
from .policy import PUBLIC_URL,TOPICS,MAX_JSON,need,canonical,load_json,outbound
from .wire import ServerState,validate_reply
from .protocol import MarketState
from .materials import tls_context
from .storage import read_small,stop_requested

def context(c):return dict(head=c['plan']['head'],run_id=c['plan']['run_id'])
def local_context(c):return dict(context(c),role=c['role'])
def der_pin(pem):
 from cryptography import x509
 from cryptography.hazmat.primitives.serialization import Encoding
 return hashlib.sha256(x509.load_pem_x509_certificate(pem).public_bytes(Encoding.DER)).digest()

def stopped(root,c):return stop_requested(root,local_context(c))

def connector(ctx,pin):
 import aiohttp
 class Pinned(aiohttp.TCPConnector):
  async def _wrap_create_connection(self,*args,**kwargs):
   transport,protocol=await super()._wrap_create_connection(*args,**kwargs)
   try:
    obj=transport.get_extra_info('ssl_object');need(obj is not None and hashlib.sha256(obj.getpeercert(binary_form=True)).digest()==pin,'S0_PEER_CERTIFICATE_BLOCKED')
   except BaseException:transport.close();raise
   return transport,protocol
 return Pinned(ssl=ctx,limit=1,force_close=False,enable_cleanup_closed=True)

async def deny_redirect(*args,**kwargs):raise ValueError('S0_REDIRECT_BLOCKED')

def trace():
 import aiohttp
 t=aiohttp.TraceConfig();t.on_request_redirect.append(deny_redirect);return t

async def public_connection(session):
 import aiohttp
 # No credentials, proxy, arbitrary URL, REST, private stream or order operation.
 return await session.ws_connect(PUBLIC_URL,timeout=aiohttp.ClientWSTimeout(ws_receive=1,ws_close=.5),max_msg_size=MAX_JSON,heartbeat=15,autoping=True,compress=0)

async def coordinator(config,root,journal,guard,*,seconds=300):
 from aiohttp import web
 need(type(seconds) in (int,float) and type(seconds) is not bool and 1<=seconds<=300)
 p=config['plan'];started=time.monotonic();end=started+seconds-.25;state=ServerState(context(config));fatal=None;last_seen=started;requests=0
 expected=der_pin(read_small(root,'peer-cert.pem'));ctx=tls_context(config,root)
 async def handler(request):
  nonlocal fatal,last_seen,requests
  try:
   guard();obj=request.transport.get_extra_info('ssl_object')
   need(obj is not None and hashlib.sha256(obj.getpeercert(binary_form=True)).digest()==expected and request.remote==p['worker_ip'],'S0_PEER_IDENTITY_BLOCKED')
   requests+=1;need(requests<=1000,'S0_REQUEST_LIMIT')
   v=load_json(await request.read());reply=state.accept(v,max(0,int((end-time.monotonic())*1000)),stopped(root,config))
   last_seen=time.monotonic();journal.add('worker-'+v['op'],dict(message=v,ack=reply));return web.Response(body=canonical(reply),content_type='application/json')
  except Exception:
   fatal='S0_WORKER_MESSAGE_BLOCKED';return web.Response(status=400,body=b'{"error":"S0_BLOCKED"}',content_type='application/json')
 app=web.Application(client_max_size=16384);app.router.add_post('/s0',handler);runner=web.AppRunner(app,access_log=None,shutdown_timeout=.2)
 sock=None;reason='WINDOW_COMPLETE'
 try:
  await runner.setup();sock=socket.socket(socket.AF_INET,socket.SOCK_STREAM)
  if hasattr(socket,'SO_EXCLUSIVEADDRUSE'):sock.setsockopt(socket.SOL_SOCKET,socket.SO_EXCLUSIVEADDRUSE,1)
  sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,0);sock.bind((p['coordinator_ip'],p['port']));sock.listen(4);sock.setblocking(False)
  site=web.SockSite(runner,sock,ssl_context=ctx,shutdown_timeout=.2);await site.start();journal.add('listening',{'port':p['port']})
  while time.monotonic()<end:
   guard()
   if fatal:raise ValueError(fatal)
   if stopped(root,config):reason='OPERATOR_STOP';await asyncio.sleep(min(.2,max(0,end-time.monotonic())));break
   if not state.registered and time.monotonic()-started>30:raise ValueError('S0_REGISTRATION_TIMEOUT')
   if state.registered and not state.final and time.monotonic()-last_seen>10:raise ValueError('S0_HEARTBEAT_TIMEOUT')
   if state.final:break
   await asyncio.sleep(.05)
 finally:
  await asyncio.wait_for(runner.cleanup(),.8)
  if sock is not None:sock.close()
 return dict(reason=reason,registered=state.registered,heartbeats=state.heartbeats,stats=state.stats,final=state.final,elapsed_ms=int((time.monotonic()-started)*1000))

async def worker(config,root,journal,market_journal,guard,*,seconds=300):
 import aiohttp
 need(type(seconds) in (int,float) and type(seconds) is not bool and 1<=seconds<=300)
 p=config['plan'];started=time.monotonic();end=started+seconds-.5;seq=0;state=MarketState();heartbeats=0;reason='WINDOW_COMPLETE';last_market=started;retries=0;ws=None
 endpoint='https://'+p['coordinator_ip']+':'+str(p['port'])+'/s0'
 ctx=tls_context(config,root);pin=der_pin(read_small(root,'peer-cert.pem'));timeout=aiohttp.ClientTimeout(total=2,connect=1,sock_read=1)
 public_ctx=ssl.create_default_context();public_ctx.minimum_version=ssl.TLSVersion.TLSv1_2
 async with aiohttp.ClientSession(connector=connector(ctx,pin),timeout=timeout,trust_env=False,cookie_jar=aiohttp.DummyCookieJar(),trace_configs=[trace()]) as control, aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=public_ctx,limit=1),timeout=aiohttp.ClientTimeout(total=5,connect=3),trust_env=False,cookie_jar=aiohttp.DummyCookieJar(),trace_configs=[trace()]) as public:
  async def send(op):
   nonlocal seq,end,heartbeats
   seq+=1;message=dict(schema=1,**context(config),node='PC4',seq=seq,op=op,stats=None if op=='register' else state.summary())
   for attempt in range(3):
    guard()
    try:
     async with control.post(endpoint,data=canonical(message),headers={'Content-Type':'application/json'},allow_redirects=False) as response:
      need(response.status==200,'S0_COORDINATOR_REPLY_BLOCKED');body=await response.content.read(16385);need(len(body)<=16384)
      reply=validate_reply(load_json(body),context(config),seq);end=min(end,time.monotonic()+reply['remaining_ms']/1000-.3)
      journal.add('coordinator-ack',dict(message=message,ack=reply))
      if op=='heartbeat':heartbeats+=1
      return reply
    except (aiohttp.ClientError,TimeoutError):
     if attempt==2:raise ValueError('S0_COORDINATOR_UNAVAILABLE') from None
     await asyncio.sleep(.2)
  reply=await send('register');need(reply['assignment']==TOPICS and not reply['stop'],'S0_NO_ASSIGNMENT')
  last_report=0.;connected_before=False;subscribed=False
  try:
   while time.monotonic()<end:
    guard()
    if stopped(root,config):reason='OPERATOR_STOP';break
    if time.monotonic()-last_report>=.5:
     reply=await send('heartbeat');last_report=time.monotonic()
     if reply['stop']:reason='COORDINATOR_STOP';break
    if ws is None:
     try:
      ws=await asyncio.wait_for(public_connection(public),min(5,max(.05,end-time.monotonic())))
      if connected_before:state.reconnect()
      connected_before=True;subscribed=False;market_journal.add('connection',{'index':state.summary()['connections']});await ws.send_json(outbound('subscribe'));journal.add('public-connected',{'reconnects':state.summary()['reconnects']})
     except (aiohttp.ClientError,OSError,TimeoutError):
      retries+=1;need(retries<=3,'S0_FEED_UNAVAILABLE');await asyncio.sleep(.2*retries);continue
    try:
     message=await asyncio.wait_for(ws.receive(),min(1,max(.05,end-time.monotonic())))
     if message.type==aiohttp.WSMsgType.TEXT:
      value=load_json(message.data)
      if 'topic' in value:
       need(subscribed,'S0_TOPIC_BEFORE_ACK');state.ingest(value,int(time.time()*1000));market_journal.add('bybit-public',value);last_market=time.monotonic()
      elif value.get('op')=='subscribe':need(value.get('success') is True and value.get('req_id')=='S0');subscribed=True
      else:need(value.get('op') in ('ping','pong') and value.get('req_id','S0')=='S0','S0_PUBLIC_CONTROL_BLOCKED')
     elif message.type in (aiohttp.WSMsgType.CLOSED,aiohttp.WSMsgType.CLOSE,aiohttp.WSMsgType.ERROR):raise ConnectionError('S0_PUBLIC_CLOSED')
     else:need(message.type in (aiohttp.WSMsgType.PING,aiohttp.WSMsgType.PONG),'S0_PUBLIC_FRAME_BLOCKED')
    except (aiohttp.ClientError,OSError,TimeoutError):
     if time.monotonic()>=end:break
     if ws.closed or time.monotonic()-last_market>10:
      await asyncio.wait_for(ws.close(),.6);ws=None;retries+=1;need(retries<=3,'S0_FEED_UNAVAILABLE');journal.add('public-disconnected',{'attempt':retries});await asyncio.sleep(.2)
    need(time.monotonic()-last_market<=20,'S0_PUBLIC_STALE_STOP')
   if connected_before:need(subscribed,'S0_SUBSCRIBE_ACK_MISSING')
   await send('final')
  finally:
   if ws is not None:await asyncio.wait_for(ws.close(),.6)
 return dict(reason=reason,registered=True,heartbeats=heartbeats,stats=state.summary(),final=True,elapsed_ms=int((time.monotonic()-started)*1000),last_market_age_ms=int((time.monotonic()-last_market)*1000))
