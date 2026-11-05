"""Synthetic admission state; no application or external database is opened."""
import asyncio
import hashlib
from grid import telegram_idempotency as admission


class Context:
    def __init__(self, value, lock=None): self.value, self.lock = value, lock
    async def __aenter__(self):
        if self.lock: await self.lock.acquire()
        return self.value
    async def __aexit__(self, *args):
        if self.lock: self.lock.release()


class Store:
    def __init__(self):
        self.claims, self.actors, self.audit, self.arguments = {}, {}, [], []
        self.lock = asyncio.Lock()
        self.minute = 0
    def acquire(self): return Context(self)
    def transaction(self): return Context(self, self.lock)
    async def execute(self, sql, *args):
        self.arguments.append(args)
        if 'INSERT INTO telegram_ingress_audit' in sql:
            self.audit.append(dict(zip(('update','chat','user','operation','decision'),args)))
        return 'OK'
    async def fetchrow(self, sql, *args):
        self.arguments.append(args)
        if 'AS audit_count' in sql:
            return dict(audit_count=len(self.audit),pending_count=sum(x['status']=='CLAIMED' and x['claim_receipt_digest'] is not None for x in self.claims.values()),claim_count=len(self.claims),actor_count=len(self.actors))
        if sql.startswith('SELECT update_id,status FROM telegram_updates WHERE callback_digest'):
            return next((dict(update_id=key,status=row['status']) for key,row in self.claims.items() if row['callback_digest']==args[0]),None)
        if sql.lstrip().startswith('SELECT chat_id'):
            return self.claims.get(args[0])
        if sql.lstrip().startswith('UPDATE telegram_updates'):
            row = self.claims.get(args[0])
            if row is None or row['claim_receipt_digest'] != args[1] or row['status'] != 'CLAIMED': return None
            row['status'], row['error'] = args[2:]
            return row
        raise AssertionError(sql)
    async def fetchval(self, sql, *args):
        self.arguments.append(args)
        if 'WHERE callback_digest=$1' in sql:
            return next((key for key,row in self.claims.items() if row['callback_digest']==args[0]),None)
        if sql.startswith('SELECT 1 FROM telegram_actor_limits'):
            return 1 if args in self.actors else None
        if 'INSERT INTO telegram_actor_limits' in sql:
            minute, attempts = self.actors.get(args,(-1,0))
            attempts = 1 if minute != self.minute else min(attempts+1,31)
            self.actors[args] = (self.minute, attempts)
            return attempts
        if 'INSERT INTO telegram_updates' in sql:
            key,chat,op,node,user,callback,receipt = args
            if key in self.claims: return None
            self.claims[key] = dict(chat_id=chat,actor_user_id=user,operation=op,
                callback_digest=callback,claim_receipt_digest=receipt,status='CLAIMED',command=op,claimed_by=node,error=None)
            return key
        raise AssertionError(sql)


def run(coro): return asyncio.run(coro)


def test_invalid_identity_and_unknown_operations_audit_only_closed_values():
    async def scenario():
        store = Store()
        for user in (None, True, '42', 0, -1, 2**63):
            assert (await admission.admit_update(store,1,-100,user,'/status','test',authorized=True)).decision == 'DENIED'
        assert (await admission.admit_update(store,2,-100,42,'/stop PRIVATE_TOKEN','test',authorized=True)).decision == 'DENIED'
        assert store.audit[-1]['operation'] == 'UNKNOWN'
        assert not store.claims and not store.actors
        assert 'PRIVATE_TOKEN' not in repr(store.arguments)
    run(scenario())


def test_durable_bindings_callback_replay_and_receipt_owned_completion():
    async def scenario():
        store = Store()
        admitted = await admission.admit_update(store,1,-100,42,'/status','one',callback_id='private-token',authorized=True)
        assert admitted.decision == 'ACCEPTED'
        assert len(admitted.receipt) == 64
        assert store.claims[1]['claim_receipt_digest'] == hashlib.sha256(admitted.receipt.encode()).hexdigest()
        assert not await admission.finish_update(store,1,'x'*64)
        assert store.claims[1]['status'] == 'CLAIMED'
        assert (await admission.admit_update(store,1,-100,42,'/status','two',callback_id='private-token',authorized=True)).decision == 'STUCK'
        assert await admission.finish_update(store,1,admitted.receipt)
        assert not await admission.finish_update(store,1,admitted.receipt)
        assert (await admission.admit_update(store,1,-100,42,'/status','two',callback_id='private-token',authorized=True)).decision == 'DUPLICATE'
        for update,chat,user,operation,callback in ((2,-100,43,'/status','private-token'),(1,-100,43,'/status','private-token'),(1,-101,42,'/status','private-token'),(1,-100,42,'/system','private-token'),(1,-100,42,'/status','changed')):
            assert (await admission.admit_update(store,update,chat,user,operation,'two',callback_id=callback,authorized=True)).decision == 'REPLAY'
        assert len(store.claims) == 1
        assert 'private-token' not in repr(store.arguments)
        assert admitted.receipt not in repr(store.arguments)
    run(scenario())


def test_actor_budget_shared_by_concurrent_deliveries_and_resets_by_database_window():
    async def scenario():
        store = Store()
        results = await asyncio.gather(*(admission.admit_update(store,i,-100,42,'/status','test',authorized=True) for i in range(35)))
        assert sum(x.decision=='ACCEPTED' for x in results) == 30
        assert sum(x.decision=='RATE_LIMITED' for x in results) == 5
        assert store.actors[(-100,42)][1] == 31
        store.minute += 1
        assert (await admission.admit_update(store,100,-100,42,'/status','new-process',authorized=True)).decision == 'ACCEPTED'
    run(scenario())


def test_caps_preserve_completion_reserve_and_prevent_effects(monkeypatch):
    async def scenario():
        store = Store()
        monkeypatch.setattr(admission,'MAX_AUDIT_ROWS',2)
        accepted = await admission.admit_update(store,1,-100,42,'/status','test',authorized=True)
        assert accepted.decision == 'ACCEPTED'
        assert (await admission.admit_update(store,2,-100,43,'/status','test',authorized=False)).decision == 'CAPACITY'
        assert len(store.audit) == 1
        assert await admission.finish_update(store,1,accepted.receipt,failed=True)
        assert len(store.audit) == 2
        assert store.audit[-1]['decision'] == 'FAILED'
        assert store.claims[1]['error'] == 'FAILED'
    run(scenario())


def test_claim_and_actor_storage_caps_fail_closed(monkeypatch):
    async def scenario():
        for limit in ('MAX_CLAIMS','MAX_ACTORS'):
            store = Store()
            with monkeypatch.context() as scoped:
                scoped.setattr(admission,limit,0)
                assert (await admission.admit_update(store,1,-100,42,'/status','test',authorized=True)).decision == 'CAPACITY'
                assert not store.claims and not store.actors
                assert store.audit[-1]['decision'] == 'CAPACITY'
    run(scenario())


def test_public_operations_are_fixed_and_callback_ids_are_hashed():
    assert '/status' in admission.PUBLIC_OPERATIONS
    assert not admission.PUBLIC_OPERATIONS & {'/confirm','/logs','/logresult','/stop','/deletestatus'}
    assert admission.callback_digest('private-token') == admission.callback_digest('private-token')
    assert len(admission.callback_digest('private-token')) == 64


def test_legacy_completion_cannot_bypass_receipt_owned_claims():
    class Pool:
        async def execute(self,sql,*args):
            assert 'claim_receipt_digest IS NULL' in sql
            assert 'actor_user_id IS NULL' in sql
    run(admission.complete_update(Pool(),1))


def test_legacy_pending_delivery_stays_stuck_and_completed_binding_is_untrusted():
    async def scenario():
        store = Store()
        store.claims[1] = dict(chat_id='-100',actor_user_id=None,operation=None,
            callback_digest=None,claim_receipt_digest=None,status='CLAIMED')
        assert (await admission.admit_update(store,1,-100,42,'/status','test',authorized=True)).decision == 'STUCK'
        store.claims[1]['status'] = 'DONE'
        assert (await admission.admit_update(store,1,-100,42,'/status','test',authorized=True)).decision == 'REPLAY'
        assert not store.actors
    run(scenario())


def test_pending_claim_holds_before_auth_or_binding_changes():
    async def scenario():
        store = Store()
        initial = await admission.admit_update(store,1,-100,42,'/status','one',callback_id='original',authorized=True)
        assert initial.decision == 'ACCEPTED'
        cases = [(1,-100,42,'/status','original',False),
                 (1,-100,43,'/status','original',True),
                 (1,-100,42,'/status','changed',True),
                 (1,-100,None,'/status','original',False),
                 (2,-100,43,'/status','original',True)]
        for update,chat,user,operation,callback,authorized in cases:
            result=await admission.admit_update(store,update,chat,user,operation,'replacement',callback_id=callback,authorized=authorized)
            assert result.decision == 'STUCK'
        assert len(store.claims)==1 and len(store.actors)==1
        assert await admission.finish_update(store,1,initial.receipt)
        assert (await admission.admit_update(store,1,-100,42,'/status','two',callback_id='original',authorized=False)).decision == 'DENIED'
        assert (await admission.admit_update(store,2,-100,43,'/status','two',callback_id='original',authorized=True)).decision == 'REPLAY'
    run(scenario())
