"""Protected constructor bridge, never an environment/serialized readiness grant.

Only central admitted service runtime supplies grant and full readmission callback.
Test doubles establish software behavior, not kernel/service qualification.
"""
import copy,ctypes
from pathlib import Path
from .data_first_process import ProcessBlocked,_local,_pinned,need

def capability(value,manifest):
 # Imported only after the central callback has admitted capsule/ACL/source.
 from unified_system.data_first_policy import validate_data_first_grant
 return validate_data_first_grant(value,manifest)

def windows_root():
 api=ctypes.WinDLL('kernel32',use_last_error=True).GetWindowsDirectoryW;api.argtypes=[ctypes.c_wchar_p,ctypes.c_uint];api.restype=ctypes.c_uint
 value=ctypes.create_unicode_buffer(32768);length=api(value,len(value));need(0<length<len(value),'PROCESS_ADMISSION_REQUIRED')
 path=Path(value.value)
 import stat
 for part in (*reversed(path.parents),path):
  info=part.lstat();need(not stat.S_ISLNK(info.st_mode) and not getattr(info,'st_file_attributes',0)&1024,'PROCESS_SOURCE_REJECTED')
 return str(_local(str(path.resolve(strict=True))))

class ProtectedDataFirstAdmission:
 def __init__(self,grant,readmission):
  need(grant is not None and not isinstance(grant,dict) and callable(getattr(grant,'require_current',None)) and callable(readmission),'PROCESS_ADMISSION_REQUIRED')
  self.grant=grant;self.readmission=readmission;self._pin=None;self._cap=None;self._snapshot=None;self._workspace=None
 def admitted(self,*,full=False):
  need(self.grant.require_current() is True,'PROCESS_ADMISSION_REVOKED')
  if self._snapshot is not None and not full:
   self.require_current();return copy.deepcopy(self._snapshot)
  config,manifest=self.readmission(self.grant)
  need(self.grant.require_current() is True,'PROCESS_ADMISSION_REVOKED')
  cap=capability(self.grant.profile.get('data_first'),manifest)
  # Full callback owns capsule/ACL/config/source admission; snapshot revision must
  # remain immutable for this supplier even if an adapter returns changed data.
  import hashlib,json
  pin=hashlib.sha256(json.dumps((config,manifest,cap),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
  need(self._pin is None or self._pin==pin,'PROCESS_ADMISSION_REVOKED');self._pin=pin;self._cap=cap;self._manifest=copy.deepcopy(manifest)
  self._snapshot=copy.deepcopy((config,manifest,cap))
  return config,manifest,cap
 def require_current(self):
  need(self.grant.require_current() is True,'PROCESS_ADMISSION_REVOKED')
  if self._cap is None:self.admitted()
  else:need(capability(self.grant.profile.get('data_first'),self._manifest)==self._cap,'PROCESS_ADMISSION_REVOKED')
  if self._workspace is not None:need(self._workspace.require_current() is True,'PROCESS_ADMISSION_REVOKED')
  return True
 def process_spec(self):
  config,manifest,cap=self.admitted(full=True);root=_local(str(self.grant.code_root));state=_local(config['state_root'])
  need(str(state)==self.grant.descriptor['service_plan']['state'],'PROCESS_ADMISSION_REQUIRED')
  program=config['programs']['grid'];python=program['argv'][0]
  def pin(path):
   path=Path(path);relative=path.relative_to(root).as_posix() if root in path.parents else None
   digest=manifest['files'][relative]['sha256'] if relative in manifest['files'] else program.get('external_file_pins',{}).get(str(path))
   _pinned(str(path),digest,64*1024*1024);return digest
  source=root/manifest['sources']['strattester']['root'];entry=root/manifest['sources']['unified-system']['root']/'unified_system/service_entry.py'
  python_pin=pin(python);entry_pin=pin(entry);worker_pin=pin(source/'strattester/engine/grid_data_first_worker.py')
  deps=_local(str(root/'dependencies/site-packages'));need(deps.is_dir(),'PROCESS_SOURCE_REJECTED')
  self.require_current()
  from unified_system.data_first_workspace import admit_data_first_workspace
  workspace=admit_data_first_workspace(self.grant,manifest)
  need(workspace.require_current() is True,'PROCESS_ADMISSION_REVOKED')
  self._workspace=workspace;self.require_current()
  return dict(python=python,python_sha256=python_pin,bootstrap=str(entry),bootstrap_sha256=entry_pin,source_root=str(source),source_commit=cap['source_commit'],worker_sha256=worker_pin,dependency_roots=[str(deps)],workspace_root=str(workspace.root),system_root=windows_root(),module_version=manifest['sources']['strattester']['version'],release_id=config['release_id'],network_scope='PUBLIC_GET_ONLY_RESEARCH',timeout_seconds=cap['limits']['timeout_seconds'],ram_limit_mb=cap['limits']['ram_limit_mb'])
 def runtime_capability(self):
  self.require_current();cap=self._cap;return {'protocol':'grid.stratt-data-first.v1','source_commit':cap['source_commit']}

 def owner_admitted_grid_root(self,expected_commit):
  _,manifest,_=self.admitted(full=True)
  source=manifest['sources']['grid']
  need(source['commit']==expected_commit,'PROCESS_SOURCE_REJECTED')
  root=_local(str(self.grant.code_root/source['root']))
  self.require_current();return root
