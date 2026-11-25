"""Grid re-anchored counterpart of tests/market_data/test_journal_retirement.py (Workstream B2, unified-system#152).

Each node executes the UNCHANGED original test function (byte-identical in Grid and in
strattester@3850995) against the closed verification root built by the session fixture
``reanchored`` (366 paths, each proven against strattester@3850995 and, for 207 live paths,
against Grid anchor bf29f81b), and then asserts the Grid-live counterpart of the requirement.
The original node stays in the 902 roster unchanged.
"""
import json

ORIGINAL = 'tests/market_data/test_journal_retirement.py'
ORDINARY_MODULES = ('strattester.research.execution', 'research.execution', 'strattester.research.scalp_entries', 'research.scalp_entries', 'strattester.strategies.builtin.research_scalp', 'strategies.builtin.research_scalp')
ORDINARY_SYMBOLS = {'Signal', 'ExecutionPolicy', 'ResearchTrade', 'simulate_trade', 'scalp_hypotheses', 'sweep_reclaim_entries', 'breakout_retest_volume_entries', 'volatility_expansion_entries', 'poc_reclaim_entries'}


def _original_in_grid_roster(api, root, node):
    roster = api.grid_roster(root)
    assert ORIGINAL + '::' + node in roster
    return roster


def test_journal_metadata_role_has_exact_canonical_owner__grid(reanchored):
    api, root = reanchored['api'], reanchored['root']
    api.run_original(reanchored['vroot'], ORIGINAL, 'test_journal_metadata_role_has_exact_canonical_owner')
    _original_in_grid_roster(api, root, 'test_journal_metadata_role_has_exact_canonical_owner')
    api.assert_grid_not_restored(root, ('strattester.research.journal', 'research.journal') + ORDINARY_MODULES, {'TradeJournal'} | ORDINARY_SYMBOLS)
    ledger = json.loads((root / 'docs/migration/journal-retirement/transfer-ledger.json').read_bytes())
    assert ledger['role']['owner'] == 'Terminan' and ledger['role']['canonical_api'] == 'terminan.research_reporting.build_research_report'
