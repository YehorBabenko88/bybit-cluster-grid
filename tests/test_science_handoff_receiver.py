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
