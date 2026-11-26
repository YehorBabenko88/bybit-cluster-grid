"""Pure closed four-role retirement custody; no owner imports or acceptance grant."""
import ast,hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
# Development custody is loaded from detached, hash-verified bytes, never sys.path.
import hashlib as _lineage_hashlib
from pathlib import Path as _LineagePath
from types import ModuleType as _LineageModule
_lineage_path = _LineagePath(__file__).resolve().parents[2]/'scripts/runtime_lineage_custody.py'
_lineage_raw = _lineage_path.read_bytes()
if _lineage_hashlib.sha256(_lineage_raw).hexdigest() != '9cec6e527a0fc80d845452e1bdbdd50962625ecf7bbb5c1e931eeb0f47e63e72':
 raise ValueError('LINEAGE_HELPER_SOURCE_SEAL')
_lineage_module = _LineageModule('_sealed_data_runtime_lineage')
_lineage_module.__file__ = str(_lineage_path)
exec(compile(_lineage_raw,str(_lineage_path),'exec'),_lineage_module.__dict__)
verified_contexts = _lineage_module.verified_contexts
def historical_context():
 return verified_contexts(ROOT)['VERIFIED_HISTORICAL']
DOC=ROOT/'docs/migration/pattern-statistics-bootstrap-retirement'
OLD_IDS=["tests/research/test_pattern_evaluation.py::test_pattern_evaluator_is_chronological_and_returns_verdict","tests/research/test_pattern_evaluation.py::test_empty_pattern_never_becomes_keep","tests/research/test_statistics_reporting.py::test_statistics_compute_core_metrics_drawdown_and_streaks","tests/research/test_validation_resampling.py::test_bootstrap_expectancy_is_seeded_and_contains_sample_mean"]
RAW_SHA={"strattester/research/pattern_evaluation.py":"dae7ec661950dd4b2b4ba0d567be8981e4ec0163825916825acbe61036173709","strattester/research/statistics.py":"dc5a03194c57d1f0c6151462787b0836490aa157a5b4f1c65988c70e60b6269e","strattester/research/resampling.py":"4d80e652e63646e2cd6dcdf870472584ca61c9b936a619de3a4ad010e2ae4d5b","tests/research/test_pattern_evaluation.py":"36f7d34194e660d70bfb31c257cbb204f43f731aceb29b7c155602626005f1c6","tests/research/test_statistics_reporting.py":"9a404f3c1460e4f85d700e0cb4c80f0fc2d43d772f92b1629676f26dee4ba0ac","tests/research/test_validation_resampling.py":"4d22060095ce2c3f5bfe782f0bebb10520b7940a2df255d7247713c445f7e215"}
PRESERVED={"docs/ci/retained-legacy-test-inventory.json":"f9868f6ef7b29936f056446896e39d3f1fc602a37096f97b8759479d60e73df9","docs/ci/four-owner-legacy-obligations.json":"ebb9a9e5b56932e14c1f74986c355b6c9c828df26cb035c98cb0c8349f1427d0","docs/migration/entry-context-retirement/transfer-ledger.json":"02005d84cdd85edb64d2fb7428fae6d47c81c91a1320eb2a45a157ecf26c994d","docs/migration/scale-mc-retirement/transfer-ledger.json":"293f94b9bf4146e7d3046c1a0ff35e8b1a89ca7c87ff168ac7504060da2a6477","docs/migration/reporting-retirement/transfer-ledger.json":"2b746b67eda7332e838fdb28a373f016d337c5a57cff0080d0ff7ba93e95181f"}
NEW_IDS=["tests/market_data/test_pattern_statistics_bootstrap_retirement.py::test_pattern_chronological_role_is_owned_by_independent_signal_accounts","tests/market_data/test_pattern_statistics_bootstrap_retirement.py::test_empty_pattern_role_preserves_no_evidence_refusal","tests/market_data/test_pattern_statistics_bootstrap_retirement.py::test_statistics_role_is_owned_by_declared_trade_summary","tests/market_data/test_pattern_statistics_bootstrap_retirement.py::test_bootstrap_role_is_owned_by_iid_mean_bootstrap"]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def functions(raw):
 text=raw.decode('utf8');return {n.name:ast.get_source_segment(text,n) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
def current_archive(path):
 value=json.loads((DOC/'transfer-ledger.json').read_bytes());return (ROOT/value['archives'][path]['archive']).read_bytes()
def common(role):
 raw=(DOC/'transfer-ledger.json').read_bytes();assert sha(raw)=='3b2ddef46c7001b271a446a098fb5dae26ef5f9e34524710819451aceaf421f6'
 value=json.loads(raw)
 assert set(value)==set(["schema","source_head","status","original_legacy_total","accepted_original_roles","remaining_accepted","candidate_original_roles","conditional_after_acceptance_publication_current_CI","prior_accepted_original_ids","roles","archives","old_canonical","canonical_current_count","canonical_ordered_sha256","new_ids","preserved_inventory","runtime49","runtime_anchor_unchanged","MathSDKSourceUnchanged","runtime_dependency_added","authority","release"])
 assert value['schema']=='market_data.pattern-statistics-bootstrap-source-retirement.v1' and value['source_head']=='cef6365fb9241a62e9ffc3ddb610d2a8575fd6e3'
 assert value['status']=='PRIVATE_SOURCE_REMOVAL_CANDIDATE_PENDING_INDEPENDENT_QA_PUBLICATION_CURRENT_CI'
 assert (value['original_legacy_total'],value['accepted_original_roles'],value['remaining_accepted'],value['candidate_original_roles'])==(547,37,510,4)
 assert value['conditional_after_acceptance_publication_current_CI']=={'accepted_original_roles':41,'remaining':506}
 assert value['runtime_dependency_added'] is False and value['authority'] is False and value['release']=='NO_GO'
 assert value['MathSDKSourceUnchanged']=='9ed369ddd41ae32c4b3a9434f0b29d6dcf51154f'
 previous=json.loads((ROOT/'docs/migration/reporting-retirement/transfer-ledger.json').read_bytes())
 prior=previous['prior_accepted_original_ids']+[r['original_id'] for r in previous['roles']]
 assert value['prior_accepted_original_ids']==prior and len(prior)==len(set(prior))==37
 originals={r['path']+'::'+name for r in json.loads((ROOT/'docs/ci/retained-legacy-test-inventory.json').read_bytes()) for name in r['tests']}
 assert len(originals)==547 and set(prior)<=originals and set(OLD_IDS)<=originals and not set(prior)&set(OLD_IDS)
 assert [r['original_id'] for r in value['roles']]==OLD_IDS
 assert value['roles']==json.loads(r'''[{"original_id":"tests/research/test_pattern_evaluation.py::test_pattern_evaluator_is_chronological_and_returns_verdict","replacement":"tests/test_independent_signal_evaluation.py::IndependentSignalAccountTests::test_original28_fivefold_and_empty_both_models","required_mode":"INDEPENDENT_PER_SIGNAL_V1","owner":"Terminan","owner_commit":"6c0e003a2552522a85638e9f52927c223dd44b34","canonical_api":"terminan.research_evaluation.evaluate_research_signals"},{"original_id":"tests/research/test_pattern_evaluation.py::test_empty_pattern_never_becomes_keep","replacement":"tests/test_independent_signal_evaluation.py::IndependentSignalAccountTests::test_original28_fivefold_and_empty_both_models","required_mode":"INDEPENDENT_PER_SIGNAL_V1","owner":"Terminan","owner_commit":"6c0e003a2552522a85638e9f52927c223dd44b34","canonical_api":"terminan.research_evaluation.evaluate_research_signals"},{"original_id":"tests/research/test_statistics_reporting.py::test_statistics_compute_core_metrics_drawdown_and_streaks","replacement":"tests/test_profit_loss_numeric.py::DeclaredTradeNumericTests::test_declared_trade_hand_oracle","labelled_original_subtest":true,"owner":"Math","owner_commit":"50048413605389a024dfef60e98f70126d788671","canonical_api":"history_statistics.numeric_trade_summary"},{"original_id":"tests/research/test_validation_resampling.py::test_bootstrap_expectancy_is_seeded_and_contains_sample_mean","replacement":"tests/test_screening_numeric.py::ScreeningNumericTests::test_iid_repeated_draw_order_deterministic","labelled_original_subtest":true,"owner":"Math","owner_commit":"50048413605389a024dfef60e98f70126d788671","canonical_api":"history_statistics.iid_observation_mean_bootstrap"}]''')
 assert value['preserved_inventory']==PRESERVED
 for path,digest in PRESERVED.items():assert sha((ROOT/path).read_bytes())==digest
 assert value['archives']==json.loads(r'''{"strattester/research/pattern_evaluation.py":{"archive":"docs/migration/pattern-statistics-bootstrap-retirement/raw/strattester__research__pattern_evaluation.py.txt","sha256":"dae7ec661950dd4b2b4ba0d567be8981e4ec0163825916825acbe61036173709","bytes":2467,"blob":"118eedbe15c3ad01fc0ff618431fd8d72b50332b"},"strattester/research/statistics.py":{"archive":"docs/migration/pattern-statistics-bootstrap-retirement/raw/strattester__research__statistics.py.txt","sha256":"dc5a03194c57d1f0c6151462787b0836490aa157a5b4f1c65988c70e60b6269e","bytes":1887,"blob":"fab928cde9976cf3fd9c9d2811e6b1b29e26cff2"},"strattester/research/resampling.py":{"archive":"docs/migration/pattern-statistics-bootstrap-retirement/raw/strattester__research__resampling.py.txt","sha256":"4d80e652e63646e2cd6dcdf870472584ca61c9b936a619de3a4ad010e2ae4d5b","bytes":916,"blob":"d174530ef200cf5a2b894f6d2cd838d8b58b6027"},"tests/research/test_pattern_evaluation.py":{"archive":"docs/migration/pattern-statistics-bootstrap-retirement/raw/tests__research__test_pattern_evaluation.py.txt","sha256":"36f7d34194e660d70bfb31c257cbb204f43f731aceb29b7c155602626005f1c6","bytes":1062,"blob":"0c8b5cfa67ff08aba5bd24417830cb7da2df90ea"},"tests/research/test_statistics_reporting.py":{"archive":"docs/migration/pattern-statistics-bootstrap-retirement/raw/tests__research__test_statistics_reporting.py.txt","sha256":"9a404f3c1460e4f85d700e0cb4c80f0fc2d43d772f92b1629676f26dee4ba0ac","bytes":943,"blob":"ba8e36d25af186944b4fec902b3f148f0b6c1757"},"tests/research/test_validation_resampling.py":{"archive":"docs/migration/pattern-statistics-bootstrap-retirement/raw/tests__research__test_validation_resampling.py.txt","sha256":"4d22060095ce2c3f5bfe782f0bebb10520b7940a2df255d7247713c445f7e215","bytes":1164,"blob":"0ae6357e9f7bc616f103b4dd04076aa5e199d260"}}''')
 assert value['old_canonical']==json.loads(r'''{"archive":"docs/migration/pattern-statistics-bootstrap-retirement/canonical-891-roster.json","sha256":"e2f41ad7ada4f806a2ce95e561c8fda59216d9ee467cf9b70a6ba89afb6637a1","ordered_sha256":"bf927586b34ed8a5c44a98bfef06ff6823e54b11b1e3b41b803ff1e17e12cb3a","count":891}''')
 assert set(value['archives'])==set(RAW_SHA)
 for path,digest in RAW_SHA.items():
  item=value['archives'][path];raw=(ROOT/item['archive']).read_bytes()
  assert item['archive']=='docs/migration/pattern-statistics-bootstrap-retirement/raw/'+path.replace('/','__')+'.txt' and item['sha256']==digest and sha(raw)==digest and len(raw)==item['bytes']
 frozen=(DOC/'canonical-891-roster.json').read_bytes();assert sha(frozen)=='e2f41ad7ada4f806a2ce95e561c8fda59216d9ee467cf9b70a6ba89afb6637a1'==value['old_canonical']['sha256']
 before=json.loads(frozen);historical_roster=historical_context()['roster']
 assert len(before)==891 and historical_roster[:891]==before and historical_roster[891:895]==NEW_IDS==value['new_ids']
 assert len(historical_roster)==len(set(historical_roster))==898 and value['canonical_current_count']==895 and all(type(x) is str for x in historical_roster)
 assert sha(json.dumps(before,separators=(',',':'),ensure_ascii=True).encode())==value['old_canonical']['ordered_sha256']=='bf927586b34ed8a5c44a98bfef06ff6823e54b11b1e3b41b803ff1e17e12cb3a'
 assert sha(json.dumps(historical_roster[:895],separators=(',',':'),ensure_ascii=True).encode())==value['canonical_ordered_sha256']=='bc6d10725016a3841ae3d1c545ca8d7d9ffca193f128fc96b89b95d29edba033'
 historical_runtime49=historical_context()['runtime49']
 custody=historical_context()['custody']
 assert len(historical_runtime49)==49 and historical_runtime49==value['runtime49']==custody['runtime_files']
 assert custody['source_head']==value['runtime_anchor_unchanged']=='c05e0cabd6c6e4c2abb2002b7b69a8f1ba8aec57' and custody['canonical_current_count']==898
 for path in ["strattester/research/pattern_evaluation.py","strattester/research/statistics.py","strattester/research/resampling.py","tests/research/test_pattern_evaluation.py","tests/research/test_statistics_reporting.py"]:assert not (ROOT/path).exists()
 forbidden={'evaluate_entry_signals','PatternEvaluation','TradeMetrics','evaluate_trades','BootstrapCI','bootstrap_expectancy'}
 modules={'pattern_evaluation','statistics','resampling'}
 for path in (ROOT/'strattester').rglob('*.py'):
  for n in ast.walk(ast.parse(path.read_bytes())):
   if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Name)):assert (getattr(n,'name',None) or getattr(n,'id',None)) not in forbidden
   if isinstance(n,ast.ImportFrom):
    assert not ((n.module or '').split('.')[-1] in modules and ('research' in (n.module or '') or n.level))
    research_package=n.module in ('strattester.research','research') or n.level>0 and (n.module is None or n.module.split('.')[-1]=='research')
    assert not (research_package and any(alias.name in modules for alias in n.names))
   if isinstance(n,ast.Constant) and type(n.value) is str:assert not any(n.value==module or n.value.startswith((module+':',module+'.')) for module in ('strattester.research.pattern_evaluation','strattester.research.statistics','strattester.research.resampling'))
   if isinstance(n,ast.Import):assert not any(a.name.startswith('strattester.research.') and a.name.split('.')[-1] in modules for a in n.names)
 raw=current_archive('tests/research/test_validation_resampling.py');current=(ROOT/'tests/research/test_validation_resampling.py').read_bytes()
 expected=raw[:raw.index(b'def test_bootstrap_expectancy_is_seeded_and_contains_sample_mean(')].replace(b'from strattester.research.resampling import bootstrap_expectancy\n',b'')
 assert current==expected and len(functions(current))==3 and functions(current)=={k:v for k,v in functions(raw).items() if k!='test_bootstrap_expectancy_is_seeded_and_contains_sample_mean'}
 attrs=(ROOT/'.gitattributes').read_bytes();assert sha(attrs[:1189])=='2ec29875ab000ff51a2944e9223125ce45ff932976bc3446fd2f000b4ad4fef8'
 for policy in (b'docs/migration/pattern-statistics-bootstrap-retirement/canonical-891-roster.json -text',b'docs/migration/pattern-statistics-bootstrap-retirement/transfer-ledger.json -text'):assert policy in attrs.splitlines()
 mapping=value['roles'][role]
 if role<2:
  assert mapping['owner']=='Terminan' and mapping['owner_commit']=='6c0e003a2552522a85638e9f52927c223dd44b34' and mapping['required_mode']=='INDEPENDENT_PER_SIGNAL_V1'
  assert mapping['replacement']=='tests/test_independent_signal_evaluation.py::IndependentSignalAccountTests::test_original28_fivefold_and_empty_both_models'
 else:
  assert mapping['owner']=='Math' and mapping['owner_commit']=='50048413605389a024dfef60e98f70126d788671' and mapping['labelled_original_subtest'] is True
 return value
def test_pattern_chronological_role_is_owned_by_independent_signal_accounts():
 common(0)
def test_empty_pattern_role_preserves_no_evidence_refusal():
 common(1)
def test_statistics_role_is_owned_by_declared_trade_summary():
 common(2)
def test_bootstrap_role_is_owned_by_iid_mean_bootstrap():
 common(3)
