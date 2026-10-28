"""Bounded, append-only S0 evidence. Never deletes or adopts existing resources."""
import hashlib,os,re,stat,time
from pathlib import Path
from .policy import need,canonical,load_json

def leaf(root,name):
 need(type(name) is str and re.fullmatch(r'[a-zA-Z0-9_-]+(?:\.[a-zA-Z0-9_-]+)*',name) and name.split('.')[0].upper() not in {'CON','PRN','AUX','NUL',*('COM'+str(i) for i in range(10)),*('LPT'+str(i) for i in range(10))})
 return Path(root)/name

def regular(fd):
 s=os.fstat(fd);need(stat.S_ISREG(s.st_mode) and s.st_nlink==1 and not getattr(s,'st_file_attributes',0)&0x400)
 return (s.st_dev,s.st_ino)

def write_new(root,name,data):
 need(type(data) is bytes and len(data)<=1048576);p=leaf(root,name)
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0),0o600)
 with os.fdopen(fd,'wb') as f:
  regular(f.fileno());f.write(data);f.flush();os.fsync(f.fileno())

def read_small(root,name,limit=1048576):
 p=leaf(root,name);s=p.lstat();need(not p.is_symlink() and not getattr(s,'st_file_attributes',0)&0x400 and s.st_nlink==1 and s.st_size<=limit)
 with p.open('rb') as f:
  regular(f.fileno());raw=f.read(limit+1);need(len(raw)<=limit);return raw

class Journal:
 def __init__(self,root,name,context,limit=8388608):
  self.path=leaf(root,name);self.context=dict(context);self.seq=0;self.previous='0'*64;self.size=0;self.limit=limit;self.synced=time.monotonic()
  fd=os.open(self.path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|getattr(os,'O_BINARY',0)|getattr(os,'O_NOFOLLOW',0),0o600)
  self.f=os.fdopen(fd,'wb');self.identity=regular(fd)
 def add(self,kind,value):
  need(regular(self.f.fileno())==self.identity)
  payload=dict(self.context,kind=kind,utc_ms=int(time.time()*1000),value=value)
  unsigned=dict(seq=self.seq+1,previous=self.previous,payload=payload)
  digest=hashlib.sha256(canonical(unsigned)).hexdigest();raw=canonical(dict(unsigned,sha256=digest))+b'\n'
  need(self.size+len(raw)<=self.limit,'S0_EVIDENCE_LIMIT_STOP')
  need(self.f.write(raw)==len(raw));self.f.flush();self.size+=len(raw);self.seq+=1;self.previous=digest
  if time.monotonic()-self.synced>=1:os.fsync(self.f.fileno());self.synced=time.monotonic()
 def close(self):
  if not self.f.closed:self.f.flush();os.fsync(self.f.fileno());self.f.close()
 def __enter__(self):return self
 def __exit__(self,*args):self.close()

def _stop(raw,context):
 v=load_json(raw);need(set(v)==set(context)|{'stop'} and all(v[k]==x for k,x in context.items()) and type(v['stop']) is bool)
 return v['stop']

def stop_requested(root,context):return _stop(read_small(root,'stop.json',4096),context)

def request_stop(root,context):
 # Only cooperative notification in the existing owned slot; never signals/PIDs.
 p=leaf(root,'stop.json')
 with p.open('r+b') as f:
  before=regular(f.fileno());raw=f.read(4097);need(len(raw)<=4096);_stop(raw,context)
  raw=canonical(dict(context,stop=True));f.seek(0);need(f.write(raw)==len(raw));f.truncate();f.flush();os.fsync(f.fileno());need(regular(f.fileno())==before)
