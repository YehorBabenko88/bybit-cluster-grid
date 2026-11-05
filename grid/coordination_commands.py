"""Typed command admission through the existing Consul authority.

Not a runtime authentication factory, SQL projector, job queue or effect executor.
The composition root must supply an admitted current-human principal provider.
No provider means denial. Persisted research-control intent is real; downstream
effects remain explicitly unwired. Unknown outcomes never trigger new identities.
Provider checks are RPC boundaries, not an atomic Consul grant/session-revocation
fence; instant revocation safety remains P0. Closing a UI does not cancel durable
commands or backend jobs. This module contains no execution authorization loop.
"""
import base64
from dataclasses import dataclass
import hashlib
import json
import math
import re
from urllib.parse import quote
import uuid

from .coordination import canonical, CoordinationLost, CoordinationUnavailable


class CommandDenied(ValueError):
    pass


def parse_command(raw):
    """Strict public JSON decoder; routes must not use permissive JSON decoding."""
    if type(raw) is not bytes or not 0 < len(raw) <= 32768:
        raise CommandDenied('invalid request byte budget')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise CommandDenied('duplicate JSON key')
            value[key] = item
        return value
    def invalid_constant(value):
        raise CommandDenied('nonfinite JSON value')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=unique,
                           parse_constant=invalid_constant)
        def bounded(item, depth=0):
            if depth > 8:
                raise CommandDenied('excessive JSON nesting')
            if type(item) is float and not math.isfinite(item):
                raise CommandDenied('nonfinite JSON value')
            if type(item) is dict:
                for child in item.values():
                    bounded(child, depth + 1)
            elif type(item) is list:
                for child in item:
                    bounded(child, depth + 1)
        bounded(value)
        if type(value) is not dict:
            raise CommandDenied('command object required')
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError, OverflowError) as exc:
        raise CommandDenied('invalid request JSON') from exc


@dataclass(frozen=True)
class CurrentPrincipal:
    actor_id: str
    grant_revision: int
    principal_kind: str = 'HUMAN'
    capabilities: frozenset[str] = frozenset()


def identifier(value):
    return type(value) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value)


def revision(value):
    return type(value) is int and 0 <= value <= 2**53 - 1


def identity(value):
    try:
        valid = type(value) is str and str(uuid.UUID(value)) == value
    except (ValueError, AttributeError):
        valid = False
    if not valid:
        raise CommandDenied('invalid UUID')
    return value


def validate_receipt(value, *, stored=False):
    """Closed schema; storage never contains a fabricated future commit index."""
    base = {'schema', 'command_id', 'generation', 'commit_status', 'effect_status'}
    if type(value) is not dict or value.get('schema') != 'unified.command-receipt.v1':
        raise CommandDenied('RECEIPT_INVALID')
    identity(value.get('command_id'))
    identity(value.get('generation'))
    if value.get('commit_status') == 'UNKNOWN':
        if stored or set(value) != base or value['effect_status'] != 'UNKNOWN':
            raise CommandDenied('RECEIPT_INVALID')
    else:
        fields = base | {'actor_id', 'grant_revision', 'idempotency_key', 'digest',
                         'action', 'aggregate_id', 'revision', 'leader_lock_index'}
        if not stored:
            fields.add('consensus_modify_index')
        if (set(value) != fields or value['commit_status'] != 'COMMITTED'
                or value['effect_status'] != 'PENDING_UNWIRED'
                or value['action'] != 'SetResearchControl'
                or not all(identifier(value[k]) for k in ('actor_id', 'aggregate_id', 'idempotency_key'))
                or not revision(value['grant_revision']) or value['grant_revision'] == 0 or not revision(value['revision'])
                or value['revision'] == 0 or type(value['digest']) is not str
                or not re.fullmatch('[0-9a-f]{64}', value['digest'])):
            raise CommandDenied('RECEIPT_INVALID')
        for key in ('leader_lock_index',) if stored else ('leader_lock_index', 'consensus_modify_index'):
            maximum = 2**63 - 1 if stored else 2**53 - 1
            if type(value[key]) is not int or not 0 < value[key] <= maximum:
                raise CommandDenied('RECEIPT_INDEX_INVALID')
        if not stored and value['consensus_modify_index'] <= value['leader_lock_index']:
            raise CommandDenied('RECEIPT_INDEX_ORDER_INVALID')
    return json.loads(canonical(value))


class CoordinationCommands:
    def __init__(self, authority, generation, *, principal_provider=None):
        self.authority = authority
        self.generation = identity(generation)
        self.provider = principal_provider
        self.prefix = authority.config.namespace + '/commands/'

    async def _principal(self, context, action, aggregate):
        if self.provider is None:
            raise CommandDenied('AUTHENTICATION_UNAVAILABLE')
        principal = await self.provider.require_current(context, action, aggregate)
        if (type(principal) in (dict, bool) or not identifier(getattr(principal, 'actor_id', None))
                or not revision(getattr(principal, 'grant_revision', None))
                or principal.grant_revision == 0
                or getattr(principal, 'principal_kind', None) != 'HUMAN'
                or type(getattr(principal, 'capabilities', None)) is not frozenset
                or {'SetResearchControl': 'research.control', 'ReadCommand': 'control.commands.read'}.get(action)
                    not in principal.capabilities):
            raise CommandDenied('invalid authenticated principal')
        return principal

    @staticmethod
    def _same_principal(before, after):
        if (before.actor_id, before.grant_revision) != (after.actor_id, after.grant_revision):
            raise CommandDenied('AUTHORIZATION_CHANGED')

    def _intent(self, envelope):
        required = {'schema', 'command_id', 'actor_id', 'idempotency_key', 'generation',
                    'aggregate_type', 'aggregate_id', 'expected_revision', 'action', 'payload'}
        if type(envelope) is not dict or set(envelope) != required:
            raise CommandDenied('invalid envelope fields')
        try:
            if len(canonical(envelope)) > 32768:
                raise CommandDenied('envelope exceeds 32KiB')
            identity(envelope['command_id'])
        except (RecursionError, TypeError, OverflowError) as exc:
            raise CommandDenied('invalid envelope encoding') from exc
        if (envelope['schema'] != 'unified.command.v1'
                or envelope['generation'] != self.generation
                or not identifier(envelope['aggregate_id'])
                or not identifier(envelope['idempotency_key'])
                or not revision(envelope['expected_revision'])):
            raise CommandDenied('invalid envelope identity or revision')
        if envelope['action'] != 'SetResearchControl' or envelope['aggregate_type'] != 'research':
            raise CommandDenied('UNSUPPORTED')
        payload = envelope['payload']
        if (type(payload) is not dict or set(payload) != {'mode', 'state'}
                or payload['mode'] != 'LAB_SIMULATION'
                or payload['state'] not in ('PAUSED', 'RUNNING')):
            raise CommandDenied('invalid research control payload')
        # Detach from caller-owned dictionaries before the first await.
        return json.loads(canonical(envelope))

    async def _read(self, key):
        rows = await self.authority._request('GET', '/v1/kv/' + quote(key, safe='/'),
            params={'consistent': ''}, missing_ok=True)
        if rows is None:
            return 0, None
        try:
            if (type(rows) is not list or len(rows) != 1 or rows[0]['Key'] != key
                    or type(rows[0]['ModifyIndex']) is not int or rows[0]['ModifyIndex'] <= 0):
                raise ValueError()
            return rows[0]['ModifyIndex'], parse_command(base64.b64decode(rows[0]['Value'], validate=True))
        except (KeyError, TypeError, ValueError) as exc:
            raise CoordinationUnavailable('invalid command storage record') from exc

    def _keys(self, intent, actor):
        binding = hashlib.sha256(canonical([self.generation, actor, intent['idempotency_key']])).hexdigest()
        return (self.prefix + 'ids/' + intent['command_id'],
                self.prefix + 'keys/' + binding,
                self.prefix + 'research_control/' + intent['aggregate_id'])

    @staticmethod
    def _check(key, index):
        return {'KV': {'Verb': 'check-index', 'Key': key, 'Index': index}}

    @staticmethod
    def _cas(key, index, value):
        return {'KV': {'Verb': 'cas', 'Key': key, 'Index': index,
                       'Value': base64.b64encode(canonical(value)).decode()}}

    async def submit(self, lease, envelope, session_context):
        intent = self._intent(envelope)
        principal = await self._principal(session_context, intent['action'], intent['aggregate_id'])
        if intent['actor_id'] != principal.actor_id:
            raise CommandDenied('ACTOR_ASSERTION_MISMATCH')
        # Actor is derived exclusively from the provider. Grant revision is audit
        # metadata, not intent identity: a current authorized retry may reconcile
        # an old committed receipt after a grant revision changes.
        digest = hashlib.sha256(canonical(intent)).hexdigest()
        id_key, retry_key, aggregate_key = self._keys(intent, principal.actor_id)
        unknown = {'schema': 'unified.command-receipt.v1', 'command_id': intent['command_id'], 'commit_status': 'UNKNOWN',
                   'effect_status': 'UNKNOWN', 'generation': self.generation}
        try:
            generation_index, generation = await self._read(self.prefix + 'generation')
            if generation != {'generation': self.generation}:
                raise CommandDenied('GENERATION_NOT_ADMITTED')
            stored_index, stored = await self._read(id_key)
            _, retried = await self._read(retry_key)
            if stored is not None or retried is not None:
                if stored is not None:
                    validate_receipt(stored, stored=True)
                if retried is not None:
                    validate_receipt(retried, stored=True)
                if (stored != retried or type(stored) is not dict
                        or stored.get('command_id') != intent['command_id']
                        or stored.get('generation') != self.generation
                        or stored.get('actor_id') != principal.actor_id or stored.get('digest') != digest):
                    raise CommandDenied('IDEMPOTENCY_CONFLICT')
                self._same_principal(principal, await self._principal(
                    session_context, intent['action'], intent['aggregate_id']))
                return validate_receipt(dict(stored, consensus_modify_index=stored_index))
            index, aggregate = await self._read(aggregate_key)
            if aggregate is not None:
                if (type(aggregate) is not dict or set(aggregate) != {'schema','generation','revision','command_id','payload'}
                        or aggregate['schema'] != 'unified.research-control.v1'
                        or aggregate['generation'] != self.generation
                        or not revision(aggregate['revision']) or aggregate['revision'] == 0
                        or type(aggregate['payload']) is not dict
                        or set(aggregate['payload']) != {'mode','state'}
                        or aggregate['payload']['mode'] != 'LAB_SIMULATION'
                        or aggregate['payload']['state'] not in ('PAUSED','RUNNING')):
                    raise CommandDenied('AGGREGATE_INVALID')
                identity(aggregate['command_id'])
            current = 0 if aggregate is None else aggregate.get('revision')
            if not revision(current) or current != intent['expected_revision'] or current >= 2**53 - 1:
                raise CommandDenied('REVISION_CONFLICT')
            if not await self.authority.validate(lease):
                return unknown
            receipt = dict(schema='unified.command-receipt.v1', command_id=intent['command_id'], generation=self.generation,
                actor_id=principal.actor_id, grant_revision=principal.grant_revision,
                idempotency_key=intent['idempotency_key'], digest=digest,
                action=intent['action'], aggregate_id=intent['aggregate_id'],
                revision=current + 1, commit_status='COMMITTED', effect_status='PENDING_UNWIRED',
                leader_lock_index=lease.token)
            validate_receipt(receipt, stored=True)
            aggregate_value = dict(schema='unified.research-control.v1', generation=self.generation, revision=current + 1,
                                   command_id=intent['command_id'], payload=intent['payload'])
            operations = [
                {'KV': {'Verb': 'check-session', 'Key': self.authority.key, 'Session': lease.session_id}},
                self._check(self.authority.key, lease.token),
                self._check(self.prefix + 'generation', generation_index),
                self._cas(id_key, 0, receipt), self._cas(retry_key, 0, receipt),
                self._cas(aggregate_key, index, aggregate_value)]
            # Recheck revocation immediately before authority I/O. Downstream
            # effect execution must independently reauthorize its current actor.
            current_principal = await self._principal(session_context, intent['action'], intent['aggregate_id'])
            self._same_principal(principal, current_principal)
            result = await self.authority._request('PUT', '/v1/txn', json=operations)
            if type(result) is not dict or result.get('Errors'):
                return unknown
            # Commit may remain durable after logout/revocation. Do not disclose
            # its private outcome under an expired admission session. This does
            # not cancel backend jobs; execution uses a separate current grant
            # and supersession fence, never the lifetime of the UI cookie.
            self._same_principal(principal, await self._principal(
                session_context, intent['action'], intent['aggregate_id']))
            committed_index, committed = await self._read(id_key)
            if committed != receipt:
                return unknown
            self._same_principal(principal, await self._principal(
                session_context, intent['action'], intent['aggregate_id']))
            return validate_receipt(dict(receipt, consensus_modify_index=committed_index))
        except CoordinationLost:
            # Could be racing duplicate, stale domain revision, or lost leader.
            # Reconciliation uses the original command id; never auto-rebase CAS.
            return await self.get_command(intent['command_id'], session_context)
        except CoordinationUnavailable:
            return unknown

    async def get_command(self, command_id, session_context):
        identity(command_id)
        principal = await self._principal(session_context, 'ReadCommand', command_id)
        unknown = dict(schema='unified.command-receipt.v1', command_id=command_id, generation=self.generation,
                       commit_status='UNKNOWN', effect_status='UNKNOWN')
        try:
            _, generation = await self._read(self.prefix + 'generation')
            if generation != {'generation': self.generation}:
                raise CommandDenied('GENERATION_NOT_ADMITTED')
            committed_index, receipt = await self._read(self.prefix + 'ids/' + command_id)
            if receipt is None:
                return unknown
            validate_receipt(receipt, stored=True)
            if (type(receipt) is not dict or receipt.get('generation') != self.generation
                    or receipt.get('command_id') != command_id
                    or (receipt.get('actor_id') != principal.actor_id
                        and 'control.commands.audit_all' not in principal.capabilities)):
                raise CommandDenied('command ownership mismatch')
            current = await self._principal(session_context, 'ReadCommand', receipt['aggregate_id'])
            self._same_principal(principal, current)
            if receipt.get('actor_id') != current.actor_id and 'control.commands.audit_all' not in current.capabilities:
                raise CommandDenied('command ownership mismatch')
            return validate_receipt(dict(receipt, consensus_modify_index=committed_index))
        except CoordinationUnavailable:
            return unknown
