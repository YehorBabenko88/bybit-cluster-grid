"""Offline codec/claim tests; these are not actual publication/fencing proof."""
import copy
import base64
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

FIXTURES=Path(__file__).parent/"fixtures"/"agent3-checkpoint-v3"
CONFIRMED_BYTES=(FIXTURES/"confirmed-unknown-time.canonical.json").read_bytes()
OBSERVED_BYTES=(FIXTURES/"confirmed-observed.canonical.json").read_bytes()
UNCONFIRMED_BYTES=(FIXTURES/"unconfirmed.canonical.json").read_bytes()

def codec():
    return importlib.import_module("grid.checkpoint_v3_codec")


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True).encode("ascii")


def reviewed_fixture_bytes(name):
    images=json.loads((FIXTURES/"approved-text-images.json").read_bytes())["images"]
    return base64.b64decode(images[name],validate=True) if name in images else (FIXTURES/name).read_bytes()


def test_confirmed_claim_with_unknown_time_is_not_unconfirmed_or_authority():
    c=codec(); parsed=c.parse_claim(CONFIRMED_BYTES)
    assert parsed.commit_status == "COMMITTED"
    assert parsed.as_dict()["publication_content"]["committed_at_utc"] is None
    assert parsed.as_dict()["publication_content"]["commit_time_status"] == "UNKNOWN_COMMIT_INSTANT"
    assert c.encode_claim(parsed.as_dict()) == CONFIRMED_BYTES
    with pytest.raises(c.AuthorityIntegrationUnavailable):
        c.require_authoritative_checkpoint(parsed)


def test_unconfirmed_result_has_no_committed_checkpoint_or_evidence():
    c=codec(); parsed=c.parse_claim(UNCONFIRMED_BYTES)
    assert parsed.commit_status == "COMMIT_UNCONFIRMED"
    assert "publication_content" not in parsed.as_dict()
    assert "publication_evidence" not in parsed.as_dict()
    assert c.encode_claim(parsed.as_dict()) == UNCONFIRMED_BYTES
    value=parsed.as_dict(); value["publication_content"]={}
    with pytest.raises(c.CheckpointFormatError): c.encode_claim(value)


def test_delayed_and_repeated_observation_never_changes_committed_content():
    c=codec(); first=c.parse_claim(CONFIRMED_BYTES); later=c.parse_claim(OBSERVED_BYTES)
    assert first.as_dict()["publication_content"] == later.as_dict()["publication_content"]
    assert first.as_dict()["publication_content_sha256"] == later.as_dict()["publication_content_sha256"]
    assert later.as_dict()["confirmed_observed_at_utc"] == "2026-11-06T18:00:00.000Z"
    assert c.parse_claim(OBSERVED_BYTES).canonical_bytes == later.canonical_bytes
    with pytest.raises(c.AuthorityIntegrationUnavailable): c.require_authoritative_checkpoint(later)


def test_reload_and_separate_process_restart_cannot_promote_claim(tmp_path):
    c=codec(); path=tmp_path/"checkpoint.json"; path.write_bytes(CONFIRMED_BYTES)
    assert c.parse_claim(path.read_bytes()).canonical_bytes == CONFIRMED_BYTES
    script = """import sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from grid.checkpoint_v3_codec import parse_claim,require_authoritative_checkpoint,AuthorityIntegrationUnavailable
claim=parse_claim(Path(sys.argv[2]).read_bytes())
assert claim.commit_status=='COMMITTED'
try:
    require_authoritative_checkpoint(claim)
except AuthorityIntegrationUnavailable:
    print('UNTRUSTED')
else:
    raise AssertionError('promoted')
"""
    result=subprocess.run([sys.executable,"-I","-S","-B","-c",script,str(Path(__file__).resolve().parents[1]),str(path)],capture_output=True,text=True,timeout=10)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "UNTRUSTED"


@pytest.mark.parametrize("path,value", [
    (("publication_content","committed_at_utc"),"2026-11-06T18:00:00.000Z"),
    (("publication_content","commit_time_status"),"KNOWN"),
    (("publication_content","schema_version"),"2"),
    (("publication_evidence","request_id"),"00000000-0000-4000-8000-000000000099"),
    (("publication_evidence","checkpoint_revision"),"99"),
    (("publication_evidence","authority_modify_index"),True),
    (("publication_content","lease_epoch"),"9223372036854775808"),
    (("publication_content","lease_epoch"),1),
    (("publication_content_sha256",),"0"*64),
    (("publication_content","fencing_token","grant_revision"),"2"),
    (("confirmed_observed_at_utc",),"2026-02-30T18:00:00.000Z"),
    (("clock_epoch_id",),None),
])
def test_rejects_fabricated_time_evidence_versions_and_inconsistent_fences(path,value):
    c=codec(); data=json.loads(OBSERVED_BYTES); current=data
    for key in path[:-1]:current=current[key]
    current[path[-1]]=value
    if path[0] == "publication_content":
        # Keep hashes self-consistent so digest mismatch does not mask the
        # intended counter/version/time/fence semantic rejection.
        digest=hashlib.sha256(canonical(data["publication_content"])).hexdigest()
        data["publication_content_sha256"]=digest
        data["publication_evidence"]["publication_content_sha256"]=digest
    with pytest.raises(c.CheckpointFormatError): c.encode_claim(data)


@pytest.mark.parametrize("old_name", ["commit_time_semantics","observed_committed_at_utc","verified"])
def test_old_aliases_and_fake_verification_flags_are_not_authority(old_name):
    c=codec(); data=json.loads(CONFIRMED_BYTES); data[old_name]=True
    with pytest.raises(c.CheckpointFormatError): c.encode_claim(data)
    with pytest.raises(c.AuthorityIntegrationUnavailable): c.require_authoritative_checkpoint({"verified":True})


@pytest.mark.parametrize("raw", [
    b'{"schema_version":"3","schema_version":"3"}',
    b" " + CONFIRMED_BYTES,
    CONFIRMED_BYTES+b"\n",
    b"["*100+b"]"*100,
    b"x"*32769,
    b'{"n":NaN}',
    b'{"n":1}',
], ids=["duplicate-key", "leading-space", "trailing-newline", "excess-depth", "oversize", "nan", "json-number"])
def test_rejects_duplicate_noncanonical_excessive_and_numeric_input(raw):
    c=codec()
    with pytest.raises(c.CheckpointFormatError): c.parse_claim(raw)


def test_missing_confirmation_and_mutable_copies_do_not_change_original():
    c=codec(); parsed=c.parse_claim(CONFIRMED_BYTES); detached=parsed.as_dict()
    detached["publication_evidence"].clear()
    assert parsed.canonical_bytes == CONFIRMED_BYTES
    with pytest.raises(c.CheckpointFormatError): c.encode_claim(detached)


def test_consistent_but_historical_fence_is_never_current_authorization():
    c=codec(); parsed=c.parse_claim(CONFIRMED_BYTES)
    # No admitted actual authority adapter exists; even consistent historical
    # provenance cannot authorize effects, irrespective of current/revoked state.
    with pytest.raises(c.AuthorityIntegrationUnavailable): c.require_authoritative_checkpoint(parsed)


def test_actual_legacy_observer_reader_keeps_its_timestamp_and_state_contract():
    from datetime import datetime, timezone
    from grid.observer_checkpoint import ObserverCheckpoint
    import asyncio

    legacy_time=datetime(2026,11,6,12,tzinfo=timezone.utc)
    class Pool:
        async def fetchrow(self,query,*args):
            assert args == ("legacy-observer", "BTCUSDT")
            return {"last_ts":legacy_time,"state":{"cursor":7}}
    result=asyncio.run(ObserverCheckpoint(Pool(),"legacy-observer").load("BTCUSDT"))
    assert result == (legacy_time,{"cursor":7})


@pytest.mark.parametrize("old", [
    {"schema_version":"1","committed_at_utc":"2026-11-06T12:00:00.000Z"},
    {"schema_version":"2","commit_time_semantics":"UNKNOWN_COMMIT_INSTANT"},
    {"last_ts":"2026-11-06T12:00:00.000Z","state":{"cursor":7}},
    {"next_end_ms":119999,"symbol":"BTCUSDT"},
])
def test_no_silent_dispatch_or_relabel_of_legacy_formats(old):
    c=codec()
    with pytest.raises(c.CheckpointFormatError): c.parse_claim(canonical(old))


def test_codec_schema_and_golden_bytes_match_exact_peer_reviewed_images():
    c=codec()
    assert c.SCHEMA_SHA256 == "4de720d9391e5a89c0577b5298c283e742fbfe490c4454c184e31c2348589ea4"
    raw=reviewed_fixture_bytes("golden-vectors.json")
    assert hashlib.sha256(raw).hexdigest() == "69ef7786400030ae1bb9dbf4bd1fb30c6b6e50ac9690437536aa669a7c18b0d4"
    for entry in json.loads(raw)["files"]:
        assert hashlib.sha256(reviewed_fixture_bytes(entry["path"])).hexdigest() == entry["sha256"]


@pytest.mark.parametrize("value", [None,[],1,True,{"schema_version":"3","untrusted":"x"*32769}])
def test_encoder_rejects_unsupported_or_excessive_python_inputs(value):
    c=codec()
    with pytest.raises(c.CheckpointFormatError): c.encode_claim(value)


def test_encoder_rejects_escape_content_outside_closed_identifier_enums():
    c=codec(); value=json.loads(UNCONFIRMED_BYTES)
    # Unsupported aliases still fail: schema identifiers are intentionally not
    # arbitrary strings even when their JSON representation could be canonical.
    value["reason"]='a"b\\c'
    with pytest.raises(c.CheckpointFormatError): c.encode_claim(value)


@pytest.mark.parametrize("category", ["spot","inverse","option"])
def test_fixed_linear_source_cannot_claim_another_market(category):
    c=codec(); value=json.loads(CONFIRMED_BYTES)
    value["publication_content"]["instrument_id"]["category"]=category
    digest=hashlib.sha256(canonical(value["publication_content"])).hexdigest()
    value["publication_content_sha256"]=digest
    value["publication_evidence"]["publication_content_sha256"]=digest
    with pytest.raises(c.CheckpointFormatError): c.encode_claim(value)
