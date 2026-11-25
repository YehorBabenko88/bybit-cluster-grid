"""Development-only Grid re-anchor of the 18 strattester-custody roster nodes (Workstream B2).

Never imports market_data, Terminan, Math or Git. Every input is checked by recomputing
Git object ids from archived raw objects:

* strattester@3850995 commit -> root tree -> ... -> blob, for every path the 18 original
  nodes read (366 paths), for 18 absence proofs and for two enumerated directories;
* Grid anchor commit bf29f81b (parent bf9cbe89, grandparent = Grid baseline c9ffdaa2)
  -> root tree -> the same subtree ids for market_data, docs/ci, docs/migration,
  docs/provenance and tests/market_data, and the same blob ids for every ``grid_live`` path;
* the live Grid checkout bytes of every ``grid_live`` path (207 paths) must equal those blobs.

``materialize`` then writes a closed verification root that contains exactly the 366
ledger paths: 207 from the live Grid checkout and 159 decoded from archived strattester
blobs. The unchanged original test functions are executed against that root.
"""
import ast
import hashlib
import json
from pathlib import Path

LEDGER = 'docs/provenance/market-data-custody-reanchor-20261125/ledger.json'
LEDGER_SHA256 = '96be37b294cbd0c7a7ac7dcdfffbeb3058c2e59ff8a70903acaac4ea3e42c2bd'
STRATTESTER = '3850995a6c28ed29b05cef4ba067e587d5033453'
GRID_ANCHOR = 'bf29f81b238c6236417f0ed9a13feea3dcbb5bec'
GRID_ANCHOR_PARENT = 'bf9cbe8949dd1a2979aa7d63a55e2df9e139d625'
GRID_BASELINE = 'c9ffdaa2af52c4d55871a48655a77a0c669da80f'
SHARED = ('docs/ci', 'docs/migration', 'docs/provenance', 'market_data', 'tests/market_data')
GRID_RUNTIME_ROOTS = ('grid', 'market_data', 'lab', 'strategies', 'installer', 'run_worker.py', 'run_coordinator.py')


def need(condition, code):
    if condition is not True:
        raise ValueError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def object_id(kind, raw):
    return hashlib.sha1(kind.encode('ascii') + b' ' + str(len(raw)).encode('ascii') + b'\0' + raw).hexdigest()


def _pairs(items):
    out = {}
    for key, value in items:
        need(type(key) is str and key not in out, 'REANCHOR_DUPLICATE_KEY')
        out[key] = value
    return out


def read(root, name):
    need(type(name) is str and bool(name) and '\\' not in name, 'REANCHOR_PATH')
    path = Path(name)
    need(not path.is_absolute() and '..' not in path.parts and '.' not in path.parts, 'REANCHOR_PATH')
    target = root / path
    for part in (target, *target.parents):
        if part == root.parent:
            break
        need(not part.is_symlink(), 'REANCHOR_SYMLINK')
    need(target.is_file(), 'REANCHOR_FILE_REQUIRED:' + name)
    return target.read_bytes()


def tree_entries(raw):
    out = {}
    i = 0
    while i < len(raw):
        sp = raw.index(b' ', i)
        nul = raw.index(b'\0', sp)
        name = raw[sp + 1:nul].decode('utf8')
        need(name not in out and '/' not in name and name not in ('', '.', '..'), 'REANCHOR_TREE_NAME')
        ident = raw[nul + 1:nul + 21]
        need(len(ident) == 20, 'REANCHOR_TREE_TRUNCATED')
        out[name] = (raw[i:sp].decode('ascii'), ident.hex())
        i = nul + 21
    return out


class Objects:
    """Content-addressed archive; every object is re-hashed before use."""

    def __init__(self, root, table):
        self.root = root
        self.table = table
        self.cache = {}

    def get(self, kind, ident):
        if ident not in self.cache:
            row = self.table.get(ident)
            need(type(row) is dict and set(row) == {'kind', 'archive'} and row['kind'] == kind, 'REANCHOR_OBJECT_MISSING:' + kind + ':' + ident)
            text = read(self.root, row['archive'])
            need(text == text.strip() and all(c in b'0123456789abcdef' for c in text), 'REANCHOR_OBJECT_HEX')
            raw = bytes.fromhex(text.decode('ascii'))
            need(object_id(kind, raw) == ident, 'REANCHOR_OBJECT_ID:' + ident)
            self.cache[ident] = raw
        return self.cache[ident]

    def commit(self, ident):
        raw = self.get('commit', ident)
        header = raw.split(b'\n\n', 1)[0].decode('utf8').splitlines()
        need(header[0].startswith('tree '), 'REANCHOR_COMMIT_TREE')
        return header[0][5:], [line[7:] for line in header if line.startswith('parent ')]

    def resolve(self, tree, path):
        parts = path.split('/')
        for depth, part in enumerate(parts):
            table = tree_entries(self.get('tree', tree))
            if part not in table:
                return None
            mode, ident = table[part]
            if depth == len(parts) - 1:
                return mode, ident
            if mode != '40000':
                return None
            tree = ident
        return None

    def walk(self, tree, prefix):
        out = {}
        for name, (mode, ident) in tree_entries(self.get('tree', tree)).items():
            if mode == '40000':
                out.update(self.walk(ident, prefix + name + '/'))
            else:
                out[prefix + name] = (mode, ident)
        return out


def load_ledger(root):
    raw = read(root, LEDGER)
    need(sha(raw) == LEDGER_SHA256, 'REANCHOR_LEDGER_HASH')
    value = json.loads(raw, object_pairs_hook=_pairs)
    need(type(value) is dict and set(value) == {'schema', 'status', 'authority', 'release', 'strattester', 'grid_anchor', 'shared_subtrees', 'enumerated_directories', 'absent_paths', 'collisions', 'files', 'objects'}, 'REANCHOR_LEDGER_KEYS')
    need((value['schema'], value['status'], value['authority'], value['release']) == ('grid.market-data-custody-reanchor.v1', 'CANDIDATE_PENDING_OWNER_AND_GPT_ACCEPTANCE', False, 'NO_GO'), 'REANCHOR_LEDGER_IDENTITY')
    need(value['strattester']['commit'] == STRATTESTER and value['grid_anchor'] == {'repository': 'YehorBabenko88/bybit-cluster-grid', 'commit': GRID_ANCHOR, 'parent': GRID_ANCHOR_PARENT, 'baseline': GRID_BASELINE}, 'REANCHOR_LEDGER_ANCHORS')
    return value


def verify(root):
    """Return the verified closed file map {path: bytes} and anchor facts."""
    root = Path(root)
    value = load_ledger(root)
    objects = Objects(root, value['objects'])
    s_tree, s_parents = objects.commit(STRATTESTER)
    g_tree, g_parents = objects.commit(GRID_ANCHOR)
    need(g_parents == [GRID_ANCHOR_PARENT], 'REANCHOR_GRID_ANCHOR_PARENT')
    need(objects.commit(GRID_ANCHOR_PARENT)[1] == [GRID_BASELINE], 'REANCHOR_GRID_ANCHOR_BASELINE')
    need(len(s_parents) == 1, 'REANCHOR_STRATTESTER_SHAPE')
    need(set(value['shared_subtrees']) == set(SHARED), 'REANCHOR_SHARED_SET')
    for path, ident in value['shared_subtrees'].items():
        need(objects.resolve(s_tree, path) == ('40000', ident) == objects.resolve(g_tree, path), 'REANCHOR_SHARED_SUBTREE:' + path)
    files = {}
    for path, row in value['files'].items():
        need(type(row) is dict and set(row) == {'mode', 'blob', 'sha256', 'bytes', 'origin'}, 'REANCHOR_FILE_ROW')
        need(objects.resolve(s_tree, path) == (row['mode'], row['blob']), 'REANCHOR_STRATTESTER_BLOB:' + path)
        if row['origin'] == 'grid_live':
            need(path not in value['collisions'], 'REANCHOR_COLLISION_LIVE')
            need(objects.resolve(g_tree, path) == (row['mode'], row['blob']), 'REANCHOR_GRID_ANCHOR_BLOB:' + path)
            raw = read(root, path)
        else:
            need(row['origin'] == 'archived_strattester', 'REANCHOR_ORIGIN')
            grid = objects.resolve(g_tree, path)
            need(grid is None or path in value['collisions'], 'REANCHOR_UNDECLARED_COLLISION:' + path)
            raw = objects.get('blob', row['blob'])
        need(object_id('blob', raw) == row['blob'] and sha(raw) == row['sha256'] and len(raw) == row['bytes'], 'REANCHOR_FILE_BYTES:' + path)
        files[path] = raw
    for path, row in value['collisions'].items():
        need(objects.resolve(g_tree, path) is not None and objects.resolve(g_tree, path)[1] == row['grid_blob'] and value['files'][path]['origin'] == 'archived_strattester', 'REANCHOR_COLLISION')
    for path in value['absent_paths']:
        need(objects.resolve(s_tree, path) is None and objects.resolve(g_tree, path) is None, 'REANCHOR_ABSENCE_PROOF:' + path)
        need(not (root / path).exists() and not (root / path).is_symlink(), 'REANCHOR_GRID_LIVE_ABSENCE:' + path)
    for directory, suffixes in value['enumerated_directories'].items():
        listed = {p for p in objects.walk(objects.resolve(s_tree, directory)[1], directory + '/') if p.endswith(tuple(suffixes))}
        need(listed == {p for p in files if p.startswith(directory + '/') and p.endswith(tuple(suffixes))}, 'REANCHOR_ENUMERATION:' + directory)
    # Grid live runtime is exactly the anchored market_data tree (which is strattester's tree id).
    anchored = {p: e for p, e in objects.walk(objects.resolve(g_tree, 'market_data')[1], 'market_data/').items() if p.endswith(('.py', '.sql'))}
    live = {}
    for p in (root / 'market_data').iterdir():
        if p.suffix in ('.py', '.sql'):
            raw = read(root, 'market_data/' + p.name)
            live['market_data/' + p.name] = ('100644', object_id('blob', raw))
    need(live == anchored and len(live) == 49, 'REANCHOR_GRID_LIVE_RUNTIME49')
    need(not (root / 'strattester').exists(), 'REANCHOR_GRID_HAS_NO_STRATTESTER_PACKAGE')
    return {'files': files, 'ledger': value, 'objects': objects, 'strattester_tree': s_tree, 'grid_tree': g_tree}


def materialize(verified, dest):
    dest = Path(dest)
    for path, raw in verified['files'].items():
        target = dest / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
    return dest


def run_original(vroot, relative, function):
    """Execute one unchanged original test function with ROOT = verification root."""
    path = Path(vroot) / relative
    need(relative.startswith('tests/market_data/test_') and relative.endswith('.py'), 'REANCHOR_ORIGINAL_PATH')
    source = path.read_bytes()
    namespace = {'__name__': '_reanchored_' + Path(relative).stem, '__file__': str(path)}
    exec(compile(source, str(path), 'exec'), namespace)
    need(callable(namespace.get(function)), 'REANCHOR_ORIGINAL_FUNCTION:' + function)
    return namespace[function]()


def grid_runtime_python(root):
    root = Path(root)
    for name in GRID_RUNTIME_ROOTS:
        base = root / name
        if base.is_file():
            yield base
        elif base.is_dir():
            yield from sorted(base.rglob('*.py'))


def _literal(node):
    if isinstance(node, ast.Constant) and type(node.value) is str:
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _literal(node.left), _literal(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def grid_restoration_findings(root, modules, symbols, symbol_roots=('market_data',)):
    """Grid-live absence: no import/descriptor of retired strattester modules anywhere in the
    Grid runtime, and no definition/use of retired symbols in ``symbol_roots``."""
    root = Path(root)
    findings = []

    def retired(text):
        return type(text) is str and any(text == m or text.startswith((m + '.', m + ':')) for m in modules)

    for path in grid_runtime_python(root):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_bytes())
        check_symbols = rel.split('/')[0] in symbol_roots
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(retired(a.name) or a.name.split('.')[0] == 'strattester' for a in node.names):
                findings.append((rel, 'import'))
            if isinstance(node, ast.ImportFrom) and node.level == 0 and (retired(node.module) or (node.module or '').split('.')[0] == 'strattester'):
                findings.append((rel, 'import-from'))
            if retired(_literal(node)):
                findings.append((rel, 'descriptor'))
            if check_symbols:
                name = getattr(node, 'name', None) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) else getattr(node, 'id', None) if isinstance(node, ast.Name) else getattr(node, 'attr', None) if isinstance(node, ast.Attribute) else None
                if name in symbols:
                    findings.append((rel, 'symbol:' + name))
    return findings


# Grid's own legacy trading-evaluation helper shares one name with a retired strattester
# statistics symbol. It is not the retired module (no strattester import/descriptor); it is
# declared exactly here so any *new* restoration still fails. Ownership of this Grid
# statistic (Math) is an open item of the market-data/Grid merge plan.
KNOWN_GRID_HOMONYMS = frozenset({
    ('grid/historical_experiment_runner.py', 'symbol:evaluate_trades'),
    ('grid/incremental_edge.py', 'symbol:evaluate_trades'),
    ('grid/ml_evaluation_pipeline.py', 'symbol:evaluate_trades'),
    ('grid/ml_robustness.py', 'symbol:evaluate_trades'),
    ('grid/sizing_comparison.py', 'symbol:evaluate_trades'),
    ('grid/trading_evaluation.py', 'symbol:evaluate_trades'),
})


def assert_grid_not_restored(root, modules, symbols):
    findings = grid_restoration_findings(root, tuple(modules), frozenset(symbols), symbol_roots=GRID_RUNTIME_ROOTS)
    need(set(findings) <= KNOWN_GRID_HOMONYMS, 'REANCHOR_GRID_RESTORED:' + repr(sorted(set(findings) - KNOWN_GRID_HOMONYMS)))
    need(not any(kind in ('import', 'import-from', 'descriptor') for _, kind in findings), 'REANCHOR_GRID_RETIRED_IMPORT')
    return findings


def grid_roster(root):
    raw = read(Path(root), 'scripts/canonical_test_roster.json')
    roster = json.loads(raw, object_pairs_hook=_pairs)
    need(type(roster) is list and len(roster) == len(set(roster)) == 902 and all(type(x) is str for x in roster), 'REANCHOR_GRID_ROSTER902')
    need(sha(json.dumps(roster, separators=(',', ':'), ensure_ascii=True).encode('ascii')) == 'd235fb38d3f0d207200af95ada41d1ad58605f663dca317e38aa442d719b6fbe', 'REANCHOR_GRID_ROSTER_ORDERED')
    return roster


def grid_workflow_counterpart(root, verified):
    """Grid market-data-tests.yml is strattester tests.yml with exactly the documented B1 delta."""
    archived = verified['files']['.github/workflows/tests.yml']
    live = read(Path(root), '.github/workflows/market-data-tests.yml')
    expected = archived.replace(b'name: tests\n', b'name: Canonical Market Data tests (relocated from strattester@3850995)\n', 1).replace(
        b'      - run: python -m pip install ".[test,legacy-test]"\n      - run: python -m pytest -v\n',
        b'      - run: python -m pip install ".[test]"\n'
        b'      - name: Run the exact 902-node canonical roster (legacy strattester nodes are not relocated)\n'
        b'        shell: python\n'
        b'        run: |\n'
        b'          import json, sys, pytest\n'
        b"          roster = json.load(open('scripts/canonical_test_roster.json'))\n"
        b'          assert len(roster) == 902 and len(set(roster)) == 902\n'
        b"          sys.exit(pytest.main(['-v', *roster]))\n", 1)
    need(live == expected, 'REANCHOR_GRID_WORKFLOW_COUNTERPART')
    need(live.count(b'9e6acbd9e12a91189f57234828e31640983af553') == archived.count(b'9e6acbd9e12a91189f57234828e31640983af553') >= 1, 'REANCHOR_GRID_WORKFLOW_MATH_PIN')
    return live
