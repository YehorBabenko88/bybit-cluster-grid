import hashlib
import json

import pytest

from grid.science_handoff_receiver import ScienceHandoffError, verify_science_handoff, science_handoff_identity


def science_bytes(symbols=None):
    payload = {
        "schema": 1,
        "source": "strattester",
        "research_scope": "HISTORICAL_BOOTSTRAP_ONLY",
        "capabilities": {"candles": True, "true_l2_orderbook": False},
        "symbols": [] if symbols is None else symbols,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    payload["sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return json.dumps(payload, sort_keys=True).encode("utf-8")


def make_package(tmp_path):
    science = tmp_path / "science_bundle.json"
    science.write_bytes(science_bytes())
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
    science.write_bytes(science_bytes([{"symbol": "BTCUSDT", "status": "READY"}]))
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


def test_rejects_missing_optional_strategy_results(tmp_path):
    manifest, _ = make_package(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["strategy_results"] = {"path": "missing.sqlite3", "sha256": "0" * 64}
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ScienceHandoffError, match="missing or empty strategy_results"):
        verify_science_handoff(manifest)


def test_rejects_optional_strategy_results_path_escape(tmp_path):
    manifest, _ = make_package(tmp_path)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["strategy_results"] = {"path": "../external.sqlite3", "sha256": "0" * 64}
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ScienceHandoffError, match="strategy_results escapes"):
        verify_science_handoff(manifest)


def test_rejects_science_symlink_to_outside_package(tmp_path):
    package = tmp_path / "package"
    package.mkdir()
    manifest, science = make_package(package)
    outside = tmp_path / "external.json"
    outside.write_bytes(science.read_bytes())
    science.unlink()
    try:
        science.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks unavailable on this runner")
    with pytest.raises(ScienceHandoffError, match="science_bundle escapes"):
        verify_science_handoff(manifest)


def test_rejects_valid_outer_hash_but_invalid_science_schema(tmp_path):
    manifest, science = make_package(tmp_path)
    invalid = {"schema": 999, "source": "strattester", "symbols": []}
    science.write_text(json.dumps(invalid), encoding="utf-8")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["science_bundle"]["sha256"] = hashlib.sha256(science.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ScienceHandoffError, match="unsupported science bundle schema"):
        verify_science_handoff(manifest)


def test_rejects_valid_outer_hash_but_corrupted_internal_science_checksum(tmp_path):
    manifest, science = make_package(tmp_path)
    data = json.loads(science.read_text(encoding="utf-8"))
    data["symbols"].append({"symbol": "ETHUSDT", "status": "READY"})
    science.write_text(json.dumps(data), encoding="utf-8")
    outer = json.loads(manifest.read_text(encoding="utf-8"))
    outer["science_bundle"]["sha256"] = hashlib.sha256(science.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(outer), encoding="utf-8")
    with pytest.raises(ScienceHandoffError, match="internal checksum mismatch"):
        verify_science_handoff(manifest)


def test_science_identity_ignores_package_location_and_creation_metadata(tmp_path):
    import shutil
    first = tmp_path / "first"
    first.mkdir()
    manifest, _ = make_package(first)
    initial = science_handoff_identity(manifest)
    second = tmp_path / "second"
    shutil.copytree(first, second)
    moved = second / "grid-handoff.json"
    data = json.loads(moved.read_text(encoding="utf-8"))
    data["created_at"] = 9999999999
    moved.write_text(json.dumps(data), encoding="utf-8")
    assert science_handoff_identity(moved) == initial


def test_science_identity_changes_with_verified_science_content(tmp_path):
    manifest, science = make_package(tmp_path)
    initial = science_handoff_identity(manifest)
    science.write_bytes(science_bytes([{"symbol": "ETHUSDT", "status": "INSUFFICIENT"}]))
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["science_bundle"]["sha256"] = hashlib.sha256(science.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(data), encoding="utf-8")
    assert science_handoff_identity(manifest) != initial
