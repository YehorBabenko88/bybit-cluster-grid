"""Small immutable budget watermarks on the existing Consul authority.

Primitive only: no budget credit, refund, reset, job queue or second DCS. A
protected runtime factory is NOT_WIRED. Optional source_guard is a trusted startup
seam, never request JSON/boolean proof. Modeled HTTP tests do not qualify durable
consensus, Windows, private inventory, human authentication or office operation.
"""
from dataclasses import dataclass
import base64
import binascii
import inspect
import json
import re
from urllib.parse import quote

from .coordination import ConsulLease, CoordinationLost, CoordinationUnavailable, canonical

SCHEMA = 'grid.network-budget-anchor.v1'
MAX_SAFE = 2**53 - 1


class AnchorRejected(ValueError):
    pass


class AnchorConflict(AnchorRejected):
    pass


def _identifier(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value) is not None


def _hash(value):
    return type(value) is str and re.fullmatch('[a-f0-9]{64}', value) is not None


def _positive(value):
    return type(value) is int and 0 < value <= MAX_SAFE


@dataclass(frozen=True)
class BudgetAnchor:
    installation_id: str
    meter_id: str
    store_generation_sha256: str
    revision: int
    offset: int
    journal_sha256: str

    def __post_init__(self):
        if (not _identifier(self.installation_id) or not _identifier(self.meter_id)
                or not _hash(self.store_generation_sha256) or not _hash(self.journal_sha256)
                or not _positive(self.revision) or not _positive(self.offset)):
            raise AnchorRejected('ANCHOR_FIELDS_INVALID')


def _record(anchor):
    if type(anchor) is not BudgetAnchor:
        raise AnchorRejected('TYPED_ANCHOR_REQUIRED')
    anchor.__post_init__()
    value = dict(schema=SCHEMA, installation_id=anchor.installation_id,
                 meter_id=anchor.meter_id, store_generation_sha256=anchor.store_generation_sha256,
                 revision=anchor.revision, offset=anchor.offset, journal_sha256=anchor.journal_sha256)
    if len(canonical(value)) > 4096:
        raise AnchorRejected('ANCHOR_BYTE_BOUND')
    return value


def _decode(raw):
    if type(raw) is not bytes or not 0 < len(raw) <= 4096:
        raise AnchorRejected('ANCHOR_BYTE_BOUND')
    def pairs(items):
        value = {}
        for key, item in items:
            if key in value:
                raise AnchorRejected('ANCHOR_DUPLICATE_KEY')
            value[key] = item
        return value
    def constant(_):
        raise AnchorRejected('ANCHOR_NONFINITE')
    try:
        # The schema is flat: nested dictionaries/arrays cannot pass field types.
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=pairs, parse_constant=constant)
        fields = {'schema','installation_id','meter_id','store_generation_sha256','revision','offset','journal_sha256'}
        if type(value) is not dict or set(value) != fields or value['schema'] != SCHEMA:
            raise AnchorRejected('ANCHOR_SCHEMA_INVALID')
        anchor = BudgetAnchor(**{k:v for k,v in value.items() if k != 'schema'})
        if canonical(_record(anchor)) != raw:
            raise AnchorRejected('ANCHOR_NOT_CANONICAL')
        return anchor
    except (UnicodeError, json.JSONDecodeError, RecursionError, TypeError, OverflowError) as exc:
        raise AnchorRejected('ANCHOR_STORAGE_INVALID') from exc


@dataclass(frozen=True)
class AnchorVersion:
    anchor: BudgetAnchor
    consensus_modify_index: int

    def __post_init__(self):
        _record(self.anchor)
        if not _positive(self.consensus_modify_index):
            raise AnchorRejected('ANCHOR_INDEX_INVALID')


@dataclass(frozen=True)
class AnchorWriteOutcome:
    status: str
    version: AnchorVersion | None = None

    def __post_init__(self):
        if not ((self.status == 'COMMITTED' and type(self.version) is AnchorVersion)
                or (self.status == 'UNKNOWN' and self.version is None)):
            raise AnchorRejected('ANCHOR_OUTCOME_INVALID')


UNKNOWN = AnchorWriteOutcome('UNKNOWN')


class ConsulBudgetAnchor:
    def __init__(self, authority, installation_id, meter_id, store_generation_sha256, *, source_guard=None):
        if (not _identifier(installation_id) or not _identifier(meter_id)
                or not _hash(store_generation_sha256)):
            raise AnchorRejected('ANCHOR_SCOPE_INVALID')
        if source_guard is not None and (isinstance(source_guard, (dict, bool))
                or not callable(getattr(source_guard, 'require_current', None))):
            raise AnchorRejected('SOURCE_GUARD_INVALID')
        self.authority = authority
        self.installation_id = installation_id
        self.meter_id = meter_id
        self.store_generation_sha256 = store_generation_sha256
        self.source_guard = source_guard
        self.key = authority.config.namespace + '/budget-anchors/' + installation_id + '/' + meter_id

    async def _current_source(self):
        if self.source_guard is not None:
            current = self.source_guard.require_current()
            if inspect.isawaitable(current):
                current = await current
            if current is not True:
                raise AnchorRejected('SOURCE_GUARD_REVOKED')

    def _scope(self, anchor):
        _record(anchor)
        if (anchor.installation_id, anchor.meter_id, anchor.store_generation_sha256) != (
                self.installation_id, self.meter_id, self.store_generation_sha256):
            raise AnchorRejected('ANCHOR_SCOPE_MISMATCH')

    async def _lease(self, lease):
        await self._current_source()
        if type(lease) is not ConsulLease or self.authority._sessions.get(lease.session_id) is not lease:
            return False
        valid = await self.authority.validate(lease)
        await self._current_source()
        return valid

    async def read(self):
        await self._current_source()
        rows = await self.authority._request('GET', '/v1/kv/' + quote(self.key, safe='/'),
                                             params={'consistent': ''}, missing_ok=True)
        if rows is None:
            await self._current_source()
            return None
        try:
            if (type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict
                    or rows[0].get('Key') != self.key or not _positive(rows[0].get('ModifyIndex'))
                    or type(rows[0].get('Value')) is not str or len(rows[0]['Value']) > 5464):
                raise AnchorRejected('ANCHOR_KV_INVALID')
            anchor = _decode(base64.b64decode(rows[0]['Value'], validate=True))
            self._scope(anchor)
            version = AnchorVersion(anchor, rows[0]['ModifyIndex'])
            await self._current_source()
            return version
        except (KeyError, UnicodeError, TypeError, binascii.Error) as exc:
            raise AnchorRejected('ANCHOR_KV_INVALID') from exc

    async def reconcile(self, next_anchor):
        self._scope(next_anchor)
        try:
            current = await self.read()
            if current is not None and current.anchor == next_anchor:
                return AnchorWriteOutcome('COMMITTED', current)
            return UNKNOWN
        except CoordinationUnavailable:
            return UNKNOWN

    async def compare_and_swap(self, lease, expected, next_anchor):
        self._scope(next_anchor)
        if expected is not None:
            if type(expected) is not AnchorVersion:
                raise AnchorRejected('TYPED_VERSION_REQUIRED')
            expected.__post_init__()
            self._scope(expected.anchor)
        try:
            if not await self._lease(lease):
                return UNKNOWN
            current = await self.read()
            if current is not None and current.anchor == next_anchor:
                return AnchorWriteOutcome('COMMITTED', current) if await self._lease(lease) else UNKNOWN
            if current != expected:
                raise AnchorConflict('ANCHOR_EXPECTED_VERSION_CHANGED')
            if expected is None:
                if next_anchor.revision != 1:
                    raise AnchorRejected('ANCHOR_FIRST_REVISION_REQUIRED')
            elif (next_anchor.revision != expected.anchor.revision + 1
                    or next_anchor.offset <= expected.anchor.offset):
                raise AnchorRejected('ANCHOR_NONMONOTONE')
            if not await self._lease(lease):
                return UNKNOWN
            index = 0 if expected is None else expected.consensus_modify_index
            operations = [
                {'KV': {'Verb': 'check-session', 'Key': self.authority.key, 'Session': lease.session_id}},
                {'KV': {'Verb': 'check-index', 'Key': self.authority.key, 'Index': lease.token}},
                {'KV': {'Verb': 'cas', 'Key': self.key, 'Index': index,
                        'Value': base64.b64encode(canonical(_record(next_anchor))).decode('ascii')}}]
            try:
                result = await self.authority._request('PUT', '/v1/txn', json=operations)
            except CoordinationLost:
                # CAS409 can be an already committed duplicate. Never rebase.
                reconciled = await self.reconcile(next_anchor)
                if reconciled.status == 'COMMITTED':
                    return reconciled if await self._lease(lease) else UNKNOWN
                raise AnchorConflict('ANCHOR_CAS_CONFLICT') from None
            if type(result) is not dict or result.get('Errors'):
                return UNKNOWN
            reconciled = await self.reconcile(next_anchor)
            return reconciled if await self._lease(lease) else UNKNOWN
        except CoordinationUnavailable:
            return UNKNOWN
