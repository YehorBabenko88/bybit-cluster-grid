"""Collect the separate hosted bootstrap fixture receipt; never physical acceptance.

Call collect after the existing restricted native fixture child completes. This
module does not launch a process, create a package target, or change an ACL.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
from tools.build_s0_package import require_hosted, NATIVE_SOURCES
from s0_smoke.policy import load_json

CASES = frozenset(('plan_no_write','unapproved_rejected','wrong_sha_rejected',
                  'wrong_sid_rejected','outside_parent_rejected','stage_closure',
                  'existing_target_rejected','concurrent_no_replace','canary_unchanged'))
KEYS = CASES | {'scope','head','package_sha256','status','s0_execute','g1_execute','cleanup'}


def validate(value, head, sha):
    if (type(value) is not dict or set(value) != KEYS or
        re.fullmatch('[0-9a-f]{40}',head) is None or
        re.fullmatch('[0-9a-f]{64}',sha) is None or
        value['head'] != head or value['package_sha256'] != sha or
        value['scope'] != 'HOSTED_BOOTSTRAP_NOT_PHYSICAL' or value['status'] != 'PASS' or
        any(value[k] is not True for k in CASES) or
        any(value[k] is not False for k in ('s0_execute','g1_execute','cleanup'))):
        raise ValueError('S0_BOOTSTRAP_FIXTURE_RECEIPT_BLOCKED')
    return value


def collect(fixture, package_sha, head):
    from tools.check_ddl_free_ci import ROOT, verify_checkout
    require_hosted(os.environ,socket.gethostname())
    verify_checkout(ROOT,head)
    path=Path(fixture)/'temp/bootstrap.json'
    raw=path.read_bytes()
    if not 0 < len(raw) <= 16384:
        raise ValueError('S0_BOOTSTRAP_FIXTURE_RECEIPT_BLOCKED')
    value=validate(load_json(raw),head,package_sha)
    with (ROOT/'s0-results/native-bootstrap-raw.json').open('xb') as stream:
        stream.write(raw)
    sources=(*NATIVE_SOURCES,'installer/physical-smoke-s0-tests/BootstrapTests.cs','installer/physical-smoke-s0-tests/InputTests.cs',
             'tools/verify_s0_bootstrap_ci.py')
    result=dict(value,run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'],
                fixture_sha256=hashlib.sha256(raw).hexdigest(),
                source_sha256={name:hashlib.sha256(subprocess.check_output(
                    ['git','show',head+':'+name],cwd=ROOT)).hexdigest() for name in sources})
    output=ROOT/'s0-results/native-bootstrap.json'
    with output.open('x',encoding='utf-8') as stream:
        json.dump(result,stream,sort_keys=True,indent=2)
        stream.write('\n')
    verify_checkout(ROOT,head)
    return result


def validate_record(value, context, sha, raw):
    """Closed enriched artifact record; return original after exact context/pins."""
    enriched={'run_id','attempt','fixture_sha256','source_sha256'}
    if type(value) is not dict or set(value) != KEYS | enriched:
        raise ValueError('S0_BOOTSTRAP_FIXTURE_RECEIPT_BLOCKED')
    validate({key:value[key] for key in KEYS},context['head'],sha)
    if type(raw) is not bytes or not 0<len(raw)<=16384 or hashlib.sha256(raw).hexdigest()!=value['fixture_sha256']:
        raise ValueError('S0_BOOTSTRAP_FIXTURE_RECEIPT_BLOCKED')
    if load_json(raw)!={key:value[key] for key in KEYS}:
        raise ValueError('S0_BOOTSTRAP_FIXTURE_RECEIPT_BLOCKED')
    if any(type(value.get(k)) is not str or value[k]!=context[k] for k in ('run_id','attempt')):
        raise ValueError('S0_BOOTSTRAP_FIXTURE_RECEIPT_BLOCKED')
    sources=(*NATIVE_SOURCES,'installer/physical-smoke-s0-tests/BootstrapTests.cs','installer/physical-smoke-s0-tests/InputTests.cs','tools/verify_s0_bootstrap_ci.py')
    pins=value['source_sha256']
    if type(pins) is not dict or set(pins)!=set(sources) or type(value['fixture_sha256']) is not str or re.fullmatch('[0-9a-f]{64}',value['fixture_sha256']) is None:
        raise ValueError('S0_BOOTSTRAP_FIXTURE_RECEIPT_BLOCKED')
    from tools.check_ddl_free_ci import ROOT
    for name in sources:
        digest=hashlib.sha256(subprocess.check_output(['git','show',context['head']+':'+name],cwd=ROOT)).hexdigest()
        if type(pins[name]) is not str or pins[name]!=digest:
            raise ValueError('S0_BOOTSTRAP_FIXTURE_RECEIPT_BLOCKED')
    return value
