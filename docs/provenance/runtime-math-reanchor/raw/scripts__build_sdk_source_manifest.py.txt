"""Hosted CI: bind installed SDK module bytes to exact approved Git blobs."""
from pathlib import Path
import hashlib,json,subprocess,sys

SOURCES={'unified-terminan':'fc0bed4937ab5dbb039320aae48e49b01b31bb43','unified-math-kernels':'9ed369ddd41ae32c4b3a9434f0b29d6dcf51154f'}

def build_manifest(terminan,math):
    modules={}
    for distribution,root in (('unified-terminan',Path(terminan)),('unified-math-kernels',Path(math))):
        revision=SOURCES[distribution]
        def git(*args):return subprocess.check_output(['git','--no-replace-objects',*args],cwd=root)
        if git('rev-parse','HEAD').decode('ascii').strip()!=revision:raise ValueError('unapproved SDK source revision')
        names=(git('ls-tree','-r','--name-only',revision,'terminan').decode('utf-8').splitlines()
               if distribution=='unified-terminan' else ['python/market_math.py','python/market_compute_api.py','python/history_statistics.py'])
        for name in names:
            if not name.endswith('.py'):continue
            relative=name if distribution=='unified-terminan' else name.removeprefix('python/')
            module=relative.removesuffix('.py').replace('/','.')
            if module.endswith('.__init__'):module=module.removesuffix('.__init__')
            if module in modules:raise ValueError('duplicate SDK module')
            raw=git('cat-file','blob',revision+':'+name)
            modules[module]={'distribution':distribution,'relative_path':relative,'sha256':hashlib.sha256(raw).hexdigest()}
    return {'schema':'unified-system.sdk-git-module-bytes.v1','sources':SOURCES,'modules':modules}

if __name__=='__main__':
    result=build_manifest(sys.argv[1],sys.argv[2]);target=Path(sys.argv[3]);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n',encoding='utf-8')
