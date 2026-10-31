import unittest
from grid.postgres_ha import PromotionController, HAError, lsn_bytes, replication_health
from grid.backup_recovery import Backup, BackupPolicy

class PromotionTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.calls=[]
  class PG:
   async def recovery(inner): return True
   async def replay_lsn(inner): return '0/200'
   async def promote(inner): self.calls.append('promote'); return True
  self.pg=PG()
  async def ack(*args): return '0/180'
  self.ack=ack
  async def stop(*args):return True
  self.stop=stop
 async def test_only_current_lease_fenced_old_primary_and_caught_up_candidate_promotes(self):
  async def lease(owner,epoch):self.calls.append('lease');return True
  async def fence(old,epoch):self.calls.append('fence');return True
  result=await PromotionController(self.pg,lease,fence,acknowledged_lsn=self.ack,fence_candidate=self.stop).promote('new','old',3,'0/180')
  self.assertEqual(self.calls,['lease','fence','lease','fence','promote','lease','fence']);self.assertEqual(result['status'],'PROMOTED')
 async def test_unknown_fence_no_quorum_and_expired_recheck_never_promote(self):
  for answers,fenced in (([False],True),([True],None),([True,False],True),([True],1)):
   values=iter(answers)
   async def lease(*args):return next(values)
   async def fence(*args):return fenced
   with self.subTest(answers=answers,fenced=fenced),self.assertRaises(HAError):await PromotionController(self.pg,lease,fence,acknowledged_lsn=self.ack,fence_candidate=self.stop).promote('new','old',3,'0/180')
   self.assertNotIn('promote',self.calls)
 async def test_lag_and_identity_bounds(self):
  async def yes(*args):return True
  for lsn in ('0/300','unknown',True):
   with self.subTest(lsn=lsn),self.assertRaises((HAError,ValueError)):await PromotionController(self.pg,yes,yes,acknowledged_lsn=self.ack,fence_candidate=self.stop).promote('new','old',3,lsn)
  self.assertEqual(lsn_bytes('1/0'),2**32)
  self.assertEqual(replication_health('0/200','0/180',128)['lag_bytes'],128)
  self.assertEqual(replication_health('0/200',None,128)['state'],'UNKNOWN')

class BackupTests(unittest.TestCase):
 def test_retention_protects_pitr_chain_latest_verified_and_unverified(self):
  policy=BackupPolicy(interval_seconds=60,retain=1)
  backups=[Backup('old',10,True,True),Backup('only-restored',20,True,True),Backup('new',30,True,False),Backup('unfinished',40,False,False)]
  self.assertEqual(policy.expired(backups,{'old'}),[])
  self.assertEqual(policy.expired(backups,set()),['old'])
  self.assertTrue(policy.due(100,30));self.assertFalse(policy.due(80,30))
 def test_restore_verification_requires_manifest_wal_and_application_checks(self):
  policy=BackupPolicy(60,2)
  for facts in ((True,True,True),(True,False,True),(False,True,True),(True,True,False),(1,True,True)):
   self.assertEqual(policy.restore_verified(*facts),all(v is True for v in facts))

class SchedulingTests(unittest.IsolatedAsyncioTestCase):
 async def test_scheduled_backup_requires_actual_manifest_and_restore_verifiers(self):
  from grid.backup_recovery import BackupScheduler
  calls=[]
  async def create():calls.append('create');return 'backup-1'
  async def manifest(identity):calls.append('manifest');return True
  async def restore(identity):calls.append('restore');return False
  scheduler=BackupScheduler(BackupPolicy(60,2),create,manifest,restore)
  result=await scheduler.run_due(100,0)
  self.assertFalse(result.restore_verified);self.assertTrue(result.manifest_verified)
  self.assertEqual(calls,['create','manifest','restore'])
  self.assertIsNone(await scheduler.run_due(110,100))

class CommitBoundaryTests(unittest.IsolatedAsyncioTestCase):
 async def test_unknown_or_forged_required_lsn_never_reaches_database(self):
  async def yes(*args): return True
  async def unknown(*args): return None
  async def known(*args): return '0/200'
  for verifier in (None,unknown,known):
   with self.subTest(verifier=verifier),self.assertRaises(HAError):
    await PromotionController(None,yes,yes,acknowledged_lsn=verifier).promote('candidate','old',1,'0/180')

class LostPromotionLeaseTests(unittest.IsolatedAsyncioTestCase):
 async def test_loss_after_promotion_fences_candidate_before_reporting_failure(self):
  calls=[];checks=iter((True,True,False))
  async def lease(*args):return next(checks)
  async def fence(*args):return True
  async def ack(*args):return '0/180'
  async def stop(*args):calls.append('fence-candidate');return True
  class PG:
   async def recovery(self):return True
   async def replay_lsn(self):return '0/200'
   async def promote(self):calls.append('promote');return True
  with self.assertRaises(HAError):await PromotionController(PG(),lease,fence,acknowledged_lsn=ack,fence_candidate=stop).promote('new','old',2,'0/180')
  self.assertEqual(calls,['promote','fence-candidate'])

class WriterGuardTests(unittest.IsolatedAsyncioTestCase):
 async def test_running_writer_is_fenced_when_lease_validation_is_lost(self):
  import asyncio
  calls=[]
  async def lease(*args):return False
  async def fence(*args):calls.append('stop-writer');return True
  controller=PromotionController(None,lease,fence,fence_candidate=fence)
  with self.assertRaises(HAError):await controller.supervise_writer('new',3,asyncio.Event(),interval=.01)
  self.assertEqual(calls,['stop-writer'])

class PostgresIOTimeoutTests(unittest.IsolatedAsyncioTestCase):
 async def check_blocked(self, operation):
  import asyncio
  calls=[]
  async def yes(*args):return True
  async def ack(*args):return '0/180'
  async def emergency_fence(*args):calls.append('fence-candidate');return True
  async def execute(name,result):
   calls.append(name)
   if name==operation:
    try:await asyncio.Event().wait()
    finally:calls.append('cancelled-'+name)
   return result
  class PG:
   async def recovery(self):return await execute('recovery',True)
   async def replay_lsn(self):return await execute('replay_lsn','0/200')
   async def promote(self):return await execute('promote',True)
  controller=PromotionController(PG(),yes,yes,timeout=.01,acknowledged_lsn=ack,fence_candidate=emergency_fence)
  # Outer deadline is only a test hang guard. It must not be the deadline that
  # produces the expected HAError; the controller owns the PG I/O deadline.
  with self.assertRaises(HAError):
   await asyncio.wait_for(controller.promote('new','old',3,'0/180'),timeout=.5)
  self.assertIn('cancelled-'+operation,calls)
  if operation=='promote':
   self.assertEqual(calls[-2:],['cancelled-promote','fence-candidate'])
  else:
   self.assertNotIn('promote',calls)
   self.assertNotIn('fence-candidate',calls)
 async def test_blocked_recovery_read_is_bounded_without_attempting_promotion(self):
  await self.check_blocked('recovery')
 async def test_blocked_replay_read_is_bounded_without_attempting_promotion(self):
  await self.check_blocked('replay_lsn')
 async def test_ambiguous_blocked_promotion_is_bounded_and_fences_candidate(self):
  await self.check_blocked('promote')
