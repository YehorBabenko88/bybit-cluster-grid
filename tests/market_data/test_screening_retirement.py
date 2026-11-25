"""Pure closed screening retirement custody; no Term import or authority grant."""
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
# Mandatory source retirement custody: exact detached sealed DEV helper, no fallback.
import hashlib as _retirement_hashlib
from pathlib import Path as _RetirementPath
from types import ModuleType as _RetirementModule
_retirement_path = _RetirementPath(__file__).resolve().parents[2]/'scripts/ordinary_execution_retirement_custody.py'
_retirement_raw = _retirement_path.read_bytes()
if _retirement_hashlib.sha256(_retirement_raw).hexdigest() != '5bbf148b9517e744a86b02943df8be64ce606d24e592a6c30603a8ab6e2d5ca3':
 raise ValueError('RETIREMENT_HELPER_SOURCE_SEAL')
_retirement_module = _RetirementModule('_sealed_ordinary_execution_retirement')
_retirement_module.__file__ = str(_retirement_path)
exec(compile(_retirement_raw,str(_retirement_path),'exec'),_retirement_module.__dict__)
verified_pre_cut_archives = _retirement_module.verified_pre_cut_archives
verify_retired_execution_absence = _retirement_module.verify_retired_execution_absence

def pre_cut_sources():
 verify_retired_execution_absence(ROOT)
 return verified_pre_cut_archives(ROOT)['VERIFIED_PRE_CUT_ARCHIVES']

def historical_context():
 return verified_contexts(ROOT)['VERIFIED_HISTORICAL']
DOC=ROOT/'docs/migration/screening-retirement'
OLD_IDS=["tests/research/test_entry_screening.py::test_majority_losing_oos_pattern_is_rejected","tests/research/test_entry_screening.py::test_stable_oos_pattern_can_survive"]
NEW_IDS=["tests/market_data/test_screening_retirement.py::test_majority_loss_screening_role_has_exact_canonical_owner","tests/market_data/test_screening_retirement.py::test_stable_screening_role_retires_whole_module_and_preserves_catalog"]
PRESERVED={"docs/ci/retained-legacy-test-inventory.json":"f9868f6ef7b29936f056446896e39d3f1fc602a37096f97b8759479d60e73df9","docs/ci/four-owner-legacy-obligations.json":"ebb9a9e5b56932e14c1f74986c355b6c9c828df26cb035c98cb0c8349f1427d0","docs/migration/entry-context-retirement/transfer-ledger.json":"02005d84cdd85edb64d2fb7428fae6d47c81c91a1320eb2a45a157ecf26c994d","docs/migration/scale-mc-retirement/transfer-ledger.json":"293f94b9bf4146e7d3046c1a0ff35e8b1a89ca7c87ff168ac7504060da2a6477","docs/migration/reporting-retirement/transfer-ledger.json":"2b746b67eda7332e838fdb28a373f016d337c5a57cff0080d0ff7ba93e95181f","docs/migration/pattern-statistics-bootstrap-retirement/transfer-ledger.json":"3b2ddef46c7001b271a446a098fb5dae26ef5f9e34524710819451aceaf421f6"}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def functions(raw):
 text=raw.decode('utf8');return {n.name:ast.get_source_segment(text,n) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
def common(role):
 raw=(DOC/'transfer-ledger.json').read_bytes();assert sha(raw)=='d842a60c01943b574be1e8be85e3abba9a5e0ff1746aaa1d2bce3314aa78d6c1'
 value=json.loads(raw);assert set(value)==set(["schema","source_head","status","original_legacy_total","accepted_original_roles","remaining_accepted","candidate_original_roles","conditional_after_acceptance_publication_current_CI","prior_accepted_original_ids","roles","whole_module_additional_semantics","archives","old_canonical","canonical_current_count","canonical_ordered_sha256","new_ids","preserved_inventory","runtime49","runtime_anchor_unchanged","MathSDKSourceUnchanged","runtime_dependency_added","authority","release"])
 assert value['schema']=='market_data.screening-source-retirement.v1' and value['source_head']=='e25856cfd6f024257de4cd3bce75552c52399378'
 assert value['status']=='PRIVATE_SOURCE_REMOVAL_CANDIDATE_PENDING_INDEPENDENT_QA_PUBLICATION_CURRENT_CI'
 assert (value['original_legacy_total'],value['accepted_original_roles'],value['remaining_accepted'],value['candidate_original_roles'])==(547,41,506,2)
 assert value['conditional_after_acceptance_publication_current_CI']=={'accepted_original_roles':43,'remaining':504}
 assert value['runtime_dependency_added'] is False and value['authority'] is False and value['release']=='NO_GO'
 assert value['MathSDKSourceUnchanged']=='9ed369ddd41ae32c4b3a9434f0b29d6dcf51154f'
 previous=json.loads((ROOT/'docs/migration/pattern-statistics-bootstrap-retirement/transfer-ledger.json').read_bytes());prior=previous['prior_accepted_original_ids']+[r['original_id'] for r in previous['roles']]
 assert value['prior_accepted_original_ids']==prior and len(prior)==len(set(prior))==41
 originals={row['path']+'::'+name for row in json.loads((ROOT/'docs/ci/retained-legacy-test-inventory.json').read_bytes()) for name in row['tests']}
 assert len(originals)==547 and set(prior)<=originals and set(OLD_IDS)<=originals and not set(prior)&set(OLD_IDS)
 assert [r['original_id'] for r in value['roles']]==OLD_IDS and value['roles']==json.loads(r'''[{"original_id":"tests/research/test_entry_screening.py::test_majority_losing_oos_pattern_is_rejected","owner":"Terminan","owner_commit":"47e40e503f9fd405f8e69165a62a4ee3ab6eb27d","canonical_api":"terminan.strategy_screening.screen_research_pattern","canonical_id":"tests/test_strategy_screening.py::ResearchScreeningTests::test_original_majority_loss_is_rejected"},{"original_id":"tests/research/test_entry_screening.py::test_stable_oos_pattern_can_survive","owner":"Terminan","owner_commit":"47e40e503f9fd405f8e69165a62a4ee3ab6eb27d","canonical_api":"terminan.strategy_screening.screen_research_pattern","canonical_id":"tests/test_strategy_screening.py::ResearchScreeningTests::test_original_stable_folds_survive_only_as_research"}]''')
 assert value['whole_module_additional_semantics']==json.loads(r'''{"canonical_api":"terminan.strategy_screening.summarize_research_segments","canonical_ids":["tests/test_strategy_screening.py::ResearchScreeningTests::test_segments_keep_all_dimensions_and_explicit_units","tests/test_strategy_screening.py::ResearchScreeningTests::test_missing_segment_label_is_unknown_and_empty_is_empty"],"dimensions":["volatility_regime","symbol","level_kind"],"authority":false}''')
 assert value['preserved_inventory']==PRESERVED
 for path,digest in PRESERVED.items():assert sha((ROOT/path).read_bytes())==digest
 assert value['archives']==json.loads(r'''{"strattester/research/entry_screening.py":{"archive":"docs/migration/screening-retirement/raw/strattester__research__entry_screening.py.txt","blob":"540971e96734b928b145456f85f5e4e0787974b5","sha256":"59dad642d23ababafa1dd7ad9dac0c93474613f96f3c8b1f56f9a0866977f51e","bytes":2786},"tests/research/test_entry_screening.py":{"archive":"docs/migration/screening-retirement/raw/tests__research__test_entry_screening.py.txt","blob":"506293a38a9af5386dd392a87fd11b04ea47105d","sha256":"1c42b614b6c05029b8b216e6fd0a64877c0dca5998c9bcb5fa59183cfd90430c","bytes":1207}}''')
 for path,item in value['archives'].items():
  raw=(ROOT/item['archive']).read_bytes();assert sha(raw)==item['sha256'] and len(raw)==item['bytes']
 assert value['old_canonical']==json.loads(r'''{"archive":"docs/migration/screening-retirement/canonical-895-roster.json","sha256":"079c5fc28c4e719f2e197c58940fc4f053772074bc086e1a57ef51046c1ed5c3","count":895,"ordered_sha256":"bc6d10725016a3841ae3d1c545ca8d7d9ffca193f128fc96b89b95d29edba033"}''')
 frozen=(DOC/'canonical-895-roster.json').read_bytes();assert sha(frozen)=='079c5fc28c4e719f2e197c58940fc4f053772074bc086e1a57ef51046c1ed5c3'
 before=json.loads(frozen);historical_roster=historical_context()['roster']
 assert len(before)==895 and historical_roster[:895]==before and historical_roster[895:897]==NEW_IDS==value['new_ids']
 assert len(historical_roster)==len(set(historical_roster))==898 and value['canonical_current_count']==897 and all(type(x) is str for x in historical_roster)
 assert sha(json.dumps(before,separators=(',',':'),ensure_ascii=True).encode())==value['old_canonical']['ordered_sha256']=='bc6d10725016a3841ae3d1c545ca8d7d9ffca193f128fc96b89b95d29edba033'
 assert sha(json.dumps(historical_roster[:897],separators=(',',':'),ensure_ascii=True).encode())==value['canonical_ordered_sha256']=='a625c31418f78bb8bdb432a210d87707e7cffee0152ecfb7d4aa6b9e338d102f'
 historical_runtime49=historical_context()['runtime49']
 custody=historical_context()['custody']
 assert len(historical_runtime49)==49 and historical_runtime49==value['runtime49']==custody['runtime_files']
 assert custody['source_head']==value['runtime_anchor_unchanged']=='c05e0cabd6c6e4c2abb2002b7b69a8f1ba8aec57' and custody['canonical_current_count']==898
 assert not (ROOT/'strattester/research/entry_screening.py').exists()
 module='strattester.research.entry_screening';forbidden={'EntryPatternVerdict','screen_entry_pattern','segment_verdicts'}
 for path in (ROOT/'strattester').rglob('*.py'):
  for node in ast.walk(ast.parse(path.read_bytes())):
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Name)):assert (getattr(node,'name',None) or getattr(node,'id',None)) not in forbidden
   if isinstance(node,ast.ImportFrom):
    assert (node.module or '').split('.')[-1]!='entry_screening'
    research_package=node.module in ('strattester.research','research') or node.level>0 and (node.module is None or node.module.split('.')[-1]=='research')
    assert not (research_package and any(alias.name=='entry_screening' for alias in node.names))
   if isinstance(node,ast.Import):assert not any(a.name in (module,'entry_screening') or a.name.startswith((module+'.','entry_screening.')) for a in node.names)
   if isinstance(node,ast.Constant) and type(node.value) is str:assert not (node.value==module or node.value.startswith((module+':',module+'.')))
 raw=(ROOT/value['archives']['tests/research/test_entry_screening.py']['archive']).read_bytes();archived_pre_cut=pre_cut_sources()['tests/research/test_entry_screening.py']
 expected=b'\n'.join(raw.split(b'\n')[1:3])+b'\n\n'+raw[raw.index(b'def test_spec_only_hypotheses_cannot_enter_executable_ranking('):]
 assert archived_pre_cut==expected
 original=functions(raw);retained=functions(archived_pre_cut)
 assert len(original)==3 and len(retained)==1 and retained=={k:v for k,v in original.items() if k not in ('test_majority_losing_oos_pattern_is_rejected','test_stable_oos_pattern_can_survive')}
 attrs=(ROOT/'.gitattributes').read_bytes();assert sha(attrs[:1359])=='72dccdf9e0015ed49115382cd05adaf1e88da2bcb61751ec3014133bf855924e'
 for policy in (b'docs/migration/screening-retirement/canonical-895-roster.json -text',b'docs/migration/screening-retirement/transfer-ledger.json -text',b'tests/research/test_entry_screening.py text eol=lf'):assert policy in attrs.splitlines()
 return value,value['roles'][role]
def test_majority_loss_screening_role_has_exact_canonical_owner():
 common(0)
def test_stable_screening_role_retires_whole_module_and_preserves_catalog():
 common(1)
