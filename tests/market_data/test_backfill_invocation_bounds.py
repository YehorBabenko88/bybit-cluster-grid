"""Inert coroutine checks: no loop, provider, PostgreSQL or child process."""
import unittest
from unittest.mock import patch
from market_data import market_backfill as module

class BackfillInvocationBoundsTests(unittest.TestCase):
    def test_known_failure_is_deferred_until_next_invocation(self):
        calls=[]
        async def recover(*a):pass
        async def claim(*a):
            calls.append('claim')
            if calls.count('claim')>2:raise AssertionError('unbounded immediate retry')
            return {'symbol':'BTCUSDT','timeframe':'1'}
        async def page(*a,**kw):calls.append('page');raise ValueError('invalid bounded provider page')
        class Pool:
            async def execute(self,sql,*a):
                self.sql=sql;calls.append('retry')
        pool=Pool()
        with patch.object(module,'recover_stale_backfill_jobs',recover),patch.object(module,'claim_backfill',claim),patch.object(module,'backfill_symbol',page):
            coro=module.run_backfill_worker(pool,'https://example.invalid',max_pages=1)
            with self.assertRaises(StopIteration) as end:coro.send(None)
        self.assertEqual(end.exception.value,{'completed':0,'chunks':0,'failed':1})
        self.assertEqual(calls,['claim','page','retry'])
        self.assertIn("status='retry'",pool.sql)

    def test_successful_chunk_uses_remaining_invocation_page_budget(self):
        claims=[];budgets=[]
        async def recover(*a):pass
        async def claim(*a):
            claims.append(1)
            if len(claims)>2:raise AssertionError('invocation budget ignored')
            return {'symbol':'BTCUSDT','timeframe':'1'}
        async def page(*a,**kw):budgets.append(kw['max_pages']);return {'complete':False,'pages':kw['max_pages']}
        async def capability(*a,**kw):pass
        with patch.object(module,'recover_stale_backfill_jobs',recover),patch.object(module,'claim_backfill',claim),patch.object(module,'backfill_symbol',page),patch('market_data.data_capabilities.set_capability',capability):
            coro=module.run_backfill_worker(object(),'https://example.invalid',max_pages=3)
            with self.assertRaises(StopIteration) as end:coro.send(None)
        self.assertEqual(budgets,[3]);self.assertEqual(len(claims),1)
        self.assertEqual(end.exception.value,{'completed':0,'chunks':1,'failed':0})

    def test_invalid_budget_refused_before_any_pool_or_claim_effect(self):
        async def touched(*a):raise AssertionError('invalid budget reached database')
        for value in (False,True,0,51,1.0,'1',None):
            with self.subTest(value=value),patch.object(module,'recover_stale_backfill_jobs',touched):
                coro=module.run_backfill_worker(object(),'https://example.invalid',max_pages=value)
                with self.assertRaises(ValueError):coro.send(None)

    def test_cancellation_never_becomes_retry_or_known_failure(self):
        import asyncio
        calls=[]
        async def recover(*a):pass
        async def claim(*a):return {'symbol':'BTCUSDT','timeframe':'1'}
        async def cancelled(*a,**kw):raise asyncio.CancelledError
        class Pool:
            async def execute(self,*a):calls.append('write')
        with patch.object(module,'recover_stale_backfill_jobs',recover),patch.object(module,'claim_backfill',claim),patch.object(module,'backfill_symbol',cancelled):
            coro=module.run_backfill_worker(Pool(),'https://example.invalid',max_pages=1)
            with self.assertRaises(asyncio.CancelledError):coro.send(None)
        self.assertEqual(calls,[])
