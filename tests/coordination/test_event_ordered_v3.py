"""MODEL HTTP predicate tests. Not real Consul, quorum or resource containment."""
import asyncio
import base64
import copy
from contextlib import aclosing
import json
from types import SimpleNamespace

import httpx
import pytest

from grid.coordination import ConsulConfig, ConsulSessionAuthority, canonical
from grid.coordination_event_v3 import EventAuthority, EventDenied

G = '11111111-1111-4111-8111-111111111111'
A = '22222222-2222-4222-8222-222222222222'
W = '33333333-3333-4333-8333-333333333333'


class Model:
    """Only supplied Consul predicates; no election, clocks or persistence."""
    def __init__(self):
        self.kv = {}
        self.sessions = set()
        self.index = 1
        self.txns = []
        self.before_txn = None
        self.lose_response = False
        self.offline = False
        self.counter = 0
        self.on_renew = None
        self.renew_response = None

    def put(self, key, value, session=''):
        self.index += 1
        self.kv[key] = dict(Key=key, ModifyIndex=self.index, Session=session,
                           Value=base64.b64encode(canonical(value)).decode())

    def invalidate(self, session):
        self.sessions.discard(session)
        for key, row in list(self.kv.items()):
            if row['Session'] == session:
                self.put(key, json.loads(base64.b64decode(row['Value'])))

    def handle(self, request):
        if self.offline:
            return httpx.Response(503)
        path = request.url.path
        if path == '/v1/session/create':
            self.counter += 1
            session = f'00000000-0000-4000-8000-{self.counter:012d}'
            self.sessions.add(session)
            return httpx.Response(200, json={'ID': session})
        if path.startswith('/v1/session/renew/'):
            session = path.rsplit('/', 1)[-1]
            if self.on_renew:
                hook,self.on_renew=self.on_renew,None;hook()
            if self.renew_response is not None:return httpx.Response(200,json=self.renew_response)
            return httpx.Response(200, json=[{'ID':session}]) if session in self.sessions else httpx.Response(404)
        if path.startswith('/v1/session/destroy/'):
            self.invalidate(path.rsplit('/', 1)[-1])
            return httpx.Response(200, json=True)
        if path == '/v1/txn':
            ops = json.loads(request.content)
            self.txns.append(copy.deepcopy(ops))
            if self.before_txn:
                hook, self.before_txn = self.before_txn, None
                hook()
            for op in ops:
                k = op['KV']; row = self.kv.get(k['Key'])
                if k['Verb'] in ('cas', 'check-index') and k['Index'] != (row['ModifyIndex'] if row else 0):
                    return httpx.Response(409, json={'Errors':[{'What':'index'}]})
                if k['Verb'] == 'check-session' and (not row or row['Session'] != k['Session'] or k['Session'] not in self.sessions):
                    return httpx.Response(409, json={'Errors':[{'What':'session'}]})
                if k['Verb'] == 'lock' and (k['Session'] not in self.sessions or (row and row['Session'] not in ('',k['Session']))):
                    return httpx.Response(409, json={'Errors':[{'What':'lock'}]})
            for op in ops:
                k = op['KV']
                if k['Verb'] in ('cas','set','lock'):
                    self.put(k['Key'], json.loads(base64.b64decode(k['Value'])), k.get('Session',''))
            if self.lose_response:
                raise httpx.ReadTimeout('MODEL lost response after apply')
            return httpx.Response(200, json={'Results':[]})
        if path.startswith('/v1/kv/'):
            key = path[len('/v1/kv/'):]
            if request.method == 'GET':
                assert 'consistent' in request.url.params
                return httpx.Response(200, json=[self.kv[key]]) if key in self.kv else httpx.Response(404)
            session = request.url.params.get('acquire')
            if session:
                self.put(key, json.loads(request.content), session)
                return httpx.Response(200, json=True)
        raise AssertionError((request.method,path))


class Provider:
    async def require_current(self, context, action, assignment):
        assert context == 'trusted-test-context'
        return SimpleNamespace(actor_id='operator', grant_revision=1, capabilities=frozenset({'authority.lifecycle'}))


async def fixture():
    model = Model()
    client = httpx.AsyncClient(transport=httpx.MockTransport(model.handle))
    authority = ConsulSessionAuthority(ConsulConfig(endpoints=('http://127.0.0.1:8500',),
        namespace='event-test',isolated_lab=True),client=client)
    leader = await authority.acquire('LS5')
    adapter = EventAuthority(authority,G,principal_provider=Provider())
    model.put(adapter.generation_key,{'generation':G})
    model.put(adapter.prefix+'principals/operator',{'actor_id':'operator','grant_revision':'1','state':'ADMITTED','capabilities':['authority.lifecycle']})
    model.put(adapter.prefix+'workers/worker',{'worker_id':'worker','incarnation':W,'state':'ADMITTED'})
    return model, client, authority, leader, adapter


def intent(action='GRANT',revision=0,request='request1',session=None):
    return dict(schema='unified.authority.lifecycle.v3',request_id=request,generation=G,actor_id='operator',
                assignment_id=A,worker_id='worker',worker_incarnation=W,lease_session_id=session,
                action=action,expected_revision=str(revision))


def run(coro):
    return asyncio.run(coro)


def test_grant_has_real_session_and_atomic_generation_worker_leader_receipt_checks():
    async def scenario():
        m,c,a,leader,v = await fixture()
        async with aclosing(c):
            candidate = await v.prepare_session(leader,'trusted-test-context',A)
            result = await v.submit(leader,intent(session=candidate),'trusted-test-context')
            assert result['status']=='COMMITTED' and result['revision']=='1'
            assert result['effect_status']=='UNWIRED'
            ops=m.txns[-1]
            assert any(x['KV']['Verb']=='lock' and x['KV']['Session']==candidate for x in ops)
            assert any(x['KV']['Verb']=='check-session' and x['KV']['Session']==leader.session_id for x in ops)
            assert any(x['KV']['Key']==v.generation_key and x['KV']['Verb']=='check-index' for x in ops)
            for suffix in ('workers/worker','assignments/'+A):
                assert any(x['KV']['Key']==v.prefix+suffix and x['KV']['Verb']=='check-index' for x in ops)
            assert len([x for x in ops if x['KV']['Verb']=='cas'])==2
    run(scenario())


def test_lost_response_reconciles_same_receipt_across_adapter_restart():
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            session=await v.prepare_session(leader,'trusted-test-context',A)
            cmd=intent(session=session);m.lose_response=True
            assert (await v.submit(leader,cmd,'trusted-test-context'))['status']=='UNKNOWN'
            committed=copy.deepcopy(m.kv)
            m.lose_response=False
            restarted=EventAuthority(a,G,principal_provider=Provider())
            result=await restarted.submit(leader,cmd,'trusted-test-context')
            assert result['status']=='COMMITTED' and m.kv==committed
            cmd['worker_id']='other'
            with pytest.raises(EventDenied,match='IDEMPOTENCY_CONFLICT'):
                await restarted.submit(leader,cmd,'trusted-test-context')
    run(scenario())


@pytest.mark.parametrize('change',['session','leader','generation','worker'])
def test_change_after_reads_before_apply_rejects_all_writes(change):
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            session=await v.prepare_session(leader,'trusted-test-context',A)
            def hook():
                if change=='session':m.invalidate(session)
                elif change=='leader':m.invalidate(leader.session_id)
                elif change=='generation':m.put(v.generation_key,{'generation':W})
                else:m.put(v.prefix+'workers/worker',{'worker_id':'worker','incarnation':G,'state':'ADMITTED'})
            m.before_txn=hook
            assert (await v.submit(leader,intent(session=session),'trusted-test-context'))['status']=='REJECTED'
            assert v.prefix+'assignments/'+A not in m.kv
            assert not any('/receipts/' in key for key in m.kv)
    run(scenario())


def test_renew_revoke_and_old_revision_rejection_without_successor():
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            session=await v.prepare_session(leader,'trusted-test-context',A)
            assert (await v.submit(leader,intent(session=session),'trusted-test-context'))['status']=='COMMITTED'
            renew=intent('RENEW',1,'renew',session)
            assert (await v.submit(leader,renew,'trusted-test-context'))['revision']=='2'
            assert (await v.submit(leader,intent('REVOKE',2,'revoke',session),'trusted-test-context'))['revision']=='3'
            stale=await v.submit(leader,intent('RENEW',2,'stale',session),'trusted-test-context')
            assert stale['status']=='REJECTED'
            assert json.loads(base64.b64decode(m.kv[v.prefix+'assignments/'+A]['Value']))['state']=='REVOKED'
    run(scenario())


def test_session_invalidation_without_successor_denies_renew_but_allows_terminal_cleanup():
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            session=await v.prepare_session(leader,'trusted-test-context',A)
            await v.submit(leader,intent(session=session),'trusted-test-context');m.invalidate(session)
            assert (await v.submit(leader,intent('RENEW',1,'renew',session),'trusted-test-context'))['status']=='REJECTED'
            assert (await v.submit(leader,intent('COMPLETE',1,'complete',session),'trusted-test-context'))['status']=='COMMITTED'
    run(scenario())


def test_no_quorum_is_unknown_not_a_new_grant_or_no_quorum_claim():
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            session=await v.prepare_session(leader,'trusted-test-context',A);m.txns.clear();m.offline=True
            result=await v.submit(leader,intent(session=session),'trusted-test-context')
            assert result['status']=='UNKNOWN' and result['reason']=='AUTHORITY_UNAVAILABLE'
            assert not m.txns
    run(scenario())


@pytest.mark.parametrize('field,value',[('expected_revision','01'),('expected_revision',True),('action','PUBLISH'),('actor_id','forged'),('extra','x')])
def test_invalid_or_forged_intent_never_sends_transaction(field,value):
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            cmd=intent(session=G);cmd[field]=value
            with pytest.raises(EventDenied):await v.submit(leader,cmd,'trusted-test-context')
            assert not m.txns
    run(scenario())


def test_missing_provider_denies_even_receipt_lookup():
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            v=EventAuthority(a,G)
            with pytest.raises(EventDenied,match='AUTHENTICATION_UNAVAILABLE'):
                await v.submit(leader,intent(session=G),'ignored')
            assert not m.txns
    run(scenario())


@pytest.mark.parametrize('response',[[None],[1],[[]],{},[{}]])
def test_malformed_native_renew_is_unknown_and_old_grant_inactive(response):
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            session=await v.prepare_session(leader,'trusted-test-context',A)
            await v.submit(leader,intent(session=session),'trusted-test-context')
            m.renew_response=response
            result=await v.submit(leader,intent('RENEW',1,'renew',session),'trusted-test-context')
            assert result['status']=='UNKNOWN'
            assert json.loads(base64.b64decode(m.kv[v.prefix+'assignments/'+A]['Value']))['state']=='RENEW_PENDING'
    run(scenario())


def test_leader_lost_during_native_renew_cannot_leave_old_active_grant():
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            session=await v.prepare_session(leader,'trusted-test-context',A)
            await v.submit(leader,intent(session=session),'trusted-test-context')
            m.on_renew=lambda:m.invalidate(leader.session_id)
            assert (await v.submit(leader,intent('RENEW',1,'renew',session),'trusted-test-context'))['status']=='REJECTED'
            assert json.loads(base64.b64decode(m.kv[v.prefix+'assignments/'+A]['Value']))['state']=='RENEW_PENDING'
    run(scenario())


def test_unknown_pending_renew_resumes_exact_request_after_restart():
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            session=await v.prepare_session(leader,'trusted-test-context',A)
            await v.submit(leader,intent(session=session),'trusted-test-context')
            cmd=intent('RENEW',1,'renew',session);m.renew_response=[None]
            assert (await v.submit(leader,cmd,'trusted-test-context'))['status']=='UNKNOWN'
            assert (await v.submit(leader,intent('RENEW',1,'other',session),'trusted-test-context'))['status']=='REJECTED'
            m.renew_response=None
            restarted=EventAuthority(a,G,principal_provider=Provider())
            assert (await restarted.submit(leader,cmd,'trusted-test-context'))['revision']=='2'
            assert (await restarted.submit(leader,cmd,'trusted-test-context'))['status']=='COMMITTED'
    run(scenario())


def test_revision_exhaustion_rejected_before_any_transaction():
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            with pytest.raises(EventDenied):
                await v.submit(leader,intent('RENEW',2**63-2,'max',G),'trusted-test-context')
            assert not m.txns
    run(scenario())


def test_identical_concurrent_renew_phase_conflict_reconciles_committed_receipt():
    async def scenario():
        m,c,a,leader,v=await fixture()
        async with aclosing(c):
            session=await v.prepare_session(leader,'trusted-test-context',A)
            await v.submit(leader,intent(session=session),'trusted-test-context')
            cmd=intent('RENEW',1,'renew',session);original=a._request;intercepted=False
            async def interleave(method,path,**kwargs):
                nonlocal intercepted
                if path=='/v1/txn' and not intercepted:
                    intercepted=True
                    assert (await v.submit(leader,cmd,'trusted-test-context'))['status']=='COMMITTED'
                return await original(method,path,**kwargs)
            a._request=interleave
            assert (await v.submit(leader,cmd,'trusted-test-context'))['status']=='COMMITTED'
    run(scenario())
