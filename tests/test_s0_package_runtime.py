import hashlib,json,zipfile,pytest
from s0_smoke.package import verify_package
H='a'*40

def fixture(root):
 f={'runtime/python.exe':b'fixture','runtime/python._pth':b'stdlib.zip\nDLLs\nSite\nApp\n','runtime/python312._pth':b'stdlib.zip\nDLLs\nSite\nApp\n','runtime/App/s0.py':b'pass','runtime/stdlib.zip':b'zip'}
 m=dict(schema=1,profile='PHYSICAL_SMOKE_S0',head=H,tree='b'*40,run_id='1',attempt='1',python='3.12.10',authority=dict(s0_execute=False,g1_execute=False,cleanup=False),files={n:dict(sha256=hashlib.sha256(b).hexdigest(),size=len(b)) for n,b in f.items()},source={})
 raw=json.dumps(m).encode();(root/'s0-package.json').write_bytes(raw)
 for n,b in f.items():p=root/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
 z=root/'source.zip'
 with zipfile.ZipFile(z,'w') as a:
  a.writestr('s0-package.json',raw)
  for n,b in f.items():a.writestr(n,b)
 return z,hashlib.sha256(z.read_bytes()).hexdigest()
def test_closed_package(tmp_path):
 z,h=fixture(tmp_path);assert verify_package(tmp_path,z,H,h)['head']==H
@pytest.mark.parametrize('mutation',['head','digest','extra','file','manifest'])
def test_package_substitution(tmp_path,mutation):
 z,h=fixture(tmp_path);head=H
 if mutation=='head':head='c'*40
 elif mutation=='digest':h='c'*64
 elif mutation=='extra':(tmp_path/'.env').write_text('SYNTHETIC_NOT_A_SECRET')
 elif mutation=='file':(tmp_path/'runtime/App/s0.py').write_bytes(b'changed')
 else:(tmp_path/'s0-package.json').write_text('{}')
 with pytest.raises(ValueError):verify_package(tmp_path,z,head,h)
