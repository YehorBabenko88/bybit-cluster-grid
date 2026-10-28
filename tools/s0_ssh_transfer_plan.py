"""Pure private-G0 transfer proposal. No filesystem, process, socket or admission API.

All input facts are supplied by the owner from existing private evidence; this
builder cannot establish their existence, custody, receiver lease or freshness.
Its output always remains BLOCKED and cannot authorize executing proposed_argv.
"""
import base64
import hashlib
import ipaddress
import ntpath
import re
import struct
import uuid

KEYS=frozenset(('head','run_id','attempt','package_sha256','payload_sha256','payload_size','ssh_path','ssh_sha256','scp_path','scp_sha256','host','username','host_key_blob','host_key_fingerprint','source_known_folder','source_root','source_path','recipient_known_folder','recipient_root','recipient_path','recipient_identity','private_key_path','approved_private_key_path'))

def _need(ok):
    if not ok:raise ValueError('S0_SSH_TRANSFER_PLAN_BLOCKED')

def _hex(value,n):
    return type(value) is str and re.fullmatch('[0-9a-f]{'+str(n)+'}',value) is not None

def _path(value):
    _need(type(value) is str and 3<len(value)<=240 and re.fullmatch(r'C:\\[A-Za-z0-9_.\\-]+',value) is not None)
    _need(ntpath.normpath(value)==value and not value.endswith('\\'))
    for part in value[3:].split('\\'):
        _need(part not in ('','.','..') and not part.endswith('.') and re.fullmatch(r'(?i:CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?',part) is None)
    return value

def _known_folder(value):
    _path(value)
    _need(re.fullmatch(r'C:\\Users\\[A-Za-z0-9_-]+\\AppData\\Local',value) is not None)

def _root(folder,root):
    _known_folder(folder);_path(root)
    _need(ntpath.dirname(root)==folder)
    leaf=ntpath.basename(root);prefix='GridS0Input-';_need(leaf.startswith(prefix))
    token=leaf[len(prefix):]
    try: parsed=uuid.UUID(token)
    except (ValueError,AttributeError):raise ValueError('S0_SSH_TRANSFER_PLAN_BLOCKED') from None
    _need(str(parsed)==token and parsed.version==4 and parsed.variant==uuid.RFC_4122)

def _host(value):
    _need(type(value) is str)
    try: address=ipaddress.ip_address(value)
    except ValueError:raise ValueError('S0_SSH_TRANSFER_PLAN_BLOCKED') from None
    _need(str(address)==value and not address.is_loopback and not address.is_link_local and not address.is_multicast and not address.is_unspecified)
    allowed=('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16','100.64.0.0/10') if address.version==4 else ('fc00::/7',)
    _need(any(address in ipaddress.ip_network(n) for n in allowed))
    return address

def _host_key(blob,fingerprint):
    _need(type(blob) is str and len(blob)<=128 and type(fingerprint) is str and re.fullmatch(r'SHA256:[A-Za-z0-9+/]{43}',fingerprint) is not None)
    try: wire=base64.b64decode(blob,validate=True)
    except (ValueError,TypeError):raise ValueError('S0_SSH_TRANSFER_PLAN_BLOCKED') from None
    _need(base64.b64encode(wire).decode('ascii')==blob)
    at=0;parts=[]
    for _ in range(2):
        _need(at+4<=len(wire));size=struct.unpack_from('>I',wire,at)[0];at+=4
        _need(size<=32 and at+size<=len(wire));parts.append(wire[at:at+size]);at+=size
    _need(at==len(wire) and parts[0]==b'ssh-ed25519' and len(parts[1])==32)
    actual='SHA256:'+base64.b64encode(hashlib.sha256(wire).digest()).decode('ascii').rstrip('=')
    _need(actual==fingerprint)

def build_transfer_plan(record):
    """Return an inert closed proposal from strictly supplied private G0 facts."""
    _need(type(record) is dict and set(record)==KEYS)
    r=record
    _need(_hex(r['head'],40) and all(_hex(r[k],64) for k in ('package_sha256','payload_sha256','ssh_sha256','scp_sha256')))
    _need(type(r['run_id']) is str and re.fullmatch('[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}',r['run_id']) is not None)
    _need(type(r['attempt']) is str and re.fullmatch('[1-9][0-9]{0,19}',r['attempt']) is not None)
    _need(type(r['payload_size']) is int and 1<=r['payload_size']<=6*1024*1024)
    _need(r['ssh_path']==r'C:\Windows\System32\OpenSSH\ssh.exe' and r['scp_path']==r'C:\Windows\System32\OpenSSH\scp.exe')
    _need(r['username']=='ls4');address=_host(r['host']);_host_key(r['host_key_blob'],r['host_key_fingerprint'])
    _root(r['source_known_folder'],r['source_root']);_root(r['recipient_known_folder'],r['recipient_root'])
    _path(r['source_path']);_path(r['recipient_path'])
    _need(r['source_path']==ntpath.join(r['source_root'],'pc4-role.zip') and r['recipient_path']==ntpath.join(r['recipient_root'],'incoming.zip'))
    _need(r['source_root']!=r['recipient_root'])
    identity=r['recipient_identity']
    # Preserve the actual legacy NTFS observer contract without widening/padding.
    _need(type(identity) is dict and set(identity)=={'root_id','file_id'})
    for key in ('root_id','file_id'):
        value=identity[key]
        _need(type(value) is str and re.fullmatch('[0-9a-f]{8}:[0-9a-f]{16}',value) is not None)
        _need(value[:8]!='0'*8 and value[9:]!='0'*16)
    _need(identity['root_id'][:8]==identity['file_id'][:8] and identity['root_id']!=identity['file_id'])
    _path(r['private_key_path']);_path(r['approved_private_key_path'])
    _need(r['private_key_path']==r['approved_private_key_path'] and re.fullmatch(r'C:\\Users\\[A-Za-z0-9_-]+\\\.ssh\\[A-Za-z0-9_-]+',r['private_key_path']) is not None)
    known_hosts=ntpath.join(r['source_root'],'known_hosts')
    options=('StrictHostKeyChecking=yes','UpdateHostKeys=no','GlobalKnownHostsFile=NUL','UserKnownHostsFile='+known_hosts,
        'HostKeyAlgorithms=ssh-ed25519','ProxyCommand=none','ProxyJump=none','IdentityAgent=none','ForwardAgent=no',
        'ForwardX11=no','ForwardX11Trusted=no','ClearAllForwardings=yes','PasswordAuthentication=no','KbdInteractiveAuthentication=no',
        'PreferredAuthentications=publickey','CertificateFile=none','ControlMaster=no','ControlPath=none','ControlPersist=no','PermitLocalCommand=no',
        'ConnectTimeout=10','ServerAliveInterval=5','ServerAliveCountMax=2','BatchMode=yes','IdentitiesOnly=yes','RequestTTY=no')
    argv=[r['scp_path'],'-q','-F','NUL','-S',r['ssh_path'],'-i',r['private_key_path']]
    for option in options:argv.extend(('-o',option))
    remote_host='['+r['host']+']' if address.version==6 else r['host']
    argv.extend((r['source_path'],'ls4@'+remote_host+':'+r['recipient_path'].replace('\\','/')))
    return dict(status='BLOCKED',plan_only=True,argv=None,proposed_argv=argv,
        scope='PRIVATE_G0_PROPOSAL_NOT_AUTHORIZATION',head=r['head'],run_id=r['run_id'],attempt=r['attempt'],
        package_sha256=r['package_sha256'],payload_sha256=r['payload_sha256'],payload_size=r['payload_size'],
        binary_sha256={'ssh.exe':r['ssh_sha256'],'scp.exe':r['scp_sha256']},recipient_root=r['recipient_root'],recipient_identity=dict(identity),
        known_hosts_path=known_hosts,known_hosts_line=r['host']+' ssh-ed25519 '+r['host_key_blob']+'\n',host_key_fingerprint=r['host_key_fingerprint'],
        gates={'owner_authorization':'BLOCKED','receiver_lease':'BLOCKED','actual_g0':'BLOCKED'},
        permissions={'execute':False,'write_known_hosts':False,'transfer':False,'receive':False,'import':False,'cleanup':False,'s0_execute':False,'g1_execute':False})
