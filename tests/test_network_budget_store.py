"""MODELED_FENCE: local persistence only, never real DCS/native I/O admission."""
import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from grid.network_budget_store import NetworkBudgetStore, BudgetStoreBlocked

NODES = ('LS5', 'PC1', 'PC2', 'PC3', 'PC4', 'LS7')
SYMBOLS = ('BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'XRPUSDT', 'BNBUSDT',
           'DOGEUSDT', 'ADAUSDT', 'AVAXUSDT', 'LINKUSDT', 'DOTUSDT')


class ModeledOwner:
    def __init__(self, root):
        self.root = root
        self.now = 0
        self.live = True
        self.root_live = True
        self.epoch = 1

    def admit_root(self, path):
        return self.live and self.root_live and path == self.root

    async def guard(self):
        if not self.live:
            raise ValueError('MODELED_FENCE_REVOKED')
        return {'owner': 'LS5', 'epoch': self.epoch}

    def clock(self):
        return self.now

    def args(self):
        return dict(installation_id='MODELED_FENCE', guard=self.guard,
                    admit_root=self.admit_root, clock_ms=self.clock)


async def create(root, **kwargs):
    root.mkdir()
    owner = ModeledOwner(root)
    return owner, await NetworkBudgetStore.create(root, **owner.args(), **kwargs)


async def granted_read(store, owner):
    await store.apply('open', 'PC1', 'grid', 'history_get', 1)
    owner.now = 1000
    connection = (await store.apply('grant'))['connection']
    await store.apply('read', 'PC1', 'grid', connection, 65536, 2)
    return await store.apply('grant')


async def consume(store, permit):
    return await store.apply('consume_read', 'PC1', 'grid', permit['connection'],
                             permit['read_id'], permit['read_sequence'])


def test_restart_preserves_spent_credit_and_uncertain_slots(tmp_path):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        permit = await granted_read(store, owner)
        await consume(store, permit)
        before = store.snapshot()
        assert before['runtime_admission'] == 'BLOCKED_ROLLBACK_ANCHOR_NOT_WIRED'
        assert before['offset'] == (owner.root / 'budget.journal').stat().st_size
        await store.close()
        owner.now = 100000
        reopened = await NetworkBudgetStore.open(owner.root, **owner.args())
        try:
            after = reopened.snapshot()
            assert after['revision'] > before['revision']
            for field in ('charged', 'research_units', 'http_units', 'high_units'):
                assert after['model'][field] == before['model'][field]
            assert after['model']['connections'][permit['connection']]['uncertain'] is True
            assert after['model']['outstanding'] == {}
            with pytest.raises(ValueError):
                await consume(reopened, permit)
            assert len(reopened.snapshot()['model']['connections']) == 1
        finally:
            await reopened.close()
    asyncio.run(scenario())


def test_native_process_crash_keeps_durable_debit_and_slot(tmp_path):
    root = tmp_path / 'crash-meter';root.mkdir()
    repo = Path(__file__).resolve().parents[1]
    program = """
import sys,asyncio,os
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from grid.network_budget_store import NetworkBudgetStore
root=Path(sys.argv[2]);clock=[0]
async def guard():return {'owner':'LS5','epoch':1}
async def scenario():
 store=await NetworkBudgetStore.create(root,installation_id='MODELED_FENCE',guard=guard,admit_root=lambda path:path==root,clock_ms=lambda:clock[0])
 await store.apply('open','PC1','grid','history_get',1)
 clock[0]=1000
 connection=(await store.apply('grant'))['connection']
 await store.apply('read','PC1','grid',connection,65536,2)
 permit=await store.apply('grant')
 await store.apply('consume_read','PC1','grid',connection,permit['read_id'],permit['read_sequence'])
 os._exit(23)
asyncio.run(scenario())
"""
    env = {name: os.environ[name] for name in ('SYSTEMROOT', 'WINDIR', 'TEMP', 'TMP') if name in os.environ}
    result = subprocess.run([sys.executable, '-I', '-S', '-B', '-c', program, str(repo), str(root)],
                            env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
    assert result.returncode == 23, (result.returncode, result.stderr[:1024])
    async def recover():
        owner = ModeledOwner(root);owner.now = 1000
        store = await NetworkBudgetStore.open(root, **owner.args())
        try:
            model = store.snapshot()['model']
            assert model['charged']['research'] == 65536
            assert len(model['connections']) == 1
            assert next(iter(model['connections'].values()))['uncertain'] is True
            assert not model['outstanding']
        finally:await store.close()
    asyncio.run(recover())


@pytest.mark.parametrize('failure', ['before_fsync', 'after_fsync'])
def test_consume_durability_failure_never_returns_permission(tmp_path, monkeypatch, failure):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        permit = await granted_read(store, owner)
        original = os.fsync
        def fail(fd):
            if failure == 'after_fsync':
                original(fd)
            raise OSError('modeled uncertain fsync')
        with monkeypatch.context() as patch:
            patch.setattr(os, 'fsync', fail)
            with pytest.raises(BudgetStoreBlocked):
                await consume(store, permit)
        with pytest.raises(BudgetStoreBlocked):
            await store.apply('grant')
        await store.close()
        # A complete uncertain write may be present; neither outcome restores
        # a usable old read or creates replacement budget on restart.
        reopened = await NetworkBudgetStore.open(owner.root, **owner.args())
        try:
            assert reopened.snapshot()['model']['charged']['research'] == 65536
            assert reopened.snapshot()['model']['connections'][permit['connection']]['uncertain']
            with pytest.raises(ValueError):
                await consume(reopened, permit)
        finally:
            await reopened.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('partial', [False, True])
def test_failed_or_short_journal_write_never_yields_receipt(tmp_path, partial):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        permit = await granted_read(store, owner)
        original = store._file
        class FailedWriter:
            def __getattr__(self, name):return getattr(original, name)
            def write(self, raw):
                if partial:return original.write(raw[:len(raw)//2])
                raise OSError('modeled write failure')
        store._file = FailedWriter()
        with pytest.raises(BudgetStoreBlocked):await consume(store, permit)
        with pytest.raises(BudgetStoreBlocked):await store.apply('grant')
        await store.close()
        before = (owner.root / 'budget.journal').read_bytes()
        if partial:
            with pytest.raises(BudgetStoreBlocked):
                await NetworkBudgetStore.open(owner.root, **owner.args())
            assert (owner.root / 'budget.journal').read_bytes() == before
        else:
            reopened = await NetworkBudgetStore.open(owner.root, **owner.args())
            assert reopened.snapshot()['model']['connections'][permit['connection']]['uncertain']
            await reopened.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('confirmed', [False, True])
def test_complete_and_close_never_refund_spent_allowance(tmp_path, confirmed):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        permit = await granted_read(store, owner)
        await consume(store, permit)
        before = store.snapshot()['model']
        assert await store.apply('complete_read', 'PC1', 'grid', permit['connection'],
                                 permit['read_id'], permit['read_sequence'],
                                 confirmed_stopped=confirmed) is confirmed
        with pytest.raises(ValueError):
            await store.apply('complete_read', 'PC1', 'grid', permit['connection'],
                              permit['read_id'], permit['read_sequence'], confirmed_stopped=True)
        await store.apply('close', permit['connection'], confirmed=confirmed)
        after = store.snapshot()['model']
        assert after['charged'] == before['charged']
        assert after['research_units'] == before['research_units']
        assert (permit['connection'] in after['connections']) is not confirmed
        await store.close()
    asyncio.run(scenario())


def test_success_receipt_follows_durable_consumed_record(tmp_path, monkeypatch):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        permit = await granted_read(store, owner)
        original = os.fsync
        observed = []
        def inspect(fd):
            original(fd)
            raw = (owner.root / 'budget.journal').read_bytes().splitlines()[-1]
            observed.append(json.loads(raw)['model']['outstanding'][permit['connection']]['status'])
        with monkeypatch.context() as patch:
            patch.setattr(os, 'fsync', inspect)
            receipt = await consume(store, permit)
        assert receipt['status'] == 'IN_FLIGHT' and observed == ['IN_FLIGHT']
        with pytest.raises(ValueError):
            await consume(store, permit)
        await store.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('during_write', [False, True])
def test_expired_read_never_returns_consumption_receipt(tmp_path, monkeypatch, during_write):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        permit = await granted_read(store, owner)
        if during_write:
            original = os.fsync
            def slow(fd):
                original(fd)
                owner.now = 1500
            with monkeypatch.context() as patch:
                patch.setattr(os, 'fsync', slow)
                with pytest.raises(BudgetStoreBlocked):
                    await consume(store, permit)
        else:
            owner.now = 1500
            with pytest.raises(ValueError):
                await consume(store, permit)
        await store.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('change', ['epoch', 'revoked'])
def test_postwrite_fence_change_blocks_receipt_and_faults_owner(tmp_path, monkeypatch, change):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        permit = await granted_read(store, owner)
        original = os.fsync
        def revoke(fd):
            original(fd)
            if change == 'epoch':owner.epoch += 1
            else:owner.live = False
        with monkeypatch.context() as patch:
            patch.setattr(os, 'fsync', revoke)
            with pytest.raises(BudgetStoreBlocked):
                await consume(store, permit)
        with pytest.raises(BudgetStoreBlocked):
            await store.apply('grant')
        await store.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('callback', ['guard', 'clock'])
def test_final_callbacks_cannot_revoke_root_and_publish_receipt(tmp_path, monkeypatch, callback):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        permit = await granted_read(store, owner)
        original = os.fsync
        durable = [False];clocks = [0]
        def flushed(fd):
            original(fd);durable[0] = True
        async def guard():
            value = await owner.guard()
            if durable[0] and callback == 'guard':owner.root_live = False
            return value
        def clock():
            if durable[0]:
                clocks[0] += 1
                if callback == 'clock' and clocks[0] == 2:owner.root_live = False
            return owner.now
        store.guard = guard;store.clock_ms = clock
        with monkeypatch.context() as patch:
            patch.setattr(os, 'fsync', flushed)
            with pytest.raises(BudgetStoreBlocked):await consume(store, permit)
        assert owner.root_live is False
        assert store.snapshot()['faulted'] is True
        # The committed debit is not rolled back even though publication failed.
        record = json.loads((owner.root / 'budget.journal').read_bytes().splitlines()[-1])
        assert record['model']['outstanding'][permit['connection']]['status'] == 'IN_FLIGHT'
        await store.close()
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['truncated', 'tampered'])
def test_restart_rejects_corrupt_log_without_repair(tmp_path, kind):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        await granted_read(store, owner)
        await store.close()
        path = owner.root / 'budget.journal'
        raw = path.read_bytes()
        raw = raw[:-1] if kind == 'truncated' else raw.replace(b'65536', b'65535', 1)
        path.write_bytes(raw)
        with pytest.raises(BudgetStoreBlocked):
            await NetworkBudgetStore.open(owner.root, **owner.args())
        assert path.read_bytes() == raw
    asyncio.run(scenario())


def test_exclusive_owner_foreign_state_and_closed_operations(tmp_path):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        with pytest.raises(BudgetStoreBlocked):
            await NetworkBudgetStore.open(owner.root, **owner.args())
        for method in ('restore', 'snapshot', '__init__', '_advance', 'arbitrary_io'):
            with pytest.raises(BudgetStoreBlocked):await store.apply(method)
        with pytest.raises(BudgetStoreBlocked):await store.apply('grant', now_ms=999999)
        await store.close()
        with pytest.raises(BudgetStoreBlocked):
            await NetworkBudgetStore.create(owner.root, **owner.args())
        foreign = tmp_path / 'foreign';foreign.mkdir();(foreign / 'data').write_bytes(b'foreign')
        other = ModeledOwner(foreign)
        with pytest.raises(BudgetStoreBlocked):
            await NetworkBudgetStore.create(foreign, **other.args())
        assert (foreign / 'data').read_bytes() == b'foreign'
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['boolean_epoch', 'installation', 'unknown_field'])
def test_marker_must_preserve_closed_owner_identity(tmp_path, kind):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        await store.close()
        path = owner.root / 'owner.json'
        value = json.loads(path.read_bytes())
        if kind == 'boolean_epoch':value['fence']['epoch'] = True
        elif kind == 'installation':value['installation_id'] = 'OTHER_INSTALLATION'
        else:value['grant'] = True
        raw = json.dumps(value, sort_keys=True, separators=(',', ':')).encode()
        path.write_bytes(raw)
        with pytest.raises(BudgetStoreBlocked):
            await NetworkBudgetStore.open(owner.root, **owner.args())
        assert path.read_bytes() == raw
    asyncio.run(scenario())


def test_unreadable_journal_blocks_without_adoption_and_releases_owner_lock(tmp_path, monkeypatch):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        await store.close()
        before = (owner.root / 'budget.journal').read_bytes()
        original = Path.open
        def denied(path, *args, **kwargs):
            if path == owner.root / 'budget.journal':raise PermissionError('modeled unreadable journal')
            return original(path, *args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(Path, 'open', denied)
            with pytest.raises(BudgetStoreBlocked):
                await NetworkBudgetStore.open(owner.root, **owner.args())
        assert (owner.root / 'budget.journal').read_bytes() == before
        reopened = await NetworkBudgetStore.open(owner.root, **owner.args())
        await reopened.close()
    asyncio.run(scenario())


def test_truthy_root_admission_cannot_create_owner_state(tmp_path):
    async def scenario():
        root = tmp_path / 'meter';root.mkdir()
        owner = ModeledOwner(root)
        args = owner.args();args['admit_root'] = lambda _: 1
        with pytest.raises(BudgetStoreBlocked):
            await NetworkBudgetStore.create(root, **args)
        assert list(root.iterdir()) == []
    asyncio.run(scenario())


def test_capacity_and_clock_rollback_fail_closed(tmp_path):
    async def scenario():
        owner, store = await create(tmp_path / 'meter', max_bytes=8192)
        count = 0
        with pytest.raises(BudgetStoreBlocked):
            while count < 100:
                await store.apply('grant');count += 1
        assert count < 100
        await store.close()
        owner.now = -1
        with pytest.raises(BudgetStoreBlocked):
            await NetworkBudgetStore.open(owner.root, **owner.args())
    asyncio.run(scenario())


def test_six_node_ten_symbol_fixture_retains_policy_queue(tmp_path):
    async def scenario():
        owner, store = await create(tmp_path / 'meter')
        sequences = dict.fromkeys(NODES, 0)
        tickets = {}
        for index, symbol in enumerate(SYMBOLS):
            node = NODES[index % len(NODES)];sequences[node] += 1
            ticket = await store.apply('open', node, 'grid', 'history_get', sequences[node])
            tickets[ticket] = (node, symbol)
        before = store.snapshot()['model']['pending']
        await store.close()
        reopened = await NetworkBudgetStore.open(owner.root, **owner.args())
        try:
            assert reopened.snapshot()['model']['pending'] == before
            assert {v[0] for v in tickets.values()} == set(NODES)
            assert {v[1] for v in tickets.values()} == set(SYMBOLS)
            assert reopened.snapshot()['runtime_admission'].startswith('BLOCKED_')
        finally:await reopened.close()
    asyncio.run(scenario())
