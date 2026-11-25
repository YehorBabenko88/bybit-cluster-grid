"""Hosted installed-consumer check; never imports retired source packages."""
import importlib.metadata as metadata
import importlib.util
import os
import sys
import stat
import hashlib
import runpy
import argparse
import json
from pathlib import Path
import tempfile

CACHE_API=runpy.run_path(str(Path(__file__).resolve().with_name('sdk_cache_custody.py')))

SOURCE_REVISIONS={'unified-terminan':'fc0bed4937ab5dbb039320aae48e49b01b31bb43','unified-math-kernels':'9ed369ddd41ae32c4b3a9434f0b29d6dcf51154f'}
MATH_MODULES=frozenset(('market_math','market_compute_api','history_statistics'))

def load_sdk_manifest(source):
    with (source/'.ci-evidence/sdk-source-manifest.json').open('rb') as handle:raw=handle.read(1048577)
    if len(raw)>1048576:raise AssertionError('SDK manifest byte cap exceeded')
    manifest=json.loads(raw)
    if type(manifest) is not dict or len(manifest)!=3 or set(manifest)!={'schema','sources','modules'} or manifest['schema']!='unified-system.sdk-git-module-bytes.v1' or manifest['sources']!=SOURCE_REVISIONS:
        raise AssertionError('unapproved SDK Git manifest')
    modules=manifest['modules']
    if type(modules) is not dict or not 1<=len(modules)<=128:raise AssertionError('invalid SDK module roster')
    for name,entry in modules.items():
        if type(name) is not str or len(name)>256 or type(entry) is not dict or len(entry)!=3 or set(entry)!={'distribution','relative_path','sha256'}:
            raise AssertionError('invalid SDK module descriptor')
        relative=entry['relative_path'];digest=entry['sha256']
        if type(relative) is not str or len(relative)>512 or not relative.endswith('.py') or any(part in ('','..','.') for part in relative.split('/')) or '\\' in relative or ':' in relative:
            raise AssertionError('invalid SDK relative module path')
        expected_name=relative.removesuffix('.py').replace('/','.')
        if expected_name.endswith('.__init__'):expected_name=expected_name.removesuffix('.__init__')
        expected_distribution='unified-math-kernels' if name in MATH_MODULES else 'unified-terminan' if name=='terminan' or name.startswith('terminan.') else None
        if name!=expected_name or expected_distribution is None or entry['distribution']!=expected_distribution or type(digest) is not str or len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):
            raise AssertionError('SDK name/path/source binding differs')
    return modules

def verify_sdk_modules(source, expected, custody):
    """Local source-byte integrity, not remote source authority or RECORD trust."""
    CACHE_API['verify_sdk_cache'](custody)
    for name,module in tuple(sys.modules.items()):
        if name not in MATH_MODULES and name!='terminan' and not name.startswith('terminan.'):continue
        if name not in expected:raise AssertionError('unapproved imported SDK module: '+name)
        entry=expected[name];distribution=metadata.distribution(entry['distribution'])
        files=getattr(distribution,'files',None)
        if files is None or len(files)>4096:raise AssertionError('SDK distribution has no bounded file ownership roster')
        members=[item for item in files if item.as_posix()==entry['relative_path']]
        if len(members)!=1:raise AssertionError('SDK module is not exactly owned by named distribution')
        declared=Path(distribution.locate_file(members[0])).resolve(strict=True)
        origin=Path(module.__file__).resolve(strict=True)
        spec=getattr(module,'__spec__',None)
        if origin!=declared or spec is None or Path(spec.origin).resolve(strict=True)!=declared or origin.is_relative_to(source):
            raise AssertionError('SDK exact installed path differs')
        CACHE_API['verify_module_cache'](custody,module,origin)
        info=Path(module.__file__).lstat()
        if not stat.S_ISREG(info.st_mode) or getattr(info,'st_file_attributes',0)&1024 or Path(module.__file__).is_symlink() or info.st_size>2097152:
            raise AssertionError('SDK module must be a bounded ordinary file')
        with origin.open('rb') as handle:raw=handle.read(2097153)
        if len(raw)>2097152 or hashlib.sha256(raw).hexdigest()!=entry['sha256']:
            raise AssertionError('SDK module differs from approved Git source bytes')



def main(argv=None):
    source = Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser()
    parser.add_argument("cache_root")
    parser.add_argument("--dependencies",required=True)
    args=parser.parse_args(argv)
    custody=CACHE_API['claim_sdk_cache'](args.cache_root,source_roots=(source,))
    sys.path.insert(0,str(source/'scripts'))
    from canonical_test_gate import StrictTestRoster
    dependencies=Path(args.dependencies).resolve(strict=True)
    CACHE_API['_ordinary_directory'](dependencies)
    if dependencies.is_relative_to(source):raise AssertionError("dependency root must be external to checkout")
    sys.path.insert(0,str(dependencies))
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix="canonical-frozen-consumer-") as temporary:
        os.chdir(temporary)
        try:
            import market_math
            import terminan.research_archive as archive
            import terminan.migration.research_results as migration
            expected_modules=load_sdk_manifest(source)
            verify_sdk_modules(source,expected_modules,custody)
            for name in ("grid","strattester","meta_analyse","market_profile_math"):
                if importlib.util.find_spec(name) is not None:
                    raise AssertionError("retired package fallback is visible: " + name)
            import pytest
            expected=json.loads((source/"scripts/frozen_consumer_roster.json").read_text(encoding="utf-8"))
            guard=StrictTestRoster(expected,expected_count=14)
            result=pytest.main(["--confcutdir",str(source/"integration_tests"),str(source/"integration_tests/test_frozen_results.py"),"-q"],plugins=[guard])
            verify_sdk_modules(source,expected_modules,custody)
            return 0 if int(result)==0 and guard.accepted else 1
        finally:
            os.chdir(previous)

if __name__ == "__main__":
    raise SystemExit(main())
