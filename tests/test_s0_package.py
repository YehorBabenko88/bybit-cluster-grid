from pathlib import Path
import hashlib
import unittest
import tempfile
import os
import copy
from tools import build_s0_package as package


class PackageTests(unittest.TestCase):
    def test_manifest_rejects_boolean_schema_numeric_authority_and_bad_context(self):
        files = {'runtime/App/s0.py': b'fixture'}
        manifest = package.make_manifest(files, head='a'*40, tree='b'*40, run_id='12', attempt='1', python='3.12.9', source={'s0_smoke/cli.py':'c'*64})
        mutations = [('schema', True), ('head', 'A'*40), ('tree', 'x'), ('run_id', '0'), ('attempt', True), ('python', '3.13.1'), ('extra', 'unreviewed')]
        for key, value in mutations:
            changed = copy.deepcopy(manifest); changed[key] = value
            with self.assertRaises(ValueError): package.validate_manifest(files, changed)
        for key in manifest['authority']:
            changed = copy.deepcopy(manifest); changed['authority'][key] = 0
            with self.assertRaises(ValueError): package.validate_manifest(files, changed)
        changed = copy.deepcopy(manifest); changed['files']['runtime/App/s0.py']['size'] = True
        with self.assertRaises(ValueError): package.validate_manifest(files, changed)

    def test_member_count_and_individual_size_bound(self):
        class LargeFixture:
            def __len__(self): return 64*1024*1024+1
        with self.assertRaises(ValueError): package.validate_members({'large':LargeFixture()})
        with self.assertRaises(ValueError): package.validate_members({str(i):b'' for i in range(20001)})

    def test_host_guard_requires_exact_hosted_windows_context(self):
        good = dict(GITHUB_ACTIONS='true', RUNNER_ENVIRONMENT='github-hosted', RUNNER_OS='Windows', GITHUB_REPOSITORY='YehorBabenko88/bybit-cluster-grid', GITHUB_JOB='s0-windows')
        package.require_hosted(good, 'fv-az123')
        for key in good:
            bad = dict(good); bad[key] = 'wrong'
            with self.assertRaises(ValueError): package.require_hosted(bad, 'fv-az123')
        for hostname in ('LS5', 'PC4', 'ls5.example'):
            with self.assertRaises(ValueError): package.require_hosted(good, hostname)
    
    
    def test_archive_names_reject_traversal_devices_collision_and_limit(self):
        for name in ('../a', 'C:/a', 'a\\b', '/a', 'a/CON.txt', 'a/../b', 'a./b'):
            with self.assertRaises(ValueError): package.validate_members({name: b'x'})
        with self.assertRaises(ValueError): package.validate_members({'A':b'a','a':b'b'})
        with self.assertRaises(ValueError): package.validate_members({'a':b'xx'}, limit=1)
    
    
    def test_deterministic_zip_and_manifest_detect_mutation(self):
        files = {'runtime/App/s0.py': b'print(1)', 'runtime/python.exe':b'fixture'}
        manifest = package.make_manifest(files, head='a'*40, tree='b'*40, run_id='12', attempt='1', python='3.12.9', source={'s0_smoke/cli.py':'c'*64})
        assert manifest['authority'] == dict(s0_execute=False,g1_execute=False,cleanup=False)
        assert manifest['files']['runtime/App/s0.py']['sha256'] == hashlib.sha256(b'print(1)').hexdigest()
        assert package.archive_bytes(files,manifest) == package.archive_bytes(dict(reversed(list(files.items()))),manifest)
        package.validate_manifest(files,manifest)
        files['runtime/App/s0.py'] = b'changed'
        with self.assertRaises(ValueError): package.validate_manifest(files,manifest)
    
    
    def test_dependency_paths_exclude_hooks_scripts_and_require_closure(self):
        assert package.safe_distribution_member('aiohttp/client.py')
        assert package.safe_distribution_member('cryptography/hazmat/bindings/_rust.pyd')
        for name in ('../Scripts/pip.exe', 'foo.pth', 'foo/__pycache__/a.pyc', 'foo.exe'):
            assert not package.safe_distribution_member(name)
        assert package.DEPENDENCIES == frozenset('aiohttp aiohappyeyeballs aiosignal attrs frozenlist multidict propcache yarl idna cryptography cffi pycparser typing_extensions'.split())
    
    
    def test_dependency_closure_rejects_unreviewed_active_requirement(self):
        package.validate_dependency_closure({'aiohttp': ['aiosignal>=1'], 'aiosignal': []}, parse=lambda r: ('aiosignal', True))
        with self.assertRaises(ValueError):
            package.validate_dependency_closure({'aiohttp': ['asyncpg']}, parse=lambda r: ('asyncpg', True))
        with self.assertRaises(ValueError):
            package.validate_dependency_closure({'aiohttp': ['aiosignal']}, parse=lambda r: ('aiosignal', True))
        package.validate_dependency_closure({'aiohttp': ['asyncpg; extra == "test"']}, parse=lambda r: ('asyncpg', False))

    def test_regular_file_rejects_hardlink_alias(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'fixture.bin'
            path.write_bytes(b'fixture')
            assert package.regular_bytes(path) == b'fixture'
            alias = Path(directory)/'alias.bin'
            os.link(path, alias)
            with self.assertRaises(ValueError): package.regular_bytes(path)

    def test_wrapper_is_thin_explicit_and_plan_precedes_launch(self):
        source=(Path(__file__).parents[1]/'installer/physical-smoke-s0.ps1').read_text()
        assert "[string]$Action = 'Plan'" in source
        assert "'Cleanup'" not in source
        assert source.index("if ($Action -eq 'Plan')") < source.index('[GridS0.ProcessHost]::Run(')
        assert "'-I', '-S', '-B'" in source
        assert 'Invoke-Expression' not in source
        assert '$start.EnvironmentVariables.Clear()' in source
        assert '$start.UseShellExecute = $false' in source
        assert '[System.Reflection.Assembly]::Load($helperBytes)' in source
        assert "GetEntry('s0-package.json')" in source
        assert "'native/S0Launcher.dll'" in source
        assert "$seconds = if ($Action -eq 'Execute') { 300 } else { 60 }" in source
        assert 'S0_NATIVE_TIMEOUT_OWN_JOB_CLOSED' in source
        assert '.Kill(' not in source and 'Stop-Process' not in source and 'taskkill' not in source.lower()
        assert '$env:' not in source
        assert 'ConvertTo-S0WindowsArgument' in source

    def test_native_launcher_is_pinned_source_and_required_hosted_build_input(self):
        files={'installer/physical-smoke-s0/S0Launcher.cs':b'fixture','native/S0Launcher.dll':b'fixture'}
        manifest=package.make_manifest(files,head='a'*40,tree='b'*40,run_id='12',attempt='1',python='3.12.9',source={'installer/physical-smoke-s0/S0Launcher.cs':'c'*64})
        package.validate_manifest(files,manifest)
        source=Path(package.__file__).read_text()
        assert "root/'s0-native-build'/'S0Launcher.dll'" in source
    
if __name__ == '__main__': unittest.main()




