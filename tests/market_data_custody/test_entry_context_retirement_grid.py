"""Grid re-anchored counterpart of tests/market_data/test_entry_context_retirement.py (Workstream B2, unified-system#152).

Each node executes the UNCHANGED original test function (byte-identical in Grid and in
strattester@3850995) against the closed verification root built by the session fixture
``reanchored`` (366 paths, each proven against strattester@3850995 and, for 207 live paths,
against Grid anchor bf29f81b), and then asserts the Grid-live counterpart of the requirement.
The original node stays in the 902 roster unchanged.
"""
import json

ORIGINAL = 'tests/market_data/test_entry_context_retirement.py'
ORDINARY_MODULES = ('strattester.research.execution', 'research.execution', 'strattester.research.scalp_entries', 'research.scalp_entries', 'strattester.strategies.builtin.research_scalp', 'strategies.builtin.research_scalp')
ORDINARY_SYMBOLS = {'Signal', 'ExecutionPolicy', 'ResearchTrade', 'simulate_trade', 'scalp_hypotheses', 'sweep_reclaim_entries', 'breakout_retest_volume_entries', 'volatility_expansion_entries', 'poc_reclaim_entries'}


def _original_in_grid_roster(api, root, node):
    roster = api.grid_roster(root)
    assert ORIGINAL + '::' + node in roster
    return roster


def test_original_547_inventory_bytes_and_all_788_baseline_roles_preserved__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_original_547_inventory_bytes_and_all_788_baseline_roles_preserved')
    roster = _original_in_grid_roster(api, root, 'test_original_547_inventory_bytes_and_all_788_baseline_roles_preserved')
    baseline = json.loads((root / 'docs/migration/entry-context-retirement/canonical-788-roster.json').read_bytes())
    inventory = json.loads((root / 'docs/ci/retained-legacy-test-inventory.json').read_bytes())
    assert len(baseline) == 788 and roster[:788] == baseline
    assert sum(len(row['tests']) for row in inventory) == 547
    assert not any('test_trade_context.py' in node for node in roster)


def test_only_unowned_context_source_removed_no_runtime_dependency_or_alias__grid(reanchored):
    import ast
    import tomllib
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_only_unowned_context_source_removed_no_runtime_dependency_or_alias')
    _original_in_grid_roster(api, root, 'test_only_unowned_context_source_removed_no_runtime_dependency_or_alias')
    api.assert_grid_not_restored(root, ('strattester.research.trade_context', 'research.trade_context'), {'attach_entry_context'})
    for path in api.grid_runtime_python(root):
        raw = path.read_text(encoding='utf8')
        assert 'trade_context' not in raw and 'attach_entry_context' not in raw
    project = tomllib.loads((root / 'pyproject.toml').read_text(encoding='utf8'))
    assert project['tool']['setuptools']['packages'] == ['market_data']
    assert all('terminan' not in x.lower() for x in project['project']['dependencies'])
    for path in (root / 'market_data').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_bytes())):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or '').startswith('terminan')
            if isinstance(node, ast.Import):
                assert all(not n.name.startswith('terminan') for n in node.names)
