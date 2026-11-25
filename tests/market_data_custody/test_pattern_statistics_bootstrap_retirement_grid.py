"""Grid re-anchored counterpart of tests/market_data/test_pattern_statistics_bootstrap_retirement.py (Workstream B2, unified-system#152).

Each node executes the UNCHANGED original test function (byte-identical in Grid and in
strattester@3850995) against the closed verification root built by the session fixture
``reanchored`` (366 paths, each proven against strattester@3850995 and, for 207 live paths,
against Grid anchor bf29f81b), and then asserts the Grid-live counterpart of the requirement.
The original node stays in the 902 roster unchanged.
"""
import json

ORIGINAL = 'tests/market_data/test_pattern_statistics_bootstrap_retirement.py'
ORDINARY_MODULES = ('strattester.research.execution', 'research.execution', 'strattester.research.scalp_entries', 'research.scalp_entries', 'strattester.strategies.builtin.research_scalp', 'strategies.builtin.research_scalp')
ORDINARY_SYMBOLS = {'Signal', 'ExecutionPolicy', 'ResearchTrade', 'simulate_trade', 'scalp_hypotheses', 'sweep_reclaim_entries', 'breakout_retest_volume_entries', 'volatility_expansion_entries', 'poc_reclaim_entries'}


def _original_in_grid_roster(api, root, node):
    roster = api.grid_roster(root)
    assert ORIGINAL + '::' + node in roster
    return roster
PATTERN_MODULES = ('strattester.research.pattern_evaluation', 'strattester.research.statistics', 'strattester.research.resampling', 'research.pattern_evaluation', 'research.statistics', 'research.resampling')
PATTERN_SYMBOLS = {'evaluate_entry_signals', 'PatternEvaluation', 'TradeMetrics', 'evaluate_trades', 'BootstrapCI', 'bootstrap_expectancy'}
OWNERS = [('Terminan', 'terminan.research_evaluation.evaluate_research_signals'), ('Terminan', 'terminan.research_evaluation.evaluate_research_signals'), ('Math', 'history_statistics.numeric_trade_summary'), ('Math', 'history_statistics.iid_observation_mean_bootstrap')]


def _grid(api, root, node, role):
    _original_in_grid_roster(api, root, node)
    findings = api.assert_grid_not_restored(root, PATTERN_MODULES, PATTERN_SYMBOLS)
    assert {kind for _, kind in findings} <= {'symbol:evaluate_trades'}
    ledger = json.loads((root / 'docs/migration/pattern-statistics-bootstrap-retirement/transfer-ledger.json').read_bytes())
    assert (ledger['roles'][role]['owner'], ledger['roles'][role]['canonical_api']) == OWNERS[role]


def test_pattern_chronological_role_is_owned_by_independent_signal_accounts__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_pattern_chronological_role_is_owned_by_independent_signal_accounts')
    _grid(api, root, 'test_pattern_chronological_role_is_owned_by_independent_signal_accounts', 0)


def test_empty_pattern_role_preserves_no_evidence_refusal__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_empty_pattern_role_preserves_no_evidence_refusal')
    _grid(api, root, 'test_empty_pattern_role_preserves_no_evidence_refusal', 1)


def test_statistics_role_is_owned_by_declared_trade_summary__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_statistics_role_is_owned_by_declared_trade_summary')
    _grid(api, root, 'test_statistics_role_is_owned_by_declared_trade_summary', 2)


def test_bootstrap_role_is_owned_by_iid_mean_bootstrap__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_bootstrap_role_is_owned_by_iid_mean_bootstrap')
    _grid(api, root, 'test_bootstrap_role_is_owned_by_iid_mean_bootstrap', 3)
