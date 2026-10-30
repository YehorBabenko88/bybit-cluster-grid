"""Ephemeral S0 mutual TLS material. No keys exist in shipped artifacts."""
import hashlib,ipaddress,re,ssl
from datetime import datetime,timedelta,timezone
from .policy import need,validate_plan,canonical,load_json
TLS_FILES={'ca.pem','tls-cert.pem','peer-cert.pem','tls-key.pem'}

def materials(plan,head,package_sha):
 validate_plan(plan,head);need(type(package_sha) is str and re.fullmatch('[0-9a-f]{64}',package_sha))
 from cryptography import x509
 from cryptography.hazmat.primitives import hashes,serialization
 from cryptography.hazmat.primitives.asymmetric import ec
 from cryptography.x509.oid import NameOID,ExtendedKeyUsageOID
 now=datetime.now(timezone.utc);issuer_key=ec.generate_private_key(ec.SECP256R1())
 issuer_name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'S0-'+plan['run_id'])])
 issuer=(x509.CertificateBuilder().subject_name(issuer_name).issuer_name(issuer_name).public_key(issuer_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).add_extension(x509.KeyUsage(False,False,False,False,False,True,True,False,False),critical=True).sign(issuer_key,hashes.SHA256()))
 pairs={}
 for role in ('LS5','PC4'):
  key=ec.generate_private_key(ec.SECP256R1());name=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,role+'-'+plan['run_id'])])
  ip=plan['coordinator_ip'] if role=='LS5' else plan['worker_ip']
  cert=(x509.CertificateBuilder().subject_name(name).issuer_name(issuer_name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(hours=1)).add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address(ip)),x509.UniformResourceIdentifier('urn:grid-s0:'+plan['run_id']+':'+head+':'+role)]),critical=False).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH if role=='LS5' else ExtendedKeyUsageOID.CLIENT_AUTH]),critical=True).sign(issuer_key,hashes.SHA256()))
  pairs[role]=(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()),cert.public_bytes(serialization.Encoding.PEM))
 out={}
 for role,peer in (('LS5','PC4'),('PC4','LS5')):
  files={'ca.pem':issuer.public_bytes(serialization.Encoding.PEM),'tls-key.pem':pairs[role][0],'tls-cert.pem':pairs[role][1],'peer-cert.pem':pairs[peer][1]}
  config=dict(schema=1,profile='PHYSICAL_SMOKE_S0',plan=plan,role=role,package_sha256=package_sha,files={n:hashlib.sha256(b).hexdigest() for n,b in files.items()})
  files['config.json']=canonical(config);context=dict(head=head,run_id=plan['run_id'],role=role);files['stop.json']=canonical(dict(context,stop=False));out[role]=files
 return out

def validate_config(raw,head,package_sha):
 c=load_json(raw);need(set(c)=={'schema','profile','plan','role','package_sha256','files'})
 need(type(c['schema']) is int and c['schema']==1 and c['profile']=='PHYSICAL_SMOKE_S0' and c['role'] in ('LS5','PC4') and c['package_sha256']==package_sha)
 validate_plan(c['plan'],head);need(type(c['files']) is dict and set(c['files'])==TLS_FILES)
 need(all(type(h) is str and re.fullmatch('[0-9a-f]{64}',h) for h in c['files'].values()))
 return c

def tls_context(c,root):
 from pathlib import Path
 from .storage import read_small
 from cryptography import x509
 from cryptography.hazmat.primitives import serialization
 from cryptography.x509.oid import ExtendedKeyUsageOID
 root=Path(root)
 for n,h in c['files'].items():need(hashlib.sha256(read_small(root,n)).hexdigest()==h,'S0_TLS_FILE_CHANGED')
 # Validate explicit signed role/run/head URI independently of file names.
 for n,role in (('tls-cert.pem',c['role']),('peer-cert.pem','PC4' if c['role']=='LS5' else 'LS5')):
  cert=x509.load_pem_x509_certificate(read_small(root,n));uri='urn:grid-s0:'+c['plan']['run_id']+':'+c['plan']['head']+':'+role
  need(cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value.get_values_for_type(x509.UniformResourceIdentifier)==[uri])
  need(list(cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value)==[ExtendedKeyUsageOID.SERVER_AUTH if role=='LS5' else ExtendedKeyUsageOID.CLIENT_AUTH])
 ctx=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER if c['role']=='LS5' else ssl.PROTOCOL_TLS_CLIENT)
 ctx.minimum_version=ssl.TLSVersion.TLSv1_2;ctx.verify_mode=ssl.CERT_REQUIRED
 if c['role']=='PC4':ctx.check_hostname=True
 ctx.load_verify_locations(cafile=str(root/'ca.pem'));ctx.load_cert_chain(str(root/'tls-cert.pem'),str(root/'tls-key.pem'))
 return ctx
