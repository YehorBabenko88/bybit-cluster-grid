import pytest
from integration.wfp_events import inspect_events
GUID='12345678-1234-4321-8765-123456789abc'
APP='C:/Packages/g1-fixture-'+GUID+'/AC/python-'+GUID+'/pythonw.exe'
def sample(app=APP,kind='FWPM_NET_EVENT_TYPE_CLASSIFY_DROP'):
    return '<netEvents><item><header><appId>'+app+'</appId><packageSid>S-1-15-2-1</packageSid><remoteAddrV4>127.0.0.1</remoteAddrV4><remotePort>1234</remotePort></header><type>'+kind+'</type><classifyDrop><filterId>77</filterId><layerId>48</layerId><isLoopback>true</isLoopback></classifyDrop></item></netEvents>'
def test_owned_image_drop_is_observation_not_authorization():
    r=inspect_events(sample(),GUID)
    assert r['status']=='OBSERVED_NOT_ATTESTED' and r['events'][0]['filter_id']=='77'
    assert r['execute_authorized'] is False
@pytest.mark.parametrize('raw',[sample('C:/foreign/python.exe'),'<netEvents/>','<!DOCTYPE x><netEvents/>','<broken',sample(kind='UNKNOWN')])
def test_unknown_or_foreign_data_never_proves_drop(raw):
    assert inspect_events(raw,GUID)['status']=='BLOCKED'


def test_documented_utf16_appid_blob_and_netevent_container():
    blob=(APP+'\0').encode('utf-16-le').hex()
    raw=sample().replace('<item>','<netEvent>').replace('</item>','</netEvent>').replace('<appId>'+APP+'</appId>','<appId><data>'+blob+'</data><asString>display only</asString></appId>')
    assert inspect_events(raw,GUID)['status']=='OBSERVED_NOT_ATTESTED'

def test_ambiguous_or_invalid_blob_is_blocked():
    raw=sample().replace('<appId>'+APP+'</appId>','<appId><data>not hex</data><asString>'+APP+'</asString></appId>')
    assert inspect_events(raw,GUID)['status']=='BLOCKED'


def test_foreign_empty_blob_does_not_hide_owned_drop():
    raw=sample().replace('<netEvents>','<netEvents><item><header><appId><data/></appId></header></item>')
    assert inspect_events(raw,GUID)['status']=='OBSERVED_NOT_ATTESTED'
