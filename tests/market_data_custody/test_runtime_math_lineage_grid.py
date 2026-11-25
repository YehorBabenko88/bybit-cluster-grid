"""Grid re-anchored counterpart of tests/market_data/test_runtime_math_lineage.py (Workstream B2, unified-system#152).

Each node executes the UNCHANGED original test function (byte-identical in Grid and in
strattester@3850995) against the closed verification root built by the session fixture
``reanchored`` (366 paths, each proven against strattester@3850995 and, for 207 live paths,
against Grid anchor bf29f81b), and then asserts the Grid-live counterpart of the requirement.
The original node stays in the 902 roster unchanged.
"""
import json

ORIGINAL = 'tests/market_data/test_runtime_math_lineage.py'
ORDINARY_MODULES = ('strattester.research.execution', 'research.execution', 'strattester.research.scalp_entries', 'research.scalp_entries', 'strattester.strategies.builtin.research_scalp', 'strategies.builtin.research_scalp')
ORDINARY_SYMBOLS = {'Signal', 'ExecutionPolicy', 'ResearchTrade', 'simulate_trade', 'scalp_hypotheses', 'sweep_reclaim_entries', 'breakout_retest_volume_entries', 'volatility_expansion_entries', 'poc_reclaim_entries'}


def _original_in_grid_roster(api, root, node):
    roster = api.grid_roster(root)
    assert ORIGINAL + '::' + node in roster
    return roster
NEW_MATH = '9e6acbd9e12a91189f57234828e31640983af553'
SUFFIX = ['tests/market_data/test_runtime_math_lineage.py::test_legacy49_c05_and_math9ed_custody_is_preserved', 'tests/market_data/test_runtime_math_lineage.py::test_current49_single_export_delta_and_mathQ_are_closed', 'tests/market_data/test_runtime_math_lineage.py::test_runtime_anchor_is_prior_runtime_commit_not_self_reference', 'tests/market_data/test_runtime_math_lineage.py::test_original898_prefix_and_new_structural_suffix_are_exact']


def _absence(api, root):
    api.assert_grid_not_restored(root, ORDINARY_MODULES, ORDINARY_SYMBOLS)


def test_legacy49_c05_and_math9ed_custody_is_preserved__grid(reanchored):
    import hashlib
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_legacy49_c05_and_math9ed_custody_is_preserved')
    _original_in_grid_roster(api, root, 'test_legacy49_c05_and_math9ed_custody_is_preserved')
    _absence(api, root)
    assert hashlib.sha256((root / 'scripts/runtime_lineage_custody.py').read_bytes()).hexdigest() == '9cec6e527a0fc80d845452e1bdbdd50962625ecf7bbb5c1e931eeb0f47e63e72'
    assert hashlib.sha256((root / 'scripts/ordinary_execution_retirement_custody.py').read_bytes()).hexdigest() == '5bbf148b9517e744a86b02943df8be64ce606d24e592a6c30603a8ab6e2d5ca3'


def test_current49_single_export_delta_and_mathQ_are_closed__grid(reanchored):
    import ast
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_current49_single_export_delta_and_mathQ_are_closed')
    _original_in_grid_roster(api, root, 'test_current49_single_export_delta_and_mathQ_are_closed')
    _absence(api, root)
    transition = json.loads((root / 'docs/provenance/runtime-math-reanchor/transition.json').read_bytes())
    live = {}
    for path in (root / 'market_data').iterdir():
        if path.suffix in ('.py', '.sql'):
            import hashlib
            live['market_data/' + path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert live == {name: row['sha256'] for name, row in transition['new_runtime'].items()} and len(live) == 49
    for name, constant in (('scripts/build_sdk_source_manifest.py', 'SOURCES'), ('scripts/check_frozen_consumer.py', 'SOURCE_REVISIONS')):
        nodes = [n for n in ast.parse((root / name).read_bytes()).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == constant for t in n.targets)]
        assert len(nodes) == 1 and ast.literal_eval(nodes[0].value)['unified-math-kernels'] == NEW_MATH
    api.grid_workflow_counterpart(root, reanchored['verified'])
    assert NEW_MATH.encode() in (root / '.github/workflows/market-data-pure.yml').read_bytes()


def test_runtime_anchor_is_prior_runtime_commit_not_self_reference__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_runtime_anchor_is_prior_runtime_commit_not_self_reference')
    _original_in_grid_roster(api, root, 'test_runtime_anchor_is_prior_runtime_commit_not_self_reference')
    _absence(api, root)
    verified = reanchored['verified']
    objects = verified['objects']
    custody = json.loads((root / 'docs/provenance/turnover-history-foundation/CURRENT_RUNTIME.json').read_bytes())
    # The Grid anchor is a prior Grid commit (an archived object cannot be its own commit),
    # whose market_data tree is exactly the runtime tree of the strattester custody anchor.
    assert objects.commit(api.GRID_ANCHOR)[1] == [api.GRID_ANCHOR_PARENT]
    assert objects.commit(api.GRID_ANCHOR_PARENT)[1] == [api.GRID_BASELINE]
    assert objects.resolve(verified['grid_tree'], 'market_data') == ('40000', custody['anchor_market_data_tree'])
    assert api.GRID_ANCHOR not in (custody['source_head'], api.STRATTESTER, api.GRID_BASELINE)


def test_original898_prefix_and_new_structural_suffix_are_exact__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_original898_prefix_and_new_structural_suffix_are_exact')
    roster = _original_in_grid_roster(api, root, 'test_original898_prefix_and_new_structural_suffix_are_exact')
    _absence(api, root)
    before = json.loads((root / 'docs/provenance/runtime-math-reanchor/raw/scripts__canonical_test_roster.json.txt').read_bytes())
    assert len(before) == 898 and roster[:898] == before and roster[898:] == SUFFIX
