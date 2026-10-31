"""Local v3 deployment actuator for Grid-issued permits, never a second fleet controller.

Only caller-admitted ephemeral labs may execute now. Production enrollment,
rollout ordering, leader fencing and credential verification belong to Grid.
The external publisher certificate pin is mandatory and is never learned from
candidate bytes. Administrative stop persists before stopping the runtime.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import socket
import tempfile

from . import update_manager as updates


def assert_ephemeral_scope(root,*,scope,authorization=False,hostname=None):
    root=Path(root).absolute();host=(hostname or socket.gethostname()).split('.')[0].upper()
    if host in ('LS5','PC4','ADMINIT') or authorization is not True:raise ValueError('physical execution prohibited')
    if scope=='CLOUD_LAB' and os.name!='nt':
        temp=Path(tempfile.gettempdir()).resolve()
        if temp not in root.resolve().parents or not root.parts[len(temp.parts)].startswith('mission3-'):raise ValueError('disposable lab root required')
    elif scope=='EPHEMERAL_WINDOWS_CI':
        temp=Path(os.environ.get('RUNNER_TEMP','/missing')).resolve()
        if (os.name!='nt' or os.environ.get('GITHUB_ACTIONS')!='true' or os.environ.get('RUNNER_ENVIRONMENT')!='github-hosted' or
            os.environ.get('RUNNER_OS')!='Windows' or temp not in root.resolve().parents):raise ValueError('explicit hosted Windows lab required')
    else:raise ValueError('physical execution prohibited')
    for item in (root,*root.parents):
        if item.is_symlink() or getattr(item,'is_junction',lambda:False)():raise ValueError('linked namespace prohibited')
    return True


def _safe_deployment_tree(root):
    """Reject pre-existing link/junction/hardlink escapes before local effects.

    Trusted single-writer namespace checks, not hostile concurrent-admin proof.
    """
    import stat
    root=Path(root)
    for parent in (root,*root.parents):
        if parent.is_symlink() or getattr(parent,'is_junction',lambda:False)():raise ValueError('linked deployment namespace')
    if not root.exists():return
    pending=[root];count=0
    while pending:
        directory=pending.pop()
        with os.scandir(directory) as entries:
            for entry in entries:
                count+=1
                if count>100000:raise ValueError('deployment namespace limit')
                info=entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or getattr(info,'st_file_attributes',0)&1024:raise ValueError('linked deployment child')
                if stat.S_ISDIR(info.st_mode):pending.append(Path(entry.path))
                elif not stat.S_ISREG(info.st_mode) or info.st_nlink!=1:raise ValueError('ambiguous deployment file')


@contextlib.contextmanager
def _lock(root):
    root.mkdir(parents=True,exist_ok=True)
    with (root/'deployment.lock').open('a+b') as f:
        if os.name=='nt':
            import msvcrt
            f.seek(0);f.write(b'0');f.flush();f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
        try:yield
        finally:
            if os.name=='nt':f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f,fcntl.LOCK_UN)


class DeploymentAgent:
    def __init__(self,root,*,node_id,publisher_pin,signature_verifier,enrollment_verifier,runtime,execution_guard,permit_verifier=None,execution_scope='PREPARE',lab_authorized=False,git_executable=None,git_sha256=None):
        if not node_id or node_id.upper() in ('LS5','PC4','ADMINIT'):raise ValueError('office node prohibited')
        if not isinstance(publisher_pin,str) or len(publisher_pin)!=64 or any(c not in '0123456789abcdef' for c in publisher_pin):raise ValueError('external publisher pin required')
        self.git_executable=git_executable;self.git_sha256=git_sha256
        self.root=Path(root);self.node_id=node_id;self.publisher_pin=publisher_pin
        self.verify_signature=signature_verifier;self.verify_enrollment=enrollment_verifier
        self.runtime=runtime;self.guard=execution_guard;self.scope=execution_scope;self.lab_authorized=lab_authorized;self.verify_permit=permit_verifier or (lambda permit:False)
    def _authorize(self):
        assert_ephemeral_scope(self.root,scope=self.scope,authorization=self.lab_authorized)
        if self.guard(self.root) is not True:raise ValueError('execution guard refused')
        _safe_deployment_tree(self.root)
    def _state(self):
        p=self.root/'deployment-state.json'
        return json.loads(p.read_text()) if p.exists() else dict(schema=1,sequence=0,admin_stopped=False,status='new',release_sha256=None)
    def _save(self,state):
        self._authorize()
        updates._write_marker(self.root,'deployment-state.json',json.dumps(state,sort_keys=True))
    def stop(self):
        self._authorize()
        with _lock(self.root):
            state=self._state();state['admin_stopped']=True;self._save(state);self.runtime.stop_release()
    def resume(self):
        self._authorize()
        with _lock(self.root):
            state=self._state();state['admin_stopped']=False;self._save(state)
    def uninstall(self):
        # Safe logical uninstall: stop only. Never delete histories, credentials,
        # immutable releases, backups, current or recovery artifacts.
        self.stop();return dict(status='stopped_preserved',data_deleted=False)
    def _require_permit(self,permit):
        self._authorize()
        if self.verify_permit(permit) is not True:raise ValueError('authenticated current Grid permit required')
    def _verify_recovery(self,release_root,state):
        import zipfile
        from unified_system.release_manifest import parse_manifest
        self._authorize()
        record=state.get('trusted_releases',{}).get(release_root.name)
        if not record:raise ValueError('no retained verified recovery release')
        raw=(release_root/'unified-release.json').read_bytes();signature=(release_root/'unified-release.p7s').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record['manifest_sha256'] or hashlib.sha256(signature).hexdigest()!=record['signature_sha256']:raise ValueError('recovery trust digest mismatch')
        if self.verify_signature(raw,signature,self.publisher_pin) is not True:raise ValueError('recovery CMS signature rejected')
        m=parse_manifest(raw,expected_publisher=self.publisher_pin)
        if m['release_id']!=release_root.name:raise ValueError('recovery release identity')
        with tempfile.TemporaryDirectory(prefix='mission3-recovery-',dir=self.root) as temp:
            for name,descriptor in m['modules'].items():
                capsule=release_root/'capsules'/name;artifact=capsule/'artifact.zip'
                if artifact.stat().st_size!=descriptor['artifact']['bytes'] or updates.sha256_file(artifact)!=descriptor['artifact']['sha256']:raise ValueError('recovery capsule digest mismatch')
                with zipfile.ZipFile(artifact) as archive:
                    if archive.namelist()!=['source.bundle'] or archive.read('source.bundle')!=(capsule/'source.bundle').read_bytes():raise ValueError('recovery source bundle changed')
                actual=release_root/'modules'/name
                if updates.sha256_file(actual/'.git/config')!=record['git_configs'][name] or (actual/'.git/config').read_bytes()!=updates.capsule_git_config() or (actual/'.git/objects/info/alternates').exists() or (actual/'.git/info/attributes').exists() or (actual/'.git/info/grafts').exists() or (actual/'.git/refs/replace').exists():raise ValueError('recovery Git configuration changed')
                updates.verify_materialized_identity(actual,descriptor,git_executable=self.git_executable,git_sha256=self.git_sha256)
                expected=updates.materialize_source_capsule(capsule/'source.bundle',Path(temp)/name,descriptor,git_executable=self.git_executable,git_sha256=self.git_sha256)
                files=lambda root:{p.relative_to(root).as_posix():p for p in root.rglob('*') if p.is_file() and '.git' not in p.relative_to(root).parts}
                wanted,found=files(expected),files(actual)
                if set(wanted)!=set(found) or any(wanted[p].read_bytes()!=found[p].read_bytes() for p in wanted):raise ValueError('recovery source bytes changed')
        return m,raw
    def apply(self,manifest_bytes,signature,artifacts,*,credential,permit=None):
        from unified_system.release_manifest import parse_manifest
        self._authorize()
        if self.verify_enrollment(self.node_id,credential) is not True:raise ValueError('server-issued enrollment required')
        if type(signature) is not bytes or not 0<len(signature)<=262144:raise ValueError('signature bounds')
        if self.verify_signature(manifest_bytes,signature,self.publisher_pin) is not True:raise ValueError('CMS signature rejected')
        m=parse_manifest(manifest_bytes,expected_publisher=self.publisher_pin)
        digest=hashlib.sha256(manifest_bytes).hexdigest();version=m['release_id']
        with _lock(self.root):
            self._authorize()
            state=self._state()
            if state['admin_stopped']:raise ValueError('administrative stop persists')
            if state['status'] in ('activating','rollback_failed'):raise ValueError('interrupted activation requires explicit recovery')
            if state['sequence']>m['sequence'] or state['sequence']==m['sequence'] and state['release_sha256']!=digest:raise ValueError('nonmonotonic release')
            if state['release_sha256']==digest and updates.current_version(self.root)==version and state['status']=='healthy':
                verified,_=self._verify_recovery(self.root/'releases'/version,state)
                active=self.root/'releases'/version/'unified-release.json'
                expected=dict(release_id=version,release_sha256=digest,ready=True,modules={k:dict(version=v['version'],ready=True) for k,v in m['modules'].items()})
                if active.read_bytes()!=manifest_bytes or self.runtime.health_release(version)!=expected:raise ValueError('active release requires recovery')
                return dict(status='already_active',release_sha256=digest)
            if self.verify_permit(permit) is not True:raise ValueError('authenticated Grid permit required')
            if permit is not None:
                if permit.get('node_id')!=self.node_id or permit.get('manifest_sha256')!=digest or permit.get('version')!=version or permit.get('status')!='queued':raise ValueError('Grid rollout permit mismatch')
            previous=updates.current_version(self.root)
            target=self.root/'releases'/version
            if target.exists():
                # A prior valid permit may have expired after complete immutable
                # staging but before registration. Reconstruct trust from this
                # newly admitted external CMS/manifest, never from cached claims.
                expected_config=hashlib.sha256(updates.capsule_git_config()).hexdigest()
                admitted=dict(manifest_sha256=digest,signature_sha256=hashlib.sha256(signature).hexdigest(),git_configs={name:expected_config for name in m['modules']})
                self._verify_recovery(target,{'trusted_releases':{version:admitted}})
            else:
                target=updates.stage_unified_release(artifacts,m,manifest_bytes,self.root,git_executable=self.git_executable,git_sha256=self.git_sha256,signature_bytes=signature)
            self._require_permit(permit)
            trusts=state.setdefault('trusted_releases',{})
            if len(trusts)>=128 and version not in trusts:raise ValueError('trusted release journal rotation required')
            trusts[version]=dict(manifest_sha256=digest,signature_sha256=hashlib.sha256(signature).hexdigest(),git_configs={name:updates.sha256_file(target/'modules'/name/'.git/config') for name in m['modules']})
            state.update(sequence=m['sequence'],release_sha256=digest,status='activating',previous=previous,target=version)
            self._save(state);updates.mark_pending(self.root,version)
            try:
                self._require_permit(permit);self.runtime.stop_release()
                self._require_permit(permit);updates.switch_current(self.root,version)
                self._require_permit(permit);self.runtime.start_release(m,target)
                health=self.runtime.health_release(version)
                if health!=dict(release_id=version,release_sha256=digest,ready=True,modules={k:dict(version=v['version'],ready=True) for k,v in m['modules'].items()}):raise ValueError('release-aware six-module health failed')
                self._require_permit(permit)
                updates.clear_pending(self.root);state['status']='healthy';self._save(state)
                return dict(status='healthy',release_sha256=digest,physical_acceptance='NOT_RUN')
            except BaseException as error:
                state['status']='rollback_pending';self._save(state)
                try:
                    self.runtime.stop_release()
                    if previous:
                        previous_root=self.root/'releases'/previous
                        previous_manifest,previous_bytes=self._verify_recovery(previous_root,state)
                        self._require_permit(permit)
                        updates.switch_current(self.root,previous,record_previous=False)
                        self._require_permit(permit)
                        self.runtime.start_release(previous_manifest,previous_root)
                        expected=dict(release_id=previous,release_sha256=hashlib.sha256(previous_bytes).hexdigest(),ready=True,modules={k:dict(version=v['version'],ready=True) for k,v in previous_manifest['modules'].items()})
                        if self.runtime.health_release(previous)!=expected:raise ValueError('rollback readiness failed')
                    else:
                        try:(self.root/'current.version').unlink()
                        except FileNotFoundError:pass
                    updates.clear_pending(self.root);state['status']='rolled_back';self._save(state)
                except BaseException:
                    state['status']='rollback_failed';self._save(state)
                    raise ValueError('activation and rollback failed') from error
                raise ValueError('activation failed; previous pointer restored') from error


class PowerShellCMSVerifier:
    """Bind exact trusted helper/runtime bytes, then reuse existing CMS verifier.

    Pins are supplied by external installation policy, never extracted from the
    candidate release. No shell expansion or execution-policy bypass is used.
    This verifies publisher signature only, not enrollment or physical admission.
    """
    def __init__(self,*,powershell,script,security_module,powershell_sha256,script_sha256,security_module_sha256):
        self.powershell=Path(powershell);self.script=Path(script);self.module=Path(security_module)
        self.pins=((self.powershell,powershell_sha256),(self.script,script_sha256),(self.module,security_module_sha256))
        self.module_pin=security_module_sha256
    def __call__(self,raw,signature,publisher_pin):
        import subprocess
        if os.name!='nt' or type(raw) is not bytes or not 0<len(raw)<=1048576 or type(signature) is not bytes or not 0<len(signature)<=262144:return False
        for path,pin in self.pins:
            if not path.is_absolute() or path.is_symlink() or not path.is_file() or len(pin)!=64 or updates.sha256_file(path)!=pin:return False
        with tempfile.TemporaryDirectory(prefix='mission3-cms-') as temp:
            root=Path(temp);(root/'release.json').write_bytes(raw);(root/'release.p7s').write_bytes(signature)
            result=subprocess.run([str(self.powershell),'-NoLogo','-NoProfile','-NonInteractive','-File',str(self.script),'-Manifest',str(root/'release.json'),'-Signature',str(root/'release.p7s'),'-PublisherSha256',publisher_pin,'-SecurityModule',str(self.module),'-SecurityModuleSha256',self.module_pin],stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=20,check=False)
            return result.returncode==0 and result.stdout.decode('utf-8-sig').strip()=='MISSION3_CMS_PIN_VERIFIED'


def _github_bytes(url,limit):
    """Bounded immutable-release transport; network policy still applies.

    No latest/branch resolution and no redirects outside GitHub release hosts.
    Transport success never substitutes for detached signature or artifact pins.
    """
    import urllib.request,urllib.parse
    class Redirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,req,fp,code,msg,headers,newurl):
            parsed=urllib.parse.urlparse(newurl)
            if parsed.scheme!='https' or parsed.hostname not in ('github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'):raise ValueError('untrusted release redirect')
            return super().redirect_request(req,fp,code,msg,headers,newurl)
    with urllib.request.build_opener(Redirect).open(urllib.request.Request(url,headers={'User-Agent':'Grid-Unified-Release-v3'}),timeout=20) as response:
        data=response.read(limit+1)
        if len(data)>limit:raise ValueError('release transport bound')
        return data


def fetch_github_release(agent,*,repository,release_id,transport=_github_bytes):
    """Stage externally signed exact-tag assets only inside admitted lab roots.

    Existing Grid controller chooses release_id and serial node permit. This
    helper never promotes a tag, enrolls a node or activates downloaded bytes.
    """
    import re
    from unified_system.release_manifest import parse_manifest
    agent._authorize()
    if not re.fullmatch('[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,79}',release_id):raise ValueError('immutable release coordinates')
    base='https://github.com/'+repository+'/releases/download/'+release_id+'/'
    raw=transport(base+'release.json',1048576);signature=transport(base+'release.p7s',262144)
    if agent.verify_signature(raw,signature,agent.publisher_pin) is not True:raise ValueError('untrusted GitHub release signature')
    m=parse_manifest(raw,expected_publisher=agent.publisher_pin)
    if m['release_id']!=release_id:raise ValueError('release tag/content mismatch')
    downloads=agent.root/'downloads';downloads.mkdir(parents=True,exist_ok=True);artifacts={}
    for name,x in m['modules'].items():
        a=x['artifact'];data=transport(base+name+'.zip',a['bytes'])
        if len(data)!=a['bytes'] or hashlib.sha256(data).hexdigest()!=a['sha256']:raise ValueError('release asset digest mismatch')
        path=downloads/(a['sha256']+'.zip')
        if path.exists():
            if updates.sha256_file(path)!=a['sha256']:raise ValueError('corrupted immutable cache')
        else:
            fd,temp=tempfile.mkstemp(prefix='mission3-download-',dir=downloads)
            try:
                with os.fdopen(fd,'wb') as stream:stream.write(data);stream.flush();os.fsync(stream.fileno())
                os.replace(temp,path)
            finally:
                try:Path(temp).unlink()
                except FileNotFoundError:pass
        artifacts[name]=path
    return raw,signature,artifacts
