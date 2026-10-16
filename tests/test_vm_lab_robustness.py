"""Bounded pure-input robustness tests; no host/native operations."""
import copy
import json
import re
import pytest
from pathlib import Path
from installer.vm_lab_plan import validate_vm_lab_plan, parse_vm_lab_plan


def plan():
    return json.loads((Path(__file__).resolve().parents[1]/'installer/tests/vm-lab-plan.example.json').read_text(encoding='utf-8'))


@pytest.mark.parametrize('raw', ['"\\ud800"', '\ud800', '['*1000+']'*1000,
                                 '{"schema":'+ '9'*5000+'}', '{"schema":1e9999}'],
                         ids=['escaped-surrogate','surrogate','depth','big-int','infinity'])
def test_json_errors_are_fixed_codes(raw):
    with pytest.raises(ValueError, match=r'^VM_[A-Z_]{1,64}$'):
        parse_vm_lab_plan(raw)


@pytest.mark.parametrize('alias', ['-', '.', '_', 'LS005', 'ls-0007.lab', 'ls__05',
                                  'LS5..lab', ' ls5', 'LS５', '127.0.0.1', 'ls5.', 'LS-5', 'LS_7', 'Ls5.FQDN'])
def test_ambiguous_or_protected_aliases_rejected(alias):
    p=plan();p['host']['aliases']=[alias]
    with pytest.raises(ValueError, match=r'^VM_[A-Z_]{1,64}$'):validate_vm_lab_plan(p)


def test_realistic_windows_protected_paths_and_casing():
    p=plan();p['host']['protected_paths']=[r'C:\Program Files\Bybit Grid', r'd:\InstalledGrid']
    p['storage']['root']=p['storage']['root'].replace('D:', 'd:').replace('GridVmLab','gridvmlab')
    assert validate_vm_lab_plan(p)['physical_ready'] is False


@pytest.mark.parametrize('protected', [r'd:\gridvmlab', 'D:\\',
    r'd:\GRIDVMLAB\11111111-1111-4111-8111-111111111111\Disk'])
def test_alias_equivalent_overlaps_block(protected):
    p=plan();p['host']['protected_paths']=[protected]
    with pytest.raises(ValueError):validate_vm_lab_plan(p)


@pytest.mark.parametrize('value', [r'D:\GridVmLab\..\Installed',r'D:\GridVmLab.\child',
    'D:\\GridVmLab \\child',r'D:\GRIDVM~1\child',r'D:\GridVmLab:stream',
    r'\\?\D:\GridVmLab',r'D:\GridVmLab\\child',r'D:/GridVmLab',r'D:\CON.txt'])
def test_ambiguous_paths_rejected(value):
    p=plan();p['host']['protected_paths']=[value]
    with pytest.raises(ValueError):validate_vm_lab_plan(p)


def test_every_nested_field_type_mutation_is_contained():
    base=plan();paths=[]
    def walk(value,path=()):
        paths.append(path)
        if type(value) is dict:
            for k,v in value.items():walk(v,path+(k,))
        elif type(value) is list:
            for i,v in enumerate(value):walk(v,path+(i,))
    walk(base)
    for path in paths:
        for value in (None,True,False,0,1,1.5,'x','😀',[],{},10**100):
            p=copy.deepcopy(base)
            if not path:p=value
            else:
                target=p
                for k in path[:-1]:target=target[k]
                target[path[-1]]=value
            try:r=validate_vm_lab_plan(p)
            except ValueError as exc:assert re.fullmatch('VM_[A-Z_]{1,64}',str(exc))
            else:assert r['status']=='BLOCKED' and not r['readiness_passed']


def test_cyclic_direct_input_is_bounded_rejection():
    p=plan();p['host']['aliases']=[p]
    with pytest.raises(ValueError, match=r'^VM_[A-Z_]{1,64}$'):validate_vm_lab_plan(p)


@pytest.mark.parametrize('raw', ['[]','{"schema":'+ '9'*5000+'}', '"\\ud800"'],ids=['top-array','huge-int','escaped-surrogate-cli'])
def test_cli_rejections_are_sanitized_without_tracebacks(raw):
    import subprocess,sys
    r=subprocess.run([sys.executable,'-B','-m','installer.vm_lab_plan'],input=raw.encode('ascii'),capture_output=True,check=False)
    assert r.returncode==2 and not r.stderr
    report=json.loads(r.stdout)
    assert report['status']=='BLOCKED' and report['execution_authorized'] is False
    assert re.fullmatch('VM_[A-Z_]{1,64}',report['reason'])


def test_quoted_brackets_do_not_consume_depth_budget():
    from installer.vm_lab_json import load
    assert load(json.dumps('['*1000))=='['*1000


def test_alias_inventory_flag_never_authenticates_aliases():
    p=plan();p['host']['aliases']=['DECLARED-ONLY-HOST']
    r=validate_vm_lab_plan(p)
    assert r['inventory_assurance']=='DECLARED_ONLY'
    assert 'HOST_ALIAS_INVENTORY_NOT_ATTESTED' in r['blockers']
