"""Closed ephemeral S0 registration/heartbeat/assignment; not durable replay protection."""
from decimal import Decimal
import hashlib,re
from .policy import need,canonical,TOPICS
from .protocol import MarketState,MIN_MS,MAX_MS
COUNTERS={'trade_count','buy_count','sell_count','duplicate_trades','book_updates','duplicate_books','connections','reconnects'}

def validate_summary(v):
 need(type(v) is dict and set(v)==set(MarketState().summary()))
 for k in COUNTERS:need(type(v[k]) is int and 0<=v[k]<=1000000000)
 need(v['trade_count']==v['buy_count']+v['sell_count'] and v['connections']==v['reconnects']+1)
 for k in ('buy_volume','sell_volume','best_bid','best_ask'):
  x=v[k]
  if x is None:need(k in ('best_bid','best_ask'));continue
  need(type(x) is str and len(x)<=60 and re.fullmatch(r'(0|[1-9][0-9]*)(\.[0-9]{1,18})?',x) and 0<=Decimal(x)<=Decimal('1e27'))
 need((v['best_bid'] is None)==(v['best_ask'] is None))
 if v['best_bid'] is not None:need(0<Decimal(v['best_bid'])<Decimal(v['best_ask']))
 for k in ('last_book_ts','last_trade_ts'):need(v[k] is None or type(v[k]) is int and MIN_MS<=v[k]<=MAX_MS)
 return v

def validate_reply(v,context,seq):
 need(type(v) is dict and set(v)=={'schema','head','run_id','seq','assignment','remaining_ms','stop'})
 need(type(v['schema']) is int and v['schema']==1 and all(v[k]==x for k,x in context.items()))
 need(type(v['seq']) is int and v['seq']==seq and v['assignment']==TOPICS)
 need(type(v['remaining_ms']) is int and 0<=v['remaining_ms']<=300000 and type(v['stop']) is bool)
 return v

class ServerState:
 def __init__(self,context):
  self.context=dict(context);self.seq=0;self.digest=None;self.reply=None;self.stats=None;self.heartbeats=0;self.registered=False;self.final=False
 def accept(self,v,remaining_ms,stop=False):
  need(type(v) is dict and set(v)=={'schema','head','run_id','node','seq','op','stats'})
  need(type(v['schema']) is int and v['schema']==1 and all(v[k]==x for k,x in self.context.items()) and v['node']=='PC4')
  need(type(v['seq']) is int and 1<=v['seq']<=1000 and v['op'] in ('register','heartbeat','final'))
  digest=hashlib.sha256(canonical(v)).hexdigest()
  if v['seq']==self.seq:need(digest==self.digest);return self.reply
  need(v['seq']==self.seq+1 and not self.final)
  if not self.registered:need(v['seq']==1 and v['op']=='register' and v['stats'] is None)
  else:
   need(v['op'] in ('heartbeat','final'));validate_summary(v['stats'])
   if self.stats:
    for key in COUNTERS:need(v['stats'][key]>=self.stats[key])
    for key in ('buy_volume','sell_volume'):need(Decimal(v['stats'][key])>=Decimal(self.stats[key]))
  need(type(remaining_ms) is int and 0<=remaining_ms<=300000 and type(stop) is bool)
  if v['op']=='heartbeat':self.heartbeats+=1
  self.registered=True;self.seq=v['seq'];self.digest=digest;self.stats=v['stats'];self.final=v['op']=='final'
  self.reply=dict(schema=1,**self.context,seq=self.seq,assignment=list(TOPICS),remaining_ms=remaining_ms,stop=stop)
  return self.reply
