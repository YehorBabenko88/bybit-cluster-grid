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
    env = dict(os.environ, LS5_EXACT_HEAD=HEAD, GITHUB_SHA="b" * 40, GITHUB_RUN_ID="1", GITHUB_RUN_ATTEMPT="1")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(source), str(tmp_path / "evidence")],
        capture_output=True, text=True, env=env, timeout=10,
    )
    return result


def test_valid_receipt(tmp_path):
    result = invoke(tmp_path, '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="tests.test_receipt" name="ok"/></testsuite>')
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "evidence" / "hashes.json").exists()
    assert (tmp_path / "evidence" / "evidence.jsonl").exists()


@pytest.mark.parametrize("xml", [
    "<testsuite/>",
    "<notjunit><testsuite><testcase classname="tests.test_receipt" name="ok"/></testsuite></notjunit>",
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

def test_pr_merge_sha_is_not_accepted_as_source_head(tmp_path):
    source = tmp_path / "junit.xml"
    source.write_text('<testsuite tests="1"><testcase/></testsuite>', encoding="utf-8")
    env = dict(os.environ, LS5_EXACT_HEAD=HEAD, GITHUB_SHA=HEAD, GITHUB_EVENT_NAME="pull_request")
    result = subprocess.run([sys.executable, str(SCRIPT), str(source), str(tmp_path / "evidence")],
                            capture_output=True, text=True, env=env, timeout=10)
    assert result.returncode != 0

@pytest.mark.parametrize("xml", [
    '<testsuite tests="1">INJECTED<testcase classname="x" name="one"/></testsuite>',
    '<testsuite tests="1"><testcase classname="x" name="one">INJECTED</testcase></testsuite>',
    '<testsuite tests="2"><testcase classname="x" name="one"/>INJECTED<testcase classname="x" name="two"/></testsuite>',
    '<testsuite tests="2"><testcase classname="x" name="one"/><testcase classname="x" name="one"/></testsuite>',
    '<testsuite tests="1"><testcase name="one"/></testsuite>',
])
def test_structural_text_and_duplicate_identity_rejected(tmp_path, xml):
    assert invoke(tmp_path, xml).returncode != 0
