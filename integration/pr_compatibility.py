"""Read-only GitHub conflict watch. Metadata and source risk, never merge/acceptance."""
import argparse
import ast
import base64
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import quote

PRS=(238,239,240,241,242,244)
REQUIRED_WORKFLOWS={238:('ls5-native-observer-offline',),239:('ls5-trusted-bootstrap-offline',),
 240:('ls5-postgres-readiness-offline','ls5-postgres18-disposable'),241:('ls5-network-offline',),
 242:('ls5-physical-acceptance-offline',),244:('full-system-first-boot',)}
REPO='repos/YehorBabenko88/bybit-cluster-grid/'
CRITICAL={'grid/coordinator.py','grid/worker.py','grid/config.py','grid/migrations.py',
 'grid/schema_preparation.py','grid/schema_contract.py','requirements.txt',
 'installer/release-runtime-guard.ps1','installer/windows_preflight.py'}
SHA=re.compile('[0-9a-f]{40}');DIGEST=re.compile('[0-9a-f]{64}')


def need(ok,reason):
    if not ok:raise ValueError(reason)


def strict_metadata(raw):
    need(type(raw) is str and len(raw.encode('utf8'))<=2_000_000,'SIZE')
    def pairs(items):
        result={}
        for key,value in items:
            need(key not in result,'DUPLICATE_JSON_KEY');result[key]=value
        return result
    def constant(_):raise ValueError('NONFINITE')
    return json.loads(raw,object_pairs_hook=pairs,parse_constant=constant)


def safe_path(path):
    return (type(path) is str and 0<len(path)<=240 and not path.startswith('/') and
            '\\' not in path and ':' not in path and not any(ord(c)<32 for c in path) and
            all(p not in ('','..','.') for p in path.split('/')))


def reviews(path):
    result=[]
    if path.startswith('grid/') or path.endswith('.sql'):result.append('SCHEMA_OR_RUNTIME_REVIEW')
    if path.startswith('.github/'):result.append('MANDATORY_CI_REVIEW')
    if 'requirement' in path or path.endswith(('.csproj','.toml')):result.append('DEPENDENCY_REVIEW')
    if 'manifest' in path:result.append('RELEASE_INTEGRITY_REVIEW')
    if path.startswith('installer/'):result.append('WINDOWS_CONTRACT_REVIEW')
    return result or ['SOURCE_REVIEW']


def compare(snapshot,baseline):
    out=dict(metadata_valid=False,ci_all_success=False,head_drift=[],changed_paths=[],overlaps=[],
             g0='BLOCKED',g1='BLOCKED',g2='NO-GO',physical_ready=False,artifact_bytes_verified=False,
             execution_authorized=False,findings=[])
    try:
        # Larger source metadata still bounded separately; no executable payloads.
        need(len(json.dumps(snapshot))<2_000_000 and len(json.dumps(baseline))<2_000_000,'SIZE')
        for data in (snapshot,baseline):
            need(type(data) is dict and set(data)=={'schema','prs'} and type(data['schema']) is int and data['schema']==1,'SCHEMA')
            need(type(data['prs']) is list and len(data['prs'])==len(PRS) and {p['pr'] for p in data['prs']}==set(PRS),'PRS')
            for p in data['prs']:
                need(type(p) is dict and set(p)=={'pr','head','files','changed_files','complete','ci'} and type(p['pr']) is int,'PR_FIELDS')
                need(type(p['head']) is str and SHA.fullmatch(p['head']) and type(p['complete']) is bool,'HEAD_OR_COMPLETENESS')
                need(type(p['files']) is dict and 0<len(p['files'])<=256 and all(safe_path(n) for n in p['files']),'FILES')
                for v in p['files'].values():
                    if v is None:continue
                    need(type(v) is dict and set(v)=={'sha256','interface_sha256'} and all(type(h) is str and DIGEST.fullmatch(h) for h in v.values()),'DIGEST')
                need(type(p['changed_files']) is list and len(p['changed_files'])<=3000 and all(safe_path(n) for n in p['changed_files']),'CHANGED_FILES')
                need(type(p['ci']) is list and len(p['ci'])<=100,'CI')
                for c in p['ci']:
                    need(type(c) is dict and set(c)=={'name','head','run_id','status','conclusion','artifact_count'},'CI_FIELDS')
                    need(type(c['run_id']) is int and c['run_id']>0 and type(c['artifact_count']) is int and c['artifact_count']>=0,'CI_ID')
                    need(type(c['name']) is str and type(c['head']) is str and SHA.fullmatch(c['head']),'CI_CONTEXT')
        old={p['pr']:p for p in baseline['prs']};now={p['pr']:p for p in snapshot['prs']}
        valid=all(p['complete'] and all(v is not None for v in p['files'].values()) for p in now.values())
        green=True
        for n,p in now.items():
            if p['head']!=old[n]['head']:out['head_drift'].append(n)
            changed=sorted(k for k in set(p['files'])|set(old[n]['files']) if p['files'].get(k)!=old[n]['files'].get(k))
            out['changed_paths'] += [dict(pr=n,path=k,review=reviews(k)) for k in changed]
            for name in REQUIRED_WORKFLOWS[n]:
                matches=[c for c in p['ci'] if c['name']==name]
                c=max(matches,key=lambda c:c['run_id']) if matches else None
                if not c or c['head']!=p['head'] or c['status']!='completed' or c['conclusion']!='success' or c['artifact_count']<1:
                    green=False;out['findings'].append(dict(priority='P0',pr=n,reason='REQUIRED_EXACT_HEAD_CI_OR_ARTIFACT_MISSING'))
        names=sorted(set().union(*(p['files'] for p in now.values())))
        for path in names:
            rows={str(n):p['files'].get(path) for n,p in now.items()}
            nonempty=[v['sha256'] for v in rows.values() if v is not None]
            divergent=len(set(nonempty))>1 or len(nonempty)!=len(PRS)
            out['overlaps'].append(dict(path=path,sha256_by_pr={k:(v['sha256'] if v else None) for k,v in rows.items()},
                interface_sha256_by_pr={k:(v['interface_sha256'] if v else None) for k,v in rows.items()},
                divergent=divergent,review=reviews(path),owners=[int(k) for k,v in rows.items() if v is not None],
                priority='P1' if divergent and any(r in reviews(path) for r in ('SCHEMA_OR_RUNTIME_REVIEW','MANDATORY_CI_REVIEW','WINDOWS_CONTRACT_REVIEW','DEPENDENCY_REVIEW','RELEASE_INTEGRITY_REVIEW')) else 'P2',proof='SOURCE_METADATA_ONLY_NOT_SEMANTIC_COMPATIBILITY'))
        out.update(metadata_valid=valid,ci_all_success=green,head_drift=sorted(out['head_drift']))
        out['findings'].append(dict(priority='P1',reason='INDEPENDENT_SOURCE_AND_ARTIFACT_REVIEW_REQUIRED'))
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):out['findings']=[dict(priority='P0',reason='INVALID_OR_INCOMPLETE_SNAPSHOT')]
    return out


def gh(endpoint):
    p=subprocess.run(['gh','api',REPO+endpoint],capture_output=True,timeout=45)
    if p.returncode or len(p.stdout)>8_000_000:raise RuntimeError('GITHUB_READ_FAILED_OR_LIMIT')
    return json.loads(p.stdout)


def interface_digest(name,raw):
    if name.endswith('.py'):
        try:
            tree=ast.parse(raw.decode('utf8'))
            shapes=[n.name+':'+ast.dump(n.args,include_attributes=False)+':'+(ast.dump(n.returns,include_attributes=False) if n.returns else '') for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))]
            shapes += [ast.dump(d,include_attributes=False) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) for d in n.decorator_list]
            return hashlib.sha256(json.dumps(shapes,sort_keys=True).encode()).hexdigest()
        except (SyntaxError,UnicodeError,RecursionError):pass
    return hashlib.sha256(raw).hexdigest()


def collect():
    meta=[];counts={}
    for n in PRS:
        p=gh(f'pulls/{n}');head=p['head']['sha'];need(SHA.fullmatch(head),'HEAD')
        files=[]
        for page in range(1,31):
            part=gh(f'pulls/{n}/files?per_page=100&page={page}');files += [x['filename'] for x in part]
            if len(part)<100:break
        need(len(files)==p['changed_files'],'TRUNCATED_PR_FILES')
        for f in files:need(safe_path(f),'PATH');counts[f]=counts.get(f,0)+1
        commit=gh('git/commits/'+head);tree=gh('git/trees/'+commit['tree']['sha']+'?recursive=1');need(not tree.get('truncated'),'TRUNCATED_TREE')
        entries={r['path']:r for r in tree['tree'] if r['type']=='blob'}
        run_page=gh('actions/runs?head_sha='+head+'&per_page=100');runs=run_page['workflow_runs'];ci=[]
        for name in REQUIRED_WORKFLOWS[n]:
            matches=[r for r in runs if r['name']==name]
            if not matches:continue
            r=max(matches,key=lambda x:x['id']);art=gh(f'actions/runs/{r["id"]}/artifacts?per_page=100')
            ci.append(dict(name=name,head=r['head_sha'],run_id=r['id'],status=r['status'],conclusion=r['conclusion'],
                           artifact_count=sum(not a['expired'] for a in art['artifacts'])))
        meta.append((dict(pr=n,head=head,files={},changed_files=files,complete=run_page['total_count']<=100,ci=ci),entries))
    selected=CRITICAL|{p for p,c in counts.items() if c>1};need(len(selected)<=256,'OVERLAP_LIMIT')
    cache={}
    for p,entries in meta:
        for name in sorted(selected):
            row=entries.get(name)
            if row is None:p['files'][name]=None;continue
            need(row.get('mode') in ('100644','100755') and row.get('size',0)<=500_000,'UNSAFE_SOURCE_OBJECT')
            oid=row['sha']
            if oid not in cache:
                blob=gh('git/blobs/'+oid);need(blob.get('encoding')=='base64','BLOB_ENCODING');cache[oid]=base64.b64decode(''.join(blob['content'].split()),validate=True)
                need(hashlib.sha1(b'blob '+str(len(cache[oid])).encode()+bytes([0])+cache[oid]).hexdigest()==oid,'GIT_BLOB_MISMATCH')
            raw=cache[oid];p['files'][name]=dict(sha256=hashlib.sha256(raw).hexdigest(),interface_sha256=interface_digest(name,raw))
    for p,_ in meta:
        if gh(f'pulls/{p["pr"]}')['head']['sha']!=p['head']:p['complete']=False
    return dict(schema=1,prs=[p for p,_ in meta])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect-github',action='store_true');parser.add_argument('--snapshot');parser.add_argument('--baseline')
    args=parser.parse_args()
    if not args.collect_github and not args.snapshot:
        print(json.dumps(dict(status='PLAN_ONLY',network_calls=0,execution_authorized=False)));return 0
    try:
        snap=collect() if args.collect_github else strict_metadata(Path(args.snapshot).read_text(encoding='utf8'))
        baseline=strict_metadata(Path(args.baseline).read_text(encoding='utf8')) if args.baseline else snap
        print(json.dumps(dict(snapshot=snap,assessment=compare(snap,baseline)),indent=2))
        return 0  # transport success; assessment remains BLOCKED, never execution authority
    except Exception:
        print(json.dumps(dict(status='BLOCKED',reason='GITHUB_OR_SNAPSHOT_UNAVAILABLE',execution_authorized=False)));return 1


if __name__=='__main__':raise SystemExit(main())
