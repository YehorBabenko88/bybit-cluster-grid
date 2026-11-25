"""Prepared catalog admission only; all connections and SQL results are inert fakes."""
import copy,sys,unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import patch
from market_data.capture_store import CaptureStore

COLUMNS={
 'market_data_capture_v2':[('observation_sha256','text',True),('observation_bytes','bytea',True),('payload_bytes','bytea',False),('connection_id','text',True),('observation_index','bigint',True)],
 'market_data_execution_v1':[('event_key','text',True),('symbol','text',True),('timestamp_us','numeric(19,0)',True),('price','text',True),('quantity','text',True),('side','text',True),('trade_id','text',True),('content_sha256','text',True)],
 'market_data_archive_checkpoint_v1':[('import_id','text',True),('blob_sha256','text',True),('committed_rows','bigint',True),('last_observation_sha256','text',True),('total_rows','bigint',True),('last_timestamp_us','text',True),('last_trade_id','text',True)]}

def prepared_rows():
 relations=[(t,'r','p',False,False,False,0,0,0) for t in sorted(COLUMNS)]
 columns=[(t,i,n,typ,required,False,'','') for t in sorted(COLUMNS) for i,(n,typ,required) in enumerate(COLUMNS[t],1)]
 keys=[('market_data_capture_v2','p',['observation_sha256'],False,False,True,11),('market_data_capture_v2','u',['connection_id','observation_index'],False,False,True,12),('market_data_execution_v1','p',['event_key'],False,False,True,13),('market_data_archive_checkpoint_v1','p',['import_id'],False,False,True,14)]
 indexes=[(i,True,True,True,True) for i in (11,12,13,14)]
 return {'relations':relations,'columns':columns,'keys':keys,'indexes':indexes}

class PreparedConnection:
 def __init__(self,rows=None):self.rows=prepared_rows() if rows is None else rows;self.info=SimpleNamespace(transaction_status=0);self.closed=False;self.sql=[];self.pending=None
 @asynccontextmanager
 async def transaction(self):
  assert self.info.transaction_status==0;self.info.transaction_status=2
  try:yield self
  finally:self.info.transaction_status=0
 async def execute(self,sql,parameters=()):
  self.sql.append(sql)
  assert self.info.transaction_status==2
  if sql.lstrip().upper().startswith(('CREATE','ALTER','DROP','INSERT','UPDATE','DELETE')):raise AssertionError('startup must never mutate prepared schema/data')
  if 'current_database()' in sql:self.pending=('fixture',)
  elif 'pg_try_advisory_lock' in sql:self.pending=(True,)
  else:
   self.pending=None
   self.kind=next((k for k in self.rows if 'prepared:'+k in sql),None)
   if self.kind is None:raise AssertionError('unknown catalog read')
  return self
 async def fetchone(self):return self.pending
 async def fetchall(self):return self.rows[self.kind]
 async def close(self):self.closed=True

class CapturePreparedSchemaTests(unittest.TestCase):
 def open(self,connection):
  async def connect(*a,**kw):return connection
  driver=SimpleNamespace(AsyncConnection=SimpleNamespace(connect=connect))
  with patch.dict(sys.modules,{'psycopg':driver}):
   coro=CaptureStore.open('synthetic://never-connect',expected_database='fixture')
   try:coro.send(None)
   except StopIteration as end:return end.value
   raise AssertionError('unexpected scheduling/I/O')
 def test_exact_prepared_schema_opens_without_ddl_or_data_write(self):
  connection=PreparedConnection();store=self.open(connection)
  self.assertIs(store._connection,connection);self.assertFalse(connection.closed);self.assertEqual(connection.info.transaction_status,0)
  self.assertEqual(len(connection.sql),6)
 def test_missing_or_foreign_shape_refused_without_repair(self):
  for kind in ('relations','columns','keys','indexes'):
   with self.subTest(kind=kind):
    rows=prepared_rows();rows[kind].pop();connection=PreparedConnection(rows)
    with self.assertRaises(ValueError):self.open(connection)
    self.assertTrue(connection.closed)
 def test_hostile_prepared_schema_features_are_refused(self):
  mutations=[('relations',0,1,'v'),('relations',0,2,'u'),('relations',0,3,True),('relations',0,6,1),('relations',0,7,1),('relations',0,8,1),('columns',0,3,'character varying'),('columns',0,4,False),('columns',0,5,True),('columns',0,6,'a'),('keys',0,3,True),('keys',0,5,False),('indexes',0,1,False),('indexes',0,3,False)]
  for kind,row,col,value in mutations:
   with self.subTest(kind=kind,row=row,col=col):
    rows=prepared_rows();changed=list(rows[kind][row]);changed[col]=value;rows[kind][row]=tuple(changed);connection=PreparedConnection(rows)
    with self.assertRaises(ValueError):self.open(connection)
    self.assertTrue(connection.closed)
 def test_database_and_writer_lock_refuse_before_catalog_reads(self):
  for marker,result in [('current_database()',('foreign',)),('pg_try_advisory_lock',(False,))]:
   with self.subTest(marker=marker):
    class Refused(PreparedConnection):
     async def execute(self,sql,parameters=()):
      out=await super().execute(sql,parameters)
      if marker in sql:self.pending=result
      return out
    connection=Refused()
    with self.assertRaises((ValueError,RuntimeError)):self.open(connection)
    self.assertTrue(connection.closed);self.assertFalse(any('prepared:' in sql for sql in connection.sql))
