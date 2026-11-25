"""Development-only, closed historical/live custody. Never imports the SDK."""
import ast
import hashlib
import json
from pathlib import Path

TRANSITION = 'docs/provenance/runtime-math-reanchor/transition.json'
TRANSITION_SHA256 = '3ebb58eeed6047516db33418982133605f7bd3e7a3f5b1699114b57f616bd3b0'
OLD_ANCHOR = 'c05e0cabd6c6e4c2abb2002b7b69a8f1ba8aec57'
OLD_MATH = '9ed369ddd41ae32c4b3a9434f0b29d6dcf51154f'
NEW_MATH = '9e6acbd9e12a91189f57234828e31640983af553'
BASELINE = '9d2920d9ee3730e5ddf579ae67e9753de9c39fe5'

def need(value, code):
    if value is not True:
        raise ValueError(code)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def blob(raw, kind='blob'):
    return hashlib.sha1((kind+' '+str(len(raw))+'\0').encode()+raw).hexdigest()

def pairs(items):
    value = {}
    for key, item in items:
        need(type(key) is str and key not in value, 'LINEAGE_DUPLICATE_KEY')
        value[key] = item
    return value

def parse(raw):
    return json.loads(raw, object_pairs_hook=pairs)

def keys(value, expected):
    need(type(value) is dict and set(value) == set(expected), 'LINEAGE_CLOSED_KEYS')

def read(root, relative):
    need(type(relative) is str and bool(relative) and '\\' not in relative, 'LINEAGE_PATH')
    p = Path(relative)
    need(not p.is_absolute() and '..' not in p.parts and '.' not in p.parts, 'LINEAGE_PATH')
    target = root / p
    for part in (target, *target.parents):
        if part == root.parent:
            break
        need(not part.is_symlink(), 'LINEAGE_SYMLINK')
    need(target.is_file(), 'LINEAGE_FILE_REQUIRED')
    return target.read_bytes()

def archive(root, row):
    need(type(row) is dict and set(row) in ({'archive','sha256','bytes'}, {'archive','sha256','bytes','blob'}), 'LINEAGE_ARCHIVE_KEYS')
    need(type(row['bytes']) is int and row['bytes'] >= 0 and type(row['sha256']) is str, 'LINEAGE_ARCHIVE_TYPES')
    raw = read(root, row['archive'])
    need(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'LINEAGE_ARCHIVE_HASH')
    if 'blob' in row:
        need(blob(raw) == row['blob'], 'LINEAGE_ARCHIVE_BLOB')
    return raw

def ordered(value):
    return sha(json.dumps(value,separators=(',',':'),ensure_ascii=True).encode('ascii'))

def tree_entries(raw):
    result = {}; position = 0
    while position < len(raw):
        split = raw.index(b' ',position); end = raw.index(b'\0',split)
        mode = raw[position:split].decode('ascii'); name = raw[split+1:end].decode('utf8')
        need(name not in result and '/' not in name and name not in ('.','..'), 'LINEAGE_TREE_NAME')
        oid = raw[end+1:end+21]
        need(len(oid) == 20, 'LINEAGE_TREE_TRUNCATED')
        result[name] = (mode,oid.hex());position = end+21
    return result

def verified_contexts(root=None):
    root = Path(root) if root is not None else Path(__file__).resolve().parents[1]
    raw = read(root, TRANSITION)
    need(sha(raw) == TRANSITION_SHA256, 'LINEAGE_TRANSITION_HASH')
    t = parse(raw)
    keys(t, ('schema','baseline','old_anchor','old_math','new_math','archives','math_fixtures','old_runtime','new_runtime','preserved_files','old_roster_count','old_roster_ordered_sha256','new_roster_count','new_roster_ordered_sha256','new_ids'))
    need((t['schema'],t['baseline'],t['old_anchor'],t['old_math'],t['new_math']) == ('market_data.runtime-math-transition.v1',BASELINE,OLD_ANCHOR,OLD_MATH,NEW_MATH), 'LINEAGE_TRANSITION_IDENTITY')
    archived = {name:archive(root,row) for name,row in t['archives'].items()}
    old = parse(archived['docs/provenance/turnover-history-foundation/CURRENT_RUNTIME.json'])
    keys(old, ('schema','source_head','runtime_files','changed_baseline_archives','canonical_original_archive','canonical_original_sha256','canonical_original_count','canonical_current_count','legacy_ledger_modified'))
    need(old['schema'] == 'market_data.turnover-runtime-custody.v1' and old['source_head'] == OLD_ANCHOR and old['canonical_current_count'] == 898 and old['legacy_ledger_modified'] is False, 'LINEAGE_HISTORICAL_CUSTODY')
    need(len(old['changed_baseline_archives']) == 6, 'LINEAGE_ORIGINAL_SIX_ARCHIVES')
    for name,digest in t['preserved_files'].items():
        need(sha(read(root,name)) == digest, 'LINEAGE_PRESERVED_BYTES:'+name)
    for runtime in (t['old_runtime'],t['new_runtime']):
        need(type(runtime) is dict and len(runtime) == 49, 'LINEAGE_RUNTIME49')
        for name,row in runtime.items():
            keys(row, ('mode','blob','sha256'))
            need(type(name) is str and name.startswith('market_data/') and '/' not in name[12:] and name.endswith(('.py','.sql')) and row['mode'] == '100644' and all(type(row[k]) is str for k in row), 'LINEAGE_RUNTIME_ROW')
    need(set(t['old_runtime']) == set(t['new_runtime']), 'LINEAGE_RUNTIME_PATHSET')
    need({name:row['sha256'] for name,row in t['old_runtime'].items()} == old['runtime_files'], 'LINEAGE_OLD_RUNTIME49')
    need([name for name in t['old_runtime'] if t['old_runtime'][name] != t['new_runtime'][name]] == ['market_data/history_export.py'], 'LINEAGE_EXACT_ONE_RUNTIME_DELTA')
    need(sha(archived['market_data/history_export.py']) == old['runtime_files']['market_data/history_export.py'], 'LINEAGE_OLD_EXPORT')
    actual = {}
    for p in (root/'market_data').iterdir():
        if p.suffix in ('.py','.sql'):
            name = 'market_data/'+p.name; data = read(root,name)
            actual[name] = {'mode':'100644','blob':blob(data),'sha256':sha(data)}
    need(actual == t['new_runtime'], 'LINEAGE_LIVE_RUNTIME49')
    keys(t['math_fixtures'], ('old','new'))
    for label in ('old','new'):
        keys(t['math_fixtures'][label], ('market_math.py','market_compute_api.py','history_statistics.py'))
        for row in t['math_fixtures'][label].values():
            archive(root,row)
    new_math_blob = t['math_fixtures']['new']['market_math.py']['blob']
    for name in ('scripts/build_sdk_source_manifest.py','scripts/check_frozen_consumer.py','.github/workflows/market-data-pure.yml','.github/workflows/tests.yml'):
        expected = archived[name].replace(OLD_MATH.encode(),NEW_MATH.encode()).replace(b'0a41c2ae27bffa3a01b45d225c819935da40ab1b',new_math_blob.encode())
        need(read(root,name) == expected, 'LINEAGE_LIVE_PIN_BYTES:'+name)
    for name,constant in (('scripts/build_sdk_source_manifest.py','SOURCES'),('scripts/check_frozen_consumer.py','SOURCE_REVISIONS')):
        for source,pin in ((archived[name],OLD_MATH),(read(root,name),NEW_MATH)):
            nodes = [n for n in ast.parse(source).body if isinstance(n,ast.Assign) and any(isinstance(a,ast.Name) and a.id == constant for a in n.targets)]
            need(len(nodes) == 1 and ast.literal_eval(nodes[0].value)['unified-math-kernels'] == pin, 'LINEAGE_PIN_AST')
    before = parse(archived['scripts/canonical_test_roster.json'])
    current = parse(read(root,'scripts/canonical_test_roster.json'))
    need(type(before) is list and len(before) == len(set(before)) == t['old_roster_count'] == 898 and ordered(before) == t['old_roster_ordered_sha256'], 'LINEAGE_OLD_ROSTER')
    need(type(current) is list and all(type(x) is str for x in current) and len(current) == len(set(current)) == t['new_roster_count'] == 902 and current[:898] == before and current[898:] == t['new_ids'] and ordered(current) == t['new_roster_ordered_sha256'], 'LINEAGE_LIVE_ROSTER')
    live_raw = read(root,'docs/provenance/turnover-history-foundation/CURRENT_RUNTIME.json')
    live = parse(live_raw)
    need(live_raw == (json.dumps(live,indent=2)+'\n').encode('utf8'), 'LINEAGE_V2_CANONICAL_BYTES')
    keys(live, ('schema','source_head','anchor_tree','anchor_market_data_tree','runtime_files','canonical_current_count','canonical_ordered_sha256','transition_path','transition_sha256','anchor_commit_archive','anchor_tree_archive','anchor_market_data_tree_archive'))
    need(live['schema'] == 'market_data.turnover-runtime-custody.v2' and live['transition_path'] == TRANSITION and live['transition_sha256'] == TRANSITION_SHA256, 'LINEAGE_REQUIRED_V2')
    need(live['runtime_files'] == {name:row['sha256'] for name,row in actual.items()} and type(live['canonical_current_count']) is int and live['canonical_current_count'] == 902 and live['canonical_ordered_sha256'] == ordered(current), 'LINEAGE_V2_LIVE_MAP')
    need((live['anchor_commit_archive'],live['anchor_tree_archive'],live['anchor_market_data_tree_archive']) == ('docs/provenance/runtime-math-reanchor/raw/RHO.commit.hex.txt','docs/provenance/runtime-math-reanchor/raw/RHO.tree.hex.txt','docs/provenance/runtime-math-reanchor/raw/RHO.market_data.tree.hex.txt'), 'LINEAGE_ANCHOR_ARCHIVE_PATHS')
    commit = bytes.fromhex(read(root,live['anchor_commit_archive']).decode('ascii'))
    root_tree = bytes.fromhex(read(root,live['anchor_tree_archive']).decode('ascii'))
    runtime_tree = bytes.fromhex(read(root,live['anchor_market_data_tree_archive']).decode('ascii'))
    need(read(root,live['anchor_commit_archive']) == commit.hex().encode('ascii') and read(root,live['anchor_tree_archive']) == root_tree.hex().encode('ascii') and read(root,live['anchor_market_data_tree_archive']) == runtime_tree.hex().encode('ascii'), 'LINEAGE_ANCHOR_HEX_BYTES')
    need(blob(commit,'commit') == live['source_head'] and live['source_head'] not in (BASELINE,OLD_ANCHOR), 'LINEAGE_RUNTIME_ANCHOR_COMMIT')
    header = commit.split(b'\n\n',1)[0].decode('ascii').splitlines()
    need(header[0] == 'tree '+live['anchor_tree'] and [line for line in header if line.startswith('parent ')] == ['parent '+BASELINE], 'LINEAGE_RUNTIME_ANCHOR_PARENT')
    need(blob(root_tree,'tree') == live['anchor_tree'] and tree_entries(root_tree)['market_data'] == ('40000',live['anchor_market_data_tree']), 'LINEAGE_ROOT_TREE')
    need(blob(runtime_tree,'tree') == live['anchor_market_data_tree'], 'LINEAGE_RUNTIME_TREE')
    entries = tree_entries(runtime_tree)
    need({name:(row['mode'],row['blob']) for name,row in actual.items()} == {'market_data/'+name:entry for name,entry in entries.items() if name.endswith(('.py','.sql'))}, 'LINEAGE_ANCHORED_RUNTIME49')
    return {'VERIFIED_HISTORICAL':{'custody':old,'runtime49':old['runtime_files'],'math_pin':OLD_MATH,'roster':before,'archived_sources':archived}, 'VERIFIED_LIVE':{'custody':live,'runtime49':live['runtime_files'],'math_pin':NEW_MATH,'roster':current,'runtime_anchor':live['source_head']}}
