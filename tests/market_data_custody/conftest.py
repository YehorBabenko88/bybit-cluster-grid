"""Session fixture: verify the Grid re-anchor once and build the closed verification root."""
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location('_grid_custody_reanchor', Path(__file__).with_name('custody_reanchor.py'))
reanchor = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(reanchor)


@pytest.fixture(scope='session')
def reanchored(tmp_path_factory):
    verified = reanchor.verify(ROOT)
    vroot = reanchor.materialize(verified, tmp_path_factory.mktemp('strattester3850995_grid_root') / 'root')
    return {'verified': verified, 'vroot': vroot, 'root': ROOT, 'api': reanchor}
