"""SOURCE ONLY: future real module tests. Not imported/discovered/run at review1."""
import copy
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

# Deliberately no fallback, copied resolver, fake authority or mock planner.
from grid.bybit_request_plan import PlanFormatError, prepare_bybit_request_plan

FIXTURES = Path(__file__).with_name('fixtures')
WIRE_SHA = '16606dee585398ae6d92139ffc1cf2ed37a4d2e08759aaa08f0c3b85958b8049'
POLICY_SHA = '973f84f87de066d6686dfbe1177dc583637fa819aa21f988303e3a649abae3f1'
BODY_SHA = 'b3ea69e77ef17b3cd2a894f16df32cb1caba3178efb8814800d4017507e15ca3'
PREFIX = 'bybit.public.linear.'


def encoded(value):
    """Input fixture serializer only; never validates or constructs a plan."""
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def instrument(symbol='BTCUSDT', version='1'):
    return dict(exchange='bybit', category='linear', symbol=symbol, instrument_version=version)


def request(operation='ws.subscribe.v1', priority='live_heartbeat', instruments=None, payload=None):
    return dict(schema='grid.bybit.local-request-plan.v1-review1', wire_profile_sha256=WIRE_SHA,
                policy_raw_sha256=POLICY_SHA, operation_id=PREFIX+operation, requested_priority=priority,
                instruments=[instrument()] if instruments is None else instruments,
                payload={'topics':['publicTrade.BTCUSDT']} if payload is None else payload)


class RequestPlanSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wire = (FIXTURES/'egress-wire-contract-v2-review2.json').read_bytes()
        cls.policy = (FIXTURES/'provider-policy-disabled-v1.json').read_bytes()
        # Exact hashes are checked independently of the future implementation.
        if hashlib.sha256(cls.wire).hexdigest() != WIRE_SHA: raise AssertionError('wire fixture drift')
        if hashlib.sha256(cls.policy).hexdigest() != POLICY_SHA: raise AssertionError('policy fixture drift')

    def plan(self, value=None, *, raw=None, wire=None, policy=None):
        return prepare_bybit_request_plan(encoded(request() if value is None else value) if raw is None else raw,
                wire_contract_bytes=self.wire if wire is None else wire,
                provider_policy_bytes=self.policy if policy is None else policy)

    def assert_blocked_data(self, plan):
        v=plan.as_dict()
        self.assertEqual(v['state'],'DATA_ONLY_NOT_ADMITTED')
        self.assertEqual(v['wire_profile_sha256'],WIRE_SHA)
        self.assertEqual(v['policy_raw_sha256'],POLICY_SHA)
        self.assertEqual(v['policy_body_digest'],BODY_SHA)
        self.assertIs(v['operation_enabled'],False)
        self.assertIsNone(v['activation_from_utc']);self.assertIsNone(v['activation_until_utc'])
        self.assertIs(v['quota_reserved'],False);self.assertIs(v['consume_performed'],False)
        self.assertIs(v['send_permission'],False)
        self.assertEqual(v['connection_state'],'UNVERIFIED')
        self.assertFalse(hasattr(plan,'send'));self.assertFalse(hasattr(plan,'reserve'));self.assertFalse(hasattr(plan,'consume'))
        self.assertLessEqual(len(plan.canonical_plan_bytes),32768)

    def test_all_six_frozen_descriptors_only_prepare_blocked_data(self):
        cases=[
            (request('instruments.v1','historical_backfill',[],{'limit':'1000','cursor':None}),
             '5d97f13c31c33de8368f29bc405804fe73f33d4fe00d2d1c689180a120fc5aa9'),
            (request('kline.1m.v1','historical_backfill',[instrument()],{'interval':'1','range':{'start_ms':'0','end_ms':'120000'},'limit':'1000'}),
             'c010d686dd1ccb125de69a41108132f73718dd2a2516a3aafa4f6a689f003047'),
            (request('ws.connect.v1','live_ingestion',[],{}),
             '10f48e096c93e8cd777def0ae4ab4f09846a5656f6d1467188364c50e74930bd'),
            (request('ws.ping.v1','live_heartbeat',[],{}),
             'ef47e7c831e96e8dd9651b8221ff71e49b6c325f0148eeb93a9968c29ea4f5cd'),
            (request(),'0761c5eed4bc4efd2dcc58ede9b6c1a704aa8083048bbdd4da3f868e749a0d71'),
            (request('ws.unsubscribe.v1'),'0a4d6126f3391b846426334d34700ddfddaf482fd954f237116164561e3da934'),
        ]
        for value,digest in cases:
            with self.subTest(operation=value['operation_id']):
                plan=self.plan(value);self.assert_blocked_data(plan)
                self.assertEqual(plan.as_dict()['operation_digest'],digest)

    def test_twenty_requested_topics_make_two_ten_arg_actions_in_input_order(self):
        identities=[instrument('S'+str(i)+'USDT') for i in range(20)]
        topics=['publicTrade.'+i['symbol'] for i in identities]
        value=request(instruments=identities,payload={'topics':topics})
        plan=self.plan(value);self.assert_blocked_data(plan);v=plan.as_dict()
        self.assertEqual(v['minimum_fresh_attempts'],'2')
        self.assertEqual(len(v['actions']),2)
        self.assertEqual(json.loads(v['actions'][0]['body_ascii']),{'op':'subscribe','args':topics[:10]})
        self.assertEqual(json.loads(v['actions'][1]['body_ascii']),{'op':'subscribe','args':topics[10:]})
        for action in v['actions']:
            self.assertLessEqual(len(json.loads(action['body_ascii'])['args']),10)
            self.assertIsNone(action['query'])

    def test_exact_100_requested_topics_produce_ten_data_only_actions(self):
        ids=[instrument('S'+str(i)+'USDT') for i in range(100)]
        plan=self.plan(request(instruments=ids,payload={'topics':['tickers.'+i['symbol'] for i in ids]}))
        self.assertEqual(len(plan.as_dict()['actions']),10);self.assert_blocked_data(plan)

    def test_101_topics_reject_whole_plan_not_truncate(self):
        ids=[instrument('S'+str(i)+'USDT') for i in range(101)]
        with self.assertRaises(PlanFormatError):
            self.plan(request(instruments=ids,payload={'topics':['tickers.'+i['symbol'] for i in ids]}))

    def test_duplicate_topics_reject_rather_than_silent_dedup(self):
        value=request();value['payload']['topics']*=2
        with self.assertRaises(PlanFormatError):self.plan(value)

    def test_duplicate_instrument_identity_rejects(self):
        value=request();value['instruments']*=2
        with self.assertRaises(PlanFormatError):self.plan(value)

    def test_same_symbol_two_incarnations_cannot_collapse_to_one_topic(self):
        value=request(instruments=[instrument(),instrument(version='2')])
        with self.assertRaises(PlanFormatError):self.plan(value)

    def test_kline_half_open_range_has_exact_inclusive_transport_projection(self):
        value=request('kline.1m.v1','historical_backfill',[instrument()],
                      {'interval':'1','range':{'start_ms':'0','end_ms':'120000'},'limit':'1000'})
        action=self.plan(value).as_dict()['actions'][0]
        self.assertEqual(action['method'],'GET')
        self.assertEqual(action['path_or_action'],'/v5/market/kline')
        self.assertEqual(action['query'],{'category':'linear','symbol':'BTCUSDT','interval':'1','start':'0','end':'119999','limit':'1000'})
        self.assertIsNone(action['body_ascii'])

    def test_catalog_cursor_preserved_as_opaque_data_not_decoded_url(self):
        value=request('instruments.v1','historical_backfill',[],{'limit':'10','cursor':'A%2FB+='})
        query=self.plan(value).as_dict()['actions'][0]['query']
        self.assertEqual(query['cursor'],'A%2FB+=')

    def test_valid_explicit_incarnation_never_defaults_to_one(self):
        plan=self.plan(request(instruments=[instrument(version='2')]))
        self.assertEqual(plan.as_dict()['instrument_ids'][0]['instrument_version'],'2')
        self.assert_blocked_data(plan)

    def test_plan_and_request_are_detached_and_immutable(self):
        value=request();raw=encoded(value);plan=self.plan(raw=raw)
        value['payload']['topics'].clear();plan.as_dict()['actions'].clear()
        self.assertEqual(plan.canonical_request_bytes,raw)
        self.assertEqual(len(plan.as_dict()['actions']),1)
        with self.assertRaises((AttributeError,TypeError)):plan.canonical_plan_bytes=b'{}'

    def test_no_io_or_clock_during_future_pure_call(self):
        raw=encoded(request())
        with patch('socket.socket',side_effect=AssertionError('socket forbidden')), \
             patch('builtins.open',side_effect=AssertionError('file IO forbidden')), \
             patch('time.time',side_effect=AssertionError('wall clock forbidden')), \
             patch('time.monotonic',side_effect=AssertionError('clock forbidden')):
            self.assert_blocked_data(self.plan(raw=raw))

    def test_changed_profile_or_enabled_policy_image_cannot_self_authorize(self):
        with self.assertRaises(PlanFormatError):self.plan(wire=self.wire+b'\n')
        policy=json.loads(self.policy);policy['operations'][0]['enabled']=True
        with self.assertRaises(PlanFormatError):self.plan(policy=encoded(policy))

    def test_profile_preflight_bounds_before_any_hash(self):
        for argument in ('wire','policy'):
            with self.subTest(argument=argument):
                # Spy on actual future module hash entry, not a copied parser.
                with patch('grid.bybit_request_plan.hashlib.sha256') as hashing:
                    with self.assertRaises(PlanFormatError):self.plan(**{argument:b'x'*65537})
                    self.assertEqual(hashing.call_count,0)

    def test_request_preflight_bound_before_any_hash(self):
        with patch('grid.bybit_request_plan.hashlib.sha256') as hashing:
            with self.assertRaises(PlanFormatError):self.plan(raw=b'x'*32769)
            self.assertEqual(hashing.call_count,0)


MUTATIONS=[
 ('unknown_operation',('operation_id',),'bybit.public.linear.unknown.v1'),
 ('provider_time_not_bootstrap_exempt',('operation_id',),'bybit.public.time.v1'),
 ('archive_not_http_alias',('operation_id',),'bybit.public.archive.download.v1'),
 ('tcp_readiness_not_free',('operation_id',),'bybit.tcp.readiness.v1'),
 ('order_never_supported',('operation_id',),'bybit.private.order.create.v1'),
 ('caller_control_priority',('requested_priority',),'control'),
 ('wire_hash',('wire_profile_sha256',),'0'*64),
 ('policy_hash',('policy_raw_sha256',),'0'*64),
 ('topic_case',('payload','topics'),['publicTrade.btcusdt']),
 ('unknown_symbol',('payload','topics'),['publicTrade.ETHUSDT']),
 ('unknown_topic_family',('payload','topics'),['kline.1.BTCUSDT']),
 ('unknown_book_depth',('payload','topics'),['orderbook.500.BTCUSDT']),
 ('empty_topics',('payload','topics'),[]),
]
for name,path,value in MUTATIONS:
    def test(self,path=path,value=value):
        data=request();target=data
        for key in path[:-1]:target=target[key]
        target[path[-1]]=copy.deepcopy(value)
        with self.assertRaises(PlanFormatError):self.plan(data)
    setattr(RequestPlanSourceTests,'test_reject_'+name,test)

IDENTITY_MUTATIONS=[('category','spot'),('exchange','BYBIT'),('symbol','btcusdt'),
                    ('symbol','BTCUSDT\n'),('symbol','BTC\u00e9USDT'),
                    ('instrument_version','0'),('instrument_version','01'),
                    ('instrument_version','9223372036854775808'),('instrument_version',1)]
for index,(key,value) in enumerate(IDENTITY_MUTATIONS):
    def test(self,key=key,value=value):
        data=request();data['instruments'][0][key]=value
        with self.assertRaises(PlanFormatError):self.plan(data)
    setattr(RequestPlanSourceTests,'test_reject_identity_'+str(index),test)

KLINE_MUTATIONS=[(('interval',),'5'),(('limit',),'0'),(('limit',),'1001'),(('limit',),1000),
                 (('range','start_ms'),'1'),(('range','end_ms'),'0'),
                 (('range','end_ms'),'60060000'),(('range','start_ms'),False),
                 (('range','end_ms'),'253402300800000')]
for index,(path,value) in enumerate(KLINE_MUTATIONS):
    def test(self,path=path,value=value):
        data=request('kline.1m.v1','historical_backfill',[instrument()],
                     {'interval':'1','range':{'start_ms':'0','end_ms':'120000'},'limit':'1000'})
        target=data['payload']
        for key in path[:-1]:target=target[key]
        target[path[-1]]=value
        with self.assertRaises(PlanFormatError):self.plan(data)
    setattr(RequestPlanSourceTests,'test_reject_kline_payload_'+str(index),test)

for index,cursor in enumerate(['', 'x'*1025, True]):
    def test(self,cursor=cursor):
        data=request('instruments.v1','historical_backfill',[],{'limit':'1000','cursor':cursor})
        with self.assertRaises(PlanFormatError):self.plan(data)
    setattr(RequestPlanSourceTests,'test_reject_catalog_cursor_'+str(index),test)

for key,value in [('authorized',True),('clock_bootstrap',True),('endpoint','https://example.invalid/'),
                  ('credentials','never'),('grant_id','caller'),('scope_id','caller')]:
    def test(self,key=key,value=value):
        data=request();data[key]=value
        with self.assertRaises(PlanFormatError):self.plan(data)
    setattr(RequestPlanSourceTests,'test_reject_unknown_'+key,test)

for index,raw in enumerate([b'{}',b'[]',b'['*400+b']'*400]):
    def test(self,raw=raw):
        with self.assertRaises(PlanFormatError):self.plan(raw=raw)
    setattr(RequestPlanSourceTests,'test_reject_hostile_shape_'+str(index),test)

for name,transform in [('trailing_lf',lambda b:b+b'\n'),('leading_space',lambda b:b' '+b),
                       ('duplicate_key',lambda b:b.replace(b'{',b'{"schema":"duplicate",',1)),
                       ('noncanonical_escape',lambda b:b.replace(b'BTCUSDT',b'BTCUSD\\u0054'))]:
    def test(self,transform=transform):
        with self.assertRaises(PlanFormatError):self.plan(raw=transform(encoded(request())))
    setattr(RequestPlanSourceTests,'test_reject_encoding_'+name,test)


if __name__=='__main__':unittest.main()
