"""Installed canonical Data test lane; exact roster and approved wheel bytes."""
import argparse,runpy,hashlib,importlib.metadata as metadata,importlib.util,json,os,pathlib,sys,tempfile

CACHE_API=runpy.run_path(str(pathlib.Path(__file__).with_name('sdk_cache_custody.py')))

def verify(site,bindings,custody):
    CACHE_API['verify_sdk_cache'](custody)
    owners={'market_data':'market_data','market_math':'unified-math-kernels','market_compute_api':'unified-math-kernels','history_statistics':'unified-math-kernels'}
    for relative,digest in bindings.items():
        path=site/relative
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=digest:
            raise AssertionError('approved wheel bytes changed: '+relative)
        distribution=metadata.distribution(owners[relative.split('/')[0].removesuffix('.py')])
        files=distribution.files
        members=[] if files is None else [item for item in files if item.as_posix()==relative]
        if len(members)!=1 or pathlib.Path(distribution.locate_file(members[0])).resolve(strict=True)!=path.resolve(strict=True):
            raise AssertionError('wheel file not exactly located by named distribution: '+relative)
    for name,module in tuple(sys.modules.items()):
        if name!='market_data' and not name.startswith('market_data.') and name not in owners:continue
        origin=pathlib.Path(module.__file__).resolve(strict=True)
        if not origin.is_relative_to(site):raise AssertionError('canonical module source fallback: '+name)
        CACHE_API['verify_module_cache'](custody,module,origin)
        relative=origin.relative_to(site).as_posix()
        if relative not in bindings or module.__spec__ is None or pathlib.Path(module.__spec__.origin).resolve(strict=True)!=origin:
            raise AssertionError('unapproved canonical module origin: '+name)
    for retired in ('grid','strattester','meta_analyse','market_profile_math'):
        if importlib.util.find_spec(retired) is not None:raise AssertionError('retired package fallback visible: '+retired)

def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('site','bindings','evidence','cache-root','dependencies'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args(argv);head=os.environ.get('MARKET_DATA_TEST_SHA')
    if type(head) is not str or len(head)!=40 or any(c not in '0123456789abcdef' for c in head):raise ValueError('exact source SHA required')
    root=pathlib.Path(__file__).resolve().parents[1]
    custody=CACHE_API['claim_sdk_cache'](args.cache_root,source_roots=(root,))
    dependencies=pathlib.Path(args.dependencies).resolve(strict=True)
    CACHE_API['_ordinary_directory'](dependencies)
    if dependencies.is_relative_to(root):raise ValueError('external dependency site required')
    site=pathlib.Path(args.site).resolve(strict=True);output=pathlib.Path(args.evidence).absolute()
    if output.exists() or output.resolve().is_relative_to(root):raise ValueError('fresh external evidence required')
    bindings=json.loads(pathlib.Path(args.bindings).read_text())['bindings']
    if len(bindings)!=52:raise ValueError('exact49Data+3Math wheel bindings required')
    Guard=runpy.run_path(str(root/'scripts/canonical_test_gate.py'))['StrictTestRoster']
    sys.path[:0]=[str(site),str(dependencies),str(root/'scripts'),str(root/'tests/market_data'),str(root/'tests/marketdata')]
    os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
    partition=runpy.run_path(str(root/'scripts/check_cross_repo_roster_partition.py'))['validate']()
    expected=partition['grid_nodes']
    guard=Guard(expected,expected_count=884)
    import market_data,market_math,pytest
    verify(site,bindings,custody)
    # Explicit Grid-owned nodes, not a skip/deselect of the canonical roster.
    # The other 18 remain mandatory in the pinned independent source checkout.
    selected=[]
    for node in expected:
        relative,marker=(node.split('::',1)+[''])[:2]
        selected.append(str(root/relative)+('::'+marker if marker else ''))
    with tempfile.TemporaryDirectory(prefix='canonical-data-tests-') as case:
        previous=pathlib.Path.cwd();os.chdir(case)
        try:
            result=pytest.main(['--rootdir',str(root),'--import-mode=importlib',
                '-p','pytest_asyncio.plugin','--confcutdir',str(root/'tests'),
                '-p','no:cacheprovider','-q',*selected],plugins=[guard])
            verify(site,bindings,custody)
            accepted=int(result)==0 and guard.accepted
            output.write_text(json.dumps({'status':'PASS_SCOPED' if accepted else 'FAIL',
                'cases':884,'other_repository_custody_required':18,'total_required':902,
                'source_head':head,'source_custody_sha':partition['source_sha'],
                'scope':'SYNTHETIC_FIXTURES_ONLY','native':'NOT_RUN',
                'release_status':'NO_GO','errors':guard.errors},indent=2)+'\n')
            return 0 if accepted else 1
        finally:os.chdir(previous)

if __name__=='__main__':raise SystemExit(main())
