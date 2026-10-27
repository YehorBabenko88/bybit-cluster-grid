"""Read-only exported WFP diagnostics. Image-GUID correlation is not attestation."""
import json,os,re,sys
from pathlib import Path
import xml.etree.ElementTree as E
from integration.python_containment_evidence import load

def inspect_events(raw,guid):
    out=dict(status='BLOCKED',assurance='IMAGE_GUID_CORRELATION_ONLY',effective_filter_verified=False,execute_authorized=False,cleanup_authorized=False,events=[])
    try:
        if type(raw) is not str or len(raw)>4*1024*1024 or not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',guid) or '<!DOCTYPE' in raw.upper() or '<!ENTITY' in raw.upper():return out
        root=E.fromstring(raw)
        for item in root.iter():
            if item.tag not in ('item','netEvent'):continue
            apps=item.findall('header/appId')
            if len(apps)!=1:continue
            node=apps[0];blobs=node.findall('data')
            if list(node):
                if len(blobs)!=1:continue
                blob=''.join((blobs[0].text or '').split())
                if len(blob)>65536 or len(blob)%4 or not re.fullmatch('[0-9A-Fa-f]+',blob):continue
                try:app=bytes.fromhex(blob).decode('utf-16-le').removesuffix('\0')
                except (ValueError,UnicodeError):continue
                if '\0' in app:continue
            else:app=node.text or '' 
            if guid not in app.lower() or not app.lower().endswith('pythonw.exe'):continue
            kind=item.findtext('type','');tag={'FWPM_NET_EVENT_TYPE_CLASSIFY_DROP':'classifyDrop','FWPM_NET_EVENT_TYPE_CAPABILITY_DROP':'capabilityDrop'}.get(kind)
            if tag is None:return out
            filter_id=item.findtext(tag+'/filterId','');layer=item.findtext(tag+'/layerId','')
            if not re.fullmatch('[0-9]{1,20}',filter_id) or not 0<int(filter_id)<=2**64-1 or not re.fullmatch('[0-9]{1,5}',layer) or int(layer)>65535:return out
            out['events'].append(dict(type=kind,filter_id=filter_id,layer_id=layer,is_loopback=item.findtext(tag+'/isLoopback','UNKNOWN'),remote_port=item.findtext('header/remotePort','UNKNOWN')[:8],remote_address=(item.findtext('header/remoteAddrV4') or item.findtext('header/remoteAddrV6.byteArray16') or 'UNKNOWN')[:64],timestamp=item.findtext('header/timeStamp','UNKNOWN')[:40]))
            if len(out['events'])>64:return dict(out,status='BLOCKED',events=[])
        if out['events']:out['status']='OBSERVED_NOT_ATTESTED'
    except (E.ParseError,ValueError,TypeError):pass
    return out

def main():
    folder=Path(sys.argv[1]);out=inspect_events('', '00000000-0000-0000-0000-000000000000')
    try:
        n=load((folder/'native.json').read_bytes());expected=tuple(os.environ[k] for k in ('EXACT_HEAD_SHA','GITHUB_RUN_ID','GITHUB_RUN_ATTEMPT'))
        if (n['head'],n['run_id'],n['attempt'])!=expected:raise ValueError('CONTEXT')
        image=next(r['Detail'] for r in n['loader_events'] if r['Event']==3)
        guid=re.search('g1-fixture-([0-9a-f-]{36})',image,re.I).group(1).lower()
        raw=Path(sys.argv[2]).read_bytes()
        if len(raw)>8*1024*1024:raise ValueError('SIZE')
        text=raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig')
        out=inspect_events(text,guid)
    except (OSError,ValueError,KeyError,TypeError,StopIteration,AttributeError):pass
    export=os.environ.get('WFP_EXPORT_EXIT','');out['export_exit_code']=int(export) if export.isdigit() and len(export)<=10 else None
    if out['export_exit_code']!=0:out['status']='BLOCKED'
    out.update(head=os.environ['EXACT_HEAD_SHA'],run_id=os.environ['GITHUB_RUN_ID'],attempt=os.environ['GITHUB_RUN_ATTEMPT'])
    (folder/'wfp-events.json').write_text(json.dumps(out),encoding='utf8')
if __name__=='__main__':main()
