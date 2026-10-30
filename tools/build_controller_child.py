"""Build the fixed native containment probe on hosted Windows only. No execution."""
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from tools.check_ddl_free_ci import verify_checkout

ROOT=Path(__file__).resolve().parents[1]
SOURCE='installer/native-g1-controller-fixture/FixtureChild.c'


def require(ok):
    if not ok:raise RuntimeError('HOSTED_CONTROLLER_BUILD_REFUSED')


def context(env, platform):
    require(platform=='nt' and env.get('GITHUB_ACTIONS')=='true' and env.get('RUNNER_ENVIRONMENT')=='github-hosted')
    require(env.get('GITHUB_REPOSITORY')=='YehorBabenko88/bybit-cluster-grid' and env.get('GITHUB_JOB')=='controller-fixture')
    require(bool(re.fullmatch('[0-9a-f]{40}',env.get('EXACT_HEAD_SHA',''))))
    for key in ('GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'):
        require(bool(re.fullmatch('[1-9][0-9]{0,19}',env.get(key,''))))


def quoted(path):
    text=str(path)
    require(bool(re.match(r'^[A-Za-z]:\\',text)) and ':' not in text[2:])
    require(len(text)<=32767 and not any(ord(c)<32 or c in '"%!&|<>^*?' for c in text))
    return '"'+text+'"'


def build():
    context(os.environ,os.name)
    head=os.environ['EXACT_HEAD_SHA'];verify_checkout(ROOT,head)
    require(Path(os.environ['GITHUB_WORKSPACE']).resolve()==ROOT)
    vswhere=Path(os.environ['ProgramFiles(x86)'])/'Microsoft Visual Studio/Installer/vswhere.exe'
    quoted(vswhere);quoted(os.environ['RUNNER_TEMP'])
    versions=subprocess.check_output([str(vswhere),'-latest','-products','*','-requires','Microsoft.VisualStudio.Component.VC.Tools.x86.x64','-property','installationPath'],text=True).splitlines()
    require(len(versions)==1)
    vs=Path(versions[0]);vc=vs/'VC/Tools/MSVC'
    candidates=[p for p in vc.iterdir() if p.is_dir() and re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+',p.name)]
    require(bool(candidates))
    selected=max(candidates,key=lambda p:tuple(map(int,p.name.split('.'))))
    compiler=selected/'bin/Hostx64/x64/cl.exe';linker=selected/'bin/Hostx64/x64/link.exe';setup=vs/'Common7/Tools/VsDevCmd.bat'
    for p in (vswhere,compiler,linker,setup):require(p.is_file() and not p.is_symlink())
    own=Path(tempfile.mkdtemp(prefix='controller-child-build-',dir=os.environ['RUNNER_TEMP']))
    source=subprocess.check_output(['git','show',head+':'+SOURCE],cwd=ROOT)
    source_path=own/'FixtureChild.c';source_path.write_bytes(source)
    obj=own/'FixtureChild.obj';output=ROOT/'installer/native-g1-controller-fixture/bin/native-child.exe'
    require(output.parent.is_dir() and not output.exists() and not output.is_symlink())
    commands=[
        '@echo off',
        'call '+quoted(setup)+' -arch=x64 -no_logo',
        'if errorlevel 1 exit /b 1',
        quoted(compiler)+' /nologo /W4 /WX /GS- /Zl /O1 /c '+quoted(source_path)+' /Fo'+quoted(obj),
        'if errorlevel 1 exit /b 1',
        quoted(linker)+' /nologo /ENTRY:FixtureEntry /SUBSYSTEM:WINDOWS,6.02 /NODEFAULTLIB /APPCONTAINER /NXCOMPAT /DYNAMICBASE /MANIFEST:NO /OUT:'+quoted(output)+' '+quoted(obj)+' kernel32.lib',
        'if errorlevel 1 exit /b 1',
        'exit /b 0',
    ]
    script=own/'build.cmd';script.write_text('\r\n'.join(commands)+'\r\n',encoding='ascii')
    native_cmd=Path(os.environ['SystemRoot'])/'System32/cmd.exe'
    subprocess.run([str(native_cmd),'/d','/c',str(script)],cwd=own,check=True)
    require(source_path.read_bytes()==source)
    payload=output.read_bytes();require(2<len(payload)<65536 and payload[:2]==b'MZ')
    h=lambda data:hashlib.sha256(data).hexdigest()
    receipt=dict(schema=1,head=head,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],source_sha256=h(source),compiler_sha256=h(compiler.read_bytes()),linker_sha256=h(linker.read_bytes()),helper_sha256=h(payload),compiler_version=selected.name)
    with (ROOT/'controller-toolchain.json').open('x',encoding='utf-8') as file:json.dump(receipt,file,sort_keys=True)
    verify_checkout(ROOT,head)
    print(json.dumps(dict(status='BUILT_NOT_EXECUTED',head=head,helper_sha256=receipt['helper_sha256'],physical='0/10 NOT_RUN')))


if __name__=='__main__':build()
