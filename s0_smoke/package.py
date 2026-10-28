"""Read-only exact extracted-package closure and original ZIP pin validation."""
import hashlib,ntpath,re,stat,zipfile
from pathlib import Path,PurePosixPath
from .policy import need,load_json
MAX_PACKAGE=536870912
PTH=b'stdlib.zip\nDLLs\nSite\nApp\n'

def name(value):
 need(type(value) is str and 0<len(value)<=512 and '\\' not in value and ':' not in value and not value.startswith('/'))
 parts=PurePosixPath(value).parts;need('/'.join(parts)==value and all(p not in ('.','..') and p.rstrip(' .')==p and p.split('.')[0].upper() not in {'CON','NUL','AUX','PRN',*('COM'+str(i) for i in range(10)),*('LPT'+str(i) for i in range(10))} for p in parts));return value

def file_bytes(path,limit=67108864):
 p=Path(path);s=p.lstat();need(p.is_file() and not p.is_symlink() and not getattr(s,'st_file_attributes',0)&0x400 and s.st_nlink==1 and 0<=s.st_size<=limit)
 with p.open('rb') as f:
  b=f.read(limit+1);need(len(b)<=limit);return b

def verify_package(root,archive,head,pin):
 root=Path(root).absolute();archive=Path(archive).absolute()
 need(type(head) is str and re.fullmatch('[0-9a-f]{40}',head) and type(pin) is str and re.fullmatch('[0-9a-f]{64}',pin))
 need(archive.parent==root and archive.name=='source.zip','S0_ARCHIVE_MUST_BE_OWN_SOURCE_ZIP')
 raw=file_bytes(archive,MAX_PACKAGE);need(hashlib.sha256(raw).hexdigest()==pin,'S0_PACKAGE_HASH_BLOCKED')
 manifest_raw=file_bytes(root/'s0-package.json',1048576);m=load_json(manifest_raw)
 fields={'schema','profile','head','tree','run_id','attempt','python','authority','files','source'};need(set(m)==fields and type(m['schema']) is int and m['schema']==1 and m['profile']=='PHYSICAL_SMOKE_S0' and m['head']==head)
 need(m['authority']==dict(s0_execute=False,g1_execute=False,cleanup=False) and all(x is False for x in m['authority'].values()))
 need(type(m['files']) is dict and 5<=len(m['files'])<=20000 and type(m['source']) is dict)
 need(type(m['tree']) is str and re.fullmatch('[0-9a-f]{40}',m['tree']) and type(m['python']) is str and m['python'].startswith('3.12.'))
 for key in ('run_id','attempt'):need(type(m[key]) is str and re.fullmatch('[1-9][0-9]{0,19}',m[key]))
 need({'runtime/python.exe','runtime/python._pth','runtime/python312._pth','runtime/App/s0.py','runtime/stdlib.zip'}<=m['files'].keys())
 names=[];total=0
 for n,f in m['files'].items():
  name(n);need(type(f) is dict and set(f)=={'sha256','size'} and type(f['size']) is int and 0<=f['size']<=67108864 and type(f['sha256']) is str and re.fullmatch('[0-9a-f]{64}',f['sha256']))
  need(not any(p.lower() in ('grid','asyncpg','psycopg','dotenv','pybit','ccxt','telegram') for p in PurePosixPath(n).parts))
  total+=f['size'];need(total<=MAX_PACKAGE);names.append(n)
  b=file_bytes(root/n);need(len(b)==f['size'] and hashlib.sha256(b).hexdigest()==f['sha256'],'S0_EXTRACTED_FILE_CHANGED')
 need(len(names)==len(set(n.casefold() for n in names)))
 for p in root.rglob('*'):
  need(not p.is_symlink() and not getattr(p.lstat(),'st_file_attributes',0)&0x400)
 actual={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}
 need(actual==set(names)|{'s0-package.json','source.zip'},'S0_PACKAGE_EXTRA_FILES')
 for pth in ('runtime/python._pth','runtime/python312._pth'):need(file_bytes(root/pth)==PTH)
 with zipfile.ZipFile(archive) as z:
  entries=z.infolist();zn=[e.filename for e in entries];need(len(zn)==len(set(n.casefold() for n in zn)) and set(zn)==set(names)|{'s0-package.json'})
  for e in entries:
   name(e.filename);need(e.file_size==(len(manifest_raw) if e.filename=='s0-package.json' else m['files'][e.filename]['size']));need(not e.is_dir() and e.file_size<=67108864 and (e.external_attr>>16)&0o170000 != stat.S_IFLNK)
  need(z.read('s0-package.json')==manifest_raw)
  for n,f in m['files'].items():need(hashlib.sha256(z.read(n)).hexdigest()==f['sha256'])
 return m
