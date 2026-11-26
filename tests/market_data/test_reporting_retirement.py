"""Pure reporting-role source custody; no runtime owner imports or acceptance grant."""
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
DOC=ROOT/'docs/migration/reporting-retirement'
OLD_IDS=["tests/research/test_statistics_reporting.py::test_primary_report_excludes_partial_history","tests/research/test_statistics_reporting.py::test_volatility_breakdown_keeps_sample_counts_and_coverage_separate"]
RAW_SHA={"strattester/research/reporting.py":"251bbbe7d14e6c711abbf532afe2f8c7a03b21e9e4eb6d11fe2cc6e718622089","tests/research/test_statistics_reporting.py":"2cfddb71a8925ec5989ed666e341b760cefb60a57cef39ea8949afcc58b5473a"}
PRESERVED={"docs/ci/retained-legacy-test-inventory.json":"f9868f6ef7b29936f056446896e39d3f1fc602a37096f97b8759479d60e73df9","docs/ci/four-owner-legacy-obligations.json":"ebb9a9e5b56932e14c1f74986c355b6c9c828df26cb035c98cb0c8349f1427d0","docs/migration/entry-context-retirement/transfer-ledger.json":"02005d84cdd85edb64d2fb7428fae6d47c81c91a1320eb2a45a157ecf26c994d","docs/migration/scale-mc-retirement/transfer-ledger.json":"293f94b9bf4146e7d3046c1a0ff35e8b1a89ca7c87ff168ac7504060da2a6477"}
NEW_IDS=["tests/market_data/test_reporting_retirement.py::test_reporting_primary_coverage_role_has_exact_canonical_counterpart","tests/market_data/test_reporting_retirement.py::test_reporting_volatility_role_removes_only_duplicate_source_and_preserves_custody"]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def functions(raw):
 text=raw.decode('utf-8');return {n.name:ast.get_source_segment(text,n) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
def common():
 value=json.loads((DOC/'transfer-ledger.json').read_bytes())
 assert set(value)==set(["schema","source_head","status","original_legacy_total","accepted_original_roles","remaining_accepted","candidate_original_roles","conditional_after_acceptance_publication_current_CI","prior_accepted_original_ids","roles","archives","old_canonical","canonical_current_count","canonical_ordered_sha256","preserved_inventory","runtime49","MathSDKSourceUnchanged","runtime_dependency_added","authority","release"])
 assert value['schema']=='market_data.reporting-source-retirement.v1' and value['source_head']=='da9e782470d1237122c99994c042c2834b026062'
 assert value['status']=='PRIVATE_SOURCE_REMOVAL_CANDIDATE_PENDING_TERM_PUBLICATION_INDEPENDENT_QA_AND_CURRENT_CI'
 assert (value['original_legacy_total'],value['accepted_original_roles'],value['remaining_accepted'],value['candidate_original_roles'])==(547,35,512,2)
 assert value['conditional_after_acceptance_publication_current_CI']=={'accepted_original_roles':37,'remaining':510}
 assert value['runtime_dependency_added'] is False and value['authority'] is False and value['release']=='NO_GO'
 assert value['MathSDKSourceUnchanged']=='9ed369ddd41ae32c4b3a9434f0b29d6dcf51154f'
 assert [r['original_id'] for r in value['roles']]==OLD_IDS
 for row in value['roles']:
  assert row['owner']=='Terminan' and row['owner_commit']=='f5e3a0bacad7b1bec7b0ca3cb72a1d0a148caddd' and row['owner_status']=='PRIVATE_PENDING_PUBLICATION_AND_CURRENT_CI'
  assert row['math_commit']=='9379384606492af33619bc9168d259917da296a0' and row['canonical_api']=='terminan.research_reporting.build_research_report'
  assert row['canonical_id']=='tests/test_research_reporting.py::ResearchReportingTests::test_all_filled_and_three_coverage_partitions_conserve_real_trades' and row['subtest_original_id']==row['original_id']
 assert [r['original_assertions'] for r in value['roles']]==[2,3]
 for original,digest in RAW_SHA.items():
  item=value['archives'][original];raw=(ROOT/item['archive']).read_bytes()
  assert item['sha256']==digest and sha(raw)==digest and len(raw)==item['bytes']
 assert value['preserved_inventory']==PRESERVED
 for path,digest in PRESERVED.items():assert sha((ROOT/path).read_bytes())==digest
 return value

def test_reporting_primary_coverage_role_has_exact_canonical_counterpart():
 value=common()
 assert not (ROOT/'strattester/research/reporting.py').exists()
 raw=(ROOT/value['archives']['tests/research/test_statistics_reporting.py']['archive']).read_bytes()
 original=functions(raw);assert len(original)==4
 assert 'test_primary_report_excludes_partial_history' in original and 'test_volatility_breakdown_keeps_sample_counts_and_coverage_separate' in original
 assert sorted(sum(isinstance(n,ast.Assert) for n in ast.walk(ast.parse(original[name]))) for name in ('test_primary_report_excludes_partial_history','test_volatility_breakdown_keeps_sample_counts_and_coverage_separate'))==[2,3]
 assert not (ROOT/'tests/research/test_statistics_reporting.py').exists()
 current=(ROOT/'docs/migration/pattern-statistics-bootstrap-retirement/raw/tests__research__test_statistics_reporting.py.txt').read_bytes()
 expected=raw[:raw.index(b'def test_primary_report_excludes_partial_history(')].replace(b'from strattester.research.reporting import research_report\n',b'')
 assert current==expected
 assert functions(current)=={k:v for k,v in original.items() if k not in ('test_primary_report_excludes_partial_history','test_volatility_breakdown_keeps_sample_counts_and_coverage_separate')}
 assert not (ROOT/'strattester/research/statistics.py').exists()
 assert sha((ROOT/'docs/migration/pattern-statistics-bootstrap-retirement/raw/strattester__research__statistics.py.txt').read_bytes())=='dc5a03194c57d1f0c6151462787b0836490aa157a5b4f1c65988c70e60b6269e'
 assert not (ROOT/'strattester/research/pattern_evaluation.py').exists()
 assert sha((ROOT/'docs/migration/pattern-statistics-bootstrap-retirement/raw/strattester__research__pattern_evaluation.py.txt').read_bytes())=='dae7ec661950dd4b2b4ba0d567be8981e4ec0163825916825acbe61036173709'

def test_reporting_volatility_role_removes_only_duplicate_source_and_preserves_custody():
 value=common()
 assert not (ROOT/'strattester/research/reporting.py').exists()
 for path in (ROOT/'strattester').rglob('*.py'):
  for node in ast.walk(ast.parse(path.read_bytes())):
   assert not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Name)) or (getattr(node,'name',None) or getattr(node,'id',None)) not in {'research_report','ResearchReport'}
   if isinstance(node,ast.ImportFrom):assert not (node.module or '').endswith('research.reporting') and node.module!='reporting'
 prior=value['prior_accepted_original_ids'];assert len(prior)==len(set(prior))==35
 previous=json.loads((ROOT/'docs/migration/scale-mc-retirement/transfer-ledger.json').read_bytes())
 assert prior==previous['prior_accepted_original_ids']+[r['original_id'] for r in previous['roles']]
 inventory=json.loads((ROOT/'docs/ci/retained-legacy-test-inventory.json').read_bytes());originals={r['path']+'::'+name for r in inventory for name in r['tests']}
 assert len(originals)==547 and set(prior)<=originals and set(OLD_IDS)<=originals and not set(prior)&set(OLD_IDS)
 frozen=(ROOT/value['old_canonical']['archive']).read_bytes();assert sha(frozen)=='c1bf1dce6aa6d294019ba3c05b479544b167551222fcd7df5bdf963e26c569b2'==value['old_canonical']['sha256']
 before=json.loads(frozen);historical_roster=historical_context()['roster']
 assert len(before)==889 and historical_roster[:889]==before and historical_roster[889:891]==NEW_IDS and len(historical_roster)==len(set(historical_roster))==898 and value['canonical_current_count']==891
 assert sha(json.dumps(historical_roster[:891],separators=(',',':'),ensure_ascii=True).encode('ascii'))==value['canonical_ordered_sha256']=='bf927586b34ed8a5c44a98bfef06ff6823e54b11b1e3b41b803ff1e17e12cb3a'
 historical_runtime49=historical_context()['runtime49']
 assert len(historical_runtime49)==49 and historical_runtime49==value['runtime49']
 attrs=(ROOT/'.gitattributes').read_bytes();assert sha(attrs[:730])=='e30342895d6598258847b98c8d450e2f38dacadc2742ac87ceb1dc448f149834'
 for policy in (b'docs/migration/reporting-retirement/canonical-889-roster.json -text',b'docs/migration/reporting-retirement/transfer-ledger.json -text',b'tests/research/test_statistics_reporting.py text eol=lf',b'.gitattributes text eol=lf',b'docs/migration/scale-mc-retirement/transfer-ledger.json -text',b'strattester/research/statistics.py text eol=lf',b'strattester/research/pattern_evaluation.py text eol=lf'):assert policy in attrs.splitlines()
