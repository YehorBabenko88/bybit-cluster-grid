"""Negative controls: the re-anchor and the re-executed originals must refuse tampering."""
import json
import shutil

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('_grid_custody_reanchor_negative', Path(__file__).with_name('custody_reanchor.py'))
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)


def _minimal_root(tmp_path):
    """Closed copy of exactly what ``verify`` reads from a Grid checkout."""
    target = tmp_path / 'grid'
    ledger = json.loads((ROOT / api.LEDGER).read_bytes())
    names = [api.LEDGER] + [row['archive'] for row in ledger['objects'].values()]
    names += [p for p, row in ledger['files'].items() if row['origin'] == 'grid_live']
    names += ['market_data/' + p.name for p in (ROOT / 'market_data').iterdir() if p.suffix in ('.py', '.sql')]
    for name in set(names):
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target / name)
    api.verify(target)
    return target, ledger


def _refused(root, code):
    with pytest.raises(ValueError) as caught:
        api.verify(root)
    assert str(caught.value).startswith(code)


def test_positive_minimal_root_verifies(tmp_path):
    root, _ = _minimal_root(tmp_path)
    assert len(api.verify(root)['files']) == 366


def test_tampered_archived_strattester_blob_is_refused(tmp_path):
    root, ledger = _minimal_root(tmp_path)
    ident = next(p for p, row in ledger['files'].items() if row['origin'] == 'archived_strattester' and p.startswith('strattester/'))
    path = root / ledger['objects'][ledger['files'][ident]['blob']]['archive']
    raw = bytearray(path.read_bytes())
    raw[-1] = ord('0') if raw[-1] != ord('0') else ord('1')
    path.write_bytes(bytes(raw))
    _refused(root, 'REANCHOR_OBJECT_ID')


def test_changed_grid_live_byte_is_refused(tmp_path):
    root, _ = _minimal_root(tmp_path)
    path = root / 'docs/migration/journal-retirement/transfer-ledger.json'
    path.write_bytes(path.read_bytes() + b' ')
    _refused(root, 'REANCHOR_FILE_BYTES:docs/migration/journal-retirement/transfer-ledger.json')


def test_crlf_converted_grid_live_file_is_refused(tmp_path):
    root, _ = _minimal_root(tmp_path)
    path = root / 'docs/ci/retained-legacy-test-inventory.json'
    path.write_bytes(path.read_bytes().replace(b'\n', b'\r\n'))
    _refused(root, 'REANCHOR_FILE_BYTES:docs/ci/retained-legacy-test-inventory.json')


def test_extra_grid_runtime_module_is_refused(tmp_path):
    root, _ = _minimal_root(tmp_path)
    (root / 'market_data/extra_runtime.py').write_bytes(b'')
    _refused(root, 'REANCHOR_GRID_LIVE_RUNTIME49')


def test_restored_strattester_package_is_refused(tmp_path):
    root, _ = _minimal_root(tmp_path)
    (root / 'strattester').mkdir()
    (root / 'strattester/__init__.py').write_bytes(b'')
    _refused(root, 'REANCHOR_GRID_HAS_NO_STRATTESTER_PACKAGE')


def test_restored_retired_source_path_is_refused(tmp_path):
    root, _ = _minimal_root(tmp_path)
    (root / 'tests/research').mkdir(parents=True)
    (root / 'tests/research/test_execution_journal.py').write_bytes(b'')
    _refused(root, 'REANCHOR_GRID_LIVE_ABSENCE:tests/research/test_execution_journal.py')


def test_tampered_ledger_is_refused(tmp_path):
    root, _ = _minimal_root(tmp_path)
    path = root / api.LEDGER
    path.write_bytes(path.read_bytes().replace(b'NO_GO', b'GO__', 1))
    _refused(root, 'REANCHOR_LEDGER_HASH')


def test_restored_retired_import_in_grid_runtime_is_refused(tmp_path):
    root = tmp_path / 'grid'
    (root / 'grid').mkdir(parents=True)
    (root / 'grid/restored.py').write_text('from strattester.research.journal import TradeJournal\n')
    with pytest.raises(ValueError):
        api.assert_grid_not_restored(root, ('strattester.research.journal',), {'TradeJournal'})
    (root / 'grid/restored.py').write_text("name = 'strattester.research.' + 'execution'\n")
    with pytest.raises(ValueError):
        api.assert_grid_not_restored(root, ('strattester.research.execution',), set())


def test_reexecuted_original_detects_missing_strattester_survivor(reanchored, tmp_path):
    vroot = tmp_path / 'vroot'
    shutil.copytree(reanchored['vroot'], vroot)
    (vroot / 'strattester/research/levels.py').unlink()
    with pytest.raises(ValueError, match='RETIREMENT_SURVIVOR_PATHSET'):
        api.run_original(vroot, 'tests/market_data/test_runtime_math_lineage.py', 'test_original898_prefix_and_new_structural_suffix_are_exact')


def test_reexecuted_original_detects_changed_preserved_doc(reanchored, tmp_path):
    vroot = tmp_path / 'vroot'
    shutil.copytree(reanchored['vroot'], vroot)
    path = vroot / 'docs/archive-transfer-map.md'
    path.write_bytes(path.read_bytes() + b'\n')
    with pytest.raises(ValueError, match='LINEAGE_PRESERVED_BYTES:docs/archive-transfer-map.md'):
        api.run_original(vroot, 'tests/market_data/test_entry_context_retirement.py', 'test_original_547_inventory_bytes_and_all_788_baseline_roles_preserved')
