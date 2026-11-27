"""Offline controls for the additive v2 wheel allowlist; no SDK imports."""
import base64
import csv
import hashlib
import io
import runpy
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
verify_wheel=runpy.run_path(str(ROOT/"scripts/check_market_package.py"))["verify_wheel"]
SRC={
    "market_data/__init__.py":b"# exact sealed runtime fixture\n",
    "market_data_v2/__init__.py":b"# exact v2 initializer\n",
    "market_data_v2/qualified_read_contract.py":b"# exact v2 validator\n",
    "market_data_v2/read_api.py":b"# exact v2 read route\n",
    "market_data_v2/qualified_rollup.py":b"# exact bounded v2 rollup\n",
}
PROJECT={
    "name":"market-data","version":"0.2.0.dev0",
    "scripts":{
        "market-data":"market_data.cli:main",
        "market-data-qualified-read-v2":"market_data_v2.read_api:main"
    }
}
TOP=("market_data","market_data_v2")


def make_wheel(path, *, content=None, tops=TOP, scripts=None,
               bad_record=False, duplicate=False):
    content=dict(SRC if content is None else content)
    prefix="market_data-0.2.0.dev0.dist-info/"
    meta={
        prefix+"METADATA":b"Metadata-Version: 2.4\nName: market-data\nVersion: 0.2.0.dev0\n",
        prefix+"WHEEL":b"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        prefix+"top_level.txt":("\n".join(tops)+"\n").encode(),
    }
    entries=PROJECT["scripts"] if scripts is None else scripts
    meta[prefix+"entry_points.txt"]=("[console_scripts]\n"+
        "".join(f"{k} = {v}\n" for k,v in entries.items())).encode()
    archive={**content,**meta}
    records=[]
    for name,data in archive.items():
        digest=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()
        records.append([name,"sha256="+digest,str(len(data))])
    if bad_record:
        records[0][1]="sha256=forged"
    records.append([prefix+"RECORD","",""])
    f=io.StringIO()
    csv.writer(f,lineterminator="\n").writerows(records)
    archive[prefix+"RECORD"]=f.getvalue().encode()
    with zipfile.ZipFile(path,"w") as wheel:
        for name,data in archive.items():
            wheel.writestr(name,data)
        if duplicate:
            wheel.writestr("market_data_v2/read_api.py",content["market_data_v2/read_api.py"])


class StrictAdditiveWheelTests(unittest.TestCase):
    def check(self,**kwargs):
        with tempfile.TemporaryDirectory(prefix="inert-market-v2-wheel-") as directory:
            wheel=Path(directory)/"market_data-0.2.0.dev0-py3-none-any.whl"
            make_wheel(wheel,**kwargs)
            return verify_wheel(wheel,SRC,PROJECT,TOP)

    def test_exact_additive_v2_wheel_accepted(self):
        raw=self.check()
        self.assertEqual(set(SRC).issubset(raw),True)
        self.assertEqual(len([k for k in raw if k.startswith("market_data_v2/")]),4)

    def test_extra_unapproved_namespace_member_refused(self):
        payload={**SRC,"market_data_v2/unreviewed_writer.py":b"# forbidden\n"}
        with self.assertRaises(AssertionError):
            self.check(content=payload)

    def test_missing_v2_rollup_refused(self):
        payload=dict(SRC);del payload["market_data_v2/qualified_rollup.py"]
        with self.assertRaises(AssertionError):
            self.check(content=payload)

    def test_changed_v2_rollup_bytes_refused(self):
        payload=dict(SRC);payload["market_data_v2/qualified_rollup.py"]=b"unsafe rewrite"
        with self.assertRaises(AssertionError):
            self.check(content=payload)

    def test_missing_v2_validator_refused(self):
        payload=dict(SRC);del payload["market_data_v2/qualified_read_contract.py"]
        with self.assertRaises(AssertionError):
            self.check(content=payload)

    def test_changed_v2_route_bytes_refused(self):
        payload=dict(SRC);payload["market_data_v2/read_api.py"]=b"unsafe rewrite"
        with self.assertRaises(AssertionError):
            self.check(content=payload)

    def test_wrong_top_level_owner_refused(self):
        with self.assertRaises(AssertionError):
            self.check(tops=("market_data","grid"))

    def test_missing_protected_entrypoint_refused(self):
        with self.assertRaises(AssertionError):
            self.check(scripts={"market-data":"market_data.cli:main"})

    def test_changed_protected_entrypoint_refused(self):
        with self.assertRaises(AssertionError):
            self.check(scripts={"market-data":"market_data.cli:main",
                                "market-data-qualified-read-v2":"grid.untrusted:main"})

    def test_bad_record_checksum_refused(self):
        with self.assertRaises(AssertionError):
            self.check(bad_record=True)

    def test_duplicate_zip_member_refused(self):
        with self.assertRaises(AssertionError):
            self.check(duplicate=True)


if __name__=="__main__":
    unittest.main()
