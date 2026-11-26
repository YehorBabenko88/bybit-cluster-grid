"""Fail-closed manifest check; does NOT execute tests or replace strict gates."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROSTER = ROOT / "scripts" / "canonical_test_roster.json"
PARTITION = ROOT / "scripts" / "cross_repo_roster_partition.json"
ROSTER_SHA = "d235fb38d3f0d207200af95ada41d1ad58605f663dca317e38aa442d719b6fbe"
SOURCE_SHA = "3850995a6c28ed29b05cef4ba067e587d5033453"
EXPECTED_CUSTODY_IDS = (
    "tests/market_data/test_entry_context_retirement.py::test_original_547_inventory_bytes_and_all_788_baseline_roles_preserved",
    "tests/market_data/test_entry_context_retirement.py::test_only_unowned_context_source_removed_no_runtime_dependency_or_alias",
    "tests/market_data/test_scale_mc_retirement.py::test_scale_independent_legs_and_partial_targets_are_retired_to_sole_owner",
    "tests/market_data/test_scale_mc_retirement.py::test_scale_no_shared_state_role_is_retired_to_sole_owner",
    "tests/market_data/test_scale_mc_retirement.py::test_scale_move_stop_role_is_retired_to_sole_owner",
    "tests/market_data/test_scale_mc_retirement.py::test_seeded_monte_carlo_role_is_retired_without_changing_other_resampling",
    "tests/market_data/test_reporting_retirement.py::test_reporting_volatility_role_removes_only_duplicate_source_and_preserves_custody",
    "tests/market_data/test_pattern_statistics_bootstrap_retirement.py::test_pattern_chronological_role_is_owned_by_independent_signal_accounts",
    "tests/market_data/test_pattern_statistics_bootstrap_retirement.py::test_empty_pattern_role_preserves_no_evidence_refusal",
    "tests/market_data/test_pattern_statistics_bootstrap_retirement.py::test_statistics_role_is_owned_by_declared_trade_summary",
    "tests/market_data/test_pattern_statistics_bootstrap_retirement.py::test_bootstrap_role_is_owned_by_iid_mean_bootstrap",
    "tests/market_data/test_screening_retirement.py::test_majority_loss_screening_role_has_exact_canonical_owner",
    "tests/market_data/test_screening_retirement.py::test_stable_screening_role_retires_whole_module_and_preserves_catalog",
    "tests/market_data/test_journal_retirement.py::test_journal_metadata_role_has_exact_canonical_owner",
    "tests/market_data/test_runtime_math_lineage.py::test_legacy49_c05_and_math9ed_custody_is_preserved",
    "tests/market_data/test_runtime_math_lineage.py::test_current49_single_export_delta_and_mathQ_are_closed",
    "tests/market_data/test_runtime_math_lineage.py::test_runtime_anchor_is_prior_runtime_commit_not_self_reference",
    "tests/market_data/test_runtime_math_lineage.py::test_original898_prefix_and_new_structural_suffix_are_exact",
)

def validate(roster=None, partition=None):
    if roster is None:
        roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    if partition is None:
        partition = json.loads(PARTITION.read_text(encoding="utf-8"))
    if type(roster) is not list or len(roster) != 902 or any(type(n) is not str for n in roster):
        raise ValueError("ROSTER_SHAPE")
    encoded = json.dumps(roster, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    if hashlib.sha256(encoded).hexdigest() != ROSTER_SHA or len(set(roster)) != 902:
        raise ValueError("ROSTER_SEAL")
    if type(partition) is not dict or set(partition) != {"schema","roster_sha256","source","grid_nodes","total_nodes","status"}:
        raise ValueError("PARTITION_KEYS")
    if partition["schema"] != "grid.market_data.cross_repository_roster_partition.v1" or partition["roster_sha256"] != ROSTER_SHA or partition["status"] != "PROPOSED_NOT_ACCEPTED":
        raise ValueError("PARTITION_IDENTITY")
    src = partition["source"]
    if type(src) is not dict or set(src) != {"repository","commit","custody_nodes"} or src["repository"] != "YehorBabenko88/strattester" or src["commit"] != SOURCE_SHA:
        raise ValueError("SOURCE_IDENTITY")
    custody = src["custody_nodes"]
    if type(custody) is not list or len(custody) != 18 or any(type(n) is not str for n in custody) or len(set(custody)) != 18:
        raise ValueError("CUSTODY_SHAPE")
    if tuple(custody) != EXPECTED_CUSTODY_IDS:
        raise ValueError("CUSTODY_IDENTITY")
    if any(n not in roster for n in custody):
        raise ValueError("CUSTODY_NOT_IN_ROSTER")
    grid = [n for n in roster if n not in set(custody)]
    if len(grid) != partition["grid_nodes"] or partition["grid_nodes"] != 884 or partition["total_nodes"] != 902:
        raise ValueError("GRID_COUNT")
    return {"grid_nodes":grid,"custody_nodes":custody,"total":902,"source_sha":SOURCE_SHA}

def negative_probes():
    import copy
    roster = json.loads(ROSTER.read_text(encoding="utf-8"))
    partition = json.loads(PARTITION.read_text(encoding="utf-8"))
    check = lambda r,p: validate(r,p)
    check(roster,partition)
    cases = {}
    def refused(name,r,p):
        try:
            check(r,p)
        except ValueError:
            cases[name] = "REFUSED"
        else:
            raise AssertionError("unsafe partition accepted: " + name)
    r=roster.copy();r.pop();refused("dropped_roster_node",r,partition)
    r=roster.copy();r[-1]=r[0];refused("duplicated_roster_node",r,partition)
    r=roster.copy();r[0]+="_changed";refused("mutated_roster_node",r,partition)
    p=copy.deepcopy(partition);p["source"]["commit"]="0"*40;refused("wrong_source_sha",roster,p)
    p=copy.deepcopy(partition);p["source"]["custody_nodes"].pop();refused("dropped_custody_node",roster,p)
    p=copy.deepcopy(partition);p["source"]["custody_nodes"][-1]=p["source"]["custody_nodes"][0];refused("duplicated_custody_node",roster,p)
    p=copy.deepcopy(partition);p["source"]["custody_nodes"][0]="tests/unknown.py::test_fake";refused("invented_custody_node",roster,p)
    p=copy.deepcopy(partition);p["source"]["custody_nodes"][0]=roster[0];refused("substituted_valid_node",roster,p)
    p=copy.deepcopy(partition);p["grid_nodes"]=883;refused("wrong_grid_count",roster,p)
    return cases

if __name__ == "__main__":
    proof = validate()
    print(json.dumps({"roster":proof["total"],"grid":len(proof["grid_nodes"]),"custody":len(proof["custody_nodes"]),"source_sha":proof["source_sha"],"negative_probes":negative_probes()},sort_keys=True))
