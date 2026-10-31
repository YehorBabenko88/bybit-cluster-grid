import copy,hashlib,json,os,pathlib,sys,tempfile,unittest,zipfile,subprocess,shutil
sys.path.insert(0,os.environ.get('UNIFIED_SOURCE_ROOT',str(pathlib.Path(__file__).resolve().parents[2]/'unified-system')))
from grid.deployment_agent import DeploymentAgent,assert_ephemeral_scope
from unified_system.release_manifest import canonical

NAMES=('unified-system','grid','strattester','math','meta_analyse','terminan')

def package(root,release='r1',sequence=1):
    with tempfile.TemporaryDirectory(prefix='mission3-source-') as temp:
        repo=pathlib.Path(temp)/'source';repo.mkdir()
        git=lambda *args:subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.PIPE).decode().strip()
        git('init');(repo/'main.txt').write_text(release)
        git('add','.');git('-c','user.name=Lab','-c','user.email=lab@example.invalid','commit','-m','fixture')
        commit,tree=git('rev-parse','HEAD'),git('rev-parse','HEAD^{tree}')
        bundle=pathlib.Path(temp)/'source.bundle';git('bundle','create',str(bundle),'HEAD')
        modules={}
        for name in NAMES:
            p=root/(name+'.zip')
            with zipfile.ZipFile(p,'w') as z:z.write(bundle,'source.bundle')
            modules[name]=dict(version=str(sequence)+'.0.0',commit=commit,tree=tree,api_major=1,dependencies={},
                artifact=dict(path='modules/'+name+'.zip',sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size),
                provenance=dict(repository='owner/'+name,run_id='123',attempt=1,workflow_sha=commit))
    return canonical(dict(schema='unified.release.v3',release_id=release,sequence=sequence,publisher_sha256='d'*64,modules=modules,execution_authority=False,trading_authorized=False))

class Runtime:
    def __init__(self):self.events=[];self.fail=False
    def stop_release(self):self.events.append('stop')
    def start_release(self,manifest,path):self.manifest=manifest;self.digest=hashlib.sha256((path/'unified-release.json').read_bytes()).hexdigest();self.events.append(('start',path.name))
    def health_release(self,release_id):return None if self.fail and release_id=='r2' else dict(release_id=release_id,release_sha256=self.digest,ready=True,modules={k:dict(version=v['version'],ready=True) for k,v in self.manifest['modules'].items()})

class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='mission3-',dir=os.environ.get('RUNNER_TEMP') if os.name=='nt' else None);self.addCleanup(self.temp.cleanup)
        self.root=pathlib.Path(self.temp.name);self.packages=self.root/'packages';self.packages.mkdir()
        self.runtime=Runtime()
        self.agent=DeploymentAgent(self.root/'node',node_id='lab-node',publisher_pin='d'*64,
            signature_verifier=lambda raw,sig,pin:sig==b'VALID',enrollment_verifier=lambda node,credential:credential=='server-issued',runtime=self.runtime,
            execution_guard=lambda root:assert_ephemeral_scope(root,scope='EPHEMERAL_WINDOWS_CI' if os.name=='nt' else 'CLOUD_LAB',authorization=True),permit_verifier=lambda permit:permit is not None,execution_scope='EPHEMERAL_WINDOWS_CI' if os.name=='nt' else 'CLOUD_LAB',lab_authorized=True,git_executable=pathlib.Path(shutil.which('git')).resolve(),git_sha256=hashlib.sha256(pathlib.Path(shutil.which('git')).resolve().read_bytes()).hexdigest())
    def apply(self,raw):
        m=json.loads(raw)
        permit=dict(node_id='lab-node',version=m['release_id'],manifest_sha256=hashlib.sha256(raw).hexdigest(),status='queued')
        return self.agent.apply(raw,b'VALID',{k:self.packages/(k+'.zip') for k in NAMES},credential='server-issued',permit=permit)
    def test_actual_staging_activation_idempotence_and_persisted_stop_intent(self):
        raw=package(self.packages);self.assertEqual(self.apply(raw)['status'],'healthy')
        self.assertEqual((self.root/'node/current.version').read_text(),'r1')
        self.assertEqual(self.apply(raw)['status'],'already_active')
        self.agent.stop();before=self.runtime.events[:]
        with self.assertRaises(ValueError):self.apply(package(self.packages,'r2',2))
        self.assertEqual(before,self.runtime.events)
        self.assertTrue(json.loads((self.root/'node/deployment-state.json').read_text())['admin_stopped'])
    def test_failed_health_restores_exact_previous_pointer(self):
        self.apply(package(self.packages));self.runtime.fail=True
        with self.assertRaises(ValueError):self.apply(package(self.packages,'r2',2))
        self.assertEqual((self.root/'node/current.version').read_text(),'r1')
        self.assertEqual(json.loads((self.root/'node/deployment-state.json').read_text())['status'],'rolled_back')
        self.assertTrue((self.root/'node/releases/r1/modules/grid/main.txt').exists())
    def test_signature_enrollment_checksum_and_sequence_fail_before_restart(self):
        raw=package(self.packages)
        with self.assertRaises(ValueError):self.agent.apply(raw,b'BAD',{},credential='server-issued')
        with self.assertRaises(ValueError):self.agent.apply(raw,b'VALID',{},credential='client-selected')
        (self.packages/'grid.zip').write_bytes(b'tamper')
        with self.assertRaises(ValueError):self.apply(raw)
        self.assertEqual(self.runtime.events,[])
        self.apply(package(self.packages,'r2',2))
        with self.assertRaises(ValueError):self.apply(package(self.packages,'r1',1))
    def test_windows_office_and_default_external_execution_denied(self):
        for host in ('LS5','PC4','ADMINIT'):
            with self.assertRaises(ValueError):assert_ephemeral_scope(self.root,scope='CLOUD_LAB',authorization=True,hostname=host)
        with self.assertRaises(ValueError):assert_ephemeral_scope(pathlib.Path('/'),scope='CLOUD_LAB',authorization=True)
        with self.assertRaises(ValueError):assert_ephemeral_scope(self.root,scope='PHYSICAL',authorization=True)
    def test_retention_never_removes_data_current_or_recovery(self):
        self.apply(package(self.packages));data=self.root/'node/history';data.mkdir();(data/'unique').write_text('only copy')
        self.agent.uninstall()
        self.assertTrue((data/'unique').exists());self.assertTrue((self.root/'node/releases/r1').exists())

    def test_unsafe_archive_rejected_and_recovery_artifacts_preserved(self):
        raw=package(self.packages);m=json.loads(raw)
        p=self.packages/'grid.zip'
        with zipfile.ZipFile(p,'w') as z:z.writestr('../history/unique','escape')
        m['modules']['grid']['artifact'].update(sha256=hashlib.sha256(p.read_bytes()).hexdigest(),bytes=p.stat().st_size)
        with self.assertRaises(ValueError):self.apply(canonical(m))
        self.assertFalse((self.root/'node/history/unique').exists());self.assertEqual(self.runtime.events,[])
    def test_missing_authenticated_permit_rejected_before_staging(self):
        raw=package(self.packages)
        with self.assertRaises(ValueError):self.agent.apply(raw,b'VALID',{},credential='server-issued')
        self.assertEqual(self.runtime.events,[])

    def test_github_transport_is_signature_first_exact_tag_and_never_activation(self):
        from grid.deployment_agent import fetch_github_release
        raw=package(self.packages);assets={'release.json':raw,'release.p7s':b'VALID'}
        assets.update({name+'.zip':(self.packages/(name+'.zip')).read_bytes() for name in NAMES})
        seen=[]
        def transport(url,limit):
            self.assertTrue(url.startswith('https://github.com/owner/system/releases/download/r1/'))
            seen.append(url);return assets[url.rsplit('/',1)[1]]
        staged=fetch_github_release(self.agent,repository='owner/system',release_id='r1',transport=transport)
        self.assertEqual(staged[0],raw);self.assertEqual(set(staged[2]),set(NAMES));self.assertEqual(self.runtime.events,[])
        assets['release.p7s']=b'BAD';seen.clear()
        with self.assertRaises(ValueError):fetch_github_release(self.agent,repository='owner/system',release_id='r1',transport=transport)
        self.assertEqual(len(seen),2)

    def test_rollback_refuses_tampered_manifest_signature_capsule_and_source(self):
        for fault in ('manifest','signature','source','capsule','git_head'):
            with self.subTest(fault=fault):
                self.setUp()
                self.apply(package(self.packages));previous=self.root/'node/releases/r1'
                if fault=='manifest':
                    raw=json.loads((previous/'unified-release.json').read_bytes());raw['modules']['grid']['version']='9.9.9'
                    (previous/'unified-release.json').write_bytes(canonical(raw))
                elif fault=='signature':(previous/'unified-release.p7s').write_bytes(b'TAMPER')
                elif fault=='source':(previous/'modules/grid/main.txt').write_text('tamper')
                elif fault=='capsule':(previous/'capsules/grid/source.bundle').write_bytes(b'TAMPER')
                else:(previous/'modules/grid/.git/HEAD').write_text('f'*40+'\n')
                self.runtime.fail=True;before=len(self.runtime.events)
                with self.assertRaises(ValueError):self.apply(package(self.packages,'r2',2))
                events=self.runtime.events[before:]
                self.assertNotIn(('start','r1'),events)
                self.assertEqual(json.loads((self.root/'node/deployment-state.json').read_text())['status'],'rollback_failed')
    def test_permit_revoked_while_staging_cannot_stop_or_activate(self):
        from unittest.mock import patch
        from grid import update_manager
        raw=package(self.packages);valid=[True]
        self.agent.verify_permit=lambda permit:valid[0]
        original=update_manager.stage_unified_release
        def revoke(*args,**kw):
            result=original(*args,**kw);valid[0]=False;return result
        with patch.object(update_manager,'stage_unified_release',side_effect=revoke):
            with self.assertRaises(ValueError):self.apply(raw)
        self.assertEqual(self.runtime.events,[])
        self.assertFalse((self.root/'node/current.version').exists())
    def test_linked_deployment_children_cannot_escape_admitted_root(self):
        for child in ('releases','downloads','deployment.lock','deployment-state.json'):
            with self.subTest(child=child):
                self.setUp();node=self.root/'node';node.mkdir();outside=self.root/'outside';outside.mkdir()
                (node/child).symlink_to(outside,target_is_directory=True)
                with self.assertRaises(ValueError):self.apply(package(self.packages))
                self.assertEqual(list(outside.iterdir()),[]);self.assertEqual(self.runtime.events,[])

    def test_revoked_prepared_release_can_retry_only_after_full_revalidation(self):
        from unittest.mock import patch
        from grid import update_manager
        raw=package(self.packages);valid=[True];self.agent.verify_permit=lambda permit:valid[0]
        original=update_manager.stage_unified_release
        def revoke(*args,**kw):
            result=original(*args,**kw);valid[0]=False;return result
        with patch.object(update_manager,'stage_unified_release',side_effect=revoke):
            with self.assertRaises(ValueError):self.apply(raw)
        self.assertEqual(self.runtime.events,[]);valid[0]=True
        self.assertEqual(self.apply(raw)['status'],'healthy')
    def test_poisoned_unregistered_prepared_release_is_never_reused(self):
        from unittest.mock import patch
        from grid import update_manager
        raw=package(self.packages);valid=[True];self.agent.verify_permit=lambda permit:valid[0]
        original=update_manager.stage_unified_release
        def revoke(*args,**kw):
            result=original(*args,**kw);valid[0]=False;return result
        with patch.object(update_manager,'stage_unified_release',side_effect=revoke):
            with self.assertRaises(ValueError):self.apply(raw)
        target=self.root/'node/releases/r1';(target/'modules/grid/main.txt').write_text('tamper')
        valid[0]=True
        with self.assertRaises(ValueError):self.apply(raw)
        self.assertEqual(self.runtime.events,[])
        self.assertTrue((target/'capsules/grid/artifact.zip').exists())

    def test_cached_zero_direntry_link_count_uses_fresh_filesystem_metadata(self):
        import contextlib
        from types import SimpleNamespace
        from unittest.mock import patch
        from grid.deployment_agent import _safe_deployment_tree
        tree=self.root/'tree';tree.mkdir();(tree/'regular').write_text('owned regular file')
        original=os.scandir
        class CachedEntry:
            def __init__(self,entry):self.path=entry.path;self.entry=entry
            def stat(self,*,follow_symlinks=True):
                actual=self.entry.stat(follow_symlinks=follow_symlinks)
                return SimpleNamespace(st_mode=actual.st_mode,st_nlink=0,st_ino=0,st_dev=0,
                    st_file_attributes=getattr(actual,'st_file_attributes',0))
        @contextlib.contextmanager
        def cached(directory):
            with original(directory) as entries:yield (CachedEntry(entry) for entry in entries)
        with patch('grid.deployment_agent.os.scandir',side_effect=cached):
            _safe_deployment_tree(tree)
    def test_actual_hardlinked_deployment_file_is_still_rejected(self):
        from grid.deployment_agent import _safe_deployment_tree
        tree=self.root/'tree';tree.mkdir();source=tree/'regular';source.write_text('owned file')
        os.link(source,tree/'alias')
        self.assertGreater(os.lstat(source).st_nlink,1)
        with self.assertRaisesRegex(ValueError,'ambiguous deployment file'):_safe_deployment_tree(tree)

    def test_fresh_unknown_zero_link_count_is_not_accepted(self):
        from types import SimpleNamespace
        from unittest.mock import patch
        from grid.deployment_agent import _safe_deployment_tree
        tree=self.root/'tree';tree.mkdir();source=tree/'regular';source.write_text('owned file')
        original=os.lstat
        def unknown(path,*args,**kwargs):
            actual=original(path,*args,**kwargs)
            if pathlib.Path(path)==source:
                return SimpleNamespace(st_mode=actual.st_mode,st_nlink=0,
                    st_file_attributes=getattr(actual,'st_file_attributes',0))
            return actual
        with patch('grid.deployment_agent.os.lstat',side_effect=unknown):
            with self.assertRaisesRegex(ValueError,'ambiguous deployment file'):_safe_deployment_tree(tree)
