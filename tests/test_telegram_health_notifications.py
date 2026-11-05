import asyncio
from grid import telegram_health_notifications as health


def test_notification_policy_requires_chat_user_and_health_grant(monkeypatch):
    monkeypatch.setenv('TELEGRAM_NOTIFICATION_USER_IDS','{"-100":[42,43]}')
    assert health.notification_policy(lambda chat,user,op: chat==-100 and user==42 and op=='/health') == {'-100':[42]}
    for raw in ('bad','{"*":[42]}','{"-100":[true]}','{"-100":[9223372036854775808]}'):
        monkeypatch.setenv('TELEGRAM_NOTIFICATION_USER_IDS',raw)
        assert health.notification_policy(lambda *args: True) == {}


class Context:
    def __init__(self,store,transaction=False): self.store,self.transaction=store,transaction
    async def __aenter__(self):
        if self.transaction:
            await self.store.lock.acquire()
            self.store.transactions+=1
        return self.store
    async def __aexit__(self,*args):
        if self.transaction:
            self.store.transactions-=1
            self.store.lock.release()


class Store:
    def __init__(self):
        self.row=None; self.owner='one'; self.epoch=1; self.now=1000.; self.live=True
        self.lock=asyncio.Lock(); self.transactions=0; self.checks=0
        self.revoke_at=None; self.cas_reject=False; self.fail_completion=False
    def acquire(self): return Context(self)
    def transaction(self): return Context(self,True)
    async def execute(self,sql,*args):
        if 'INSERT INTO replicated_control_state' in sql and self.row is None:
            self.row={'value':args[1],'version':1}
        return 'OK'
    async def fetchrow(self,sql,*args):
        import copy,json
        if 'UPDATE replicated_control_state' in sql or 'INSERT INTO replicated_control_state' in sql:
            if getattr(self,'revoke_on_mutation',False):
                self.owner='two';self.epoch=2
            if 'active_service' in sql:
                assert 'FOR SHARE' in sql and 'lease_until>clock_timestamp()' in sql
                if args[4:]!=('control-plane-leader',self.owner,self.epoch) or not self.live:
                    return None
            if 'INSERT INTO replicated_control_state' in sql:
                if self.row is not None: return None
                self.row={'value':args[1],'version':1}
                return {'version':1}
            assert 'WHERE state_key=$1 AND version=$4' in sql
            if self.fail_completion and self.transactions and any(x['status']=='SENDING' for x in self.state()['events']):
                raise RuntimeError('PRIVATE_TOKEN database exception')
            if self.cas_reject or args[3]!=self.row['version']: return None
            self.row={'value':args[1],'version':self.row['version']+1}
            return {'version':self.row['version']}
        if 'FROM service_leases' in sql:
            self.checks+=1
            if self.revoke_at==self.checks: self.owner='two'; self.epoch=2
            return {'owner':self.owner,'epoch':self.epoch,'now':self.now,'live':self.live}
        if 'SELECT value,version' in sql: return copy.deepcopy(self.row)
        raise AssertionError(sql)
    def state(self):
        import json
        return json.loads(self.row['value'])


def setup(monkeypatch):
    monkeypatch.setenv('TELEGRAM_NOTIFICATION_USER_IDS','{"-100":[42]}')
    async def fleet(pool,nodes,seconds):
        return {'online':[key for key,value in nodes.items() if value],
                'offline':[key for key,value in nodes.items() if not value]}
    monkeypatch.setattr(health,'fleet_health',fleet)
    return lambda chat,user,op: chat==-100 and user==42 and op=='/health'


def test_baseline_loss_recovery_dedup_and_no_transaction_during_http(monkeypatch):
    allowed=setup(monkeypatch)
    async def scenario():
        store=Store(); sent=[]
        async def send(chat,text):
            assert store.transactions==0
            sent.append((chat,text))
        assert (await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed))['outcome']=='NO_CHANGE'
        assert sent==[]
        assert (await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed))['outcome']=='DELIVERED'
        for _ in range(3): await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed)
        assert sent==[(-100,'NODE_LOST: PC1')]
        await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed)
        assert sent[-1]==(-100,'NODE_RECOVERED: PC1')
        assert len(sent)==2 and store.state()['events']==[]
        assert store.state()['delivered']['PC1']['-100']==2
    asyncio.run(scenario())


def test_transport_failure_is_ambiguous_not_delivered_and_not_retried(monkeypatch,caplog):
    allowed=setup(monkeypatch)
    async def scenario():
        store=Store(); attempts=[]
        async def send(*args): attempts.append(1); raise RuntimeError('PRIVATE_TOKEN URL')
        await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed)
        result=await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed)
        assert result['outcome']=='AMBIGUOUS'
        assert store.state()['delivered']=={}
        for _ in range(3): await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed)
        assert attempts==[1] and store.state()['events'][0]['status']=='AMBIGUOUS'
        assert 'PRIVATE_TOKEN' not in caplog.text
    asyncio.run(scenario())


def test_revocation_between_claim_and_send_prevents_http(monkeypatch):
    allowed=setup(monkeypatch)
    async def scenario():
        store=Store(); sent=[]
        async def send(*args): sent.append(1)
        await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed)
        # Next authority read claims, following read sees a replacement leader.
        store.revoke_at=store.checks+2
        result=await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed)
        assert result['outcome']=='AMBIGUOUS' and sent==[]
        await health.notify_node_health(store,{'PC1':False},5,'two',send,allowed)
        assert store.state()['events'][0]['status']=='AMBIGUOUS'
        assert store.state()['delivered']=={} and sent==[]
    asyncio.run(scenario())


def test_old_leader_cannot_ack_and_crash_sending_recovers_ambiguous(monkeypatch):
    allowed=setup(monkeypatch)
    async def scenario():
        store=Store(); sent=[]
        async def send(*args):
            sent.append(1); store.owner='two';store.epoch=2
        await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed)
        assert (await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed))['outcome']=='AMBIGUOUS'
        assert store.state()['events'][0]['status']=='SENDING'
        assert store.state()['delivered']=={}
        await health.notify_node_health(store,{'PC1':False},5,'two',send,allowed)
        assert store.state()['events'][0]['status']=='AMBIGUOUS' and sent==[1]
    asyncio.run(scenario())


def test_rate_budget_persists_and_pending_overflow_does_not_forget_observation(monkeypatch):
    allowed=setup(monkeypatch)
    monkeypatch.setattr(health,'MAX_PENDING',2)
    monkeypatch.setattr(health,'ATTEMPTS_PER_MINUTE',1)
    async def scenario():
        store=Store();sent=[]
        async def send(*args): sent.append(args)
        nodes={'PC1':True,'PC2':True,'PC3':True}
        await health.notify_node_health(store,nodes,5,'one',send,allowed)
        offline=dict.fromkeys(nodes,False)
        result=await health.notify_node_health(store,offline,5,'one',send,allowed)
        assert store.state()['nodes']['PC3'] is True
        assert result.get('queue_outcome')=='CAPACITY'
        for _ in range(3): await health.notify_node_health(store,offline,5,'one',send,allowed)
        assert len(sent)==1
        assert len(store.state()['events'])<=2
        store.now+=61
        await health.notify_node_health(store,offline,5,'one',send,allowed)
        assert len(sent)==2
    asyncio.run(scenario())


def test_success_then_database_outage_reports_ambiguity_without_delivery_advance(monkeypatch,caplog):
    allowed=setup(monkeypatch)
    async def scenario():
        store=Store()
        async def send(*args): store.fail_completion=True
        await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed)
        result=await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed)
        assert result['outcome']=='AMBIGUOUS' and result['ambiguous']==1
        assert store.state()['delivered']=={}
        assert store.state()['events'][0]['status']=='SENDING'
        assert 'PRIVATE_TOKEN' not in caplog.text
    asyncio.run(scenario())


def test_policy_revoked_after_claim_prevents_http_and_preserves_delivery(monkeypatch):
    setup(monkeypatch)
    async def scenario():
        store=Store();sent=[];checks=0
        async def send(*args): sent.append(1)
        await health.notify_node_health(store,{'PC1':True},5,'one',send,lambda *args: True)
        def grant(*args):
            nonlocal checks
            checks+=1
            return checks==1
        result=await health.notify_node_health(store,{'PC1':False},5,'one',send,grant)
        assert result['outcome']=='AMBIGUOUS' and sent==[]
        assert store.state()['events'][0]['status']=='AMBIGUOUS'
        assert store.state()['delivered']=={}
    asyncio.run(scenario())


def test_cancelled_sender_is_not_retried_after_attempt_deadline(monkeypatch,caplog):
    allowed=setup(monkeypatch)
    async def scenario():
        store=Store();sent=[]
        async def send(*args): sent.append(1); raise asyncio.CancelledError
        await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed)
        try: await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed)
        except asyncio.CancelledError: pass
        assert store.state()['events'][0]['status']=='SENDING'
        store.now+=61
        result=await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed)
        assert result['outcome']=='AMBIGUOUS' and result['ambiguous']==1
        assert sent==[1] and store.state()['delivered']=={}
        assert any(record.event=='telegram_health_ambiguous' for record in caplog.records)
    asyncio.run(scenario())


def test_cas_rejection_and_expired_authority_never_send(monkeypatch):
    allowed=setup(monkeypatch)
    async def scenario():
        store=Store();sent=[]
        async def send(*args): sent.append(1)
        await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed)
        store.cas_reject=True
        assert (await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed))['outcome']=='UNAVAILABLE'
        assert sent==[] and store.state()['nodes']['PC1'] is True
        store.cas_reject=False;store.live=False
        assert (await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed))['outcome']=='NOT_LEADER'
        assert sent==[]
    asyncio.run(scenario())


def test_existing_bot_poll_consumes_notifier_without_new_scheduler(monkeypatch):
    from types import SimpleNamespace
    from grid import telegram_bot as bot
    monkeypatch.setattr(bot.settings,'telegram_bot_token','synthetic')
    monkeypatch.setattr(bot.settings,'telegram_allowed_chat_ids','-100')
    received=[]
    async def cursor(*args): return 0
    async def api(session,method,**kwargs):
        if method=='getMe': return {'result':{}}
        if method=='sendMessage':
            assert kwargs['retries']==0
            received.append(kwargs['body'])
            return {'ok':True}
        if received: raise asyncio.CancelledError
        return {'result':[]}
    async def notify(pool,nodes,heartbeat,owner,send,allowed):
        assert pool=='synthetic-pool' and nodes=={'PC1':{}}
        assert owner==bot.settings.grid_control_node_id
        await send(-100,'NODE_LOST: PC1')
        return {'outcome':'DELIVERED','ambiguous':0}
    class Session:
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
    monkeypatch.setattr(bot.aiohttp,'ClientSession',lambda **kwargs: Session())
    monkeypatch.setattr(bot,'telegram_cursor',cursor)
    monkeypatch.setattr(bot,'_tg_api',api)
    monkeypatch.setattr(bot,'notify_node_health',notify)
    try: asyncio.run(bot.telegram_loop(SimpleNamespace(pool='synthetic-pool'),{'PC1':{}}))
    except asyncio.CancelledError: pass
    assert received==[{'chat_id':-100,'text':'NODE_LOST: PC1'}]


def test_state_save_lease_race_cannot_ack_delivery(monkeypatch):
    allowed=setup(monkeypatch)
    async def scenario():
        store=Store(); sent=[]
        async def send(*args):
            sent.append(1)
            store.revoke_on_mutation=True
        await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed)
        result=await health.notify_node_health(store,{'PC1':False},5,'one',send,allowed)
        assert result['outcome']=='AMBIGUOUS'
        assert store.state()['delivered']=={}
        assert store.owner=='two' and sent==[1]
    asyncio.run(scenario())


def test_decode_rejects_entire_corrupt_schema_and_oversized_object():
    import copy,json,pytest
    initial={'schema':1,'nodes':{'PC1':True},'events':[],'buckets':{},'delivered':{},'sequence':1}
    corrupt=[]
    for key,value in [('schema',True),('sequence',-1),('sequence',True),('sequence',2**63),
                      ('nodes',[]),('nodes',{'PRIVATE_TOKEN arbitrary node':True}),('nodes',{'PC1':1}),
                      ('events',{}),('delivered','x'*1_000_000),('buckets',{'-100':{'start':float('nan'),'attempts':1}}),
                      ('buckets',{'-100':{'start':1.,'attempts':-1}}),('delivered',{'PC1':{'-100':2}}),
                      ('unknown','PRIVATE_TOKEN')]:
        state=copy.deepcopy(initial);state[key]=value;corrupt.append(state)
    event={'id':1,'node':'PC1','chat':'-100','users':[42],'kind':'NODE_LOST','status':'READY'}
    for key,value in [('kind','PRIVATE_TOKEN'),('node','PRIVATE_TOKEN / injected'),('status','DONE'),
                      ('users',[True]),('users',[42]*101),('users',[42,42]),('chat','*'),('id',0),
                      ('owner','one'),('receipt_digest','a'*64)]:
        changed=copy.deepcopy(event);changed[key]=value
        state=copy.deepcopy(initial);state['events']=[changed];corrupt.append(state)
    sending=dict(event,status='SENDING',owner='one',epoch=1,deadline=1060.,receipt_digest='a'*64)
    for key,value in [('owner','PRIVATE_TOKEN / injected'),('epoch',True),('epoch',-1),
                      ('deadline',float('inf')),('receipt_digest','wrong')]:
        changed=copy.deepcopy(sending);changed[key]=value
        state=copy.deepcopy(initial);state['events']=[changed];corrupt.append(state)
    for state in corrupt:
        with pytest.raises(ValueError): health._decode({'value':state})
        with pytest.raises(ValueError): health._decode({'value':json.dumps(state)})
    assert health._decode({'value':initial})==initial
    with pytest.raises(ValueError): health._decode({'value':' '*1_000_000})
    cyclic=copy.deepcopy(initial);cyclic['events'].append(cyclic)
    with pytest.raises(ValueError): health._decode({'value':cyclic})


def test_forged_ready_event_never_emits_private_text(monkeypatch):
    import json
    allowed=setup(monkeypatch)
    async def scenario():
        store=Store();sent=[]
        async def send(*args): sent.append(args)
        await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed)
        state=store.state();state['sequence']=1
        state['events']=[{'id':1,'node':'PRIVATE_TOKEN / injected','chat':'-100','users':[42],
                         'kind':'ARBITRARY_PRIVATE_KIND','status':'READY'}]
        store.row['value']=json.dumps(state)
        result=await health.notify_node_health(store,{'PC1':True},5,'one',send,allowed)
        assert result['outcome']=='UNAVAILABLE' and sent==[]
    asyncio.run(scenario())
