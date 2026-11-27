"""Legacy B9e0 and B28 candidate exact installed wheel source diagnostics.

This executes a genuine pip --target installation of the built Grid market-data
wheel. The result is diagnostic source and installed-byte evidence only; it
does NOT authenticate the release, bind an immutable protected install root,
or mint E's Root operation permit.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import zipfile


LAB = {
    "grid/__init__.py": "3dc1f76bc69e3f559bee6253b24fc93acee9e1f9",
    "grid/canonical_lab_continuous_collector.py": "873e83839bee9ceb1cca710a5291ba2cf5f7f038",
    "grid/c_lab_journal_adapter.py": "ab93c6d421c3d3f0232060f6ded7ac01bf8eeda0",
    "grid/canonical_lab_fenced_writer.py": "247d7fab2738e1892a05979e407f637f9df62784",
    "grid/c_async_fenced_writer.py": "35bf202bb1674238d53b74f962af966d2a699fa2",
}
# Preserve original B9e0 custody while independently admitting ONLY the
# explicit source-reviewed original B writer candidate; this is not a
# protected issuer or a general permission to use any later writer blob.
B28_WRITER_BLOB = "747941f609b5f877f7f794a770b465e7b6a41f6c"
V2_BASE = (
    "market_data_v2/__init__.py",
    "market_data_v2/qualified_read_contract.py",
    "market_data_v2/read_api.py",
)
V2_ROLLUP = "market_data_v2/qualified_rollup.py"

MODULES = (
    "grid",
    "grid.canonical_lab_continuous_collector",
    "grid.c_lab_journal_adapter",
    "grid.canonical_lab_fenced_writer",
    "grid.c_async_fenced_writer",
    "market_data",
    "market_data.cli",
    "market_data_v2",
    "market_data_v2.qualified_read_contract",
    "market_data_v2.read_api",
)
SCRIPTS = {
    "market-data": "market_data.cli:main",
    "market-data-qualified-read-v2": "market_data_v2.read_api:main",
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def exact_git_blob(root: Path, name: str) -> bytes:
    committed = subprocess.check_output(
        ["git", "--no-replace-objects", "-C", str(root), "cat-file",
         "blob", "HEAD:" + name])
    work = (root / name).read_bytes()
    # Git checkout on Windows may convert LF to CRLF; only normalized exact
    # committed bytes are permitted, and test artifact always uses Git bytes.
    assert work == committed or (
        work.replace(b"\r\n", b"\n") == committed
        and b"\r" not in work.replace(b"\r\n", b"")
    ), "source does not match committed B cohort: " + name
    return committed


def inspect(root: Path, wheel: Path, sdist: Path, math_wheel: Path, ftool: Path):
    assert run("git", "-C", str(root), "rev-parse", "HEAD") == os.environ["MARKET_DATA_TEST_SHA"]
    # Strict two-member cohort: legacy EXACT B9e0 writer or reviewed B302
    # writer. All four other pinned LAB modules remain raw-byte identical.
    actual_writer=run("git","-C",str(root),"rev-parse","HEAD:grid/canonical_lab_fenced_writer.py")
    if actual_writer == LAB["grid/canonical_lab_fenced_writer.py"]:
        cohort="ORIGINAL_B9E0"
    elif actual_writer == B28_WRITER_BLOB:
        cohort="REVIEWED_B302_SOURCE_CANDIDATE"
    else:
        raise AssertionError("UNAPPROVED_CANONICAL_LAB_WRITER_BLOB")
    observed_v2={p.relative_to(root).as_posix() for p in (root/"market_data_v2").iterdir()}
    if cohort == "ORIGINAL_B9E0":
        v2_names=V2_BASE
    elif observed_v2==set(V2_BASE):
        # B302 source-only session correction before optional MTF cutover.
        cohort="REVIEWED_B302_SOURCE_CANDIDATE"
        v2_names=V2_BASE
    else:
        cohort="REVIEWED_B28_MTF_SOURCE_CANDIDATE"
        v2_names=V2_BASE+(V2_ROLLUP,)
    assert observed_v2==set(v2_names), ("UNAPPROVED_V2_RUNTIME_MEMBER",observed_v2)
    for name in v2_names:
        path=root/name
        assert path.is_file() and not path.is_symlink(), "V2_RUNTIME_NONREGULAR_SOURCE"
    committed={name:exact_git_blob(root,name) for name in (*LAB,*v2_names)}
    for name, blob in LAB.items():
        expected=B28_WRITER_BLOB if name=="grid/canonical_lab_fenced_writer.py" and cohort!="ORIGINAL_B9E0" else blob
        assert run("git","-C",str(root),"rev-parse","HEAD:"+name)==expected, (
            "PINNED_CANONICAL_LAB_RUNTIME_CHANGED",name)

    wb = wheel.read_bytes()
    sb = sdist.read_bytes()
    # A single immutable byte snapshot is hashed and parsed; never reopen
    # the wheel path to parse different bytes.
    with zipfile.ZipFile(io.BytesIO(wb)) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names))
        contents = {name: archive.read(name) for name in names}
        members = {name for name in names if name.startswith("grid/")}
        assert members == set(LAB), ("LEGACY_GRID_WHEEL_LEAK", members)
        for name, data in committed.items():
            assert contents[name] == data, ("GIT_WHEEL_BYTES_MISMATCH", name)
        meta = [name for name in names if name.endswith(".dist-info/METADATA")]
        assert len(meta) == 1 and b"Name: market-data\n" in contents[meta[0]]
        assert b"Version: 0.2.0.dev0\n" in contents[meta[0]]
        ep = [name for name in names if name.endswith(".dist-info/entry_points.txt")]
        assert len(ep) == 1
        from configparser import ConfigParser
        cp = ConfigParser(interpolation=None)
        cp.optionxform = str
        cp.read_string(contents[ep[0]].decode())
        assert dict(cp.items("console_scripts")) == SCRIPTS
        assert b"Requires-Dist: aiohttp" in contents[meta[0]]
        assert b"Requires-Dist: psycopg" in contents[meta[0]]
        assert b"Requires-Dist: websockets" in contents[meta[0]]
    with tarfile.open(fileobj=io.BytesIO(sb), mode="r:gz") as archive:
        entries = {m.name: m for m in archive.getmembers()}
        grid_names = {n.rsplit("/grid/", 1)[1] for n in entries if "/grid/" in n}
        assert grid_names == {name.removeprefix("grid/") for name in LAB}, (
            "LEGACY_GRID_SDIST_LEAK", grid_names
        )
        for name, data in committed.items():
            present = [m for n, m in entries.items() if n.endswith("/" + name)]
            assert len(present) == 1 and present[0].isfile()
            assert archive.extractfile(present[0]).read() == data

    with tempfile.TemporaryDirectory(prefix="b19-installed-", dir=os.environ.get("RUNNER_TEMP")) as tmp:
        install = Path(tmp, "b-wheel")
        math_install = Path(tmp, "math")
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--no-deps",
                        "--no-compile", "--target", str(math_install),
                        str(math_wheel)], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "--no-index", "--no-deps",
                        "--no-compile", "--target", str(install), str(wheel)], check=True)
        # F's actual qualifier is the single existing offline package checker,
        # not an E protected Root issuance API. It verifies installed RECORD.
        namespace = importlib.util.module_from_spec(
            importlib.util.spec_from_loader("f_source_only", loader=None))
        exec(compile(ftool.read_bytes(), str(ftool), "exec"), namespace.__dict__)
        qualified = namespace.qualify_wheel(
            wheel, install, expected_sha256=digest(wb),
            source_files={name: digest(data) for name, data in committed.items()},
            expected_distribution="market-data",
            expected_version="0.2.0.dev0", expected_entrypoints=SCRIPTS,
        )
        assert qualified["wheel_bytes_match"] is True
        assert qualified["installed_bytes_match"] is True
        assert qualified["installed_record_verified"] is True
        assert qualified["source_bytes_match"] is True
        assert qualified["all_installed_bytes_authenticated"] is False
        # F truthfully refuses authenticated release/import closure.
        assert qualified["unhashed_install_auxiliary_count"] == 0
        assert qualified["writer_admitted"] is False
        assert qualified["release_authenticated"] is False

        # Negative check on the REAL installed B bytes in an OWNED disposable
        # test target: a changed installed writer must fail F's byte qualifier.
        installed_writer = install / "grid/canonical_lab_fenced_writer.py"
        original = installed_writer.read_bytes()
        try:
            installed_writer.write_bytes(original + b"\\n# deliberate disposable corruption\\n")
            try:
                namespace.qualify_wheel(
                    wheel, install, expected_sha256=digest(wb),
                    source_files={name: digest(data) for name, data in committed.items()},
                    expected_distribution="market-data",
                    expected_version="0.2.0.dev0", expected_entrypoints=SCRIPTS,
                )
            except ValueError:
                pass
            else:
                raise AssertionError("MUTATED_INSTALLED_WRITER_ACCEPTED")
        finally:
            installed_writer.write_bytes(original)
        assert installed_writer.read_bytes() == original

        # No historical Grid Python file may appear on the installed target.
        installed_grid = {p.relative_to(install).as_posix()
                          for p in (install / "grid").rglob("*.py")}
        assert installed_grid == set(LAB), ("INSTALLED_GRID_CLOSURE", installed_grid)
        assert not list(install.rglob("*.pyc")), "UNHASHED_BYTECODE_PRESENT"

        # Real imports in a fresh isolated interpreter. Nothing is executed
        # as a service or a writer, and no Root permit is issued.
        probe = """
import importlib, importlib.metadata, pathlib, sys
site=pathlib.Path(sys.argv[1]).resolve()
math_site=pathlib.Path(sys.argv[2]).resolve()
sys.path[:0]=[str(site),str(math_site)]
names=%r
for name in names:
    module=importlib.import_module(name)
    actual=pathlib.Path(module.__spec__.origin).resolve(strict=True)
    expected=site.joinpath(*name.split('.'))
    expected=expected/'__init__.py' if expected.is_dir() else expected.with_suffix('.py')
    assert actual==expected.resolve(strict=True), ('IMPORT_ORIGIN_MISMATCH', name, actual, expected)
    assert module.__spec__.loader is not None
assert importlib.metadata.version('market-data')=='0.2.0.dev0'
from market_data.cli import main as cli
from market_data_v2.read_api import main as qualified_entry
assert callable(cli) and callable(qualified_entry)
print('B19_REAL_INSTALLED_IMPORTS=PASS;ROOT_ADMISSION=DENIED')
""" % (MODULES+("market_data_v2.qualified_rollup",) if V2_ROLLUP in v2_names else MODULES,)
        subprocess.run([sys.executable, "-I", "-B", "-c", probe,
                        str(install), str(math_install)],
                       cwd=tmp, check=True, env={
                           **os.environ, "PYTHONDONTWRITEBYTECODE": "1",
                       })
        return {
            "source_head": os.environ["MARKET_DATA_TEST_SHA"],
            "source_cohort": cohort,
            "qualified_v2_runtime_count": len(v2_names),
            "b9e0_runtime_blobs": LAB,
            "effective_lab_blobs": {name:(B28_WRITER_BLOB if name=="grid/canonical_lab_fenced_writer.py" and cohort!="ORIGINAL_B9E0" else sha) for name,sha in LAB.items()},
            "wheel_sha256": digest(wb),
            "sdist_sha256": digest(sb),
            "source_sha256": {n: digest(data) for n, data in committed.items()},
            "installed_record_verified": True,
            "installed_source_bytes_verified": True,
            "runtime_import_origin_checked": True,
            "entrypoint_metadata_checked": True,
            "release_authenticated": False,
            "protected_root_admitted": False,
            "operation_permit_issued": False,
            "native_postgres18_executed": False,
        }


def main():
    parser = argparse.ArgumentParser()
    for name in ("root", "wheel", "sdist", "math-wheel", "f-tool", "output"):
        parser.add_argument("--" + name, required=True)
    args = parser.parse_args()
    output = Path(args.output)
    assert not output.exists(), "only fresh evidence can be written"
    proof = inspect(Path(args.root).resolve(), Path(args.wheel).resolve(),
                    Path(args.sdist).resolve(), Path(args.math_wheel).resolve(),
                    Path(args.f_tool).resolve())
    output.write_text(json.dumps(proof, indent=2, sort_keys=True) + "\n")
    print(json.dumps(proof, sort_keys=True))


if __name__ == "__main__":
    main()
