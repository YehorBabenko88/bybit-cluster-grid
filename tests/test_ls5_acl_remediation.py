"""Synthetic snapshots only; no host, credentials, ACL or service observations."""
import copy
import pytest
from installer.ls5_acl_remediation import assess, desired_acl, prepare, advance, recover, SYSTEM, ADMINS, USERS


def snapshot():
    roles={'service':SYSTEM,'custodian':ADMINS}
    objects=[]
    for name,profile,path,kind in [
        ('data-root','boundary',r'C:\ProgramData\BybitClusterGrid','directory'),
        ('code-root','boundary',r'C:\Program Files\BybitClusterGrid','directory'),
        ('installer','code',r'C:\ProgramData\BybitClusterGrid\installer','directory'),
        ('runtime','code',r'C:\ProgramData\BybitClusterGrid\runtime','directory'),
        ('secret','secret',r'C:\ProgramData\BybitClusterGrid\.env','file'),
        ('state','data',r'C:\ProgramData\BybitClusterGrid\spool','directory')]:
        objects.append(dict(name=name,path=path,profile=profile,kind=kind,owner=ADMINS,
            protected=True,aces=desired_acl(profile,kind,roles),identity='volume1:'+name,
            links=1,reparse=False,sddl='SYNTHETIC_ORIGINAL_'+name))
    active='9ab1f5b85ec471ea21ec89f1b76740c0b01537b6'
    releases=[active,*[c*40 for c in 'bcdef']]
    paths=[(r'C:\ProgramData\BybitClusterGrid\installer\coordinator-launcher.ps1','file'),
           (r'C:\ProgramData\BybitClusterGrid\runtime\venv','directory'),
           (r'C:\ProgramData\BybitClusterGrid\runtime\venv\Scripts','directory'),
           (r'C:\ProgramData\BybitClusterGrid\runtime\venv\Scripts\python.exe','file'),
           (r'C:\ProgramData\BybitClusterGrid\runtime\venv\Lib','directory'),
           (r'C:\ProgramData\BybitClusterGrid\runtime\venv\Lib\site-packages','directory'),
           (r'C:\Program Files\BybitClusterGrid\current.version','file'),
           (r'C:\Program Files\BybitClusterGrid\releases','directory')]
    for version in releases:
        root=r'C:\Program Files\BybitClusterGrid\releases'+'\\'+version
        paths.extend([(root,'directory'),(root+r'\grid','directory'),(root+r'\grid\coordinator.py','file')])
    paths.extend([(r'C:\ProgramData\BybitClusterGrid'+'\\'+n,'directory') for n in ('logs','backups','deploy','ml-artifacts')])
    for path,kind in paths:
        name='object'+str(len(objects))
        profile='data' if path.rsplit('\\',1)[-1] in ('logs','backups') else 'code'
        objects.append(dict(name=name,path=path,profile=profile,kind=kind,owner=ADMINS,
            protected=True,aces=desired_acl(profile,kind,roles),identity='volume1:'+name,
            links=1,reparse=False,sddl='SYNTHETIC_ORIGINAL_'+name,
            sha256=('f1a1a49c22f71cf5a65beb3d8512c088805c39afc96633d93a852f7a360111f6'
                    if path.endswith('coordinator-launcher.ps1') else '1'*64)))
    return dict(schema=1,run_id='77777777-7777-4777-8777-777777777777',head='a'*40,
        roles=roles,objects=objects,releases=releases,active_version=active,inventory_complete=True,ancestors_verified=True,
        identities_verified=True,source_integrity_verified=True,toolchain_verified=True,
        role_inventory_complete=True,all_releases_verified=True,all_launch_paths_verified=True,
        tasks={n:dict(state='Disabled',enabled=False,principal_sid=SYSTEM,action_verified=True) for n in ('BybitClusterGridAgent','BybitClusterGridCoordinator','BybitClusterGridArchivePipeline')},python_processes=[],
        process_inventory_complete=True,unrelated_resources_unmodified=True)


def test_complete_snapshot_is_model_only():
    r=assess(snapshot())
    assert r['status']=='OFFLINE_MODEL_PASS' and r['host_verified'] is False
    assert r['execute_authorized'] is False and r['cleanup_authorized'] is False


@pytest.mark.parametrize('profile,mask',[('code',2),('code',4),('code',16),('code',256),('code',64),
    ('code',0x40000),('code',0x80000),('secret',0x120089)])
def test_inherited_and_explicit_users_permissions_are_unsafe(profile,mask):
    s=snapshot();o=next(x for x in s['objects'] if x['profile']==profile)
    o['aces'].append(dict(sid=USERS,mask=mask,flags=3,inherited=True,type='allow'))
    assert assess(s)['status']=='FAIL'


@pytest.mark.parametrize('field',['inventory_complete','ancestors_verified','identities_verified',
    'source_integrity_verified','toolchain_verified','role_inventory_complete',
    'all_releases_verified','all_launch_paths_verified','process_inventory_complete'])
@pytest.mark.parametrize('value',[False,None,'true',1])
def test_incomplete_model_is_blocked(field,value):
    s=snapshot();s[field]=value
    assert assess(s)['status']=='BLOCKED'


@pytest.mark.parametrize('fault',['reparse','hardlink','owner','unknown-sid','inheritance','unknown-task',
    'process','parent-system-target','path-alias','path-collision','extra-role','missing-identity'])
def test_unsafe_scope_or_identity(fault):
    s=snapshot();o=s['objects'][2]
    if fault=='reparse':o['reparse']=True
    if fault=='hardlink':s['objects'][4]['links']=2
    if fault=='owner':o['owner']=USERS
    if fault=='unknown-sid':o['aces'][0]['sid']='BUILTIN\\Administrators'
    if fault=='inheritance':o['protected']=False
    if fault=='unknown-task':s['tasks']['BybitClusterGridCoordinator']='Unknown'
    if fault=='process':s['python_processes']=[{'pid':1,'command_line':None}]
    if fault=='parent-system-target':o['path']=r'C:\ProgramData'
    if fault=='path-alias':o['path']=r'C:\ProgramData\BybitClusterGrid\installer.'
    if fault=='path-collision':o['path']=s['objects'][0]['path'].upper()
    if fault=='extra-role':s['roles']['unknown']='S-1-5-21-1-2-3-1005'
    if fault=='missing-identity':o['identity']=None
    assert assess(s)['status'] in ('FAIL','BLOCKED')


def test_pure_transaction_preserves_original_and_is_idempotent():
    s=snapshot();j=prepare(s);assert j['state']=='PREPARED'
    for i in range(len(s['objects'])):j=advance(j,s,i)
    assert j['state']=='COMMITTED_MODEL_ONLY'
    assert j['originals']=={o['identity']:o['sddl'] for o in s['objects']}
    assert advance(j,s,len(s['objects']))==j
    assert j['activation_authorized'] is False


@pytest.mark.parametrize('fault',['identity','sddl','run','head','partial','unknown-journal'])
def test_partial_failure_and_recovery_fail_closed(fault):
    s=snapshot();j=advance(prepare(s),s,0);changed=copy.deepcopy(s)
    if fault=='identity':changed['objects'][1]['identity']='replacement'
    if fault=='sddl':changed['objects'][1]['sddl']='CONCURRENT_CHANGE'
    if fault=='run':changed['run_id']='88888888-8888-4888-8888-888888888888'
    if fault=='head':changed['head']='b'*40
    if fault=='partial':j['state']='INTERRUPTED'
    if fault=='unknown-journal':j['state']='UNKNOWN'
    r=recover(j,changed)
    assert r['status']=='BLOCKED' and r['rollback_authorized'] is False


def test_original_unsafe_acl_is_not_automatically_restored():
    s=snapshot();j=prepare(s)
    r=recover(j,s)
    assert r['status']=='BLOCKED' and r['rollback_authorized'] is False

@pytest.mark.parametrize('suffix',[r'\python.exe',r'\current.version',r'\coordinator.py',r'\.env'])
def test_required_files_cannot_be_disguised_as_directories(suffix):
    s=snapshot()
    for o in s['objects']:
        if o['path'].endswith(suffix):
            o['kind']='directory';o.pop('sha256',None)
            o['aces']=desired_acl(o['profile'],o['kind'],s['roles'])
    assert assess(s)['status']=='BLOCKED'


@pytest.mark.parametrize('fault',['apply','activate','rollback','changes','originals','bool-cursor','state','extra','committed'])
def test_forged_model_journal_is_rejected(fault):
    s=snapshot();j=prepare(s)
    if fault=='apply':j['apply_authorized']=True
    if fault=='activate':j['activation_authorized']=True
    if fault=='rollback':j['rollback_authorized']=True
    if fault=='changes':j['changes'][0]['path']=r'C:\Windows'
    if fault=='originals':j['originals']={}
    if fault=='bool-cursor':j['cursor']=False
    if fault=='state':j['state']='APPLYING_MODEL_ONLY'
    if fault=='extra':j['host_verified']=True
    if fault=='committed':j['state']='COMMITTED_MODEL_ONLY';j['cursor']=len(j['changes']);j['apply_authorized']=True
    with pytest.raises(ValueError):advance(j,s,j['cursor'])

@pytest.mark.parametrize('fault',['required-missing','directory-as-file','profile','hash','unknown-role','ace-mask-bool','ace-flags','ace-type','ace-missing','sddl','links-bool','source-replaced'])
def test_incomplete_or_substituted_snapshot_is_blocked(fault):
    s=snapshot();o=s['objects'][2]
    if fault=='required-missing':s['objects'].pop()
    if fault=='directory-as-file':o['kind']='file';o['sha256']='1'*64;o['aces']=desired_acl(o['profile'],'file',s['roles'])
    if fault=='profile':o['profile']='data'
    if fault=='hash':next(x for x in s['objects'] if x['path'].endswith('python.exe'))['sha256']='unknown'
    if fault=='unknown-role':s['roles']['service']='unknown'
    if fault=='ace-mask-bool':o['aces'][0]['mask']=True
    if fault=='ace-flags':o['aces'][0]['flags']=32
    if fault=='ace-type':o['aces'][0]['type']='callback'
    if fault=='ace-missing':del o['aces'][0]['inherited']
    if fault=='sddl':o['sddl']=''
    if fault=='links-bool':o['links']=True
    if fault=='source-replaced':next(x for x in s['objects'] if x['path'].endswith('coordinator-launcher.ps1'))['sha256']='0'*64
    assert assess(s)['status']=='BLOCKED'


def test_source_and_model_are_not_mutated():
    s=snapshot();before=copy.deepcopy(s);prepare(s);assess(s)
    assert s==before


@pytest.mark.parametrize('raw',['{"head":"a","head":"b"}','NaN','[]','{"password":"DO_NOT_ECHO"}'])
def test_cli_invalid_input_is_blocked_and_does_not_echo(raw,tmp_path,capsys,monkeypatch):
    from installer.ls5_acl_remediation import main
    p=tmp_path/'snapshot.json';p.write_text(raw)
    monkeypatch.setattr('sys.argv',['model','--snapshot',str(p),'--expected-head','a'*40])
    main();out=capsys.readouterr().out
    assert 'BLOCKED' in out and 'DO_NOT_ECHO' not in out


def test_default_cli_is_non_authorizing(capsys,monkeypatch):
    from installer.ls5_acl_remediation import main
    monkeypatch.setattr('sys.argv',['model']);main()
    assert 'BLOCKED' in capsys.readouterr().out
