"""Four exact structural obligations for required historical and live custody."""
import hashlib
from pathlib import Path
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


def test_legacy49_c05_and_math9ed_custody_is_preserved():
    verify_retired_execution_absence(Path(__file__).resolve().parents[2])
    verified_pre_cut_archives(Path(__file__).resolve().parents[2])
    assert hashlib.sha256((Path(__file__).resolve().parents[2]/'scripts/runtime_lineage_custody.py').read_bytes()).hexdigest()=='9cec6e527a0fc80d845452e1bdbdd50962625ecf7bbb5c1e931eeb0f47e63e72'
    contexts=verified_contexts(); old=contexts['VERIFIED_HISTORICAL']
    assert len(old['runtime49'])==49 and old['custody']['source_head']=='c05e0cabd6c6e4c2abb2002b7b69a8f1ba8aec57'
    assert old['math_pin']=='9ed369ddd41ae32c4b3a9434f0b29d6dcf51154f' and len(old['custody']['changed_baseline_archives'])==6

def test_current49_single_export_delta_and_mathQ_are_closed():
    verify_retired_execution_absence(Path(__file__).resolve().parents[2])
    verified_pre_cut_archives(Path(__file__).resolve().parents[2])
    contexts=verified_contexts();old=contexts['VERIFIED_HISTORICAL'];live=contexts['VERIFIED_LIVE']
    assert set(old['runtime49'])==set(live['runtime49']) and len(live['runtime49'])==49
    assert [name for name in old['runtime49'] if old['runtime49'][name]!=live['runtime49'][name]]==['market_data/history_export.py']
    assert live['math_pin']=='9e6acbd9e12a91189f57234828e31640983af553'

def test_runtime_anchor_is_prior_runtime_commit_not_self_reference():
    verify_retired_execution_absence(Path(__file__).resolve().parents[2])
    verified_pre_cut_archives(Path(__file__).resolve().parents[2])
    live=verified_contexts()['VERIFIED_LIVE']
    assert live['custody']['schema']=='market_data.turnover-runtime-custody.v2'
    assert live['runtime_anchor'] not in ('9d2920d9ee3730e5ddf579ae67e9753de9c39fe5','c05e0cabd6c6e4c2abb2002b7b69a8f1ba8aec57')

def test_original898_prefix_and_new_structural_suffix_are_exact():
    verify_retired_execution_absence(Path(__file__).resolve().parents[2])
    verified_pre_cut_archives(Path(__file__).resolve().parents[2])
    contexts=verified_contexts();old=contexts['VERIFIED_HISTORICAL']['roster'];live=contexts['VERIFIED_LIVE']['roster']
    assert len(old)==898 and len(live)==902 and live[:898]==old and len(set(live))==902
    assert live[898:]==["tests/market_data/test_runtime_math_lineage.py::test_legacy49_c05_and_math9ed_custody_is_preserved","tests/market_data/test_runtime_math_lineage.py::test_current49_single_export_delta_and_mathQ_are_closed","tests/market_data/test_runtime_math_lineage.py::test_runtime_anchor_is_prior_runtime_commit_not_self_reference","tests/market_data/test_runtime_math_lineage.py::test_original898_prefix_and_new_structural_suffix_are_exact"]
