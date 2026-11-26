"""Exact source-owned SDK wheel/sdist bytes and closed installer metadata."""
import ast,base64,configparser,csv,email.parser,hashlib,io,json,pathlib,sys,tarfile,tempfile,tomllib,zipfile

def project(root,name):
 value=tomllib.loads((root/'pyproject.toml').read_text(encoding='utf-8'))['project']
 assert value['name']==name and type(value['version']) is str and not value.get('dynamic')
 return value

def verify_wheel(path,expected,metadata,top_levels):
 prefix=metadata['name'].replace('-','_')+'-'+metadata['version']+'.dist-info/'
 scripts=metadata.get('scripts',{})
 allowed={prefix+n for n in ('METADATA','WHEEL','top_level.txt','RECORD')}
 if scripts:allowed.add(prefix+'entry_points.txt')
 with zipfile.ZipFile(path) as z:
  names=z.namelist();assert 0<len(names)<=256 and len(names)==len(set(names))
  assert set(names)==set(expected)|allowed,'unapproved wheel member or missing required member'
  assert sum(info.file_size for info in z.infolist())<=16*1024*1024
  for info in z.infolist():
   p=pathlib.PurePosixPath(info.filename)
   assert not p.is_absolute() and '..' not in p.parts and chr(92) not in info.filename and ':' not in info.filename and not info.is_dir() and info.file_size<=2*1024*1024
  raw={name:z.read(name) for name in names}
  for name,source in expected.items():assert raw[name]==source,'wheel differs from raw source: '+name
  headers=email.parser.BytesParser().parsebytes(raw[prefix+'METADATA'])
  assert headers.get_all('Name')==[metadata['name']] and headers.get_all('Version')==[metadata['version']]
  wheel=email.parser.BytesParser().parsebytes(raw[prefix+'WHEEL'])
  assert wheel.get_all('Wheel-Version')==['1.0'] and wheel.get_all('Root-Is-Purelib')==['true'] and wheel.get_all('Tag')==['py3-none-any']
  observed=raw[prefix+'top_level.txt'].decode('utf-8').splitlines()
  assert len(observed)==len(set(observed)) and set(observed)==set(top_levels)
  if scripts:
   entries=configparser.ConfigParser(interpolation=None,strict=True);entries.optionxform=str;entries.read_string(raw[prefix+'entry_points.txt'].decode('utf-8'))
   assert entries.sections()==['console_scripts'] and dict(entries.items('console_scripts'))==scripts
  records=list(csv.reader(io.StringIO(raw[prefix+'RECORD'].decode('utf-8'))))
  assert len(records)==len(names) and all(len(row)==3 for row in records) and len({row[0] for row in records})==len(names) and {row[0] for row in records}==set(names)
  for name,digest,size in records:
   if name==prefix+'RECORD':assert digest==size==''
   else:
    assert size==str(len(raw[name]))
    assert digest=='sha256='+base64.urlsafe_b64encode(hashlib.sha256(raw[name]).digest()).rstrip(b'=').decode('ascii')
  return raw

def main():
 root=pathlib.Path(sys.argv[1]);sdk=pathlib.Path(sys.argv[2])
 data_project=project(root,'market-data');math_project=project(root/'.source/math','unified-math-kernels')
 source={p.relative_to(root).as_posix():p.read_bytes() for p in (root/'market_data').iterdir() if p.suffix in ('.py','.sql')}
 # Additive v2 is a second NAMESPACE in this ONE distribution, not a
 # second distribution or an unreviewed replacement of sealed runtime49.
 # The legacy 0.1.0 synthetic package gate remains byte-for-byte compatible.
 v2_dir=root/'market_data_v2'
 v2={}
 if v2_dir.exists():
  assert data_project['version']=='0.2.0.dev0','unapproved qualified read package version'
  assert v2_dir.is_dir() and not v2_dir.is_symlink()
  allowed={'__init__.py','qualified_read_contract.py','read_api.py'}
  entries=list(v2_dir.iterdir())
  assert {p.name for p in entries}==allowed and all(p.is_file() and not p.is_symlink() for p in entries),'unknown or linked v2 runtime'
  v2={p.relative_to(root).as_posix():p.read_bytes() for p in entries}
 else:
  assert data_project['version']=='0.1.0','unapproved legacy package version'
 numerical={name:(root/'.source/math/python'/name).read_bytes() for name in ('market_math.py','market_compute_api.py','history_statistics.py')}
 wheels=list((root/'.candidate-dist').glob('market_data-*.whl'));sdists=list((root/'.candidate-dist').glob('*.tar.gz'));assert len(wheels)==len(sdists)==1
 wheel=wheels[0];sdist=sdists[0]
 payload=verify_wheel(wheel,{**source,**v2},data_project,('market_data', 'market_data_v2') if v2 else ('market_data',))
 numerical_payload=verify_wheel(sdk,numerical,math_project,tuple(name.removesuffix('.py') for name in numerical))
 for name,raw in {**source,**v2}.items():
  if not name.endswith('.py'):continue
  for node in ast.walk(ast.parse(raw)):
   imports=[item.name for item in node.names] if isinstance(node,ast.Import) else [node.module or ''] if isinstance(node,ast.ImportFrom) else []
   assert not any(value.split('.')[0] in ('grid','strattester','meta_analyse','subprocess') for value in imports),(name,imports)
 with tarfile.open(sdist) as t:
  members=t.getmembers();names=[member.name for member in members];assert len(names)==len(set(names)) and len(names)<=512
  assert not any('/strattester/' in n or '/grid/' in n or '/meta_analyse/' in n or n.endswith(('.ps1','.cmd','.bat','.exe')) for n in names)
  for source_name,raw in {**source,**v2}.items():
   matched=[member for member in members if member.name.endswith('/'+source_name)]
   assert len(matched)==1 and matched[0].isfile() and matched[0].size==len(raw) and t.extractfile(matched[0]).read()==raw
 site=pathlib.Path(tempfile.mkdtemp(prefix='.artifact-site-',dir=root))
 for archive in (wheel,sdk):
  with zipfile.ZipFile(archive) as z:z.extractall(site)
 bindings={name:hashlib.sha256(raw).hexdigest() for name,raw in {**source,**numerical}.items()}
 print(json.dumps({'bindings':bindings,'artifact_site':str(site),'wheel_sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'sdist_sha256':hashlib.sha256(sdist.read_bytes()).hexdigest(),'runtime_files':len(source),'qualified_v2_files':len(v2),'qualified_v2_source_sha256':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(v2.items())},'python_files':sum(n.endswith('.py') for n in source),'sql_files':sum(n.endswith('.sql') for n in source),'math_files':len(numerical),'byte_comparison':'RAW_IDENTICAL','closed_wheel_members':True,'exact_entrypoints':True,'record_integrity':True,'legacy_packages_absent':True,'native_scripts_absent':True,'source_namespace_scan':'PASS'},sort_keys=True))

if __name__=='__main__':main()
