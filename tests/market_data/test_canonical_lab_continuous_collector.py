"""B Round10: exact E async diagnostic type and C durable-pending refusal.

These tests are pure Python, with an isolated import shim for E's *exact*
LabAuthorityStatus dataclass. They never create a native permission, DB,
network connection, process, or real exchange transport.
"""
import asyncio
import sys
import types
import unittest
from unittest.mock import patch
from market_data.provenance import digest

from grid.canonical_lab_continuous_collector import (
    ContinuousLabCollector,CollectorRejected,_minute,
)

def _e_status(epoch="a"*64,**changes):
    from unified_system.lab_writer_authority import LabAuthorityStatus
    args=dict(schema="unified.lab-root-writer-authority.v1",
              scope="ISOLATED_LAB_ONLY",epoch=epoch,generation=1,
              state="READ_ONLY_REVALIDATED_NOT_NATIVE",
              native_admitted=False,trading_authorized=False)
    args.update(changes)
    return LabAuthorityStatus(**args)

class Authority:
    def __init__(self,status=None):self.status=status;self.calls=0
    async def check(self):
        self.calls+=1
        return self.status if self.status is not None else _e_status()

class Journal:
    def __init__(self,pending=None,checkpoint=None):
        self._pending=pending;self._checkpoint=checkpoint
        self.calls=[]
    async def pending(self):self.calls.append("pending");return self._pending
    async def checkpoint(self):self.calls.append("checkpoint");return self._checkpoint
    async def append_pending(self,m):self.calls.append("append")
    async def readback(self,m):self.calls.append("readback")
    async def commit_cursor(self,m):self.calls.append("commit")
    async def clear_pending(self,m):self.calls.append("clear")
    async def exact_existing_checkpoint(self,m):
        self.calls.append("exact")
        return {"state":"UNRESOLVED"}

class Transport:
    def __init__(self):self.calls=0
    async def backfill(self,*args):self.calls+=1;return []

class Writer:
    def __init__(self):self.calls=0
    async def __call__(self,*args):self.calls+=1;raise AssertionError("NO_WRITE_GRANT")

def pending():
    return dict(symbol="BTCUSDT",start_ms=60000,fingerprint="b"*64,
                content_id="c"*64,generation=1,token=7,
                source_sha256="d"*64,schema_sha256="e"*64)

class Boundaries(unittest.TestCase):
    def setUp(self):
        # E's dataclass layout is mirrored only as an isolated test import,
        # not as an authority object. No test-side root grants exist.
        import dataclasses
        package=types.ModuleType("unified_system")
        package.__path__=[]
        e=types.ModuleType("unified_system.lab_writer_authority")
        @dataclasses.dataclass(frozen=True)
        class LabAuthorityStatus:
            schema:str; scope:str;epoch:str;generation:int;state:str
            native_admitted:bool=False;trading_authorized:bool=False
        e.LabAuthorityStatus=LabAuthorityStatus
        self.old_package=sys.modules.get("unified_system")
        self.old_e=sys.modules.get("unified_system.lab_writer_authority")
        sys.modules["unified_system"]=package
        sys.modules["unified_system.lab_writer_authority"]=e
    def tearDown(self):
        for name,old in (
            ("unified_system",self.old_package),
            ("unified_system.lab_writer_authority",self.old_e)):
            if old is None:sys.modules.pop(name,None)
            else:sys.modules[name]=old
    def make(self,*,authority=None,journal=None,writer=None,transport=None):
        t=transport or Transport()
        w=writer or Writer()
        j=journal or Journal()
        a=authority or Authority()
        c=ContinuousLabCollector(transport=t,writer_factory=w,
                                  journal=j,authority=a)
        return c,t,w,j,a

    def test_content_id_is_hash_of_validated_canonical_record(self):
        # Validator independently owns the complete provenance contract.
        # This unit only checks the B collector's binding to its exact output.
        item=dict(symbol="BTCUSDT",start_ms=60000,
                  dataset_fingerprint="a"*64,status="PARTIAL",
                  source_identity_verified=True,execution_authority=False)
        with patch("market_data_v2.qualified_read_contract.validate_minute",
                   return_value=item):
            m=_minute({"symbol":"BTCUSDT"},digest(item))
            self.assertEqual(m.content_id,digest(item))
            self.assertEqual(m.fingerprint,"a"*64)
            with self.assertRaisesRegex(
                    CollectorRejected,"CONTENT_ID_CANONICAL_RECORD_MISMATCH"):
                _minute({"symbol":"BTCUSDT"},"0"*64)

    def test_readonly_start_without_unresolved_pending(self):
        c,t,w,j,a=self.make()
        self.assertEqual(asyncio.run(c.begin()),"READ_ONLY_READY")
        self.assertEqual(c.state,"READY")
        self.assertEqual(j.calls,["pending","checkpoint"])
        self.assertEqual(w.calls,0)

    def test_fresh_collector_reads_durable_unresolved_pending(self):
        c,t,w,j,a=self.make(journal=Journal(pending=pending()))
        self.assertEqual(asyncio.run(c.begin()),"RECOVERY_REQUIRED")
        self.assertEqual(c.state,"HALTED")
        self.assertEqual(c.pending["content_id"],"c"*64)
        self.assertEqual(j.calls,["pending"])
        self.assertEqual(w.calls,0)

    def test_readonly_e_status_never_admits_write(self):
        c,t,w,j,a=self.make()
        asyncio.run(c.begin())
        with self.assertRaisesRegex(CollectorRejected,"E_NATIVE_WRITER_NOT_ADMITTED"):
            asyncio.run(c.deliver({},content_id="0"*64))
        self.assertEqual(c.state,"HALTED")
        self.assertEqual(w.calls,0)
        self.assertNotIn("append",j.calls)

    def test_even_caller_writer_grant_cannot_override_e_denial(self):
        c,t,w,j,a=self.make()
        c.writer_grant=object()
        asyncio.run(c.begin())
        with self.assertRaisesRegex(CollectorRejected,"E_NATIVE_WRITER_NOT_ADMITTED"):
            asyncio.run(c.deliver({},content_id="0"*64))
        self.assertEqual(w.calls,0)

    def test_stale_journal_generation_denies_before_c_journal_read(self):
        j=Journal()
        j.generation=2
        j.backend_pid=555
        c,t,w,j,a=self.make(journal=j)
        with self.assertRaisesRegex(CollectorRejected,"JOURNAL_OWNER_BACKEND_MISMATCH"):
            asyncio.run(c.begin())
        self.assertEqual(c.state,"HALTED")
        self.assertEqual(j.calls,[])
        self.assertEqual(w.calls,0)

    def test_journal_missing_bound_backend_pid_denies(self):
        j=Journal()
        j.generation=1
        j.backend_pid=None
        c,t,w,j,a=self.make(journal=j)
        with self.assertRaisesRegex(CollectorRejected,"JOURNAL_OWNER_BACKEND_MISMATCH"):
            asyncio.run(c.begin())
        self.assertEqual(c.state,"HALTED")
        self.assertEqual(j.calls,[])
        self.assertEqual(w.calls,0)

    def test_new_owner_generation_and_backend_readonly_begin(self):
        j=Journal()
        j.generation=1
        j.backend_pid=555
        c,t,w,j,a=self.make(journal=j)
        self.assertEqual(asyncio.run(c.begin()),"READ_ONLY_READY")
        self.assertEqual(j.calls,["pending","checkpoint"])
    def test_not_async_e_fails_closed(self):
        class Bad:
            def check(self):return _e_status()
        c,t,w,j,a=self.make(authority=Bad())
        with self.assertRaisesRegex(CollectorRejected,"ROOT_E_AUTHORITY_UNVERIFIED"):
            asyncio.run(c.begin())
        self.assertEqual(c.state,"HALTED")

    def test_fake_boolean_and_dict_do_not_count_as_status(self):
        for value in (True,{"native_admitted":True},"READY"):
            c,t,w,j,a=self.make(authority=Authority(value))
            with self.subTest(value=value):
                with self.assertRaisesRegex(CollectorRejected,"E_STATUS_REJECTED"):
                    asyncio.run(c.begin())

    def test_e_claim_native_admitted_true_rejected(self):
        c,t,w,j,a=self.make(authority=Authority(
            _e_status(native_admitted=True)))
        with self.assertRaisesRegex(CollectorRejected,"E_STATUS_REJECTED"):
            asyncio.run(c.begin())

    def test_epoch_rotation_and_revoke_fail_closed(self):
        a=Authority()
        c,t,w,j,a=self.make(authority=a)
        asyncio.run(c.begin())
        a.status=_e_status(epoch="b"*64)
        with self.assertRaisesRegex(CollectorRejected,"E_EPOCH_CHANGED"):
            asyncio.run(c.deliver({},content_id="0"*64))
        self.assertEqual(c.state,"HALTED")

    def test_readonly_status_not_sufficient_to_reconcile_pending(self):
        c,t,w,j,a=self.make(journal=Journal(pending=pending()))
        asyncio.run(c.begin())
        with self.assertRaisesRegex(CollectorRejected,"RECOVERY_REQUIRES_FRESH_ROOT_COHORT"):
            asyncio.run(c.reconcile_after_restart(fresh_authority=Authority(),fresh_grant=None))
        self.assertEqual(c.pending["content_id"],"c"*64)
        self.assertEqual(w.calls,0)

    def test_feed_is_never_iterated_without_real_e_grant(self):
        touched=[]
        async def feed():
            touched.append("CONNECTED")
            yield ({}, "a"*64)
        c,t,w,j,a=self.make()
        asyncio.run(c.begin())
        with self.assertRaisesRegex(CollectorRejected,"E_NATIVE_WRITER_NOT_ADMITTED"):
            asyncio.run(c.pump_existing_grid_feed(feed()))
        self.assertEqual(touched,[])
        self.assertEqual(w.calls,0)
    def test_no_transport_on_gap_when_not_admitted(self):
        c,t,w,j,a=self.make()
        asyncio.run(c.begin())
        with self.assertRaisesRegex(CollectorRejected,"NO_GAP"):
            asyncio.run(c.recover_gap())
        self.assertEqual(t.calls,0)

    def test_corrupt_durable_pending_denied(self):
        x=pending();x["content_id"]="INVALID"
        c,t,w,j,a=self.make(journal=Journal(pending=x))
        with self.assertRaisesRegex(CollectorRejected,"INVALID_CONTENT_ID"):
            asyncio.run(c.begin())
        self.assertEqual(w.calls,0)

    def test_in_place_rebind_is_rejected_before_touching_old_backend(self):
        j=Journal(pending=pending())
        c,t,w,j,a=self.make(journal=j)
        asyncio.run(c.begin())
        calls_before=list(j.calls)
        with self.assertRaisesRegex(CollectorRejected,"RECOVERY_REQUIRES_FRESH_ROOT_COHORT"):
            asyncio.run(c.reconcile_after_restart(fresh_authority=Authority(),fresh_grant=object()))
        self.assertEqual(j.calls,calls_before)
        self.assertIs(c.journal,j)
        self.assertIs(c.authority,a)
        self.assertEqual(w.calls,0)

    def test_new_instance_recovery_requires_true_extinction_types(self):
        c,t,w,j,a=self.make(journal=Journal(pending=pending()))
        asyncio.run(c.begin())
        with self.assertRaisesRegex(CollectorRejected,"ROOT_EXTINCTION_WITNESS_NOT_AVAILABLE"):
            asyncio.run(c.recover_durable_pending(
                previous_generation=1,previous_epoch="a"*64,
                old_backend_extinct=True,old_process_extinct=True))
        self.assertIsNotNone(c.pending)
        self.assertNotIn("clear",j.calls)
    def test_restart_without_trusted_e_capability_never_clears_pending(self):
        c,t,w,j,a=self.make(journal=Journal(pending=pending()))
        asyncio.run(c.begin())
        with self.assertRaisesRegex(CollectorRejected,"RECOVERY_REQUIRES_FRESH_ROOT_COHORT"):
            asyncio.run(c.reconcile_after_restart(fresh_authority=None,fresh_grant=None))
        self.assertIsNotNone(c.pending)
        self.assertNotIn("clear",j.calls)

if __name__=="__main__":unittest.main()
