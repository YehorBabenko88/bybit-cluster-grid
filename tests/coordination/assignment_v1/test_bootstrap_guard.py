"""Negative executable guard bootstrap cache fixture; no native processes."""
import importlib.util,importlib._bootstrap_external,subprocess,tempfile,unittest,os,sys
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
            head=subprocess.check_output(['git','--no-replace-objects','-C',str(root),'rev-parse','HEAD']).decode().strip()
            result=subprocess.run([sys.executable,'-I','-B',str(root/'tests/coordination/assignment_v1/source_runner.py'),'--expected-head',head,'--support-source',str(folder/'support'),'--binary',str(folder/'not-used.exe'),'--scratch',str(folder/'not-used-data'),'--output',str(folder/'evidence')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
            output=result.stdout.decode(errors='replace');self.assertNotEqual(result.returncode,0)
            self.assertNotIn(sentinel,output)
            self.assertTrue(any(text in output for text in ('UNEXPECTED_IMPORTABLE_SOURCE','HEAD_MISMATCH','RAW_SOURCE_MISMATCH:','not a git repository')),output)
if __name__=='__main__':unittest.main()
