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
    result = invoke(tmp_path, '<testsuite tests="1" failures="0" errors="0" skipped="0"><testcase classname="synthetic" name="ok"/></testsuite>')
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

def test_pr_merge_sha_is_not_accepted_as_source_head(tmp_path):
    source = tmp_path / "junit.xml"
    source.write_text('<testsuite tests="1"><testcase/></testsuite>', encoding="utf-8")
    env = dict(os.environ, LS5_EXACT_HEAD=HEAD, GITHUB_SHA=HEAD, GITHUB_EVENT_NAME="pull_request")
    result = subprocess.run([sys.executable, str(SCRIPT), str(source), str(tmp_path / "evidence")],
                            capture_output=True, text=True, env=env, timeout=10)
    assert result.returncode != 0


@pytest.mark.parametrize("xml", [
    '<testsuite tests="2"><testcase classname="c" name="x"/><testcase classname="c" name="x"/></testsuite>',
    '<testsuite tests="1"><testcase name="x"/></testsuite>',
    '<testsuite tests="1"><testcase classname="c"/></testsuite>',
    '<testsuites>UNTRUSTED<testsuite tests="1"><testcase classname="c" name="x"/></testsuite></testsuites>',
    '<testsuite tests="1">UNTRUSTED<testcase classname="c" name="x"/></testsuite>',
    '<testsuite tests="1"><testcase classname="c" name="x">UNTRUSTED</testcase></testsuite>',
    '<testsuite tests="1"><testcase classname="c" name="x"/>UNTRUSTED</testsuite>',
])
def test_ambiguous_bootstrap_junit_never_creates_pass_receipt(tmp_path, xml):
    assert invoke(tmp_path, xml).returncode != 0
    assert not (tmp_path / "evidence" / "hashes.json").exists()
