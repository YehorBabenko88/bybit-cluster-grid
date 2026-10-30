"""Validate declared Windows SD bytes offline; no host or MIC attestation."""
import base64
import binascii
import re
import struct


def need(condition):
    if not condition:
        raise ValueError('PIPE_DACL_EVIDENCE_REFUSED')


def sid_argument(value):
    need(type(value) is str and len(value)<=200 and re.fullmatch(r'S-1-(0|[1-9][0-9]*)(?:-(0|[1-9][0-9]*)){1,15}',value))
    numbers=[int(x) for x in value.split('-')[1:]]
    need(numbers[1]<2**48 and all(x<2**32 for x in numbers[2:]))
    return value


def validate_descriptor(value,parent_user_sid,app_sid):
    user=sid_argument(parent_user_sid);app=sid_argument(app_sid)
    need(user!=app and user!='S-1-5-18' and app.startswith('S-1-15-2-'))
    need(type(value) is str and 0<len(value)<=4*((131072+2)//3) and value.isascii())
    try:
        raw=base64.b64decode(value,validate=True)
    except (ValueError,binascii.Error):
        raise ValueError('PIPE_DACL_EVIDENCE_REFUSED') from None
    need(20<=len(raw)<=131072 and base64.b64encode(raw).decode('ascii')==value)
    revision,reserved,control,owner,group,_sacl,dacl=struct.unpack_from('<BBHIIII',raw)
    need(revision==1 and reserved==0 and control&0x9004==0x9004)
    # SACL is deliberately not parsed or included in claims. Its presence does
    # not establish a low integrity label or grant authority.
    def sid_at(offset,limit):
        need(type(offset) is int and offset>=20 and offset%4==0 and offset+8<=limit<=len(raw))
        rev,count=raw[offset:offset+2]
        end=offset+8+4*count
        need(rev==1 and count<=15 and end<=limit)
        authority=int.from_bytes(raw[offset+2:offset+8],'big')
        sub=[str(struct.unpack_from('<I',raw,offset+8+4*i)[0]) for i in range(count)]
        return 'S-1-'+str(authority)+('' if not sub else '-'+ '-'.join(sub)),end
    owner_sid,owner_end=sid_at(owner,len(raw));group_sid,group_end=sid_at(group,len(raw))
    need(dacl>=20 and dacl%4==0 and dacl+8<=len(raw))
    acl_revision,acl_reserved,acl_size,ace_count,acl_reserved2=struct.unpack_from('<BBHHH',raw,dacl)
    need(acl_revision in (2,4) and acl_reserved==0 and acl_reserved2==0 and acl_size>=8 and dacl+acl_size<=len(raw) and ace_count==3)
    regions=[(owner,owner_end),(group,group_end),(dacl,dacl+acl_size)]
    for i,left in enumerate(regions):
        for j in range(i+1,len(regions)):
            right=regions[j]
            if i==0 and j==1 and left==right:
                continue
            need(left[1]<=right[0] or right[1]<=left[0])
    grants={};offset=dacl+8;limit=dacl+acl_size
    for _ in range(ace_count):
        need(offset+8<=limit)
        ace_type,flags,size,mask=struct.unpack_from('<BBHI',raw,offset)
        need(ace_type==0 and flags==0 and size>=16 and size%4==0 and offset+size<=limit)
        identity,end=sid_at(offset+8,offset+size)
        need(end==offset+size and identity not in grants)
        grants[identity]=mask;offset+=size
    need(offset==limit and grants=={'S-1-5-18':0x1f01ff,user:0x1f01ff,app:0x120116})
    return dict(owner=owner_sid,group=group_sid,grants=grants,assurance='DECLARED_DACL_BYTES_ONLY',label='LABEL_UNVERIFIED',host_verified=False,execute_authorized=False,cleanup_authorized=False)
