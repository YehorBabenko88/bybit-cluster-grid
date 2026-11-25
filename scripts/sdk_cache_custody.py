"""Fresh external bytecode custody for isolated installed-SDK test processes.

The launcher creates only an empty private owner directory. The cache path does
not exist until the child, started with -B -X pycache_prefix=..., claims it.
No subprocess is created by this helper.
"""
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
import importlib.machinery,importlib.util,stat,sys,tempfile

_SDK_MODULES=frozenset(('market_math','market_compute_api','history_statistics'))
_SDK_PREFIXES=('market_data','terminan')

def _ordinary_directory(path):
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode) or path.is_symlink() or getattr(info,'st_file_attributes',0)&1024:
        raise AssertionError('ordinary private cache directory required')
    return info

def _canonical_directory(path):
    """Accept ordinary spelling aliases only after validating BOTH full chains."""
    lexical=Path(path).absolute()
    before=None
    for part in (*reversed(lexical.parents),lexical):before=_ordinary_directory(part)
    canonical=lexical.resolve(strict=True)
    after=None
    for part in (*reversed(canonical.parents),canonical):after=_ordinary_directory(part)
    if (before.st_dev,before.st_ino)!=(after.st_dev,after.st_ino):
        raise AssertionError('cache directory identity changed during canonicalization')
    return canonical


def _external(path,source_roots):
    roots=(Path(__file__).resolve().parents[1],*(Path(p).resolve() for p in source_roots))
    if any(path.is_relative_to(root) for root in roots):raise AssertionError('SDK cache must be external to source checkouts')

@contextmanager
def fresh_sdk_cache(*,source_roots=()):
    """Yield a NONEXISTENT cache path for a new -B -X child interpreter."""
    with tempfile.TemporaryDirectory(prefix='unified-sdk-cache-') as directory:
        owner=_canonical_directory(Path(directory).absolute())
        _external(owner,source_roots)
        cache=owner/'bytecode'
        if cache.exists() or cache.is_symlink():raise AssertionError('cache path was not fresh')
        yield cache

@dataclass(frozen=True)
class SdkCacheCustody:
    path:Path
    identity:tuple

def assert_no_preloaded_sdks():
    for name in tuple(sys.modules):
        if name in _SDK_MODULES or any(name==prefix or name.startswith(prefix+'.') for prefix in _SDK_PREFIXES):
            raise AssertionError('SDK was loaded before fresh cache custody: '+name)

def _startup_cache(path):
    if sys.flags.isolated!=1 or sys.flags.no_site!=1:
        raise AssertionError('startup -I -S isolation required before SDK imports')
    configured=sys._xoptions.get('pycache_prefix')
    if type(configured) is not str or Path(configured).absolute()!=path or sys.pycache_prefix is None or Path(sys.pycache_prefix).absolute()!=path:
        raise AssertionError('fresh SDK cache must be selected with startup -X pycache_prefix')
    if sys.flags.dont_write_bytecode!=1 or sys.dont_write_bytecode is not True:
        raise AssertionError('startup -B write prohibition required; it alone does not forbid reads')

def claim_sdk_cache(path,*,source_roots=()):
    """Refuse existing cache, then exclusively claim the unused startup path."""
    assert_no_preloaded_sdks()
    path=Path(path).absolute();_startup_cache(path);_external(path,source_roots)
    if _canonical_directory(path.parent)!=path.parent:
        raise AssertionError('startup cache must use canonical owner spelling')
    try:path.mkdir(mode=0o700,exist_ok=False)
    except FileExistsError:raise AssertionError('pre-existing SDK cache refused') from None
    if _canonical_directory(path)!=path:raise AssertionError('cache spelling changed')
    info=path.stat()
    return SdkCacheCustody(path,(info.st_dev,info.st_ino))

def verify_sdk_cache(custody):
    path=custody.path;_startup_cache(path)
    if _canonical_directory(path)!=path:raise AssertionError('cache spelling changed')
    info=path.stat()
    if (info.st_dev,info.st_ino)!=custody.identity or any(path.iterdir()):
        raise AssertionError('SDK cache custody changed or contains bytecode')

def verify_module_cache(custody,module,origin):
    verify_sdk_cache(custody)
    expected=Path(importlib.util.cache_from_source(str(origin))).absolute()
    cached=getattr(module,'__cached__',None);spec=getattr(module,'__spec__',None)
    loader=getattr(module,'__loader__',None)
    if (type(cached) is not str or Path(cached).absolute()!=expected
            or not expected.is_relative_to(custody.path)
            or spec is None or type(spec.cached) is not str or Path(spec.cached).absolute()!=expected
            or not isinstance(loader,importlib.machinery.SourceFileLoader)
            or spec.loader is not loader
            or Path(loader.get_filename(module.__name__)).resolve(strict=True)!=origin):
        raise AssertionError('SDK loader/cache is outside fresh startup custody')
    if expected.exists():raise AssertionError('SDK unexpectedly has executable cached bytecode')
