import base64
import struct
import pytest
from integration.pipe_dacl_evidence import validate_descriptor

USER='S-1-5-21-1-2-3-1001'
APP='S-1-15-2-123-456'

def sid(text):
    parts=[int(x) for x in text.split('-')[1:]]
    return bytes([parts[0],len(parts)-2])+parts[1].to_bytes(6,'big')+b''.join(struct.pack('<I',x) for x in parts[2:])

def descriptor(owner=USER,group=USER,alias=False,grants=None):
    owner_bytes=sid(owner);group_bytes=b'' if alias else sid(group)
    aces=[]
    for identity,mask in (grants if grants is not None else [('S-1-5-18',0x1f01ff),(USER,0x1f01ff),(APP,0x120116)]):
        value=sid(identity);aces.append(struct.pack('<BBHI',0,0,8+len(value),mask)+value)
    acl=struct.pack('<BBHHH',2,0,8+sum(map(len,aces)),3,0)+b''.join(aces)
    return struct.pack('<BBHIIII',1,0,0x9004,20,20 if alias else 20+len(owner_bytes),0,20+len(owner_bytes)+len(group_bytes))+owner_bytes+group_bytes+acl

def encoded(raw):return base64.b64encode(raw).decode('ascii')

def test_valid_and_owner_group_alias():
    for alias in (False,True):
        result=validate_descriptor(encoded(descriptor(alias=alias)),USER,APP)
        assert result['owner']==USER and result['group']==USER
        assert result['grants']=={'S-1-5-18':0x1f01ff,USER:0x1f01ff,APP:0x120116}
        assert result['assurance']=='DECLARED_DACL_BYTES_ONLY'

@pytest.mark.parametrize('value',['AA==','', '!!!!','YQ==\n','YQ','A'*174768],ids=['short','empty','alphabet','whitespace','padding','oversize'])
def test_invalid_base64_or_structure(value):
    with pytest.raises(ValueError):validate_descriptor(value,USER,APP)

@pytest.mark.parametrize('kind',['revision','control','owner_overlap','dacl_overlap','acl_size','ace_count','ace_type','ace_flags','ace_size','mask','duplicate','sid_revision','sid_count','truncated','trailing_acl'])
def test_mutations(kind):
    raw=bytearray(descriptor());dacl=struct.unpack_from('<I',raw,16)[0];ace=dacl+8
    if kind=='revision':raw[0]=2
    elif kind=='control':struct.pack_into('<H',raw,2,0x8004)
    elif kind=='owner_overlap':struct.pack_into('<I',raw,8,21)
    elif kind=='dacl_overlap':struct.pack_into('<I',raw,16,20)
    elif kind=='acl_size':struct.pack_into('<H',raw,dacl+2,7)
    elif kind=='ace_count':struct.pack_into('<H',raw,dacl+4,4)
    elif kind=='ace_type':raw[ace]=9
    elif kind=='ace_flags':raw[ace+1]=0x10
    elif kind=='ace_size':struct.pack_into('<H',raw,ace+2,8)
    elif kind=='mask':struct.pack_into('<I',raw,ace+4,0x1f01fe)
    elif kind=='duplicate':raw[ace+8:ace+20]=sid('S-1-5-19')
    elif kind=='sid_revision':raw[ace+8]=2
    elif kind=='sid_count':raw[ace+9]=16
    elif kind=='truncated':raw=raw[:-1]
    elif kind=='trailing_acl':struct.pack_into('<H',raw,dacl+2,len(raw)-dacl+4);raw+=b'\0'*4
    with pytest.raises(ValueError):validate_descriptor(encoded(raw),USER,APP)

def test_sid_argument_binding():
    for user,app in [(APP,APP),('not-a-sid',APP),(USER,'S-1-5-18')]:
        with pytest.raises(ValueError):validate_descriptor(encoded(descriptor()),user,app)

@pytest.mark.parametrize('grants',[
    [('S-1-5-18',0x1f01ff),(USER,0x1f01ff),(USER,0x120116)],
    [('S-1-5-18',0x1f01ff),(USER,0x1f01ff),(APP,0x120117)],
    [('S-1-5-18',0x1f01ff),(USER,0x1f01ff),('S-1-5-32-545',0x120116)],
],ids=['duplicate','package-read-data','group-substitution'])
def test_exact_grants(grants):
    with pytest.raises(ValueError):validate_descriptor(encoded(descriptor(grants=grants)),USER,APP)

def test_sacl_is_not_mic_attestation():
    raw=bytearray(descriptor());struct.pack_into('<I',raw,12,0xffffffff)
    result=validate_descriptor(encoded(raw),USER,APP)
    assert result['label']=='LABEL_UNVERIFIED' and result['host_verified'] is False
