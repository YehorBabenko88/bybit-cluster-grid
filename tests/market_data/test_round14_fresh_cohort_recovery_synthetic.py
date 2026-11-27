"""Round 14 SYNTHETIC fresh-collector recovery matrix.

These are isolated B state-machine tests. The E authority/grant and extinction
classes below exist ONLY inside this test; they are deliberately forgeable and
are NEVER native Root, Consul, Windows, PostgreSQL, WAL or Bybit evidence.
Production E does not currently issue RootBackendExtinction/RootProcessExtinction.
No DB connection, transport session, service, or trading action is created.
"""
import asyncio
import dataclasses
import sys
import types
import unittest

from grid.canonical_lab_continuous_collector import (
    ContinuousLabCollector, CollectorRejected,
)

OLD_EPOCH = "a" * 64
NEW_EPOCH = "b" * 64
STREAM = "grid/BTCUSDT/1m"


def pending_identity():
    return dict(
        symbol="BTCUSDT", start_ms=60000, fingerprint="f" * 64,
        content_id="c" * 64, generation=1, token=7,
        source_sha256="d" * 64, schema_sha256="e" * 64,
    )


def minute_identity(value):
    return (value["symbol"], value["start_ms"], value["fingerprint"],
            value["content_id"])


class DurableJournal:
    def __init__(self, *, committed=False, cursor=False, generation=2,
                 backend_pid=302, lost_cursor_ack=False,
                 lost_pending_clear_ack=False):
        self.stream_id = STREAM
        self.generation = generation
        self.backend_pid = backend_pid
        self._pending = pending_identity()
        self._stored = committed
        self._cursor = cursor
        self._lost_cursor_ack = lost_cursor_ack
        self._lost_pending_clear_ack = lost_pending_clear_ack
        self.calls = []

    async def pending(self):
        self.calls.append("pending")
        return self._pending

    async def checkpoint(self):
        self.calls.append("checkpoint")
        if self._cursor:
            return dict(self._pending)
        return None

    async def append_pending(self, minute):
        raise AssertionError("RECOVERY_MUST_NOT_APPEND_PENDING")

    async def readback(self, minute):
        self.calls.append("readback")
        assert minute_identity(self._pending) == (
            minute.symbol, minute.start_ms, minute.fingerprint,
            minute.content_id)
        return {"status": "MATCH" if self._stored else "MISSING"}

    async def commit_cursor(self, minute):
        self.calls.append("commit_cursor")
        assert self._stored
        assert not self._cursor
        self._cursor = True
        if self._lost_cursor_ack:
            self._lost_cursor_ack = False
            raise TimeoutError("SYNTHETIC_LOST_CURSOR_ACK")
        return {"cursor": minute.start_ms}

    async def exact_existing_checkpoint(self, minute):
        self.calls.append("exact")
        assert minute_identity(self._pending) == (
            minute.symbol, minute.start_ms, minute.fingerprint,
            minute.content_id)
        return {"state": "EXACT_ALREADY_ACKNOWLEDGED"
                if self._cursor else "UNRESOLVED"}

    async def clear_pending(self, minute):
        self.calls.append("clear_pending")
        assert self._cursor and self._pending is not None
        self._pending = None
        if self._lost_pending_clear_ack:
            self._lost_pending_clear_ack = False
            raise TimeoutError("SYNTHETIC_LOST_CLEAR_ACK")
        return True


class NoTransport:
    def __init__(self):
        self.calls = 0

    async def backfill(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("RECOVERY_MUST_NOT_OPEN_BACKFILL")


class NoWriterFactory:
    def __init__(self):
        self.calls = 0

    async def __call__(self, minute):
        self.calls += 1
        raise AssertionError("RECOVERY_MUST_NOT_REWRITE_MARKET_ROW")


class Round14FreshCohort(unittest.TestCase):
    def setUp(self):
        package = types.ModuleType("unified_system")
        package.__path__ = []
        authority_mod = types.ModuleType(
            "unified_system.lab_writer_authority")
        revoke_mod = types.ModuleType("unified_system.lab_writer_revoke")

        @dataclasses.dataclass(frozen=True)
        class LabAuthorityStatus:
            schema: str
            scope: str
            epoch: str
            generation: int
            state: str
            native_admitted: bool = False
            trading_authorized: bool = False

        class LabWriterGrant:
            def __init__(self, epoch):
                self.epoch = epoch

            async def require_write_current(self):
                return self

        class RootBackendExtinction:
            pass

        class RootProcessExtinction:
            pass

        authority_mod.LabAuthorityStatus = LabAuthorityStatus
        authority_mod.LabWriterGrant = LabWriterGrant
        revoke_mod.RootBackendExtinction = RootBackendExtinction
        revoke_mod.RootProcessExtinction = RootProcessExtinction

        names = ("unified_system", "unified_system.lab_writer_authority",
                 "unified_system.lab_writer_revoke")
        self._prior = {name: sys.modules.get(name) for name in names}
        sys.modules[names[0]] = package
        sys.modules[names[1]] = authority_mod
        sys.modules[names[2]] = revoke_mod
        self._status_type = LabAuthorityStatus
        self._grant_type = LabWriterGrant
        self._backend_type = RootBackendExtinction
        self._process_type = RootProcessExtinction

    def tearDown(self):
        for name, previous in self._prior.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous

    def make(self, journal, *, epoch=NEW_EPOCH, generation=2,
             writer_grant=True):
        class Authority:
            async def check(inner_self):
                return self._status_type(
                    schema="unified.lab-root-writer-authority.v1",
                    scope="ISOLATED_LAB_ONLY",
                    epoch=epoch,
                    generation=generation,
                    state="READ_ONLY_REVALIDATED_NOT_NATIVE",
                )

        transport = NoTransport()
        writer = NoWriterFactory()
        grant = self._grant_type(epoch) if writer_grant else None
        collector = ContinuousLabCollector(
            transport=transport, writer_factory=writer, journal=journal,
            authority=Authority(), writer_grant=grant, stream_id=STREAM)
        return collector, transport, writer

    async def attempt(self, collector, *, previous_generation=1,
                      previous_epoch=OLD_EPOCH, backend=None, process=None):
        return await collector.recover_durable_pending(
            previous_generation=previous_generation,
            previous_epoch=previous_epoch,
            old_backend_extinct=backend if backend is not None
            else self._backend_type(),
            old_process_extinct=process if process is not None
            else self._process_type(),
        )

    def test_unknown_commit_exact_row_with_fresh_journal_no_rewrite(self):
        async def run():
            old = DurableJournal(committed=True, generation=1,
                                 backend_pid=301)
            fresh = DurableJournal(committed=True)
            c, transport, writer = self.make(fresh)
            self.assertEqual(await c.begin(), "RECOVERY_REQUIRED")
            self.assertEqual(await self.attempt(c), "RECOVERED_BY_EXACT_ROW")
            self.assertEqual(c.state, "READY")
            self.assertIsNone(c.pending)
            self.assertEqual(fresh.calls.count("commit_cursor"), 1)
            self.assertEqual(fresh.calls.count("clear_pending"), 1)
            self.assertEqual(old.calls, [])
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_lost_clear_ack_cursor_already_present_no_second_cas(self):
        async def run():
            fresh = DurableJournal(committed=True, cursor=True)
            c, transport, writer = self.make(fresh)
            self.assertEqual(await c.begin(), "RECOVERY_REQUIRED")
            self.assertEqual(await self.attempt(c),
                             "CURSOR_ALREADY_ACKNOWLEDGED")
            self.assertEqual(fresh.calls.count("commit_cursor"), 0)
            self.assertEqual(fresh.calls.count("clear_pending"), 1)
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_missing_commit_row_preserves_pending_and_never_cas(self):
        async def run():
            fresh = DurableJournal(committed=False)
            c, transport, writer = self.make(fresh)
            await c.begin()
            with self.assertRaisesRegex(
                    CollectorRejected, "UNKNOWN_COMMIT_UNRESOLVED"):
                await self.attempt(c)
            self.assertEqual(c.state, "HALTED")
            self.assertIsNotNone(c.pending)
            self.assertNotIn("commit_cursor", fresh.calls)
            self.assertNotIn("clear_pending", fresh.calls)
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_lost_cursor_ack_never_automatically_retries_cas(self):
        async def run():
            fresh = DurableJournal(committed=True, lost_cursor_ack=True)
            c, transport, writer = self.make(fresh)
            await c.begin()
            with self.assertRaisesRegex(
                    TimeoutError, "SYNTHETIC_LOST_CURSOR_ACK"):
                await self.attempt(c)
            self.assertEqual(c.state, "HALTED")
            self.assertIsNotNone(c.pending)
            self.assertEqual(fresh.calls.count("commit_cursor"), 1)
            self.assertNotIn("clear_pending", fresh.calls)
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_lost_pending_clear_ack_never_rewrites_or_retries(self):
        async def run():
            fresh = DurableJournal(
                committed=True, cursor=True, lost_pending_clear_ack=True)
            c, transport, writer = self.make(fresh)
            await c.begin()
            with self.assertRaisesRegex(
                    TimeoutError, "SYNTHETIC_LOST_CLEAR_ACK"):
                await self.attempt(c)
            self.assertEqual(c.state, "HALTED")
            self.assertEqual(fresh.calls.count("commit_cursor"), 0)
            self.assertEqual(fresh.calls.count("clear_pending"), 1)
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_old_generation_on_fresh_owner_is_rejected_before_read(self):
        async def run():
            fresh = DurableJournal(generation=1, backend_pid=301)
            c, transport, writer = self.make(fresh, generation=2)
            with self.assertRaisesRegex(
                    CollectorRejected, "JOURNAL_OWNER_BACKEND_MISMATCH"):
                await c.begin()
            self.assertEqual(fresh.calls, [])
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_no_epoch_rotation_prevents_recovery_sql(self):
        async def run():
            fresh = DurableJournal(committed=True)
            c, transport, writer = self.make(fresh, epoch=OLD_EPOCH)
            await c.begin()
            with self.assertRaisesRegex(
                    CollectorRejected, "ROOT_GENERATION_EPOCH_NOT_ROTATED"):
                await self.attempt(c)
            self.assertNotIn("exact", fresh.calls)
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_missing_typed_grant_prevents_recovery_sql(self):
        async def run():
            fresh = DurableJournal(committed=True)
            c, transport, writer = self.make(fresh, writer_grant=False)
            await c.begin()
            with self.assertRaisesRegex(
                    CollectorRejected, "E_NATIVE_WRITER_NOT_ADMITTED"):
                await self.attempt(c)
            self.assertNotIn("exact", fresh.calls)
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_boolean_or_dict_extinction_is_rejected_before_sql(self):
        async def run():
            for fake in (True, False, {"state": "EXTINCT"}, object()):
                fresh = DurableJournal(committed=True)
                c, transport, writer = self.make(fresh)
                await c.begin()
                with self.assertRaisesRegex(
                        CollectorRejected, "ROOT_EXTINCTION_WITNESS_REQUIRED"):
                    await self.attempt(c, backend=fake, process=fake)
                self.assertNotIn("exact", fresh.calls)
                self.assertEqual(writer.calls, 0)
                self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_unrotated_generation_never_reconciles_even_if_epoch_changes(self):
        async def run():
            fresh = DurableJournal(committed=True, generation=1)
            c, transport, writer = self.make(fresh, generation=1)
            await c.begin()
            with self.assertRaisesRegex(
                    CollectorRejected, "ROOT_GENERATION_EPOCH_NOT_ROTATED"):
                await self.attempt(c)
            self.assertNotIn("exact", fresh.calls)
            self.assertNotIn("clear_pending", fresh.calls)
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_mismatching_previous_generation_preserves_pending(self):
        async def run():
            fresh = DurableJournal(committed=True)
            c, transport, writer = self.make(fresh)
            await c.begin()
            with self.assertRaisesRegex(
                    CollectorRejected, "PENDING_OLD_GENERATION_MISMATCH"):
                await self.attempt(c, previous_generation=0 + 3)
            self.assertIsNotNone(c.pending)
            self.assertNotIn("exact", fresh.calls)
            self.assertNotIn("clear_pending", fresh.calls)
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_old_epoch_receipt_shape_is_not_authority_without_new_grant(self):
        async def run():
            fresh = DurableJournal(committed=True, cursor=True)
            c, transport, writer = self.make(fresh, writer_grant=False)
            await c.begin()
            with self.assertRaisesRegex(
                    CollectorRejected, "E_NATIVE_WRITER_NOT_ADMITTED"):
                await self.attempt(c, backend=self._backend_type(),
                                   process=self._process_type())
            self.assertIsNotNone(c.pending)
            self.assertEqual(fresh.calls, ["pending"])
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_wrong_backend_identity_denied_before_pending_read(self):
        async def run():
            for bad_pid in (None, 0, True, "302"):
                fresh = DurableJournal(committed=True, backend_pid=bad_pid)
                c, transport, writer = self.make(fresh)
                with self.subTest(bad_pid=bad_pid):
                    with self.assertRaisesRegex(
                            CollectorRejected, "JOURNAL_OWNER_BACKEND_MISMATCH"):
                        await c.begin()
                self.assertEqual(fresh.calls, [])
                self.assertEqual(writer.calls, 0)
                self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_duplicate_attempt_on_same_collector_is_rejected_after_ack(self):
        async def run():
            fresh = DurableJournal(committed=True, cursor=True)
            c, transport, writer = self.make(fresh)
            await c.begin()
            self.assertEqual(await self.attempt(c),
                             "CURSOR_ALREADY_ACKNOWLEDGED")
            with self.assertRaisesRegex(
                    CollectorRejected, "DURABLE_PENDING_REQUIRED"):
                await self.attempt(c)
            self.assertEqual(fresh.calls.count("clear_pending"), 1)
            self.assertEqual(fresh.calls.count("commit_cursor"), 0)
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())

    def test_stop_latch_prevents_recovery_sql_even_with_dummy_types(self):
        async def run():
            fresh = DurableJournal(committed=True)
            c, transport, writer = self.make(fresh)
            await c.begin()
            c.stop()
            with self.assertRaisesRegex(
                    CollectorRejected, "COLLECTOR_STOP_LATCHED"):
                await self.attempt(c)
            self.assertNotIn("exact", fresh.calls)
            self.assertEqual(writer.calls, 0)
            self.assertEqual(transport.calls, 0)
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
