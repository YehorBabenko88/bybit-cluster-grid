
"""Custody of two transferred research roles; no Terminan runtime import."""
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
LEDGER=ROOT/'docs/migration/entry-context-retirement/transfer-ledger.json'
def ledger():
 value=json.loads(LEDGER.read_bytes())
 assert set(value)=={'schema','source_head','target','roles','original_raw_archives','preserved_inventory','runtime_baseline','baseline_canonical_count','added_custody_cases','candidate_canonical_count','original_legacy_total','remaining_accepted','remaining_after_acceptance_publication_CI','candidate_original_roles','status','runtime_dependency_added','authority','production'}
 return value
def test_exact_two_original_roles_bind_published_canonical_owner():
 value=ledger()
 assert value['target']=={'repository':'YehorBabenko88/Terminan','commit':'7ba5eb12987ecb6ab80f3b1139cc5ef56c3bfe14','pr':123,'api':'terminan.entry_context.build_entry_context'}
 assert {r['original_id'] for r in value['roles']}=={'tests/research/test_trade_context.py::test_entry_context_uses_latest_snapshot_known_at_entry','tests/research/test_trade_context.py::test_future_context_is_never_attached'}
 assert {r['canonical_id'] for r in value['roles']}=={'tests/test_entry_context.py::EntryContextTests::test_entry_context_uses_latest_snapshot_available_at_entry','tests/test_entry_context.py::EntryContextTests::test_future_context_is_never_attached'}
 assert sorted(r['original_assertion_count'] for r in value['roles'])==[2,4]
 assert value['candidate_original_roles']==2 and value['remaining_accepted']==518 and value['remaining_after_acceptance_publication_CI']==516
 assert value['runtime_dependency_added'] is False and value['authority']=='NONE' and value['production']=='NO_GO'
def test_original_547_inventory_bytes_and_all_788_baseline_roles_preserved():
 value=ledger()
 for row in value['preserved_inventory']:
  raw=(ROOT/row['path']).read_bytes()
  assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256']
 original=json.loads((ROOT/'docs/ci/retained-legacy-test-inventory.json').read_bytes())
 assert sum(len(row['tests']) for row in original)==547
 baseline=json.loads((ROOT/'docs/migration/entry-context-retirement/canonical-788-roster.json').read_bytes())
 historical_roster=historical_context()['roster']
 custody=historical_context()['custody']
 original_raw=(ROOT/custody['canonical_original_archive']).read_bytes()
 assert hashlib.sha256(original_raw).hexdigest()==custody['canonical_original_sha256']
 original=json.loads(original_raw)
 assert len(baseline)==788 and historical_roster[:788]==baseline
 assert len(original)==custody['canonical_original_count']==791 and historical_roster[:791]==original
 assert len(historical_roster)==custody['canonical_current_count']==898
 assert len(set(historical_roster))==898
 assert not any('test_trade_context.py' in node for node in baseline)
def test_only_unowned_context_source_removed_no_runtime_dependency_or_alias():
 value=ledger()
 for path in ('strattester/research/trade_context.py','tests/research/test_trade_context.py'):
  assert not (ROOT/path).exists()
 for path in (ROOT/'strattester').rglob('*.py'):
  raw=path.read_text(encoding='utf8')
  assert 'trade_context' not in raw and 'attach_entry_context' not in raw
 custody=historical_context()['custody']
 assert custody['schema']=='market_data.turnover-runtime-custody.v1' and custody['source_head']=='c05e0cabd6c6e4c2abb2002b7b69a8f1ba8aec57'
 assert set(custody['changed_baseline_archives'])=={'market_data/footprint_state.py','market_data/provenance.py','market_data/history_export.py','market_data/history_export_v11.py','market_data/numeric_dto.py','market_data/history_snapshot.py'}
 assert custody['legacy_ledger_modified'] is False
 historical_runtime49=historical_context()['runtime49']
 assert len(historical_runtime49)==49 and historical_runtime49==custody['runtime_files']
 for relative,sha in value['runtime_baseline'].items():
  archive=custody['changed_baseline_archives'].get(relative)
  assert hashlib.sha256((ROOT/(archive or relative)).read_bytes()).hexdigest()==sha
 assert len(value['runtime_baseline'])==45
 project=tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf8'))
 assert project['tool']['setuptools']['packages']==['market_data']
 assert all('terminan' not in x.lower() for x in project['project']['dependencies'])
 for path in (ROOT/'market_data').glob('*.py'):
  tree=ast.parse(path.read_bytes())
  for node in ast.walk(tree):
   if isinstance(node,ast.ImportFrom):assert not (node.module or '').startswith('terminan')
   if isinstance(node,ast.Import):assert all(not n.name.startswith('terminan') for n in node.names)
