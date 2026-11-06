"""Additive event-ordered lifecycle adapter for the existing Consul authority.

Experimental internal ABI, not a production provider, executor or publication API.
Real session/index transactions; UTC is never an authorization predicate. Current
provider plus authority principal/worker records must be supplied by composition.
No bootstrap, election, timers, storage engine, endpoints or effects are created.
"""
import base64
from dataclasses import dataclass
import hashlib
import json
import re
from urllib.parse import quote
import uuid

from .coordination import canonical, CoordinationLost, CoordinationUnavailable
from .coordination_commands import parse_command


class EventDenied(ValueError):
    pass


def _uuid(value):
    try:
        if type(value) is not str or str(uuid.UUID(value)) != value:
            raise ValueError()
    except (ValueError, AttributeError, TypeError):
        raise EventDenied('INVALID_UUID') from None
    return value


def _id(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}', value):
        raise EventDenied('INVALID_IDENTIFIER')
    return value


def _revision(value):
    if (type(value) is not str or not re.fullmatch(r'0|[1-9][0-9]{0,18}', value)
            or int(value) >= 2**63-1):
        raise EventDenied('INVALID_REVISION')
    return int(value)


@dataclass(frozen=True)
class Record:
    index: int
    value: dict | None
    session: str = ''


def _check(key, index):
    return {'KV':dict(Verb='check-index',Key=key,Index=index)}


def _write(key, index, value):
    return {'KV':dict(Verb='cas',Key=key,Index=index,Value=base64.b64encode(canonical(value)).decode())}


class EventAuthority:
    """Owns only namespace/event-v3; existing leader/generation are checked.

    All resulting assignment states remain EFFECT_UNWIRED. They are not worker,
    storage or egress admission until exact downstream contracts are qualified.
    """
    def __init__(self, authority, generation, *, principal_provider=None):
        self.authority = authority
        self.generation = _uuid(generation)
        self.provider = principal_provider
        self.prefix = authority.config.namespace + '/event-v3/'
        self.generation_key = authority.config.namespace + '/commands/generation'

    def _intent(self, value):
        fields = {'schema','request_id','generation','actor_id','assignment_id','worker_id',
                  'worker_incarnation','lease_session_id','action','expected_revision'}
        if type(value) is not dict or set(value) != fields:
            raise EventDenied('INVALID_FIELDS')
        try:
            raw = canonical(value)
        except (TypeError, ValueError, RecursionError):
            raise EventDenied('INVALID_ENCODING') from None
        if len(raw) > 4096:
            raise EventDenied('INTENT_TOO_LARGE')
        v = json.loads(raw)  # detach caller dictionaries before any await
        if v['schema'] != 'unified.authority.lifecycle.v3' or v['generation'] != self.generation:
            raise EventDenied('INVALID_PROFILE_OR_GENERATION')
        for key in ('request_id','actor_id','worker_id'):
            _id(v[key])
        for key in ('assignment_id','worker_incarnation','lease_session_id'):
            _uuid(v[key])
        n = _revision(v['expected_revision'])
        if n >= 2**63-2:
            raise EventDenied('REVISION_EXHAUSTED')
        if v['action'] not in ('GRANT','RENEW','REVOKE','COMPLETE') or (v['action']=='GRANT') != (n==0):
            raise EventDenied('INVALID_ACTION_OR_REVISION')
        return v

    async def _principal(self, context, action, assignment):
        if self.provider is None:
            raise EventDenied('AUTHENTICATION_UNAVAILABLE')
        p = await self.provider.require_current(context,action,assignment)
        actor = _id(getattr(p,'actor_id',None))
        revision = getattr(p,'grant_revision',None)
        if (type(revision) is not int or not 0 < revision < 2**63-1
                or type(getattr(p,'capabilities',None)) is not frozenset
                or 'authority.lifecycle' not in p.capabilities):
            raise EventDenied('AUTHORIZATION_DENIED')
        return actor, str(revision)

    async def _read(self, key):
        rows = await self.authority._request('GET','/v1/kv/'+quote(key,safe='/'),
            params={'consistent':''},missing_ok=True)
        if rows is None:
            return Record(0,None)
        try:
            if type(rows) is not list or len(rows)!=1 or type(rows[0]) is not dict:
                raise ValueError()
            row=rows[0]
            if (row['Key']!=key or type(row['ModifyIndex']) is not int
                    or not 0<row['ModifyIndex']<2**63 or type(row.get('Session','')) is not str):
                raise ValueError()
            raw=base64.b64decode(row['Value'],validate=True)
            if len(raw)>8192:
                raise ValueError()
            return Record(row['ModifyIndex'],parse_command(raw),row.get('Session',''))
        except (ValueError,TypeError,KeyError) as exc:
            raise CoordinationUnavailable('invalid event-v3 authority record') from exc

    async def _guards(self, actor):
        generation=await self._read(self.generation_key)
        if generation.value!={'generation':self.generation}:
            raise EventDenied('GENERATION_NOT_ADMITTED')
        principal=await self._read(self.prefix+'principals/'+actor[0])
        if principal.value!={'actor_id':actor[0],'grant_revision':actor[1],
                'state':'ADMITTED','capabilities':['authority.lifecycle']}:
            raise EventDenied('PRINCIPAL_NOT_ADMITTED')
        return [_check(self.generation_key,generation.index),
                _check(self.prefix+'principals/'+actor[0],principal.index)]

    def _leader_checks(self, leader):
        return [{'KV':dict(Verb='check-session',Key=self.authority.key,Session=leader.session_id)},
                _check(self.authority.key,leader.token)]

    async def prepare_session(self, leader, context, assignment_id):
        """Prepare inert lease candidate. No grant exists until submit commits.

        On ambiguous create/candidate commit do NOT auto-remint or destroy. A
        known candidate identity is attached to the raised error for recovery.
        An orphan session expires; it cannot grant assignment/effect authority.
        """
        assignment_id=_uuid(assignment_id)
        actor=await self._principal(context,'PREPARE',assignment_id)
        checks=await self._guards(actor)
        if not await self.authority.validate(leader):
            raise CoordinationLost('current leader required')
        created=await self.authority._request('PUT','/v1/session/create',json={
            'Name':'event-v3-'+assignment_id,'TTL':str(self.authority.config.ttl_seconds)+'s',
            'Behavior':'release','LockDelay':'0s','NodeChecks':[]})
        try:
            session=_uuid(created['ID'])
        except (EventDenied,KeyError,TypeError):
            raise CoordinationUnavailable('session creation outcome unknown') from None
        candidate=dict(generation=self.generation,assignment_id=assignment_id,actor_id=actor[0],session_id=session)
        try:
            if await self._principal(context,'PREPARE',assignment_id)!=actor:
                raise EventDenied('AUTHORIZATION_CHANGED')
            await self.authority._request('PUT','/v1/txn',json=self._leader_checks(leader)+checks+[
                _write(self.prefix+'candidates/'+session,0,candidate)])
        except (CoordinationUnavailable,EventDenied) as exc:
            error=CoordinationUnavailable('candidate commit unknown; preserve known identity')
            error.candidate_session_id=session
            raise error from exc
        return session

    def _receipt_key(self, v):
        identity=hashlib.sha256(canonical([self.generation,v['actor_id'],v['request_id']])).hexdigest()
        return self.prefix+'receipts/'+identity

    def _recover(self, record, v, digest):
        if record.value is None:
            return None
        value=record.value
        expected={'schema','status','effect_status','request_id','generation','actor_id',
                  'assignment_id','action','digest','revision','state','lease_session_id'}
        if (set(value)!=expected or value.get('schema')!='unified.authority.lifecycle-receipt.v3'
                or value.get('status')!='COMMITTED' or value.get('effect_status')!='UNWIRED'):
            raise CoordinationUnavailable('invalid lifecycle receipt')
        if any(value.get(k)!=v[k] for k in ('request_id','generation','actor_id','assignment_id','action','lease_session_id')) or value['digest']!=digest:
            raise EventDenied('IDEMPOTENCY_CONFLICT')
        _revision(value['revision'])
        if value['state'] not in ('ACTIVE','REVOKED','COMPLETED'):
            raise CoordinationUnavailable('invalid receipt state')
        return dict(value,authority_modify_index=str(record.index),historical=True)

    async def submit(self, leader, intent, context):
        v=self._intent(intent)
        actor=await self._principal(context,v['action'],v['assignment_id'])
        if actor[0]!=v['actor_id']:
            raise EventDenied('ACTOR_ASSERTION_MISMATCH')
        digest=hashlib.sha256(canonical(v)).hexdigest()
        receipt_key=self._receipt_key(v)
        unknown=dict(schema='unified.authority.lifecycle-outcome.v3',status='UNKNOWN',
            request_id=v['request_id'],digest=digest,reason='AUTHORITY_UNAVAILABLE',effect_status='UNWIRED')
        rejected=dict(unknown,status='REJECTED',reason='PREDICATE_REJECTED')
        async def reject():
            # Another identical caller may have committed since our initial read.
            if await self._principal(context,v['action'],v['assignment_id'])!=actor:
                raise EventDenied('AUTHORIZATION_CHANGED')
            try:
                recovered=self._recover(await self._read(receipt_key),v,digest)
                return recovered if recovered else rejected
            except CoordinationUnavailable:
                return unknown
        try:
            guards=await self._guards(actor)
            recovered=self._recover(await self._read(receipt_key),v,digest)
            if recovered is not None:
                # Current read authorization, not old leader authority, permits history lookup.
                if await self._principal(context,v['action'],v['assignment_id'])!=actor:
                    raise EventDenied('AUTHORIZATION_CHANGED')
                return recovered
            if not await self.authority.validate(leader):
                return await reject()
            if v['lease_session_id']==leader.session_id:
                raise EventDenied('DEDICATED_LEASE_SESSION_REQUIRED')
            assignment_key=self.prefix+'assignments/'+v['assignment_id']
            lease_key=self.prefix+'leases/'+v['assignment_id']
            worker_key=self.prefix+'workers/'+v['worker_id']
            state=await self._read(assignment_key)
            worker=await self._read(worker_key)
            session=await self._read(lease_key)
            if worker.value!={'worker_id':v['worker_id'],'incarnation':v['worker_incarnation'],'state':'ADMITTED'}:
                return await reject()
            revision=int(v['expected_revision'])
            if v['action']=='GRANT':
                if state.value is not None or session.index:
                    return await reject()
                candidate_key=self.prefix+'candidates/'+v['lease_session_id']
                candidate=await self._read(candidate_key)
                if candidate.value!=dict(generation=self.generation,assignment_id=v['assignment_id'],
                    actor_id=actor[0],session_id=v['lease_session_id']):
                    return await reject()
                guards.append(_check(candidate_key,candidate.index))
            else:
                expected=dict(schema='unified.authority.assignment.v3',generation=self.generation,
                    assignment_id=v['assignment_id'],worker_id=v['worker_id'],worker_incarnation=v['worker_incarnation'],
                    lease_session_id=v['lease_session_id'],revision=str(revision),state='ACTIVE',effect_status='UNWIRED')
                if v['action']=='RENEW':
                    pending=dict(expected,revision=str(revision+1),state='RENEW_PENDING',
                        pending_request_id=v['request_id'],pending_digest=digest)
                    if state.value==expected:
                        if session.session!=v['lease_session_id']:
                            return await reject()
                        phase=self._leader_checks(leader)+guards+[_check(worker_key,worker.index),
                            _check(lease_key,session.index),_check(receipt_key,0),
                            {'KV':dict(Verb='check-session',Key=lease_key,Session=v['lease_session_id'])},
                            _write(assignment_key,state.index,pending)]
                        try:
                            response=await self.authority._request('PUT','/v1/txn',json=phase)
                            if type(response) is not dict or response.get('Errors'):
                                return unknown
                        except CoordinationLost:
                            # A transport retry may reject a phase it already committed.
                            pass
                        state=await self._read(assignment_key)
                    if state.value!=pending:
                        return await reject()
                    if session.session!=v['lease_session_id']:
                        return await reject()
                    # Old ACTIVE revision is durably closed before native renewal.
                    # A stale/failed finalizer can extend an inert session only.
                    try:
                        renewed=await self.authority._request('PUT','/v1/session/renew/'+v['lease_session_id'],missing_ok=True)
                    except CoordinationUnavailable:
                        return unknown
                    if renewed is None:
                        return await reject()
                    if (type(renewed) is not list or len(renewed)!=1
                            or type(renewed[0]) is not dict or renewed[0].get('ID')!=v['lease_session_id']):
                        return unknown
                else:
                    # Terminal cleanup may invalidate a pending renewal as well.
                    if state.value!=expected:
                        value=state.value
                        if not isinstance(value,dict) or value.get('state')!='RENEW_PENDING':
                            return await reject()
                        stable={k:val for k,val in value.items() if k not in ('pending_request_id','pending_digest')}
                        if stable!=dict(expected,state='RENEW_PENDING'):
                            return await reject()
            if await self._principal(context,v['action'],v['assignment_id'])!=actor:
                raise EventDenied('AUTHORIZATION_CHANGED')
            new_state={'GRANT':'ACTIVE','RENEW':'ACTIVE','REVOKE':'REVOKED','COMPLETE':'COMPLETED'}[v['action']]
            assignment=dict(schema='unified.authority.assignment.v3',generation=self.generation,
                assignment_id=v['assignment_id'],worker_id=v['worker_id'],worker_incarnation=v['worker_incarnation'],
                lease_session_id=v['lease_session_id'],revision=str(revision+1),state=new_state,effect_status='UNWIRED')
            receipt=dict(schema='unified.authority.lifecycle-receipt.v3',status='COMMITTED',effect_status='UNWIRED',
                request_id=v['request_id'],generation=self.generation,actor_id=actor[0],assignment_id=v['assignment_id'],
                action=v['action'],digest=digest,revision=str(revision+1),state=new_state,lease_session_id=v['lease_session_id'])
            ops=self._leader_checks(leader)+guards+[_check(worker_key,worker.index),
                _check(assignment_key,state.index),_check(lease_key,session.index),_check(receipt_key,0)]
            if v['action']=='GRANT':
                ops.append({'KV':dict(Verb='lock',Key=lease_key,Session=v['lease_session_id'],
                    Value=base64.b64encode(canonical(dict(assignment_id=v['assignment_id'],generation=self.generation))).decode())})
            elif v['action']=='RENEW':
                ops.append({'KV':dict(Verb='check-session',Key=lease_key,Session=v['lease_session_id'])})
            ops += [_write(assignment_key,state.index,assignment),_write(receipt_key,0,receipt)]
            if len(ops)>32 or len(canonical(ops))>16384:
                raise EventDenied('TRANSACTION_TOO_LARGE')
            try:
                response=await self.authority._request('PUT','/v1/txn',json=ops)
                if type(response) is not dict or response.get('Errors'):
                    return unknown
            except CoordinationLost:
                # The existing transport may have retried an already-applied txn.
                recovered=self._recover(await self._read(receipt_key),v,digest)
                return recovered if recovered else rejected
            return self._recover(await self._read(receipt_key),v,digest) or unknown
        except CoordinationLost:
            return await reject()
        except CoordinationUnavailable:
            return unknown
