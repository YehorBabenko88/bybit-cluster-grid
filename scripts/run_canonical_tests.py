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
    expected=json.loads((root/'scripts/canonical_test_roster.json').read_text())
    guard=Guard(expected,expected_count=902)
    import market_data,market_math,pytest
    verify(site,bindings,custody)
    with tempfile.TemporaryDirectory(prefix='canonical-data-tests-') as case:
        previous=pathlib.Path.cwd();os.chdir(case)
        try:
            result=pytest.main(['--rootdir',str(root),'--import-mode=importlib','-p','pytest_asyncio.plugin','--confcutdir',str(root/'tests'),str(root/'tests/market_data'),str(root/'tests/marketdata/test_rich_sync.py'),str(root/'tests/marketdata/test_coverage.py'),str(root/'tests/marketdata/test_audit.py'),str(root/'tests/marketdata/test_history_plan.py'),str(root/'tests/marketdata/test_readiness.py::test_requirements_skip_explicitly_unsupported_optional_datasets'),str(root/'tests/marketdata/test_readiness.py::test_supported_optional_datasets_remain_required'),str(root/'tests/marketdata/test_readiness.py::test_requirements_stop_at_delisting_boundary'),str(root/'tests/marketdata/test_readiness.py::test_requirements_empty_before_instrument_launch'),str(root/'tests/marketdata/test_readiness.py::test_zero_delivery_time_does_not_truncate_perpetual_instrument'),str(root/'tests/marketdata/test_readiness.py::test_dataset_windows_align_to_their_own_sampling_grid'),str(root/'tests/marketdata/test_readiness.py::test_open_market_store_refuses_creation_without_existing_history'),str(root/'tests/marketdata/test_readiness.py::test_existing_candles_not_promoted_to_source_attested'),str(root/'tests/marketdata/test_readiness.py::test_frozen_empty_history_inspection_is_unqualified_without_fetch_or_mutation'),str(root/'tests/unmigrated_market_data/test_source_provenance.py::test_event_time_ohlc_duplicate_and_late_trades'),str(root/'tests/unmigrated_market_data/test_source_provenance.py::test_actual_builder_decimal_tick_rounding_retains_integrity'),'-p','no:cacheprovider','-q'],plugins=[guard])
            verify(site,bindings,custody)
            accepted=int(result)==0 and guard.accepted
            output.write_text(json.dumps({'status':'PASS_SCOPED' if accepted else 'FAIL','cases':902,'source_head':head,'scope':'SYNTHETIC_FIXTURES_ONLY','native':'NOT_RUN','release_status':'NO_GO','errors':guard.errors},indent=2)+'\n')
            return 0 if accepted else 1
        finally:os.chdir(previous)

if __name__=='__main__':raise SystemExit(main())
