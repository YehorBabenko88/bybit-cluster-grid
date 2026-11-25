"""Closed custody of four original roles; no Term/Math runtime import or counter grant."""
import ast,hashlib,json,pathlib,tomllib
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
DOC=ROOT/"docs/migration/scale-mc-retirement"
OLD_IDS=["tests/research/test_scale_execution.py::test_scale_trade_has_two_independent_entry_legs_and_partial_targets","tests/research/test_scale_execution.py::test_scale_trade_does_not_share_state_between_calls","tests/research/test_scale_execution.py::test_scale_trade_can_move_stop_after_first_target","tests/research/test_validation_resampling.py::test_monte_carlo_drawdown_is_seeded"]
RAW_HASHES={"strattester/research/execution.py":"99c1a3a7907b0481c0f2a4f239fb6808f137834b39fffaf7885ef60f66246832","tests/research/test_scale_execution.py":"c4b2c3dd70f42a8f7e0926d8e1f4c8599fcd3531a39f92af8f3306e9d4839d96","strattester/research/resampling.py":"795b77b9e68d0265813645d48c277f379d0e1c6e27cbf33524d1a41c4cceef21","tests/research/test_validation_resampling.py":"abebf46ae3a067f011e7732d7c674c949cc842a292cf648aa56e9e90c9bd5a71"}
PRIOR_IDS_SHA="4ec755dd5f6e7f2ef46ed3d2beadd21fba5d985ca3f4ccbc603e3f117b5f67fe"

def _sha(raw):return hashlib.sha256(raw).hexdigest()
def _functions(raw):
 text=raw.decode('utf8');tree=ast.parse(text)
 return {n.name:ast.get_source_segment(text,n) for n in tree.body if isinstance(n,ast.FunctionDef)}
def _common(role):
 value=json.loads((DOC/'transfer-ledger.json').read_bytes())
 assert value['schema']=='market_data.scale-mc-source-retirement.v1' and value['source_head']=="30ef77cefe5e5b9d8af8dafc6da24e587711f897"
 assert (value['original_legacy_total'],value['accepted_original_roles'],value['remaining_accepted'],value['candidate_original_roles'])==(547,31,516,4)
 assert value['conditional_after_acceptance_publication_current_CI']=={'accepted_original_roles':35,'remaining':512}
 assert value['status']=='PRIVATE_SOURCE_REMOVAL_CANDIDATE_NOT_ACCEPTED_RETIREMENT'
 assert value['runtime_dependency_added'] is False and value['authority'] is False and value['release']=='NO_GO'
 prior=value['prior_accepted_original_ids'];assert len(prior)==len(set(prior))==31
 assert _sha(json.dumps(prior,separators=(',',':'),ensure_ascii=True).encode('ascii'))==PRIOR_IDS_SHA
 inventory=json.loads((ROOT/'docs/ci/retained-legacy-test-inventory.json').read_bytes())
 originals={row['path']+'::'+name for row in inventory for name in row['tests']}
 assert len(originals)==547 and set(prior)<=originals and set(OLD_IDS)<=originals and not set(prior)&set(OLD_IDS)
 assert [row['original_id'] for row in value['roles']]==OLD_IDS
 for relative,digest in value['preserved_inventory'].items():assert _sha((ROOT/relative).read_bytes())==digest
 for original,digest in RAW_HASHES.items():
  item=value['archives'][original];raw=(ROOT/item['archive']).read_bytes()
  assert item['sha256']==digest and _sha(raw)==digest and len(raw)==item['bytes']
 old=(ROOT/value['old_canonical']['archive']).read_bytes();assert _sha(old)==value['old_canonical']['sha256']
 before=json.loads(old);historical_roster=historical_context()['roster']
 assert len(before)==885 and historical_roster[:885]==before and len(historical_roster)==len(set(historical_roster))==898
 historical_runtime49=historical_context()['runtime49']
 assert len(historical_runtime49)==49 and historical_runtime49==value['runtime49']
 custody=historical_context()['custody']
 assert custody['source_head']==value['runtime_anchor_unchanged']=='c05e0cabd6c6e4c2abb2002b7b69a8f1ba8aec57' and custody['canonical_current_count']==898 and custody['runtime_files']==historical_runtime49
 project=tomllib.loads((ROOT/'pyproject.toml').read_text('utf8'));assert project['tool']['setuptools']['packages']==['market_data']
 assert all('terminan' not in dependency.lower() for dependency in project['project']['dependencies'])
 return value,value['roles'][role]
def _scale(role,canonical):
 assert not (ROOT/'tests/research/test_scale_execution.py').exists()
 value,mapping=_common(role)
 assert mapping['owner']=='Terminan' and mapping['owner_commit']=="26af145a1c53d85f607fc18c4fd200f0a42b0f73" and mapping['canonical_api']=='terminan.paper.PaperEngine.execute_scale_plan' and mapping['canonical_ids']==[canonical]
 raw=(ROOT/value['archives']['strattester/research/execution.py']['archive']).read_bytes();prefix=raw[:4515]
 assert _sha(prefix)=='47154908f325ef7b99c26e79f4184ccfb66756ed1998810a27d1a7f54de550a5'
 assert (ROOT/'strattester/research/execution.py').read_bytes()==prefix
 for p in (ROOT/'strattester').rglob('*.py'):
  tree=ast.parse(p.read_bytes())
  assert not any(isinstance(n,(ast.Name,ast.ClassDef,ast.FunctionDef)) and (getattr(n,'id',None) or getattr(n,'name',None)) in {'ScaleSignal','ExecutionFill','ExecutionExit','ScaleTrade','simulate_scale_trade'} for n in ast.walk(tree))

def test_scale_independent_legs_and_partial_targets_are_retired_to_sole_owner():
 _scale(0,"tests/test_scaled_limit_execution.py::ScaledLimitExecutionTests::test_two_independent_entry_legs_and_partial_targets")
def test_scale_no_shared_state_role_is_retired_to_sole_owner():
 _scale(1,"tests/test_scaled_limit_execution.py::ScaledLimitExecutionTests::test_no_state_shared_between_calls")
def test_scale_move_stop_role_is_retired_to_sole_owner():
 _scale(2,"tests/test_scaled_limit_execution.py::ScaledLimitExecutionTests::test_move_stop_after_first_target")
def test_seeded_monte_carlo_role_is_retired_without_changing_other_resampling():
 assert not (ROOT/'strattester/research/resampling.py').exists()
 source=(ROOT/'docs/migration/pattern-statistics-bootstrap-retirement/raw/strattester__research__resampling.py.txt').read_bytes()
 assert not {'_max_drawdown','monte_carlo_max_drawdowns'}&set(_functions(source))
 value,mapping=_common(3)
 assert mapping['owner']=='Math' and mapping['owner_commit']=="9379384606492af33619bc9168d259917da296a0" and mapping['canonical_api']=='history_statistics.permutation_drawdowns'
 assert mapping['canonical_ids']==["tests/test_permutation_drawdowns.py::PermutationDrawdownTests::test_exact_seed_order_matches_pinned_legacy","tests/test_permutation_drawdowns.py::PermutationDrawdownTests::test_hand_oracle_default_count_and_immutable_float_result","tests/test_permutation_drawdowns.py::PermutationDrawdownTests::test_global_random_state_and_inputs_unchanged"] and len(value['all_canonical_mc_ids'])==14
 old=(ROOT/value['archives']['strattester/research/resampling.py']['archive']).read_bytes()
 assert source==old[:916] and _sha(source)=="4d80e652e63646e2cd6dcdf870472584ca61c9b936a619de3a4ad010e2ae4d5b"
 original=(ROOT/value['archives']['tests/research/test_validation_resampling.py']['archive']).read_bytes()
 current=(ROOT/'docs/migration/pattern-statistics-bootstrap-retirement/raw/tests__research__test_validation_resampling.py.txt').read_bytes()
 old_functions=_functions(original);new_functions=_functions(current)
 assert len(old_functions)==5 and len(new_functions)==4 and 'test_monte_carlo_drawdown_is_seeded' not in new_functions
 assert {k:v for k,v in old_functions.items() if k!='test_monte_carlo_drawdown_is_seeded'}==new_functions
 assert current==original[:original.index(b'def test_monte_carlo_drawdown_is_seeded(')].replace(b',monte_carlo_max_drawdowns',b'')

 live=(ROOT/'tests/research/test_validation_resampling.py').read_bytes()
 assert live==current[:current.index(b'def test_bootstrap_expectancy_is_seeded_and_contains_sample_mean(')].replace(b'from strattester.research.resampling import bootstrap_expectancy\n',b'')
 assert len(_functions(live))==3 and _functions(live)=={k:v for k,v in new_functions.items() if k!='test_bootstrap_expectancy_is_seeded_and_contains_sample_mean'}
 for p in (ROOT/'strattester').rglob('*.py'):
  assert not any(isinstance(n,ast.Name) and n.id in {'_max_drawdown','monte_carlo_max_drawdowns'} for n in ast.walk(ast.parse(p.read_bytes())))
