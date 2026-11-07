"""Offline untrusted response interpretation; never quota/dispatch admission."""
import importlib
import json
import hashlib
from pathlib import Path

import pytest


def api(): return importlib.import_module('grid.bybit_response_advice')
def body(code=0,message='OK'):
    return json.dumps({'retCode':code,'retMsg':message}).encode()


def test_429_is_system_signal_not_ip_or_uid_allowance():
    a=api().parse_response_advice('429',[],body())
    assert a.classification=='HTTP_SYSTEM_FREQUENCY'
    assert a.minimum_backoff_seconds=='1'
    assert a.authority_status=='UNTRUSTED_ADVICE_ONLY'
    assert not hasattr(a,'permit') and not hasattr(a,'retry_at')


def test_access_too_frequent_403_preserves_minimum_even_short_retry_after():
    a=api().parse_response_advice('403',[['Retry-After','2']],body(0,'access too frequent'))
    assert a.classification=='HTTP_IP_FREQUENCY_BAN'
    assert a.minimum_backoff_seconds=='600'
    assert a.session_action=='REQUIRE_HTTP_SESSION_CONTAINMENT'


def test_generic_403_and_empty_body_are_ambiguous_and_never_auto_clear():
    for b in (b'',body(0,'Forbidden'),body(0,'U.S IP restricted')):
        a=api().parse_response_advice('403',[],b)
        assert a.classification=='FORBIDDEN_AMBIGUOUS'
        assert a.minimum_backoff_seconds is None
        assert a.authority_status=='UNTRUSTED_ADVICE_ONLY'


def test_retcode_10006_and_endpoint_headers_do_not_create_ip_allowance():
    a=api().parse_response_advice('200',[['X-Bapi-Limit','10'],['X-Bapi-Limit-Status','9'],['X-Bapi-Limit-Reset-Timestamp','1672738134824']],body(10006,'Too many visits!'))
    assert a.classification=='API_UID_ENDPOINT_THROTTLE'
    assert a.endpoint_remaining=='9'
    assert a.endpoint_reset_timestamp_ms=='1672738134824'
    assert not hasattr(a,'ip_remaining')


def test_http_date_is_retained_as_untrusted_guidance_without_worker_clock():
    date='Fri, 06 Nov 2026 12:00:00 GMT'
    a=api().parse_response_advice('429',[['Retry-After',date]],body())
    assert a.retry_after_http_date==date
    assert a.retry_after_seconds is None and a.minimum_backoff_seconds=='1'


def test_valid_success_or_high_remaining_never_grants_permission():
    a=api().parse_response_advice('200',[['X-Bapi-Limit','1000'],['X-Bapi-Limit-Status','1000']],body())
    assert a.classification=='NO_RECOGNIZED_THROTTLE'
    assert a.authority_status=='UNTRUSTED_ADVICE_ONLY'
    assert not hasattr(a,'quota_delta')


@pytest.mark.parametrize('headers',[
    [['Retry-After','1'],['retry-after','1']],
    [['X-Bapi-Limit','10'],['x-bapi-limit','11']],
    [['X-Bapi-Limit','10'],['X-Bapi-Limit-Status','11']],
    [['Retry-After','-1']],[['Retry-After','1.5']],[['Retry-After','01']],
    [['Retry-After','bad-date']],[['Retry-After','Sun, 06 Nov 2026 12:00:00 GMT']],
    [['X-Bapi-Limit','NaN']],[['X-Bapi-Limit','9007199254740992']],
    [['X-Bapi-Limit-Reset-Timestamp','253402300800000']],
    [['Retry-After','1\r\nInjected: yes']],[['Retry-After',' 1']],
    [['Content-Type','application/json']],[['Retry-After','x'*257]],
    [['Date','Fri, 06 Nov 2026 12:00:00 GMT']]*6,
    [['Retry-After',1]], [('Retry-After','1')], {'Retry-After':'1'}])
def test_duplicate_conflicting_invalid_unknown_or_excess_projected_headers(headers):
    with pytest.raises(api().ResponseAdviceFormatError):
        api().parse_response_advice('429',headers,body())


@pytest.mark.parametrize('bad',[
    b'{',b'[]',b'null',b'{"retCode":0,"retCode":10006,"retMsg":"x"}',
    b'{"retCode":true,"retMsg":"x"}',b'{"retCode":1.0,"retMsg":"x"}',
    b'{"retCode":-1,"retMsg":"x"}',b'{"retCode":0}',
    b'{"retCode":0,"retMsg":null}',b'x'*4097,
    b'{"retCode":0,"retMsg":"x","result":'+b'['*9+b'0'+b']'*9+b'}',
    b'{"retCode":0,"retMsg":"x","result":['+b'0,'*128+b'0]}'])
def test_malformed_body_is_unavailable_not_permission_or_guessed_reset(bad):
    with pytest.raises(api().ResponseAdviceFormatError):
        api().parse_response_advice('429',[],bad)


@pytest.mark.parametrize('status',[429,'0429','99','600',True,None])
def test_status_projection_is_exact(status):
    with pytest.raises(api().ResponseAdviceFormatError):
        api().parse_response_advice(status,[],body())


def test_profile_and_source_evidence_hashes_are_exact():
    c=api();f=Path(__file__).parent/'fixtures/agent3-bybit-response'
    assert (f/'profile.json').read_bytes()==c.profile_bytes()
    assert c.PROFILE_SHA256==hashlib.sha256(c.profile_bytes()).hexdigest()
    b=body();a=c.parse_response_advice('200',[],b)
    assert a.body_sha256==hashlib.sha256(b).hexdigest()
    assert a.profile_sha256==c.PROFILE_SHA256
