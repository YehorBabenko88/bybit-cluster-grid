"""Owned module health uses real HTTP, source Git metadata and live readiness."""
import asyncio
import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import httpx
import pytest

PATH = '/internal/v2/module/health'
TOKEN = 'a' * 64
ENV = ('UNIFIED_MODULE_ID', 'UNIFIED_MODULE_VERSION', 'UNIFIED_RELEASE_ID',
       'UNIFIED_INSTANCE_TOKEN', 'UNIFIED_SOURCE_COMMIT')


class Pool:
    def __init__(self): self.calls = []
    async def fetchval(self, query):
        self.calls.append(query)
        return 1


@pytest.fixture
def module(monkeypatch, tmp_path):
    from grid import coordinator
    root = tmp_path / 'source'
    root.mkdir()
    def git(*args):
        clean_env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        return subprocess.check_output(['git', '-c', 'core.fsmonitor=false', '-c', 'core.hooksPath=' + os.devnull,
            '-C', str(root), *args], env=clean_env, text=True).strip()
    git('init', '-q')
    git('config', 'core.autocrlf', 'false')
    (root / 'owner.py').write_bytes(b'OWNER = "grid"\n')
    git('add', '.')
    git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'owned source')
    head = git('rev-parse', 'HEAD')
    for key in ENV: monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(coordinator, '_MODULE_SOURCE_ROOT', root, raising=False)
    monkeypatch.setattr(coordinator, '_owned_module_binding', None, raising=False)
    monkeypatch.setattr(coordinator, 'db', SimpleNamespace(pool=Pool()))
    monkeypatch.setattr(coordinator, 'control_leader', None)
    monkeypatch.setattr(coordinator, 'settings', SimpleNamespace(grid_coordination_mode='legacy', grid_ha_required=False))
    return coordinator, root, head


def profile(monkeypatch, head):
    for key, value in zip(ENV, ('grid', '1.2.3', 'release-1.2.3', TOKEN, head)):
        monkeypatch.setenv(key, value)


async def request(coordinator, *, suffix='', headers=None):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=coordinator.app), base_url='http://owned-test') as client:
        return await client.get(PATH + suffix, headers=headers if headers is not None else {'Authorization': 'Bearer ' + TOKEN})


def test_unowned_default_is_503_without_database_probe(module):
    coordinator, _, _ = module
    response = asyncio.run(request(coordinator))
    assert response.status_code == 503
    assert coordinator.db.pool.calls == []
    assert TOKEN not in response.text


def test_real_git_bound_identity_and_sql_probe_return_exact_five_fields(module, monkeypatch):
    coordinator, _, head = module
    async def scenario():
        profile(monkeypatch, head)
        await coordinator._initialize_owned_module_health()
        response = await request(coordinator)
        assert response.status_code == 200
        assert response.json() == {'module_id': 'grid', 'version': '1.2.3', 'release_id': 'release-1.2.3',
                                   'instance_token': TOKEN, 'ready': True}
        assert response.headers['cache-control'] == 'no-store'
        assert coordinator.db.pool.calls == ['SELECT 1']
    asyncio.run(scenario())


@pytest.mark.parametrize('headers', [[], [('Authorization', 'Bearer ' + 'b' * 64)],
    [('Authorization', 'bearer ' + TOKEN)], [('Authorization', 'Bearer ' + TOKEN + ' ')],
    [('Authorization', 'Bearer ' + TOKEN), ('Authorization', 'Bearer ' + TOKEN)]])
def test_authentication_requires_one_exact_bearer(module, monkeypatch, headers):
    coordinator, _, head = module
    async def scenario():
        profile(monkeypatch, head)
        await coordinator._initialize_owned_module_health()
        response = await request(coordinator, headers=headers)
        assert response.status_code == 403
        assert TOKEN not in response.text and coordinator.db.pool.calls == []
    asyncio.run(scenario())


def test_query_is_denied_even_for_an_owned_token(module, monkeypatch):
    coordinator, _, head = module
    async def scenario():
        profile(monkeypatch, head)
        await coordinator._initialize_owned_module_health()
        response = await request(coordinator, suffix='?probe=1')
        assert response.status_code == 400 and TOKEN not in response.text
        assert coordinator.db.pool.calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('key,value', [('UNIFIED_MODULE_ID', 'terminan'), ('UNIFIED_MODULE_VERSION', 'latest'),
    ('UNIFIED_RELEASE_ID', '../forged'), ('UNIFIED_INSTANCE_TOKEN', 'short'), ('UNIFIED_SOURCE_COMMIT', 'not-a-commit')])
def test_malformed_or_changed_identity_is_unavailable(module, monkeypatch, key, value):
    coordinator, _, head = module
    async def scenario():
        profile(monkeypatch, head)
        await coordinator._initialize_owned_module_health()
        monkeypatch.setenv(key, value)
        response = await request(coordinator)
        assert response.status_code == 503 and TOKEN not in response.text
        assert coordinator.db.pool.calls == []
    asyncio.run(scenario())


@pytest.mark.parametrize('kind', ['dirty', 'wrong-pin', 'malformed'])
def test_rejected_owned_startup_has_no_database_side_effects(module, monkeypatch, kind):
    coordinator, root, head = module
    async def scenario():
        profile(monkeypatch, head)
        if kind == 'dirty': (root / 'untracked.py').write_text('untrusted\n')
        elif kind == 'wrong-pin': monkeypatch.setenv('UNIFIED_SOURCE_COMMIT', 'b' * 40)
        else: monkeypatch.setenv('UNIFIED_MODULE_VERSION', 'invalid')
        async def forbidden(): raise AssertionError('database startup must not be reached')
        monkeypatch.setattr(coordinator, 'prepare_database', forbidden)
        with pytest.raises(RuntimeError, match='Owned module'):
            await coordinator.startup()
    asyncio.run(scenario())


@pytest.mark.parametrize('section,key,value', [('core', 'fsmonitor', 'untrusted-command'),
    ('filter "unsafe"', 'clean', 'untrusted-command'), ('include', 'path', 'external-config'),
    ('includeIf "gitdir:*"', 'path', 'external-config'), ('core', 'hooksPath', 'untrusted-hooks')])
def test_unsafe_local_git_configuration_is_rejected_before_status(module, monkeypatch, section, key, value):
    coordinator, root, head = module
    config = root / '.git' / 'config'
    with config.open('a') as stream: stream.write('\n[' + section + ']\n\t' + key + ' = ' + value + '\n')
    async def scenario():
        profile(monkeypatch, head)
        with pytest.raises(RuntimeError, match='Owned module'):
            await coordinator._initialize_owned_module_health()
    asyncio.run(scenario())


def test_trusted_null_attributes_config_is_allowed_and_git_redirects_are_ignored(module, monkeypatch, tmp_path):
    coordinator, root, head = module
    config = root / '.git' / 'config'
    with config.open('a') as stream: stream.write('\n[core]\n\tattributesFile = ' + os.devnull + '\n')
    async def scenario():
        profile(monkeypatch, head)
        monkeypatch.setenv('GIT_DIR', str(tmp_path / 'wrong-git'))
        monkeypatch.setenv('GIT_CONFIG_COUNT', '1')
        monkeypatch.setenv('GIT_CONFIG_KEY_0', 'core.fsmonitor')
        monkeypatch.setenv('GIT_CONFIG_VALUE_0', 'untrusted-command')
        await coordinator._initialize_owned_module_health()
        assert (await request(coordinator)).status_code == 200
    asyncio.run(scenario())


def test_database_failure_and_fence_change_return_503_without_private_logs(module, monkeypatch, caplog):
    coordinator, _, head = module
    async def scenario():
        profile(monkeypatch, head)
        await coordinator._initialize_owned_module_health()
        async def fail(query): raise RuntimeError('postgres://private:secret@example.invalid ' + TOKEN)
        coordinator.db.pool.fetchval = fail
        response = await request(coordinator)
        assert response.status_code == 503 and response.json()['ready'] is False
        assert set(response.json()) == {'module_id', 'version', 'release_id', 'instance_token', 'ready'}
        assert 'private' not in caplog.text and TOKEN not in caplog.text
        leader = SimpleNamespace(requires_fencing=False)
        monkeypatch.setattr(coordinator, 'control_leader', leader)
        async def fenced(query): leader.requires_fencing = True; return 1
        coordinator.db.pool.fetchval = fenced
        assert (await request(coordinator)).json()['ready'] is False
    asyncio.run(scenario())


def test_database_probe_is_bounded(module, monkeypatch):
    coordinator, _, head = module
    async def scenario():
        profile(monkeypatch, head)
        await coordinator._initialize_owned_module_health()
        monkeypatch.setattr(coordinator, '_MODULE_HEALTH_TIMEOUT', .05)
        cancelled = []
        async def slow(query):
            try: await asyncio.sleep(2)
            finally: cancelled.append(True)
        coordinator.db.pool.fetchval = slow
        response = await asyncio.wait_for(request(coordinator), .5)
        assert response.status_code == 503 and response.json()['ready'] is False
        assert cancelled == [True]
    asyncio.run(scenario())


def test_expired_dcs_lease_remains_blocked_by_existing_middleware(module, monkeypatch):
    coordinator, _, head = module
    async def scenario():
        profile(monkeypatch, head)
        await coordinator._initialize_owned_module_health()
        class Expired:
            async def validate(self, lease): return False
        monkeypatch.setattr(coordinator, 'settings', SimpleNamespace(grid_coordination_mode='consul'))
        leader = SimpleNamespace(ready=True, is_leader=True, requires_fencing=False,
            coordination=Expired(), coordination_lease=SimpleNamespace(owner='node-a'), epoch=42,
            node_id='node-a', pool=coordinator.db.pool)
        monkeypatch.setattr(coordinator, 'control_leader', leader)
        response = await request(coordinator)
        assert response.status_code == 503 and TOKEN not in response.text
    asyncio.run(scenario())


@pytest.mark.skipif(not os.environ.get('MISSION3_TEST_DATABASE_URL'), reason='explicit disposable cloud PG fixture not supplied')
def test_actual_disposable_postgres_select_one_health(module, monkeypatch):
    import asyncpg
    coordinator, _, head = module
    async def scenario():
        profile(monkeypatch, head)
        await coordinator._initialize_owned_module_health()
        connection = await asyncpg.connect(os.environ['MISSION3_TEST_DATABASE_URL'], timeout=2)
        try:
            coordinator.db.pool = connection
            response = await request(coordinator)
            assert response.status_code == 200 and response.json()['ready'] is True
        finally: await connection.close()
    asyncio.run(scenario())


def test_actual_capsule_git_configuration_is_accepted(module, monkeypatch):
    from grid.update_manager import capsule_git_config
    coordinator, root, head = module
    (root / '.git' / 'config').write_bytes(capsule_git_config())
    assert coordinator._owned_source_is_clean(head) is True


@pytest.mark.parametrize('flag', ['--assume-unchanged', '--skip-worktree'])
def test_index_flags_cannot_hide_modified_head_blob(module, flag):
    coordinator, root, head = module
    subprocess.check_call(['git', '-C', str(root), 'update-index', flag, 'owner.py'])
    (root / 'owner.py').write_text('OWNER = "forged"\n')
    assert coordinator._owned_source_is_clean(head) is False


@pytest.mark.parametrize('relative', ['objects/info/alternates', 'objects/info/http-alternates', 'info/attributes'])
def test_external_objects_and_local_attributes_are_rejected(module, relative):
    coordinator, root, head = module
    path = root / '.git' / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('/external/objects\n')
    assert coordinator._owned_source_is_clean(head) is False


def test_source_root_symlink_is_not_resolved_into_trust(module, monkeypatch, tmp_path):
    coordinator, root, head = module
    link = tmp_path / 'linked-source'
    try: link.symlink_to(root, target_is_directory=True)
    except OSError: pytest.skip('symlink creation unavailable')
    monkeypatch.setattr(coordinator, '_MODULE_SOURCE_ROOT', link)
    assert coordinator._owned_source_is_clean(head) is False


def test_object_store_cannot_contain_external_symlink(module, tmp_path):
    coordinator, root, head = module
    external = tmp_path / 'external-object'
    external.write_bytes(b'not a trusted object')
    link = root / '.git' / 'objects' / 'unexpected-external'
    try: link.symlink_to(external)
    except OSError: pytest.skip('symlink creation unavailable')
    assert coordinator._owned_source_is_clean(head) is False


def test_exact_owner_exception_is_command_local_and_default_still_rejects_foreign_owner(module,monkeypatch):
 coordinator,root,head=module;original=coordinator.subprocess.Popen;calls=[]
 # Normalize only this disposable fixture to its actual committed raw blob;
 # user Git autocrlf may differ from hosted defaults. Production raw check stays.
 (root/'owner.py').write_bytes(subprocess.check_output(['git','-C',str(root),'show','HEAD:owner.py']))
 clean={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
 clean.update(GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_SYSTEM=os.devnull,GIT_CONFIG_GLOBAL=os.devnull)
 subprocess.check_call(['git','-c','core.autocrlf=false','-C',str(root),'add','owner.py'],env=clean)
 config=(root/'.git/config').read_bytes()
 def foreign_child(command,**kwargs):
  env=dict(kwargs['env']);env['GIT_TEST_ASSUME_DIFFERENT_OWNER']='1';kwargs['env']=env
  calls.append((list(command),dict(env)));return original(command,**kwargs)
 monkeypatch.setattr(coordinator.subprocess,'Popen',foreign_child)
 # Caller Git injection and an environment owner opt-in never authorize scope.
 monkeypatch.setenv('GIT_CONFIG_COUNT','1');monkeypatch.setenv('GIT_CONFIG_KEY_0','safe.directory');monkeypatch.setenv('GIT_CONFIG_VALUE_0','*')
 monkeypatch.setenv('UNIFIED_OWNER_ADMITTED_ROOT',str(root))
 assert coordinator._owned_source_is_clean(head) is False
 assert coordinator._owned_source_is_clean(head,owner_admitted_root=root) is True
 assert (root/'.git/config').read_bytes()==config
 assert not any('GIT_CONFIG_COUNT' in env for _,env in calls)
 admitted=[cmd for cmd,_ in calls if 'safe.directory='+str(root) in cmd]
 assert admitted and all(cmd[cmd.index('safe.directory='+str(root))-1]=='-c' for cmd in admitted)
 assert all('config' not in cmd for cmd,_ in calls)
 (root/'owner.py').write_bytes(b'tampered')
 assert coordinator._owned_source_is_clean(head,owner_admitted_root=root) is False


def test_owner_exception_rejects_parent_wildcard_and_noncanonical_scope_before_git(module,monkeypatch):
 coordinator,root,head=module
 def forbidden(*a,**kw):raise AssertionError('Git called for invalid owner scope')
 monkeypatch.setattr(coordinator.subprocess,'Popen',forbidden)
 for value in (root.parent,str(root)+'/*',str(root)+'/../source'):
  assert coordinator._owned_source_is_clean(head,owner_admitted_root=value) is False
