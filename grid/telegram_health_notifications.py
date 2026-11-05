"""Bounded notification metadata, never a source of fleet health or leadership.

A crash or uncertain HTTP result is AMBIGUOUS and is never retried automatically.
Telegram delivery cannot be made exactly once across the network/DB boundary.
"""
import copy
import hashlib
import json
import logging
import math
import os
import re
import secrets
from .control_state import get_control_state, put_control_state
from .fleet_health import fleet_health

log = logging.getLogger('telegram')
STATE_KEY = 'telegram_health_notifications_v1'
LOCK_KEY = 0x54474E48
MAX_NODES, MAX_CHATS, MAX_PENDING = 200, 20, 100
ATTEMPTS_PER_MINUTE = 10
ATTEMPT_SECONDS = 60
MAX_STATE_BYTES = 524288
MAX_STATE_ITEMS = 30000
_NODE = re.compile(r'[A-Za-z0-9_.:-]{1,80}\Z')


def notification_policy(allowed):
    """Only explicit chat/user grants with the existing /health permission."""
    raw = os.environ.get('TELEGRAM_NOTIFICATION_USER_IDS', '{}')
    if len(raw) > 16384:
        return {}
    try:
        policy = json.loads(raw)
        if not isinstance(policy, dict) or len(policy) > MAX_CHATS:
            return {}
        result = {}
        for chat, users in policy.items():
            numeric_chat = int(chat)
            if str(numeric_chat) != chat or not -2**63 <= numeric_chat < 2**63 or numeric_chat == 0:
                return {}
            if not isinstance(users, list) or not 1 <= len(users) <= 100:
                return {}
            if any(type(user) is not int or not 0 < user < 2**63 for user in users):
                return {}
            granted = sorted({user for user in users if allowed(numeric_chat, user, '/health')})
            if granted:
                result[chat] = granted
        return result
    except (ValueError, TypeError):
        return {}


def _integer(value, minimum=0, maximum=2**63-1):
    return type(value) is int and minimum<=value<=maximum


def _clock(value):
    return type(value) in (int,float) and math.isfinite(value) and 0<=value<=2**53


def _node(value):
    return isinstance(value,str) and _NODE.fullmatch(value) is not None


def _chat(value):
    if not isinstance(value,str) or not 1<=len(value)<=20:
        return False
    try:
        parsed=int(value)
        return str(parsed)==value and parsed!=0 and -2**63<=parsed<2**63
    except ValueError:
        return False


async def _authority(conn, owner, epoch=None):
    if not _node(owner):
        return None
    row = await conn.fetchrow('''SELECT owner,(metadata->>'epoch')::bigint AS epoch,
        lease_until>clock_timestamp() AS live,extract(epoch FROM clock_timestamp())::float8 AS now
        FROM service_leases WHERE service_key='control-plane-leader' ''')
    if (not row or row['owner'] != owner or row['live'] is not True
            or not _integer(row['epoch'],1) or not _clock(row['now'])):
        return None
    if epoch is not None and row['epoch'] != epoch:
        return None
    return row


def _bounded_object(value):
    # Validate the already-parsed form before copying or serializing it. Every
    # container, depth, scalar and traversal count has a fixed budget.
    stack=[(value,0)]
    seen=set()
    remaining=MAX_STATE_BYTES
    items=0
    while stack:
        current,depth=stack.pop()
        items+=1
        if items>MAX_STATE_ITEMS or depth>8:
            raise ValueError('invalid notification state')
        if type(current) in (dict,list):
            if id(current) in seen or len(current)>MAX_NODES:
                raise ValueError('invalid notification state')
            seen.add(id(current))
            remaining-=2+len(current)
            if isinstance(current,dict):
                stack.extend((part,depth+1) for pair in current.items() for part in pair)
            else:
                stack.extend((part,depth+1) for part in current)
        elif isinstance(current,str):
            if len(current)>remaining:
                raise ValueError('invalid notification state')
            remaining-=len(current.encode('utf-8'))+2
        elif type(current) is bool:
            remaining-=5
        elif type(current) is int:
            if not -2**63<=current<2**63:
                raise ValueError('invalid notification state')
            remaining-=21
        elif type(current) is float and math.isfinite(current):
            remaining-=32
        else:
            raise ValueError('invalid notification state')
        if remaining<0:
            raise ValueError('invalid notification state')


def _json_pairs(pairs):
    result={}
    for key,value in pairs:
        if key in result:
            raise ValueError('invalid notification state')
        result[key]=value
    return result


def _decode(row):
    try:
        state=row['value']
        if isinstance(state,str):
            # A character check bounds UTF-8 materialization itself; byte length
            # is then checked before JSON decoding creates any containers.
            if len(state)>MAX_STATE_BYTES or len(state.encode('utf-8'))>MAX_STATE_BYTES:
                raise ValueError('invalid notification state')
            state=json.loads(state,object_pairs_hook=_json_pairs)
        _bounded_object(state)
        if (type(state) is not dict or set(state)!={'schema','nodes','events','buckets','delivered','sequence'}
                or type(state['schema']) is not int or state['schema']!=1
                or not _integer(state['sequence'])):
            raise ValueError('invalid notification state')
        nodes,events,buckets,delivered=state['nodes'],state['events'],state['buckets'],state['delivered']
        if type(nodes) is not dict or len(nodes)>MAX_NODES or any(not _node(node) or type(online) is not bool for node,online in nodes.items()):
            raise ValueError('invalid notification state')
        if type(buckets) is not dict or len(buckets)>MAX_CHATS:
            raise ValueError('invalid notification state')
        for chat,bucket in buckets.items():
            if (not _chat(chat) or type(bucket) is not dict or set(bucket)!={'start','attempts'}
                    or not _clock(bucket['start']) or not _integer(bucket['attempts'],0,ATTEMPTS_PER_MINUTE)):
                raise ValueError('invalid notification state')
        if type(delivered) is not dict or len(delivered)>MAX_NODES:
            raise ValueError('invalid notification state')
        delivered_chats=set()
        for node,recipients in delivered.items():
            if node not in nodes or type(recipients) is not dict or len(recipients)>MAX_CHATS:
                raise ValueError('invalid notification state')
            for chat,sequence in recipients.items():
                if not _chat(chat) or not _integer(sequence,1,state['sequence']):
                    raise ValueError('invalid notification state')
                delivered_chats.add(chat)
        if len(delivered_chats)>MAX_CHATS or type(events) is not list or len(events)>MAX_PENDING:
            raise ValueError('invalid notification state')
        bindings=set()
        transitions={}
        base={'id','node','chat','users','kind','status'}
        attempt={'owner','epoch','deadline','receipt_digest'}
        for event in events:
            if type(event) is not dict or event.get('status') not in ('READY','SENDING','AMBIGUOUS'):
                raise ValueError('invalid notification state')
            expected=base if event['status']=='READY' else base|attempt
            if (set(event)!=expected or not _integer(event['id'],1,state['sequence'])
                    or event['node'] not in nodes or not _chat(event['chat'])
                    or event['kind'] not in ('NODE_LOST','NODE_RECOVERED')
                    or type(event['users']) is not list or not 1<=len(event['users'])<=100
                    or any(not _integer(user,1) for user in event['users'])
                    or sorted(set(event['users']))!=event['users']):
                raise ValueError('invalid notification state')
            binding=(event['id'],event['chat'])
            transition=(event['node'],event['kind'])
            if binding in bindings or event['id'] in transitions and transitions[event['id']]!=transition:
                raise ValueError('invalid notification state')
            bindings.add(binding)
            transitions[event['id']]=transition
            if event['status']!='READY' and (not _node(event['owner']) or not _integer(event['epoch'],1)
                    or not _clock(event['deadline']) or not isinstance(event['receipt_digest'],str)
                    or re.fullmatch('[0-9a-f]{64}',event['receipt_digest']) is None):
                raise ValueError('invalid notification state')
        return state
    except (KeyError,TypeError,UnicodeError,OverflowError,RecursionError) as exc:
        raise ValueError('invalid notification state') from None


def _fence(owner,epoch):
    return {'service_key':'control-plane-leader','owner':owner,'epoch':epoch}


async def _save(conn, owner, epoch, row, state):
    _decode({'value':state})
    version = await put_control_state(conn, STATE_KEY, state, owner, expected_version=row['version'],
                                      service_fence=_fence(owner,epoch))
    if version is None:
        raise RuntimeError('notification state CAS rejected')


def _permitted(event, policy):
    return bool(set(event['users']) & set(policy.get(event['chat'], [])))


async def _claim(pool, owner, snapshot, policy):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock($1)', LOCK_KEY)
            authority = await _authority(conn, owner)
            if authority is None:
                return None, 'NOT_LEADER', 0
            initial = {'schema':1,'nodes':{},'events':[],'buckets':{},'delivered':{},'sequence':0}
            row = await get_control_state(conn, STATE_KEY)
            if row is None:
                version=await put_control_state(conn,STATE_KEY,initial,owner,expected_version=0,
                                                service_fence=_fence(owner,authority['epoch']))
                if version is None:
                    raise RuntimeError('notification state initialization fenced')
                row=await get_control_state(conn,STATE_KEY)
            state = copy.deepcopy(_decode(row))
            original = copy.deepcopy(state)
            now, epoch = authority['now'], authority['epoch']
            outcome = 'NO_CHANGE'
            for event in state['events']:
                if event['status'] == 'SENDING' and (event['owner'] != owner or event['epoch'] != epoch or event['deadline'] <= now):
                    event['status'] = 'AMBIGUOUS'
                    outcome = 'AMBIGUOUS'
            # Revocation cancels only definitely-unsent READY events.
            retained = [event for event in state['events'] if event['status'] != 'READY' or _permitted(event, policy)]
            if len(retained) != len(state['events']):
                outcome = 'REVOKED'
            state['events'] = retained
            state['buckets'] = {chat:bucket for chat,bucket in state['buckets'].items() if chat in policy}
            for delivered in state['delivered'].values():
                for chat in list(delivered):
                    if chat not in policy:
                        del delivered[chat]
            for node, online in sorted(snapshot.items()):
                if node not in state['nodes']:
                    if len(state['nodes']) >= MAX_NODES:
                        outcome = 'CAPACITY'
                        continue
                    state['nodes'][node] = online  # Baseline: no startup flood.
                    continue
                if state['nodes'][node] == online:
                    continue
                if len(state['events']) + len(policy) > MAX_PENDING:
                    outcome = 'CAPACITY'
                    continue  # Preserve observation until all recipients fit.
                if state['sequence'] >= 2**63-1:
                    outcome = 'CAPACITY'
                    continue
                state['sequence'] += 1
                for chat, users in sorted(policy.items()):
                    state['events'].append({'id':state['sequence'],'node':node,'chat':chat,
                        'users':list(users),'kind':'NODE_RECOVERED' if online else 'NODE_LOST','status':'READY'})
                state['nodes'][node] = online
            attempt = None
            for event in state['events']:
                if event['status'] != 'READY' or not _permitted(event, policy):
                    continue
                bucket = state['buckets'].get(event['chat'], {'start':now,'attempts':0})
                if now - bucket['start'] >= 60:
                    bucket = {'start':now,'attempts':0}
                if bucket['attempts'] >= ATTEMPTS_PER_MINUTE:
                    if outcome == 'NO_CHANGE': outcome = 'RATE_LIMITED'
                    continue
                bucket['attempts'] += 1
                state['buckets'][event['chat']] = bucket
                receipt = secrets.token_hex(32)
                event.update(status='SENDING',owner=owner,epoch=epoch,deadline=now+ATTEMPT_SECONDS,
                             receipt_digest=hashlib.sha256(receipt.encode()).hexdigest())
                attempt = dict(event,receipt=receipt)
                break
            if state != original:
                await _save(conn, owner, authority['epoch'], row, state)
            ambiguous = sum(event['status']=='AMBIGUOUS' for event in state['events'])
            return attempt, outcome, ambiguous


async def _preflight(pool, owner, attempt, policy):
    async with pool.acquire() as conn:
        authority = await _authority(conn, owner, attempt['epoch'])
        if authority is None or authority['now'] >= attempt['deadline'] or not _permitted(attempt, policy):
            return False
        row = await get_control_state(conn, STATE_KEY)
        return any(event['id']==attempt['id'] and event['chat']==attempt['chat']
                   and event['status']=='SENDING' and event.get('receipt_digest')==attempt['receipt_digest']
                   for event in _decode(row)['events'])


async def _complete(pool, owner, attempt, policy, success):
    async with pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock($1)', LOCK_KEY)
            authority = await _authority(conn, owner, attempt['epoch'])
            if authority is None:
                return 'AMBIGUOUS'  # New leader will recover the durable SENDING row.
            row = await get_control_state(conn, STATE_KEY)
            state = copy.deepcopy(_decode(row))
            event = next((event for event in state['events'] if event['id']==attempt['id'] and event['chat']==attempt['chat']), None)
            if event is None or event['status'] != 'SENDING' or event.get('receipt_digest') != hashlib.sha256(attempt['receipt'].encode()).hexdigest():
                return 'AMBIGUOUS'
            if success and _permitted(event, policy) and authority['now'] < event['deadline']:
                state['delivered'].setdefault(event['node'], {})[event['chat']] = event['id']
                state['events'].remove(event)
                outcome = 'DELIVERED'
            else:
                event['status'] = 'AMBIGUOUS'
                outcome = 'AMBIGUOUS'
            await _save(conn, owner, authority['epoch'], row, state)
            return outcome


async def notify_node_health(pool, nodes, heartbeat_seconds, owner, send, allowed):
    """Observe existing fleet_health, attempt at most one notification per poll.

    No transaction spans HTTP. A final authority check cannot eliminate the
    network race after that check; uncertain delivery is explicitly AMBIGUOUS.
    """
    attempt = None
    try:
        policy = notification_policy(allowed)
        if not policy:
            return {'outcome':'DISABLED','ambiguous':0}
        status = await fleet_health(pool, nodes, heartbeat_seconds)
        snapshot = {node:True for node in status['online']}
        snapshot.update({node:False for node in status['offline']})
        if len(snapshot)>MAX_NODES or any(not isinstance(node,str) or not _NODE.fullmatch(node) for node in snapshot):
            log.warning('telegram health notification capacity reached',extra={'event':'telegram_health_capacity','component':'SnapshotLimit'})
            return {'outcome':'CAPACITY','ambiguous':0}
        attempt, outcome, ambiguous = await _claim(pool, owner, snapshot, policy)
        if outcome == 'CAPACITY':
            log.warning('telegram health notification capacity reached',extra={'event':'telegram_health_capacity','component':'PendingQueueLimit'})
        if attempt is None:
            if outcome == 'AMBIGUOUS':
                log.warning('telegram health delivery ambiguous',extra={'event':'telegram_health_ambiguous','component':'InterruptedAttempt'})
            return {'outcome':outcome,'ambiguous':ambiguous}
        if not await _preflight(pool, owner, attempt, notification_policy(allowed)):
            await _complete(pool, owner, attempt, notification_policy(allowed), False)
            log.warning('telegram health delivery ambiguous',extra={'event':'telegram_health_ambiguous','component':'AuthorityChanged'})
            return {'outcome':'AMBIGUOUS','ambiguous':max(1,ambiguous),'queue_outcome':outcome}
        success = False
        diagnostic = None
        try:
            await send(int(attempt['chat']), f"{attempt['kind']}: {attempt['node']}")
            success = True
        except Exception as exc:
            diagnostic = type(exc).__name__[:80]
        queue_outcome = outcome
        outcome = await _complete(pool, owner, attempt, notification_policy(allowed), success)
        if outcome == 'AMBIGUOUS':
            log.warning('telegram health delivery ambiguous',extra={'event':'telegram_health_ambiguous','component':diagnostic or 'DeliveryUncertain'})
        return {'outcome':outcome,'ambiguous':max(1,ambiguous) if outcome=='AMBIGUOUS' else ambiguous,'queue_outcome':queue_outcome}
    except Exception as exc:
        log.error('telegram health notification unavailable',extra={'event':'telegram_health_unavailable','component':type(exc).__name__[:80]})
        return {'outcome':'AMBIGUOUS' if attempt is not None else 'UNAVAILABLE','ambiguous':1 if attempt is not None else 0}


async def notification_status(pool):
    """Read-only operational visibility; never treats an uncertain send as done."""
    try:
        row = await get_control_state(pool, STATE_KEY)
        if row is None:
            return {'state':'NOT_STARTED','pending':0,'ambiguous':0,'sending':0}
        events = _decode(row)['events']
        return {'state':'AVAILABLE','pending':len(events),
                'ambiguous':sum(event['status']=='AMBIGUOUS' for event in events),
                'sending':sum(event['status']=='SENDING' for event in events)}
    except Exception:
        return {'state':'UNAVAILABLE','pending':None,'ambiguous':None,'sending':None}
