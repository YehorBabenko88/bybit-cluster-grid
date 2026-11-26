"""Pure original in-memory journal role custody; no journal or owner runtime execution."""
import ast,hashlib,json,pathlib
ROOT=pathlib.Path(__file__).resolve().parents[2]
# Development custody is loaded from detached, hash-verified bytes, never sys.path.
import hashlib as _lineage_hashlib
from pathlib import Path as _LineagePath
from types import ModuleType as _LineageModule
_lineage_path = _LineagePath(__file__).resolve().parents[2]/'scripts/runtime_lineage_custody.py'
_lineage_raw = _lineage_path.read_bytes()
if _lineage_hashlib.sha256(_lineage_raw).hexdigest() != '9cec6e527a0fc80d845452e1bdbdd50962625ecf7bbb5c1e931eeb0f47e63e72':
 raise ValueError('LINEAGE_HELPER_SOURCE_SEAL')
_lineage_module = _LineageModule('_sealed_data_runtime_lineage')
_lineage_module.__file__ = str(_lineage_path)
exec(compile(_lineage_raw,str(_lineage_path),'exec'),_lineage_module.__dict__)
verified_contexts = _lineage_module.verified_contexts
# Mandatory source retirement custody: exact detached sealed DEV helper, no fallback.
import hashlib as _retirement_hashlib
from pathlib import Path as _RetirementPath
from types import ModuleType as _RetirementModule
_retirement_path = _RetirementPath(__file__).resolve().parents[2]/'scripts/ordinary_execution_retirement_custody.py'
_retirement_raw = _retirement_path.read_bytes()
if _retirement_hashlib.sha256(_retirement_raw).hexdigest() != '5bbf148b9517e744a86b02943df8be64ce606d24e592a6c30603a8ab6e2d5ca3':
 raise ValueError('RETIREMENT_HELPER_SOURCE_SEAL')
_retirement_module = _RetirementModule('_sealed_ordinary_execution_retirement')
_retirement_module.__file__ = str(_retirement_path)
exec(compile(_retirement_raw,str(_retirement_path),'exec'),_retirement_module.__dict__)
verified_pre_cut_archives = _retirement_module.verified_pre_cut_archives
verify_retired_execution_absence = _retirement_module.verify_retired_execution_absence

def pre_cut_sources():
 verify_retired_execution_absence(ROOT)
 return verified_pre_cut_archives(ROOT)['VERIFIED_PRE_CUT_ARCHIVES']

def historical_context():
 return verified_contexts(ROOT)['VERIFIED_HISTORICAL']
DOC=ROOT/'docs/migration/journal-retirement'
OLD_ID='tests/research/test_execution_journal.py::test_journal_preserves_research_metadata'
NEW_ID='tests/market_data/test_journal_retirement.py::test_journal_metadata_role_has_exact_canonical_owner'
PRESERVED={"docs/ci/retained-legacy-test-inventory.json":"f9868f6ef7b29936f056446896e39d3f1fc602a37096f97b8759479d60e73df9","docs/ci/four-owner-legacy-obligations.json":"ebb9a9e5b56932e14c1f74986c355b6c9c828df26cb035c98cb0c8349f1427d0","docs/migration/entry-context-retirement/transfer-ledger.json":"02005d84cdd85edb64d2fb7428fae6d47c81c91a1320eb2a45a157ecf26c994d","docs/migration/scale-mc-retirement/transfer-ledger.json":"293f94b9bf4146e7d3046c1a0ff35e8b1a89ca7c87ff168ac7504060da2a6477","docs/migration/reporting-retirement/transfer-ledger.json":"2b746b67eda7332e838fdb28a373f016d337c5a57cff0080d0ff7ba93e95181f","docs/migration/pattern-statistics-bootstrap-retirement/transfer-ledger.json":"3b2ddef46c7001b271a446a098fb5dae26ef5f9e34524710819451aceaf421f6","docs/migration/screening-retirement/transfer-ledger.json":"d842a60c01943b574be1e8be85e3abba9a5e0ff1746aaa1d2bce3314aa78d6c1"}
CODE={"strattester/research/execution.py":"47154908f325ef7b99c26e79f4184ccfb66756ed1998810a27d1a7f54de550a5","strattester/research/scalp_entries.py":"fcc39f27efe6730eaa85329dcab6160b838c0b2229e8a1ec58443f582218b24b","strattester/strategies/builtin/research_scalp.py":"32a0bf1d43b710dcff70d8f3572543b293dcf1151012c0d75e42de7fd8edee17"}
def sha(raw):return hashlib.sha256(raw).hexdigest()
def functions(raw):
 text=raw.decode('utf8');return {n.name:ast.get_source_segment(text,n) for n in ast.parse(text).body if isinstance(n,ast.FunctionDef)}
def literal(node):
 if isinstance(node,ast.Constant) and type(node.value) is str:return node.value
 if isinstance(node,ast.BinOp) and isinstance(node.op,ast.Add):
  left,right=literal(node.left),literal(node.right)
  if left is not None and right is not None:return left+right
 return None
def retired_module(text):
 return type(text) is str and any(text==name or text.startswith((name+':',name+'.')) for name in ('strattester.research.journal','research.journal'))
def test_journal_metadata_role_has_exact_canonical_owner():
 raw=(DOC/'transfer-ledger.json').read_bytes();assert sha(raw)=='9ab3af5294fb8f40d24bd166021dd07f191507192ad20ed00263f544289ee324'
 value=json.loads(raw);assert set(value)==set(["schema","source_head","status","original_legacy_total","accepted_original_roles","remaining_accepted","candidate_original_roles","conditional_after_acceptance_publication_current_CI","prior_accepted_original_ids","role","archives","old_canonical","canonical_current_count","canonical_ordered_sha256","new_id","preserved_inventory","preserved_code","runtime49","runtime_anchor_unchanged","MathSDKSourceUnchanged","runtime_dependency_added","authority","release"])
 assert value['schema']=='market_data.journal-source-retirement.v1' and value['source_head']=='3bc0c2423d47725123dc95de994cbda192825da2'
 assert value['status']=='PRIVATE_SOURCE_REMOVAL_CANDIDATE_PENDING_INDEPENDENT_QA_PUBLICATION_CURRENT_CI'
 assert (value['original_legacy_total'],value['accepted_original_roles'],value['remaining_accepted'],value['candidate_original_roles'])==(547,43,504,1)
 assert value['conditional_after_acceptance_publication_current_CI']=={'accepted_original_roles':44,'remaining':503}
 assert value['runtime_dependency_added'] is False and value['authority'] is False and value['release']=='NO_GO'
 assert value['MathSDKSourceUnchanged']=='9ed369ddd41ae32c4b3a9434f0b29d6dcf51154f'
 for script,name in (('scripts/build_sdk_source_manifest.py','SOURCES'),('scripts/check_frozen_consumer.py','SOURCE_REVISIONS')):
  assignments=[node for node in ast.parse(historical_context()['archived_sources'][script]).body if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets)]
  assert len(assignments)==1 and ast.literal_eval(assignments[0].value)['unified-math-kernels']==value['MathSDKSourceUnchanged']
 previous=json.loads((ROOT/'docs/migration/screening-retirement/transfer-ledger.json').read_bytes());prior=previous['prior_accepted_original_ids']+[r['original_id'] for r in previous['roles']]
 assert value['prior_accepted_original_ids']==prior and len(prior)==len(set(prior))==43
 originals={r['path']+'::'+name for r in json.loads((ROOT/'docs/ci/retained-legacy-test-inventory.json').read_bytes()) for name in r['tests']}
 assert len(originals)==547 and set(prior)<=originals and OLD_ID in originals and OLD_ID not in prior
 assert value['role']==json.loads(r'''{"original_id":"tests/research/test_execution_journal.py::test_journal_preserves_research_metadata","owner":"Terminan","owner_commit":"f111ccb7706de6654ba234e0e175221e7a938518","functional_build":"754e99bbb1cbecb2fd2d7766cbae39802d6b4831","canonical_api":"terminan.research_reporting.build_research_report","canonical_id":"tests/test_journal_declared_labels.py::JournalDeclaredLabelTests::test_original_journal_three_labels_survive_actual_modeled_fill","literal_labels":{"coverage":"COMPLETE_HISTORY","declared_volatility":"HIGH","declared_poc_mode":"TRADE_POC"},"hosted_evidence":{"path":"outputs/hosted-termf111-1795495526719/receipt.json","sha256":"71ee237c4669a8b595c0d423c16a46bb1ebbdc82a43d346ecef015e87f15ecdf"},"independent_evidence":{"path":"outputs/qa-independent-journal-labels-1795494768931/receipt.json","sha256":"ef698aeafa172e8f0b3feb9d5949069e3c0900c944a619e319ff1bb43cf8a27a"},"durable_storage_qualified":false}''')
 assert value['preserved_inventory']==PRESERVED and value['preserved_code']==CODE
 for path,digest in PRESERVED.items():assert sha((ROOT/path).read_bytes())==digest
 archived_code=pre_cut_sources()
 for path,digest in CODE.items():assert sha(archived_code[path])==digest
 assert value['archives']==json.loads(r'''{"strattester/research/journal.py":{"archive":"docs/migration/journal-retirement/raw/strattester__research__journal.py.txt","blob":"14abc71411e8ae90ac3bbe87f310b97c729e4f25","sha256":"fb11dbeeddf728d2350ca779ec6eec1bdbfc51145acf740dbec40e188834c035","bytes":163},"tests/research/test_execution_journal.py":{"archive":"docs/migration/journal-retirement/raw/tests__research__test_execution_journal.py.txt","blob":"494f8408eaed87a81edbe353ee5b1ef7e675f6b2","sha256":"36e8feef44ce246d3fe3ddcd5c07f135fb131fdd596a78426ddbad2a6df8d823","bytes":3517}}''')
 for item in value['archives'].values():
  raw=(ROOT/item['archive']).read_bytes();assert sha(raw)==item['sha256'] and len(raw)==item['bytes']
 assert value['old_canonical']==json.loads(r'''{"archive":"docs/migration/journal-retirement/canonical-897-roster.json","sha256":"bc1630041f9e60421cb713b52df38bef3f6d947ecc649ee24028b901d1ed0362","count":897,"ordered_sha256":"a625c31418f78bb8bdb432a210d87707e7cffee0152ecfb7d4aa6b9e338d102f"}''')
 frozen=(DOC/'canonical-897-roster.json').read_bytes();assert sha(frozen)=='bc1630041f9e60421cb713b52df38bef3f6d947ecc649ee24028b901d1ed0362'
 before=json.loads(frozen);historical_roster=historical_context()['roster']
 assert len(before)==897 and historical_roster[:897]==before and historical_roster[897:]==[NEW_ID] and value['new_id']==NEW_ID
 assert len(historical_roster)==len(set(historical_roster))==value['canonical_current_count']==898 and all(type(x) is str for x in historical_roster)
 assert sha(json.dumps(before,separators=(',',':'),ensure_ascii=True).encode())==value['old_canonical']['ordered_sha256']=='a625c31418f78bb8bdb432a210d87707e7cffee0152ecfb7d4aa6b9e338d102f'
 assert sha(json.dumps(historical_roster,separators=(',',':'),ensure_ascii=True).encode())==value['canonical_ordered_sha256']=='cce8e94b8a6dc655718e09b8d38e39aa3b66eff3d3b24f6d81593916544ec538'
 historical_runtime49=historical_context()['runtime49']
 custody=historical_context()['custody']
 assert len(historical_runtime49)==49 and historical_runtime49==value['runtime49']==custody['runtime_files']
 assert custody['source_head']==value['runtime_anchor_unchanged']=='c05e0cabd6c6e4c2abb2002b7b69a8f1ba8aec57' and custody['canonical_current_count']==898
 assert not (ROOT/'strattester/research/journal.py').exists()
 raw=(ROOT/value['archives']['tests/research/test_execution_journal.py']['archive']).read_bytes();archived_pre_cut=pre_cut_sources()['tests/research/test_execution_journal.py']
 start=raw.index(b'def test_journal_preserves_research_metadata(');end=raw.index(b'def test_long_limit_gapped_below_fills_at_better_open(')
 expected=(raw[:start]+raw[end:]).replace(b'from strattester.research.journal import TradeJournal\n',b'')
 assert archived_pre_cut==expected
 original=functions(raw);retained=functions(archived_pre_cut)
 assert len(original)==9 and len(retained)==8 and retained=={k:v for k,v in original.items() if k!='test_journal_preserves_research_metadata'}
 for path in (ROOT/'strattester').rglob('*.py'):
  for node in ast.walk(ast.parse(path.read_bytes())):
   if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Name)):assert (getattr(node,'name',None) or getattr(node,'id',None))!='TradeJournal'
   if isinstance(node,ast.Attribute):assert node.attr!='TradeJournal'
   if retired_module(literal(node)):raise AssertionError('RETIRED_JOURNAL_DESCRIPTOR')
   if isinstance(node,ast.Import):assert not any(retired_module(a.name) or a.name=='journal' for a in node.names)
   if isinstance(node,ast.ImportFrom):
    assert (node.module or '').split('.')[-1]!='journal'
    research_package=node.module in ('strattester.research','research') or node.level>0 and (node.module is None or node.module.split('.')[-1]=='research')
    assert not (research_package and any(alias.name=='journal' for alias in node.names))
   if isinstance(node,ast.Call):
    name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else None
    if name in ('getattr','__getattribute__'):
     field_index=0 if name=='__getattribute__' and isinstance(node.func,ast.Attribute) and len(node.args)==1 else 1
     if len(node.args)>field_index:assert literal(node.args[field_index]) not in ('TradeJournal','journal')
    if name in ('__import__','import_module') and node.args:
     target=literal(node.args[0]);assert target not in ('journal','.journal') and not retired_module(target)
     if target in ('strattester.research','research'):
      fromlists=([node.args[3]] if len(node.args)>3 else [])+[k.value for k in node.keywords if k.arg=='fromlist']
      assert not any(isinstance(names,(ast.Tuple,ast.List)) and any(literal(n)=='journal' for n in names.elts) for names in fromlists)
 attrs=(ROOT/'.gitattributes').read_bytes();assert sha(attrs[:1541])=='79176543e25c69bc37baeedb0e8c75827c515d86cf6368fea464b92582b4fed4'
 for policy in (b'docs/migration/journal-retirement/canonical-897-roster.json -text',b'docs/migration/journal-retirement/transfer-ledger.json -text',b'tests/research/test_execution_journal.py text eol=lf',b'strattester/research/scalp_entries.py text eol=lf',b'strattester/strategies/builtin/research_scalp.py text eol=lf'):assert policy in attrs.splitlines()
