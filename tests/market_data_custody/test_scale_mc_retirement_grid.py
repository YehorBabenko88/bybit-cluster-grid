"""Grid re-anchored counterpart of tests/market_data/test_scale_mc_retirement.py (Workstream B2, unified-system#152).

Each node executes the UNCHANGED original test function (byte-identical in Grid and in
strattester@3850995) against the closed verification root built by the session fixture
``reanchored`` (366 paths, each proven against strattester@3850995 and, for 207 live paths,
against Grid anchor bf29f81b), and then asserts the Grid-live counterpart of the requirement.
The original node stays in the 902 roster unchanged.
"""
import json

ORIGINAL = 'tests/market_data/test_scale_mc_retirement.py'
ORDINARY_MODULES = ('strattester.research.execution', 'research.execution', 'strattester.research.scalp_entries', 'research.scalp_entries', 'strattester.strategies.builtin.research_scalp', 'strategies.builtin.research_scalp')
ORDINARY_SYMBOLS = {'Signal', 'ExecutionPolicy', 'ResearchTrade', 'simulate_trade', 'scalp_hypotheses', 'sweep_reclaim_entries', 'breakout_retest_volume_entries', 'volatility_expansion_entries', 'poc_reclaim_entries'}


def _original_in_grid_roster(api, root, node):
    roster = api.grid_roster(root)
    assert ORIGINAL + '::' + node in roster
    return roster
SCALE_MODULES = ('strattester.research.execution', 'research.execution', 'strattester.research.resampling', 'research.resampling')
SCALE_SYMBOLS = {'ScaleSignal', 'ExecutionFill', 'ExecutionExit', 'ScaleTrade', 'simulate_scale_trade', '_max_drawdown', 'monte_carlo_max_drawdowns'}
OWNERS = [('Terminan', 'terminan.paper.PaperEngine.execute_scale_plan')] * 3 + [('Math', 'history_statistics.permutation_drawdowns')]


def _grid(api, root, node, role):
    _original_in_grid_roster(api, root, node)
    api.assert_grid_not_restored(root, SCALE_MODULES + ORDINARY_MODULES, SCALE_SYMBOLS | ORDINARY_SYMBOLS)
    assert not (root / 'tests/research').exists()
    ledger = json.loads((root / 'docs/migration/scale-mc-retirement/transfer-ledger.json').read_bytes())
    assert (ledger['roles'][role]['owner'], ledger['roles'][role]['canonical_api']) == OWNERS[role]


def test_scale_independent_legs_and_partial_targets_are_retired_to_sole_owner__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_scale_independent_legs_and_partial_targets_are_retired_to_sole_owner')
    _grid(api, root, 'test_scale_independent_legs_and_partial_targets_are_retired_to_sole_owner', 0)


def test_scale_no_shared_state_role_is_retired_to_sole_owner__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_scale_no_shared_state_role_is_retired_to_sole_owner')
    _grid(api, root, 'test_scale_no_shared_state_role_is_retired_to_sole_owner', 1)


def test_scale_move_stop_role_is_retired_to_sole_owner__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_scale_move_stop_role_is_retired_to_sole_owner')
    _grid(api, root, 'test_scale_move_stop_role_is_retired_to_sole_owner', 2)


def test_seeded_monte_carlo_role_is_retired_without_changing_other_resampling__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_seeded_monte_carlo_role_is_retired_without_changing_other_resampling')
    _grid(api, root, 'test_seeded_monte_carlo_role_is_retired_without_changing_other_resampling', 3)
