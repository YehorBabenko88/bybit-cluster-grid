"""Local crash-durability primitive, NOT a runtime network grant or authority.

runtime_admission remains BLOCKED_ROLLBACK_ANCHOR_NOT_WIRED. A valid old local
hash chain cannot prove freshness. Future integration must bind {offset,
revision, sha256} to an existing Consul session/lock-index checked transaction
and expected prior anchor CAS, with a consistent read on recovery. A missing,
ahead, behind or uncertain anchor must block; never adopt/reset local state or
put the full 128 KiB model into Consul's 32 KiB control record. That typed
anchor and actual Grid admission are NOT wired here. guard/admit_root are
trusted in-process structural seams, not authenticated DCS qualification.

No sockets, transport callbacks, job scheduler, credit refunds, repair,
compaction or deletion. The owner must admit a private local root/ACL namespace
and this source. OS locking excludes cooperative owners, not privileged or
hostile same-user code. Payload counters are not WAN/TLS/OS byte measurement.
"""
import asyncio
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import stat

from .network_budget_model import BudgetModel, NODES

RUNTIME_ADMISSION = 'BLOCKED_ROLLBACK_ANCHOR_NOT_WIRED'
SCHEMA = 'grid.local-network-budget-store.v1'
MAX_RECORD = 140000
METHODS = frozenset(('open', 'read', 'grant', 'consume_read', 'complete_read',
                     'close', 'renew', 'set_authority', 'feedback', 'observe'))


class BudgetStoreBlocked(ValueError):
    pass


def need(value, reason='BUDGET_STORE_BLOCKED'):
    if value is not True:
        raise BudgetStoreBlocked(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('ascii')


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result)
            result[key] = value
        return result
    value = json.loads(raw, object_pairs_hook=pairs,
                       parse_constant=lambda _: need(False))
    need(canonical(value) == raw)
    return value


def ordinary(path, *, directory=False):
    path = Path(path)
    need(path.is_absolute() and '..' not in path.parts and not str(path).startswith(('\\\\', '//')))
    for item in (*reversed(path.parents), path):
        info = item.lstat()
        need(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 1024)
    info = path.stat()
    need(stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode) and info.st_nlink == 1)
    return [info.st_dev, info.st_ino]


def valid_fence(value):
    return (type(value) is dict and set(value) == {'owner', 'epoch'} and
            type(value['owner']) is str and value['owner'] in NODES and
            type(value['epoch']) is int and 1 <= value['epoch'] < 2**53)


class NetworkBudgetStore:
    """Serialize existing BudgetModel transitions, fsync before LAB receipts.

    The clock is trusted native monotonic milliseconds supplied by the owner.
    An old boot's larger clock blocks recovery; no wall-clock refill workaround
    exists. A changed authority fence cannot automatically adopt this store.
    """
    runtime_admission = RUNTIME_ADMISSION

    def __init__(self, root, installation_id, guard, admit_root, clock_ms):
        need(type(installation_id) is str and re.fullmatch('[A-Za-z0-9_-]{1,80}', installation_id) is not None)
        need(callable(guard) and callable(admit_root) and callable(clock_ms))
        self.root = Path(root)
        self.installation_id = installation_id
        self.guard = guard
        self.admit_root = admit_root
        self.clock_ms = clock_ms
        self._mutex = asyncio.Lock()
        self._lock_file = self._file = None
        self._closed = self._faulted = False
        self._fence = self._marker = None
        self._revision = self._size = 0
        self._sha = '0' * 64
        self._model = None
        self._root_id = ordinary(self.root, directory=True)
        self._admitted()

    def _admitted(self):
        need(self.admit_root(self.root) is True, 'BUDGET_ROOT_ADMISSION_REVOKED')
        need(ordinary(self.root, directory=True) == self._root_id, 'BUDGET_ROOT_CHANGED')

    async def _current(self):
        self._admitted()
        value = await self.guard()
        need(valid_fence(value))
        if self._fence is not None:
            need(value == self._fence, 'BUDGET_FENCE_CHANGED')
        return dict(value)

    def _clock(self):
        value = self.clock_ms()
        need(type(value) is int and 0 <= value < 2**53, 'BUDGET_CLOCK_REJECTED')
        return value

    def _take_lock(self):
        self._lock_file.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(self._lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(self._lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release(self):
        for name in ('_file', '_lock_file'):
            stream = getattr(self, name)
            if stream is not None:
                stream.close()
                setattr(self, name, None)
        self._closed = True

    @classmethod
    async def create(cls, root, *, installation_id, guard, admit_root, clock_ms, max_bytes=8*1024*1024):
        owner = None
        try:
            owner = cls(root, installation_id, guard, admit_root, clock_ms)
            need(type(max_bytes) is int and 4096 <= max_bytes <= 64*1024*1024)
            owner._fence = await owner._current()
            need(not list(owner.root.iterdir()), 'BUDGET_FOREIGN_STATE_NOT_ADOPTED')
            owner._lock_file = (owner.root / 'owner.lock').open('xb+', buffering=0)
            owner._lock_file.write(secrets.token_hex(16).encode('ascii'))
            owner._lock_file.flush();os.fsync(owner._lock_file.fileno())
            owner._take_lock()
            owner._file = (owner.root / 'budget.journal').open('xb+', buffering=0)
            os.fsync(owner._file.fileno())
            marker = dict(schema=SCHEMA, installation_id=installation_id, root_id=owner._root_id,
                          lock_id=ordinary(owner.root / 'owner.lock'),
                          journal_id=ordinary(owner.root / 'budget.journal'),
                          fence=owner._fence, max_bytes=max_bytes)
            owner._marker = canonical(marker)
            with (owner.root / 'owner.json').open('xb') as stream:
                stream.write(owner._marker);stream.flush();os.fsync(stream.fileno())
            owner._marker_id = ordinary(owner.root / 'owner.json')
            owner._max_bytes = max_bytes
            await owner._persist(BudgetModel(now_ms=owner._clock()), 'INITIAL')
            return owner
        except BaseException as exc:
            if owner is not None:owner._release()
            if not isinstance(exc, Exception):raise
            raise BudgetStoreBlocked('BUDGET_CREATE_BLOCKED') from None

    @classmethod
    async def open(cls, root, *, installation_id, guard, admit_root, clock_ms, max_bytes=None):
        owner = None
        try:
            owner = cls(root, installation_id, guard, admit_root, clock_ms)
            lock_id = ordinary(owner.root / 'owner.lock')
            owner._lock_file = (owner.root / 'owner.lock').open('r+b', buffering=0)
            owner._take_lock()
            owner._marker_id = ordinary(owner.root / 'owner.json')
            with (owner.root / 'owner.json').open('rb') as stream:
                owner._marker = stream.read(4097)
            need(len(owner._marker) <= 4096)
            marker = parse(owner._marker)
            need(type(marker) is dict and set(marker) == {'schema', 'installation_id', 'root_id', 'lock_id', 'journal_id', 'fence', 'max_bytes'})
            need(marker['schema'] == SCHEMA and marker['installation_id'] == installation_id)
            need(valid_fence(marker['fence']))
            for name in ('root_id', 'lock_id', 'journal_id'):
                need(type(marker[name]) is list and len(marker[name]) == 2 and
                     all(type(item) is int and item >= 0 for item in marker[name]))
            need(marker['root_id'] == owner._root_id and marker['lock_id'] == lock_id)
            need(type(marker['max_bytes']) is int and 4096 <= marker['max_bytes'] <= 64*1024*1024)
            need(max_bytes is None or max_bytes == marker['max_bytes'])
            owner._max_bytes = marker['max_bytes'];owner._fence = marker['fence']
            await owner._current()
            need(ordinary(owner.root / 'budget.journal') == marker['journal_id'])
            owner._file = (owner.root / 'budget.journal').open('r+b', buffering=0)
            owner._load()
            now = owner._clock()
            need(now >= owner._model.snapshot()['clock_ms'], 'BUDGET_CLOCK_ROLLBACK')
            restored = BudgetModel.restore(owner._model.dumps(), now_ms=now)
            await owner._persist(restored, 'RESTORE')
            return owner
        except BaseException as exc:
            if owner is not None:owner._release()
            if not isinstance(exc, Exception):raise
            raise BudgetStoreBlocked('BUDGET_OPEN_BLOCKED') from None

    def _assets(self):
        self._admitted()
        marker = parse(self._marker)
        need(ordinary(self.root / 'owner.json') == self._marker_id)
        with (self.root / 'owner.json').open('rb') as stream:
            need(stream.read(4097) == self._marker, 'BUDGET_MARKER_CHANGED')
        for name, stream, identity in (('owner.lock', self._lock_file, marker['lock_id']),
                                       ('budget.journal', self._file, marker['journal_id'])):
            need(ordinary(self.root / name) == identity)
            held = os.fstat(stream.fileno())
            need([held.st_dev, held.st_ino] == identity and held.st_nlink == 1)
        need(os.fstat(self._file.fileno()).st_size == self._size, 'BUDGET_JOURNAL_CHANGED')

    def _load(self):
        size = os.fstat(self._file.fileno()).st_size
        need(0 < size <= self._max_bytes)
        self._file.seek(0)
        last_model = None
        while True:
            raw = self._file.readline(MAX_RECORD+1)
            if not raw:break
            need(len(raw) <= MAX_RECORD and raw.endswith(b'\n'))
            value = parse(raw[:-1])
            need(type(value) is dict and set(value) == {'schema', 'revision', 'previous_sha256', 'fence', 'operation', 'model'})
            need(value['schema'] == SCHEMA and type(value['revision']) is int and value['revision'] == self._revision+1)
            need(value['previous_sha256'] == self._sha and value['fence'] == self._fence)
            need(value['operation'] in METHODS | {'INITIAL', 'RESTORE'})
            need((self._revision == 0) == (value['operation'] == 'INITIAL'))
            model_raw = canonical(value['model'])
            # Validate each original snapshot; restore is applied only after
            # the complete chain has been validated, never to infer a grant.
            validated = BudgetModel.restore(model_raw, now_ms=value['model']['clock_ms'])
            last_model = validated
            self._sha = hashlib.sha256(raw).hexdigest();self._revision += 1
        need(last_model is not None and self._file.tell() == size)
        self._model = last_model;self._size = size
        self._assets()

    async def _persist(self, model, operation):
        await self._current()
        self._assets()
        model_raw = model.dumps()
        value = dict(schema=SCHEMA, revision=self._revision+1, previous_sha256=self._sha,
                     fence=self._fence, operation=operation, model=json.loads(model_raw))
        raw = canonical(value)+b'\n'
        need(len(raw) <= MAX_RECORD and self._size+len(raw) <= self._max_bytes, 'BUDGET_JOURNAL_CAPACITY')
        self._file.seek(self._size)
        written = self._file.write(raw)
        need(type(written) is int and written == len(raw), 'BUDGET_SHORT_WRITE')
        self._file.flush();os.fsync(self._file.fileno())
        self._size += len(raw);self._revision += 1
        self._sha = hashlib.sha256(raw).hexdigest();self._model = model
        self._assets()
        await self._current()
        need(self._clock() >= model.snapshot()['clock_ms'], 'BUDGET_CLOCK_ROLLBACK')

    async def apply(self, method, *args, **kwargs):
        need(type(method) is str and method in METHODS and 'now_ms' not in kwargs, 'BUDGET_METHOD_REJECTED')
        async with self._mutex:
            need(not self._closed and not self._faulted, 'BUDGET_OWNER_FAULTED')
            try:
                await self._current()
                self._assets()
                model = copy.deepcopy(self._model)
                error = None
                try:result = getattr(model, method)(*args, **kwargs, now_ms=self._clock())
                except ValueError as exc:error = exc;result = None
                # Denials can advance time/expire an old reservation too.
                # Persist those conservative changes before reporting denial.
                await self._persist(model, method)
                if isinstance(result, dict) and method in ('grant', 'consume_read'):
                    deadline = (result['expires_ms'] if result['kind'] == 'READ' else
                                model.snapshot()['connections'][result['connection']]['deadline_ms'])
                    need(self._clock() < deadline, 'BUDGET_RECEIPT_EXPIRED_DURING_PERSIST')
            except BaseException as exc:
                self._faulted = True
                if not isinstance(exc, Exception):raise
                raise BudgetStoreBlocked('BUDGET_OWNER_FAULTED') from None
            if error is not None:raise error
            return copy.deepcopy(result)

    def snapshot(self):
        return dict(runtime_admission=RUNTIME_ADMISSION, revision=self._revision, offset=self._size,
                    sha256=self._sha, faulted=self._faulted,
                    model=self._model.snapshot() if self._model is not None else None)

    async def close(self):
        async with self._mutex:
            self._release()
