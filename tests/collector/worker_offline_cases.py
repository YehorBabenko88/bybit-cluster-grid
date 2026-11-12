"""Actual complete Worker source; inert non-ingestion collaborators, no loop."""
import ast
from contextlib import contextmanager
import importlib.util
import json
from pathlib import Path
import sys
import types
import unittest

PROFILE = 'grid.data-only-collector.v1'
ENDPOINT = 'synthetic://bybit/linear'
STAMP = 1794441600000
IDENTITY = dict(exchange='bybit', category='linear', symbol='BTCUSDT', instrument_version='1')


def complete(coro):
    try:
        try:
            coro.send(None)
        except StopIteration as result:
            return result.value
        raise AssertionError('unexpected suspension; no event-loop fallback')
    finally:
        coro.close()


@contextmanager
def actual_worker():
    """Load whole Worker, not AST-copied methods or a replacement Worker."""
    root = Path(__file__).resolve().parents[2] / 'grid'
    package_name = '_a3_collector_grid'
    bindings = {}
    calls = []

    def inert(*args, **kwargs):
        calls.append((args, kwargs))
        return types.SimpleNamespace()

    package = types.ModuleType(package_name)
    package.__path__ = []
    bindings[package_name] = package
    for name in ('aiohttp', 'websockets'):
        bindings[name] = types.ModuleType(name)
    # AST inspects only import declarations to build inert collaborators. Actual
    # Worker source is imported intact; no production function is copied.
    tree = ast.parse((root / 'worker.py').read_text(encoding='utf-8'))
    real = {'models', 'public_trade_validation', 'raw_capture'}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module not in real:
            alias = package_name + '.' + node.module
            module = bindings.setdefault(alias, types.ModuleType(alias))
            for item in node.names:
                setattr(module, item.name, inert)
    bindings[package_name + '.config'].settings = types.SimpleNamespace(
        micro_tape_bucket_ms=250, resource_cpu_limit=75, resource_ram_limit=78,
        resource_disk_free_gb=25, bybit_ws_url=ENDPOINT, cluster_interval_seconds=60,
        heartbeat_seconds=10)
    sentinel = object()
    prior = {name: sys.modules.get(name, sentinel) for name in bindings}
    if any(name.startswith(package_name) and value is not sentinel for name, value in prior.items()):
        raise AssertionError('unexpected private module cache')
    sys.modules.update(bindings)
    loaded = []
    try:
        for leaf in ('models', 'public_trade_validation', 'raw_capture', 'worker'):
            name = package_name + '.' + leaf
            spec = importlib.util.spec_from_file_location(name, root / (leaf + '.py'))
            module = importlib.util.module_from_spec(spec)
            sys.modules[name] = module
            loaded.append(name)
            spec.loader.exec_module(module)
            setattr(package, leaf, module)
        yield package.worker, package.raw_capture, calls
    finally:
        for name in loaded:
            sys.modules.pop(name, None)
        for name, value in prior.items():
            if value is sentinel:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


class WorkerRestrictionTests(unittest.TestCase):
    def test_unknown_profile_rejected_before_collaborators(self):
        with actual_worker() as (module, _, calls):
            with self.assertRaises(ValueError):
                module.Worker(launch_profile='unknown', raw_capture_factory=lambda *_: None)
            self.assertEqual(calls, [])

    def test_data_only_requires_factory_before_collaborators(self):
        with actual_worker() as (module, _, calls):
            with self.assertRaises(ValueError):
                module.Worker(launch_profile=PROFILE)
            self.assertEqual(calls, [])

    def test_research_mixing_rejected_before_collaborators(self):
        with actual_worker() as (module, _, calls):
            with self.assertRaises(ValueError):
                module.Worker(launch_profile=PROFILE, raw_capture_factory=lambda *_: None,
                              data_first_admission=object())
            self.assertEqual(calls, [])

    def test_legacy_default_keeps_factory_and_constructors(self):
        with actual_worker() as (module, _, calls):
            factory = lambda *_: None
            worker = module.Worker(raw_capture_factory=factory)
            self.assertIs(worker.raw_capture_factory, factory)
            self.assertIsNone(worker.launch_profile)
            self.assertGreater(len(calls), 0)

    def test_legacy_globals_resolve_once_and_preserve_patches(self):
        with actual_worker() as (module, _, _):
            settings=module.settings
            created=[]
            def storage():
                created.append('patched')
                return object()
            module.Storage=storage
            module.Worker()
            module.Worker()
            self.assertIs(module.settings,settings)
            self.assertEqual(created,['patched','patched'])

    def test_data_only_run_blocks_before_effects(self):
        with actual_worker() as (module, _, calls):
            factory = lambda *_: None
            worker = module.Worker(launch_profile=PROFILE, raw_capture_factory=factory)
            self.assertIs(worker.raw_capture_factory, factory)
            before = list(calls)
            with self.assertRaisesRegex(RuntimeError, 'COLLECTOR_SOURCE_ADMISSION_REQUIRED'):
                complete(worker.run())
            self.assertEqual(calls, before)

    def test_direct_provider_and_heartbeat_entrypoints_block(self):
        with actual_worker() as (module, _, calls):
            worker = module.Worker(launch_profile=PROFILE, raw_capture_factory=lambda *_: None)
            before = list(calls)
            for coro in (worker.heartbeat(), worker.trade_stream('BTCUSDT'), worker.reconcile()):
                with self.assertRaisesRegex(RuntimeError, 'COLLECTOR_SOURCE_ADMISSION_REQUIRED'):
                    complete(coro)
            worker._start_data_first_consumer()
            self.assertIsNone(worker.data_first_task)
            self.assertEqual(calls, before)

    def test_offline_rejects_unbounded_or_network_input_before_factory(self):
        with actual_worker() as (module, _, _):
            factories = []
            worker = module.Worker(launch_profile=PROFILE,
                                  raw_capture_factory=lambda *args: factories.append(args))
            for frames, endpoint in (([], ENDPOINT), ((b'{}',) * 5, ENDPOINT),
                                     ((b'{}',), 'wss://stream.bybit.com/v5/public/linear')):
                with self.assertRaises(ValueError):
                    complete(worker.receive_offline(frames, symbol='BTCUSDT', endpoint=endpoint,
                                                    observed_at_ms=STAMP))
            self.assertEqual(factories, [])

    def test_full_worker_cannot_use_offline_route(self):
        with actual_worker() as (module, _, _):
            worker = module.Worker(raw_capture_factory=lambda *_: None)
            with self.assertRaisesRegex(RuntimeError, 'COLLECTOR_OFFLINE_PROFILE_REQUIRED'):
                complete(worker.receive_offline((b'{}',), symbol='BTCUSDT', endpoint=ENDPOINT,
                                                observed_at_ms=STAMP))
