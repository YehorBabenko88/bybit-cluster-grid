import hashlib
import json

import pytest

from grid.science_handoff_receiver import ScienceHandoffError, verify_science_handoff


def make_package(tmp_path):
    science = tmp_path / "science_bundle.json"
    science.write_text('{"symbols":[]}', encoding="utf-8")
    manifest = tmp_path / "grid-handoff.json"
    manifest.write_text(json.dumps({
        "schema": 1,
        "source": "strattester",
        "ready_for_grid_import": True,
        "science_bundle": {"path": science.name, "sha256": hashlib.sha256(science.read_bytes()).hexdigest()},
        "strategy_results": None,
        "phase_manifest": None,
    }), encoding="utf-8")
    return manifest, science


def test_accepts_portable_science_package(tmp_path):
    manifest, _ = make_package(tmp_path)
    assert verify_science_handoff(manifest)["source"] == "strattester"


def test_rejects_corrupted_science(tmp_path):
    manifest, science = make_package(tmp_path)
    science.write_text("changed", encoding="utf-8")
    with pytest.raises(ScienceHandoffError, match="checksum mismatch"):
        verify_science_handoff(manifest)


def test_rejects_path_traversal(tmp_path):
    manifest, _ = make_package(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["science_bundle"]["path"] = "../outside.json"
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ScienceHandoffError, match="escapes"):
        verify_science_handoff(manifest)


def test_rejects_legacy_research_handoff(tmp_path):
    manifest = tmp_path / "grid-handoff.json"
    manifest.write_text(json.dumps({"phase": "GRID_IMPORT_PENDING", "cache_repair_complete": True}), encoding="utf-8")
    with pytest.raises(ScienceHandoffError, match="unsupported"):
        verify_science_handoff(manifest)


def test_accepts_relocated_package_with_optional_strategy_database(tmp_path):
    import shutil

    original = tmp_path / "original"
    original.mkdir()
    science = original / "science_bundle.json"
    science.write_text('{"symbols":["BTCUSDT"]}', encoding="utf-8")
    strategy = original / "strategy_results.sqlite3"
    strategy.write_bytes(b"portable-test-strategy-results")
    manifest = original / "grid-handoff.json"
    manifest.write_text(json.dumps({
        "schema": 1,
        "source": "strattester",
        "ready_for_grid_import": True,
        "science_bundle": {
            "path": science.name,
            "sha256": hashlib.sha256(science.read_bytes()).hexdigest(),
        },
        "strategy_results": {
            "path": strategy.name,
            "sha256": hashlib.sha256(strategy.read_bytes()).hexdigest(),
        },
        "phase_manifest": None,
    }), encoding="utf-8")
    moved = tmp_path / "relocated"
    shutil.move(str(original), str(moved))
    accepted = verify_science_handoff(moved / "grid-handoff.json")
    assert accepted["strategy_results"]["path"] == strategy.name
    (moved / strategy.name).write_bytes(b"tampered")
    with pytest.raises(ScienceHandoffError, match="strategy_results checksum mismatch"):
        verify_science_handoff(moved / "grid-handoff.json")
