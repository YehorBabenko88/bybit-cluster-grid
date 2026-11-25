"""Development-only builder of the Grid custody re-anchor archive (Workstream B2).

Never run in CI. Reproduces docs/provenance/market-data-custody-reanchor-20261125/
from two local Git repositories:

    python build_reanchor_archive.py <strattester-git> <grid-git> <paths.json> <grid-root>

* <paths.json> is the closed list of repository paths that the 18 original custody
  nodes read when they pass on strattester@3850995 (produced by trace_original_reads.py).
* Every path is resolved in strattester@3850995. A path whose exact Git blob is also
  present at the same path in the Grid anchor commit is recorded as ``grid_live``
  (the live Grid checkout must keep those bytes). Every other path is archived as a
  hex-encoded Git blob (``archived_strattester``) so that no checkout conversion can
  alter it.
* All Git commit/tree objects needed to resolve those paths, the absence proofs and
  the enumerated directories are archived as hex so a verifier can recompute every
  object id without Git.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

STRATTESTER = '3850995a6c28ed29b05cef4ba067e587d5033453'
GRID_ANCHOR = 'bf29f81b238c6236417f0ed9a13feea3dcbb5bec'
GRID_ANCHOR_PARENT = 'bf9cbe8949dd1a2979aa7d63a55e2df9e139d625'
GRID_BASELINE = 'c9ffdaa2af52c4d55871a48655a77a0c669da80f'
OUT = 'docs/provenance/market-data-custody-reanchor-20261125'
ABSENT = sorted([
    'strattester/research/trade_context.py', 'tests/research/test_trade_context.py',
    'strattester/research/journal.py',
    'strattester/research/pattern_evaluation.py', 'strattester/research/statistics.py',
    'strattester/research/resampling.py', 'tests/research/test_pattern_evaluation.py',
    'tests/research/test_statistics_reporting.py', 'strattester/research/reporting.py',
    'tests/research/test_scale_execution.py', 'strattester/research/entry_screening.py',
    'strattester/research/execution.py', 'strattester/research/scalp_entries.py',
    'strattester/strategies/builtin/research_scalp.py', 'tests/research/test_execution_journal.py',
    'tests/research/test_same_bar_execution.py', 'tests/research/test_scalp_entries.py',
    'tests/research/test_entry_screening.py',
])
ENUMERATED = {'market_data': ['.py', '.sql'], 'strattester': ['.py']}
SHARED_SUBTREES = ['docs/ci', 'docs/migration', 'docs/provenance', 'market_data', 'tests/market_data']
COLLISIONS = {
    '.gitattributes': 'strattester@3850995 checkout policy; Grid keeps its own .gitattributes '
                      '(Windows installer byte policy). The strattester bytes are used only '
                      'inside the reconstructed verification root.',
}


def git(repo, *args):
    return subprocess.check_output(['git', '--no-replace-objects', '-C', str(repo), *args])


def oid(kind, raw):
    return hashlib.sha1(kind.encode() + b' ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def entries(raw):
    out = {}
    i = 0
    while i < len(raw):
        sp = raw.index(b' ', i)
        nul = raw.index(b'\0', sp)
        out[raw[sp + 1:nul].decode()] = (raw[i:sp].decode(), raw[nul + 1:nul + 21].hex())
        i = nul + 21
    return out


class Store:
    def __init__(self, repo):
        self.repo = repo
        self.objects = {}

    def get(self, kind, ident):
        raw = git(self.repo, 'cat-file', kind, ident)
        assert oid(kind, raw) == ident
        self.objects[ident] = (kind, raw)
        return raw

    def root(self, commit):
        raw = self.get('commit', commit)
        return raw.split(b'\n', 1)[0].decode().split(' ')[1]

    def resolve(self, tree, path):
        parts = path.split('/')
        for depth, part in enumerate(parts):
            table = entries(self.get('tree', tree))
            if part not in table:
                return None
            mode, ident = table[part]
            if depth == len(parts) - 1:
                return mode, ident
            if mode != '40000':
                return None
            tree = ident

    def walk(self, tree, prefix):
        out = {}
        for name, (mode, ident) in entries(self.get('tree', tree)).items():
            if mode == '40000':
                out.update(self.walk(ident, prefix + name + '/'))
            else:
                out[prefix + name] = (mode, ident)
        return out


def main(strattester, grid, paths_file, grid_root):
    grid_root = Path(grid_root)
    out = grid_root / OUT
    paths = json.loads(Path(paths_file).read_text())
    s = Store(strattester)
    g = Store(grid)
    s_root = s.root(STRATTESTER)
    g_root = g.root(GRID_ANCHOR)
    assert git(grid, 'rev-parse', GRID_ANCHOR + '^').decode().strip() == GRID_ANCHOR_PARENT
    assert git(grid, 'rev-parse', GRID_ANCHOR_PARENT + '^').decode().strip() == GRID_BASELINE
    g.get('commit', GRID_ANCHOR_PARENT)
    shared = {}
    for path in SHARED_SUBTREES:
        a = s.resolve(s_root, path)
        b = g.resolve(g_root, path)
        assert a == b and a[0] == '40000', path
        shared[path] = a[1]
    files = {}
    blobs = {}
    for path in paths:
        mode, ident = s.resolve(s_root, path)
        raw = s.get('blob', ident)
        row = {'mode': mode, 'blob': ident, 'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        in_grid = g.resolve(g_root, path)
        if in_grid is not None and in_grid[1] == ident and path not in COLLISIONS:
            row['origin'] = 'grid_live'
        else:
            row['origin'] = 'archived_strattester'
            blobs[ident] = raw
        files[path] = row
    for path in ABSENT:
        assert s.resolve(s_root, path) is None, path
        assert g.resolve(g_root, path) is None, path
    for directory, suffixes in ENUMERATED.items():
        listed = {p for p in s.walk(s.resolve(s_root, directory)[1], directory + '/') if p.endswith(tuple(suffixes))}
        assert listed == {p for p in files if p.startswith(directory + '/') and p.endswith(tuple(suffixes))}, directory
    collisions = {}
    for path, reason in COLLISIONS.items():
        mode, ident = g.resolve(g_root, path)
        raw = g.get('blob', ident)
        collisions[path] = {'grid_blob': ident, 'grid_sha256': hashlib.sha256(raw).hexdigest(), 'reason': reason}
    objects = {}
    for store in (s, g):
        for ident, (kind, raw) in store.objects.items():
            if kind == 'blob':
                continue
            objects[ident] = {'kind': kind, 'archive': f'{OUT}/objects/{ident}.{kind}.hex'}
            (out / 'objects').mkdir(parents=True, exist_ok=True)
            (out / 'objects' / f'{ident}.{kind}.hex').write_bytes(raw.hex().encode('ascii'))
    for ident, raw in blobs.items():
        objects[ident] = {'kind': 'blob', 'archive': f'{OUT}/objects/{ident}.blob.hex'}
        (out / 'objects' / f'{ident}.blob.hex').write_bytes(raw.hex().encode('ascii'))
    ledger = {
        'schema': 'grid.market-data-custody-reanchor.v1',
        'status': 'CANDIDATE_PENDING_OWNER_AND_GPT_ACCEPTANCE',
        'authority': False,
        'release': 'NO_GO',
        'strattester': {'repository': 'YehorBabenko88/strattester', 'commit': STRATTESTER,
                        'ci_runs_on_commit': ['https://github.com/YehorBabenko88/strattester/actions/runs/45411461397',
                                              'https://github.com/YehorBabenko88/strattester/actions/runs/45411461080']},
        'grid_anchor': {'repository': 'YehorBabenko88/bybit-cluster-grid', 'commit': GRID_ANCHOR,
                        'parent': GRID_ANCHOR_PARENT, 'baseline': GRID_BASELINE},
        'shared_subtrees': shared,
        'enumerated_directories': ENUMERATED,
        'absent_paths': ABSENT,
        'collisions': collisions,
        'files': files,
        'objects': dict(sorted(objects.items())),
    }
    # One line, no terminal newline: no checkout end-of-line policy can change these bytes.
    (out / 'ledger.json').write_bytes(json.dumps(ledger, separators=(',', ':'), ensure_ascii=True).encode('ascii'))
    print(hashlib.sha256((out / 'ledger.json').read_bytes()).hexdigest())


if __name__ == '__main__':
    main(*sys.argv[1:])
