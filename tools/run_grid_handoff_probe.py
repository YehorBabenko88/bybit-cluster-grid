"""Hosted-only standalone handoff fixture. Not a Core20/Runtime2 producer."""
import hashlib,json,os,re,socket,subprocess,uuid
from pathlib import Path
from tools.build_s0_package import require_hosted,hosted_native_build_root,hosted_local_app_data,create_hosted_root
from tools.check_ddl_free_ci import ROOT,verify_checkout
from tools.s0_independent_acceptance import archive_members,strict_json
from s0_smoke.windows import current_identity,create_fresh_file,Custody


def instrument_fixture(source):
    start=' public static void HostedRuntime(string sourceRoot,string head,string sid,bool diagnosticOnly=false) {'
    stop=' static void RuntimeActions('
    if source.count(start)!=1 or source.count(stop)!=1:raise ValueError('PROBE_SOURCE_SHAPE_BLOCKED')
    a=source.index(start);b=source.index(stop,a)
    return source[:a]+start+'\n  HandoffProbe.Run(sourceRoot,head,sid);\n }\n'+source[b:]


def create_hosted_payload(path,sid,data,*,archive=False,api=None):
    """Diagnostic package payload, not the 1MiB production mutable-file API.

    Preserve its exclusive CREATE_NEW/handle custody; write at most1MiB per call.
    Package-member bound64MiB, complete sourceZIP bound512MiB, hosted-only.
    """
    require_hosted(os.environ,socket.gethostname())
    from s0_smoke.windows import Win32,WindowsBlocked,_absolute,_protected_sddl,_validate_mutable
    import ntpath
    if type(archive) is not bool or type(data) is not bytes or len(data)>(512 if archive else 64)*1024*1024:raise WindowsBlocked()
    path=_absolute(path);sddl=_protected_sddl(sid);api=api or Win32()
    with Custody(ntpath.dirname(path),sid,api=api) as parent:
        handle=api.create_file(path,sddl)
        try:
            before=api.inspect(handle);_validate_mutable(before,sid);parent.guard()
            for offset in range(0,len(data),1024*1024):
                parent.guard();api.write(handle,data[offset:offset+1024*1024])
            api.flush(handle)
            after=api.inspect(handle);_validate_mutable(after,sid)
            if before['identity']!=after['identity']:raise WindowsBlocked()
            parent.guard()
        finally:api.close(handle)


def run():
    require_hosted(os.environ,socket.gethostname());head=os.environ['EXACT_HEAD_SHA'];verify_checkout(ROOT,head)
    receipt=strict_json((ROOT/'s0-package/package-receipt.json').read_bytes())
    raw=(ROOT/'s0-package'/receipt['package']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=receipt['sha256'] or receipt['head']!=head:raise ValueError('PROBE_PACKAGE_CONTEXT')
    identity=current_identity();fixture=hosted_local_app_data()/('s0-maintenance-'+str(uuid.uuid4()))
    create_hosted_root(fixture,identity.sid)
    from s0_smoke.package import verify_package
    members=archive_members(raw)
    for name,data in members.items():
        path=fixture/name
        chain=[];parent=path.parent
        while parent!=fixture and not parent.exists():chain.append(parent);parent=parent.parent
        for directory in reversed(chain):create_hosted_root(directory,identity.sid)
        create_hosted_payload(path,identity.sid,data)
    create_hosted_payload(fixture/'source.zip',identity.sid,raw,archive=True);manifest=verify_package(fixture,fixture/'source.zip',head,receipt['sha256']);create_hosted_root(fixture/'temp',identity.sid)
    env=dict(os.environ);build=hosted_native_build_root()
    with Custody(build,identity.sid,[build/name for name in ('HandoffFixture.exe','S0Launcher.dll','HandoffChild.ps1')]) as custody:
        with subprocess.Popen([str(build/'HandoffFixture.exe'),'--runtime-diagnostic-parent',str(fixture),manifest['files']['runtime/python.exe']['sha256'],head,str(fixture/'temp/unused.json')],cwd=build,env=env,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE) as child:
            out,err=child.communicate(timeout=100);code=child.returncode
        custody.guard()
    result=ROOT/'maintenance-results';result.mkdir(exist_ok=True)
    captures={}
    for name in ('handoff-core.jsonl','handoff-child.jsonl'):
        path=fixture/'temp'/name
        if path.exists():
            data=path.read_bytes()
            if len(data)>4096:raise ValueError('PROBE_EVIDENCE_BOUND')
            (result/name).write_bytes(data);captures[name]=hashlib.sha256(data).hexdigest()
    (result/'handoff-driver.txt').write_bytes(out[:16384]);(result/'handoff-stderr.txt').write_bytes(err[:4096])
    provenance={name:hashlib.sha256((build/name).read_bytes()).hexdigest() for name in ('ProbeUserProfileTests.cs','HandoffChild.ps1','HandoffFixture.exe','S0Launcher.dll')}
    provenance['original_userprofile_source']=hashlib.sha256(subprocess.check_output(['git','show',head+':installer/physical-smoke-s0-tests/UserProfileTests.cs'],cwd=ROOT)).hexdigest()
    record=dict(provenance=provenance,package_sha256=receipt['sha256'],scope='HOSTED_DIAGNOSTIC_NOT_ACCEPTANCE',head=head,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],fixture_id=fixture.name,exit_code=code,status='BLOCKED' if code else 'MINIMAL_PROBE_COMPLETED_NOT_ACCEPTANCE',files=captures,execute=False,cleanup=False)
    (result/'handoff.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record));return 1 if code else 0

if __name__=='__main__':raise SystemExit(run())
