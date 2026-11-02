"""Externally pinned installer bytes must survive an actual Windows checkout."""
import subprocess
import tempfile
import unittest
from pathlib import Path


class PinnedCheckoutTests(unittest.TestCase):
    def test_autocrlf_preserves_native_installer_inputs(self):
        source=Path(__file__).resolve().parents[1]
        names=('.gitattributes','installer/PortableRuntime.psm1','installer/NativeJobProcess.cs')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            def git(*args):
                return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.PIPE)
            git('init','-q');git('config','core.autocrlf','true')
            expected={}
            for name in names:
                raw=subprocess.check_output(['git','-C',str(source),'show','HEAD:'+name])
                if name=='.gitattributes':raw=(source/name).read_bytes()
                expected[name]=raw
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
            git('add',*names)
            git('-c','user.name=Checkout Test','-c','user.email=checkout@example.invalid','commit','-qm','fixture')
            for name in names:(root/name).unlink()
            git('checkout','HEAD','--',*names)
            for name in names:
                with self.subTest(path=name):self.assertEqual((root/name).read_bytes(),expected[name])


if __name__=='__main__':unittest.main()
