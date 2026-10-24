"""Isolated synthetic tests for CI evidence receipt validation."""
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "installer" / "ls5_bootstrap_ci_evidence.py"
HEAD = "a" * 40


def invoke(tmp_path, xml):
    source = tmp_path / "junit.xml"
    source.write_text(xml, encoding="utf-8")
    env = dict(os.environ, GITHUB_SHA=HEAD, GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(source), str(tmp_path / "evidence")],
        capture_output=True, text=True, env=env, timeout=10,
    )
    return result


def test_valid_receipt(tmp_path):
    result = invoke(tmp_path, '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase name="ok"/></testsuite>')
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "evidence" / "hashes.json").exists()
    assert (tmp_path / "evidence" / "evidence.jsonl").exists()


@pytest.mark.parametrize("xml", [
    "<testsuite/>",
    "<notjunit><testsuite><testcase/></testsuite></notjunit>",
    '<testsuite tests="2"><testcase/></testsuite>',
    '<testsuite tests="1" failures="1"><testcase/></testsuite>',
    '<testsuite tests="1" errors="1"><testcase/></testsuite>',
    '<testsuite tests="1" skipped="1"><testcase/></testsuite>',
    '<testsuite tests="1"><testcase><failure/></testcase></testsuite>',
    '<testsuite tests="1"><testcase><skipped/></testcase></testsuite>',
    '<testsuite tests="NaN"><testcase/></testsuite>',
    "<testsuite",
])
def test_bad_receipts_fail_closed(tmp_path, xml):
    assert invoke(tmp_path, xml).returncode != 0
