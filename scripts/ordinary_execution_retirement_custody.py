"""Development-only closed pre-cut custody and independent live absence proof.

The survivor map binds this71cd-to-candidate cut; future source work needs its own
explicit custody transition. Nothing here imports or replaces retired runtime.
"""
import ast
import hashlib
import json
from pathlib import Path

LEDGER = 'docs/migration/ordinary-producer-retirement/transfer-ledger.json'
LEDGER_SHA256 = '5842ab6129559810e99b4109c71286adec1db976811d84dc06f64560ed158385'
BASELINE = '71cd99876107a7c1a378c32077dba15cf1bdc4a0'
OWNER = '92b30fd3364b2c0e8eb05b2592193cf126b86d2d'
RETIRED_SYMBOLS = frozenset(["Signal","ExecutionPolicy","ResearchTrade","simulate_trade","scalp_hypotheses","sweep_reclaim_entries","breakout_retest_volume_entries","volatility_expansion_entries","poc_reclaim_entries"])
RETIRED_LEAVES = frozenset(('execution','scalp_entries','research_scalp'))
RETIRED_MODULES = ('strattester.research.execution','research.execution','strattester.research.scalp_entries','research.scalp_entries','strattester.strategies.builtin.research_scalp','strategies.builtin.research_scalp')

def need(condition, code):
    if condition is not True:raise ValueError(code)

def sha(raw):return hashlib.sha256(raw).hexdigest()

def _pairs(items):
    result={}
    for key,value in items:
        need(type(key) is str and key not in result,'RETIREMENT_DUPLICATE_KEY')
        result[key]=value
    return result

def _json(raw):return json.loads(raw,object_pairs_hook=_pairs)

def _keys(value,expected):
    need(type(value) is dict and set(value)==set(expected),'RETIREMENT_CLOSED_KEYS')

def _read(root,name):
    need(type(name) is str and name and '\\' not in name,'RETIREMENT_PATH')
    path=Path(name)
    need(not path.is_absolute() and '..' not in path.parts,'RETIREMENT_PATH')
    target=root/path
    for part in (target,*target.parents):
        if part==root.parent:break
        need(not part.is_symlink(),'RETIREMENT_SYMLINK')
    need(target.is_file(),'RETIREMENT_REQUIRED_FILE:'+name)
    return target.read_bytes()

def _archive(root,item):
    need(type(item) is dict and set(item) in ({'archive','sha256','bytes'},{'archive','sha256','bytes','blob'}),'RETIREMENT_ARCHIVE_KEYS')
    need(type(item['bytes']) is int and item['bytes']>=0 and type(item['sha256']) is str,'RETIREMENT_ARCHIVE_TYPES')
    raw=_read(root,item['archive'])
    need(len(raw)==item['bytes'] and sha(raw)==item['sha256'],'RETIREMENT_ARCHIVE_HASH')
    if 'blob' in item:
        need(hashlib.sha1(('blob '+str(len(raw))+'\0').encode()+raw).hexdigest()==item['blob'],'RETIREMENT_ARCHIVE_BLOB')
    return raw

def _root(root):return Path(root) if root is not None else Path(__file__).resolve().parents[1]

def _ledger(root):
    raw=_read(root,LEDGER)
    need(sha(raw)==LEDGER_SHA256,'RETIREMENT_LEDGER_HASH')
    value=_json(raw)
    _keys(value,('schema','baseline','qualified_owner','status','original_total','accepted_before','remaining_before','roles','conditional_after_publication_independent_QA_current_Data14','archives','owner_contracts','gate_evidence','deleted_paths','mixed_edit','production_survivors','preserved_docs','generic_families','canonical_roster_sha256','canonical_count','runtime49','MathQ','helper9cec','authority','release'))
    need((value['schema'],value['baseline'],value['qualified_owner'],value['status'])==('market_data.ordinary-producer-retirement.v1',BASELINE,OWNER,'SOURCE_CUT_CANDIDATE_NOT_ACCEPTED_RETIREMENT'),'RETIREMENT_IDENTITY')
    need(type(value['original_total']) is int and type(value['accepted_before']) is int and type(value['remaining_before']) is int and (value['original_total'],value['accepted_before'],value['remaining_before'])==(547,44,503),'RETIREMENT_BASELINE_COUNTER')
    need(value['conditional_after_publication_independent_QA_current_Data14']=={'accepted':60,'remaining':487} and value['authority'] is False and value['release']=='NO_GO','RETIREMENT_CONDITIONAL_ONLY')
    need(type(value['roles']) is list and len(value['roles'])==16,'RETIREMENT_EXACT16')
    for role in value['roles']:
        need(type(role) is dict and set(role) in ({'original_id','canonical_ids','role','parameter_cases','original_body_sha256','body_hash_encoding'},{'original_id','canonical_ids','role','parameter_cases','original_body_sha256','clock_contract','body_hash_encoding'}),'RETIREMENT_ROLE_KEYS')
        need(type(role['original_id']) is str and type(role['parameter_cases']) is int and role['parameter_cases'] in (1,2) and type(role['canonical_ids']) is list and role['canonical_ids'] and all(type(x) is str for x in role['canonical_ids']) and type(role['original_body_sha256']) is str,'RETIREMENT_ROLE_TYPES')
    ids=[role['original_id'] for role in value['roles']]
    need(len(set(ids))==16 and sum(role['parameter_cases'] for role in value['roles'])==17,'RETIREMENT_UNIQUE_IDS_CASES')
    need(type(value['deleted_paths']) is list and len(value['deleted_paths'])==len(set(value['deleted_paths']))==7,'RETIREMENT_DELETED7')
    need(value['canonical_count']==902 and type(value['canonical_count']) is int and value['MathQ']=='9e6acbd9e12a91189f57234828e31640983af553' and value['helper9cec']=='9cec6e527a0fc80d845452e1bdbdd50962625ecf7bbb5c1e931eeb0f47e63e72','RETIREMENT_UNCHANGED_RUNTIME_CONTEXT')
    return value

def verified_pre_cut_archives(root=None):
    """Only verified historical bytes; this function never supplies a live view."""
    root=_root(root);value=_ledger(root)
    sources={name:_archive(root,item) for name,item in value['archives'].items()}
    contracts={name:_json(_archive(root,item)) for name,item in value['owner_contracts'].items()}
    for item in value['gate_evidence'].values():_archive(root,item)
    for name,digest in value['preserved_docs'].items():
        need(sha(_read(root,name))==digest,'RETIREMENT_PRESERVED_DOC:'+name)
    inventory=_json(_read(root,'docs/ci/retained-legacy-test-inventory.json'))
    originals={row['path']+'::'+name for row in inventory for name in row['tests']}
    prior=_json(_read(root,'docs/migration/journal-retirement/transfer-ledger.json'))
    accepted=prior['prior_accepted_original_ids']+[prior['role']['original_id']]
    ids={role['original_id'] for role in value['roles']}
    need(len(originals)==547 and len(accepted)==len(set(accepted))==44 and ids<=originals and not ids.intersection(accepted),'RETIREMENT_ORIGINAL547_DISJOINT')
    ordinary=contracts['tests/original_ordinary_signal_roster_v1.json']['original_roles']
    producer=contracts['tests/original_producer_counterparts_v1.json']['roles']
    need(ids=={row['id'] for row in ordinary+producer},'RETIREMENT_OWNER16_CONTRACT')
    need(sum(role['role']=='ordinary' for role in value['roles'])==10,'RETIREMENT_ORDINARY10')
    old_contract=contracts['tests/original_ordinary_signal_roster_v1.json']
    canonical_ids=set(old_contract['case_ids'])
    producer_contract={row['id']:row for row in producer}
    for role in value['roles']:
        normalized=[]
        for ident in role['canonical_ids']:
            parts=ident.split('::')
            need(len(parts)==3 and parts[0].startswith('tests/'),'RETIREMENT_CANONICAL_ID')
            normalized.append('<run_path>.'+parts[1]+'.'+parts[2])
        need(set(normalized)<=canonical_ids,'RETIREMENT_CANONICAL_ROSTER')
        if role['original_id'] in producer_contract:
            row=producer_contract[role['original_id']]
            expected=row['counterparts'] if 'counterparts' in row else [row['counterpart']]
            need(normalized==expected and role['original_body_sha256']==row['raw_body_sha256'],'RETIREMENT_PRODUCER_BINDING')
        else:
            row=next(row for row in ordinary if row['id']==role['original_id'])
            need(role['original_body_sha256']==row['sha256'] and role['parameter_cases']==row['parameter_cases'],'RETIREMENT_ORDINARY_BINDING')

    for role in value['roles']:
        filename,name=role['original_id'].split('::')
        text=sources[filename].decode('utf8').replace('\r\n','\n')
        nodes=[n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name==name]
        need(len(nodes)==1,'RETIREMENT_ORIGINAL_BODY:'+role['original_id'])
        need(role['body_hash_encoding'] in ('AST_SOURCE_SEGMENT_LF','AST_SOURCE_SEGMENT_WITH_TERMINAL_LF'),'RETIREMENT_BODY_ENCODING')
        segment=ast.get_source_segment(text,nodes[0])+('\n' if role['body_hash_encoding']=='AST_SOURCE_SEGMENT_WITH_TERMINAL_LF' else '')
        need(sha(segment.encode())==role['original_body_sha256'],'RETIREMENT_ORIGINAL_BODY:'+role['original_id'])
    roster=_read(root,'scripts/canonical_test_roster.json')
    need(sha(roster)==value['canonical_roster_sha256'] and roster==sources['scripts/canonical_test_roster.json'] and len(_json(roster))==902,'RETIREMENT_ROSTER902_UNCHANGED')
    need(sha(_read(root,'scripts/runtime_lineage_custody.py'))==value['helper9cec'],'RETIREMENT_OLD_HELPER_UNCHANGED')
    for name,item in value['runtime49'].items():
        need(sha(_read(root,name))==item['sha256'],'RETIREMENT_RUNTIME49_UNCHANGED')
    mixed=value['mixed_edit'];old=sources[mixed['path']]
    need(sha(old)==mixed['old_sha256'] and old[mixed['decorator_start']:].startswith(b"@pytest.mark.parametrize('side,sl,tp,bar', ["),'RETIREMENT_MIXED_OLD_CUT')
    expected=old[:mixed['decorator_start']].replace(mixed['removed_import'].encode(),b'')
    need(sha(expected)==mixed['new_sha256'],'RETIREMENT_MIXED_EXPECTED')
    return {'VERIFIED_PRE_CUT_ARCHIVES':sources,'roles':value['roles'],'expected_mixed':expected}

def _literal(node):
    if isinstance(node,ast.Constant) and type(node.value) is str:return node.value
    if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):
        left,right=_literal(node.left),_literal(node.right)
        if left is not None and right is not None:return left+right
    if isinstance(node,ast.JoinedStr) and all(isinstance(v,ast.Constant) and type(v.value) is str for v in node.values):return ''.join(v.value for v in node.values)
    return None

def _retired_module(value):
    return type(value) is str and any(value==name or value.startswith((name+'.',name+':')) for name in RETIRED_MODULES)

def require_no_retired_nodes(tree):
    for node in ast.walk(tree):
        if isinstance(node,(ast.Name,ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            need((getattr(node,'id',None) or getattr(node,'name',None)) not in RETIRED_SYMBOLS,'RETIREMENT_RESTORED_SYMBOL')
        if isinstance(node,ast.Attribute):need(node.attr not in RETIRED_SYMBOLS,'RETIREMENT_RESTORED_ATTRIBUTE')
        if isinstance(node,ast.Import):need(not any(_retired_module(a.name) or a.name in RETIRED_LEAVES for a in node.names),'RETIREMENT_RESTORED_IMPORT')
        if isinstance(node,ast.ImportFrom):
            need(not _retired_module(node.module) and (node.module or '').split('.')[-1] not in RETIRED_LEAVES,'RETIREMENT_RESTORED_IMPORT')
            need(not any(a.name in RETIRED_LEAVES or a.name in RETIRED_SYMBOLS for a in node.names),'RETIREMENT_RESTORED_ALIAS')
        need(not _retired_module(_literal(node)),'RETIREMENT_RESTORED_DESCRIPTOR')
        if isinstance(node,ast.Call):
            name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else None
            if name in ('__import__','import_module') and node.args:
                target=_literal(node.args[0])
                need(target not in RETIRED_LEAVES and not _retired_module(target),'RETIREMENT_RESTORED_DYNAMIC_IMPORT')
            if name in ('getattr','__getattribute__'):
                index=0 if name=='__getattribute__' and isinstance(node.func,ast.Attribute) else 1
                if len(node.args)>index:need(_literal(node.args[index]) not in RETIRED_SYMBOLS,'RETIREMENT_RESTORED_GETATTR')

def verify_retired_execution_absence(root=None):
    """Live-only proof, independent of archived-source availability or contents."""
    root=_root(root);value=_ledger(root)
    for name in value['deleted_paths']:
        path=root/name
        need(not path.exists() and not path.is_symlink(),'RETIREMENT_RESTORED_PATH:'+name)
    paths={p.relative_to(root).as_posix() for p in (root/'strattester').rglob('*') if p.is_file() and p.suffix.lower()=='.py'}
    need(paths==set(value['production_survivors']),'RETIREMENT_SURVIVOR_PATHSET')
    for name,digest in value['production_survivors'].items():
        raw=_read(root,name)
        need(sha(raw)==digest,'RETIREMENT_SURVIVOR_BYTES:'+name)
        require_no_retired_nodes(ast.parse(raw))
    mixed=value['mixed_edit'];raw=_read(root,mixed['path'])
    need(sha(raw)==mixed['new_sha256'],'RETIREMENT_MIXED_LIVE_BYTES')
    functions=[n for n in ast.parse(raw).body if isinstance(n,ast.FunctionDef)]
    need(len(functions)==8 and sum(n.name.startswith('test_') for n in functions)==7 and any(n.name=='snapshot' for n in functions),'RETIREMENT_MIXED_SEVEN_PLUS_HELPER')
    require_no_retired_nodes(ast.parse(raw))
    for item in value['generic_families']:
        need(len(_read(root,item['path']))==item['bytes'] and sha(_read(root,item['path']))==item['sha256'],'RETIREMENT_GENERIC_FAMILY')
    return {'VERIFIED_LIVE_ABSENCE':True,'removed_paths':tuple(value['deleted_paths']),'surviving_production_files':len(paths),'retained_mixed_tests':7}
