"""Negative executable guard bootstrap cache fixture; no native processes."""
import importlib.util,importlib._bootstrap_external,subprocess,tempfile,unittest,os,sys,types
from pathlib import Path
class SourceBootstrapTests(unittest.TestCase):
    def test_checked_helper_bytes_cannot_be_replaced_by_valid_pyc(self):
        root=Path(__file__).resolve().parents[3]
        support=Path(os.environ.get('A2_ASSIGNMENT_TEST_SUPPORT',str(root.parent/'mux-get-raw-be5cb94')))
        raw=(support/'tests/control_mux/source_runner.py').read_bytes()
        with tempfile.TemporaryDirectory(prefix='a2-bootstrap-cache-') as tmp:
            folder=Path(tmp).resolve();self.assertTrue(folder.is_relative_to(Path(tempfile.gettempdir()).resolve()))
            helper=folder/'support/tests/control_mux/source_runner.py';helper.parent.mkdir(parents=True);helper.write_bytes(raw)
            sentinel='A2_MATCHED_HELPER_CACHE_EXECUTED'
            payload=compile('raise RuntimeError('+repr(sentinel)+')',str(helper),'exec')
            cache=Path(importlib.util.cache_from_source(str(helper)));cache.parent.mkdir(parents=True)
            cache.write_bytes(importlib._bootstrap_external._code_to_timestamp_pyc(payload,int(helper.stat().st_mtime),len(raw)))
            spec=importlib.util.spec_from_file_location('positive_matched_cache_control',helper);module=importlib.util.module_from_spec(spec)
            with self.assertRaisesRegex(RuntimeError,sentinel):spec.loader.exec_module(module)
            runner=root/'tests/coordination/assignment_v1/source_runner.py'
            namespace={'__name__':'assignment_bootstrap_test','__file__':str(runner)}
            exec(compile(runner.read_bytes(),str(runner),'exec'),namespace)
            guard=namespace['load_checked_guard'](helper)
            self.assertTrue(callable(guard.source_receipt))
            self.assertEqual(guard.source_receipt.__code__.co_filename,str(helper))
            with self.assertRaises(subprocess.CalledProcessError):guard.source_receipt(folder/'support',namespace['SUPPORT_HEAD'])
if __name__=='__main__':unittest.main()
