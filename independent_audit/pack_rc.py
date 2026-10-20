"""Create a local review ZIP from the current local commit; never publish/deploy."""
import hashlib,io,json,pathlib,subprocess,zipfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git','-c','safe.directory='+str(ROOT),'-c','core.autocrlf=false',*args],cwd=ROOT)
def main():
    sha=git('rev-parse','HEAD').decode().strip()
    out=ROOT/'artifacts';out.mkdir(exist_ok=True)
    raw=git('archive','--format=zip',sha)
    source=out/('offline-rc-source-'+sha+'.zip');assert not source.exists()
    comp=json.loads((ROOT/'independent_audit/composition.json').read_text())
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        assert z.testzip() is None
        for overlap in comp['overlap']:
            assert hashlib.sha256(z.read(overlap['path'])).hexdigest()==overlap['sha256_a']==overlap['sha256_b']
    source.write_bytes(raw)
    manifest=dict(kind='OFFLINE_REVIEW_ONLY',candidate_sha=sha,base_sha=comp['base'],heads=comp['heads'],
      source_zip=source.name,source_zip_sha256=hashlib.sha256(raw).hexdigest(),
      collected_tests=739,subtests=78,former_reproductions=10,skipped=0,xfail=0,
      physical_ready=False,execution_authorized=False,schema2_enabled=False,guest_cases='12 NOT_RUN',
      combined_github_actions='NOT_RUN_LOCAL_ONLY',infrastructure_operations=[])
    manifest_path=out/'manifest.json';manifest_path.write_text(json.dumps(manifest,indent=2),encoding='utf8')
    review=out/('offline-rc-review-20261020-'+sha[:12]+'.zip');assert not review.exists()
    with zipfile.ZipFile(review,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('README.txt','OFFLINE REVIEW ONLY. NO INSTALL/DEPLOY/VM/SQL/SERVICES.\nRead manifest.json and OPERATIONS_DRAFT.md. Source archive is data, not activation authority.\nPhysical deployment NO-GO; schema2 disabled; 12 guests NOT_RUN.\n')
        z.write(source,source.name);z.write(manifest_path,'manifest.json')
        for src,dest in [('docs/OFFLINE_RC_OPERATIONS_DRAFT.md','OPERATIONS_DRAFT.md'),
            ('independent_audit/RELEASE_CANDIDATE_REPORT.md','REPORT.md'),
            ('independent_audit/dry-run-plan.json','dry-run-plan.json'),
            ('independent_audit/ci-freeze.json','ci-freeze.json'),
            ('independent_audit/evidence/former10.xml','evidence/former10.xml'),
            ('independent_audit/evidence/offline-junit.xml','evidence/offline-junit.xml'),
            ('independent_audit/evidence/inventory.json','evidence/inventory.json')]:z.write(ROOT/src,dest)
    with zipfile.ZipFile(review) as z:
        assert z.testzip() is None
        assert hashlib.sha256(z.read(source.name)).hexdigest()==manifest['source_zip_sha256']
    sums={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (source,review)}
    (out/'SHA256SUMS.txt').write_text(''.join(h+'  '+n+'\n' for n,h in sums.items()),encoding='ascii')
    print(json.dumps(dict(commit=sha,artifacts=sums),indent=2))
if __name__=='__main__':main()
