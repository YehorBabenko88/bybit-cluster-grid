"""Typed Job accounting model; native child integration is tested separately."""
import ctypes
import pytest
from grid.ml_windows_job import WindowsJob

class Kernel:
 def __init__(self,counts=(2,1,0),fail=None):self.counts=list(counts);self.events=[];self.fail=fail
 def TerminateJobObject(self,handle,code):self.events.append(('terminate',handle));return self.fail!='terminate'
 def QueryInformationJobObject(self,handle,kind,pointer,size,length):
  assert kind==1 and size==48
  self.events.append(('active',self.counts[0]))
  pointer._obj.ActiveProcesses=self.counts[0]
  if len(self.counts)>1:self.counts.pop(0)
  return self.fail!='query'
 def CloseHandle(self,handle):self.events.append(('close',handle));return self.fail!='close'

def job(kernel):
 value=object.__new__(WindowsJob);value._job=77;value._kernel=kernel;return value

def test_terminate_wait_proves_delayed_descendants_empty_before_close():
 kernel=Kernel();owned=job(kernel)
 assert owned.terminate_and_wait(.2) is True
 assert kernel.events==[('terminate',77),('active',2),('active',1),('active',0),('close',77)]
 assert owned._job is None

@pytest.mark.parametrize('failure',['terminate','query','close'])
def test_api_failure_never_returns_empty_proof_or_loses_owned_handle(failure):
 kernel=Kernel((0,),failure);owned=job(kernel)
 with pytest.raises(OSError):owned.terminate_and_wait(.1)
 assert owned._job==77
 if failure!='close':assert not any(event[0]=='close' for event in kernel.events)

def test_still_active_timeout_does_not_close_or_claim_empty(monkeypatch):
 import grid.ml_windows_job as module
 clock=[0.];monkeypatch.setattr(module.time,'monotonic',lambda:clock[0]);monkeypatch.setattr(module.time,'sleep',lambda delay:clock.__setitem__(0,clock[0]+delay))
 kernel=Kernel((1,));owned=job(kernel)
 with pytest.raises(TimeoutError):owned.terminate_and_wait(.02)
 assert owned._job==77 and not any(event[0]=='close' for event in kernel.events)
 owned.close();assert kernel.events[-1]==('close',77) # backward-compatible best effort

def test_missing_handle_and_unbounded_timeout_never_return_proof():
 for value in (None,0):
  owned=job(Kernel());owned._job=value
  with pytest.raises(RuntimeError):owned.terminate_and_wait(.1)
 for timeout in (0,-1,float('nan'),float('inf'),61,True):
  with pytest.raises(ValueError):job(Kernel()).terminate_and_wait(timeout)


def test_late_zero_count_is_not_accepted_after_deadline(monkeypatch):
 import grid.ml_windows_job as module
 clock=[0.];monkeypatch.setattr(module.time,'monotonic',lambda:clock[0])
 class Late(Kernel):
  def QueryInformationJobObject(self,*args):
   result=super().QueryInformationJobObject(*args);clock[0]=1.;return result
 kernel=Late((0,));owned=job(kernel)
 with pytest.raises(TimeoutError):owned.terminate_and_wait(.1)
 assert owned._job==77 and not any(event[0]=='close' for event in kernel.events)


@pytest.mark.skipif(__import__('os').name!='nt',reason='actual owned Windows Job accounting integration')
def test_actual_job_wait_terminates_and_observes_parent_and_descendant_exit(tmp_path):
 import json,os,subprocess,sys,time,psutil
 marker=tmp_path/'owned-child.json'
 code="import json,pathlib,subprocess,sys,time; child=subprocess.Popen([sys.executable,'-I','-S','-B','-c','import time;time.sleep(60)']);pathlib.Path(sys.argv[1]).write_text(json.dumps({'pid':child.pid}));time.sleep(60)"
 child=subprocess.Popen([sys.executable,'-I','-S','-B','-c',code,str(marker)],creationflags=4,env={'SystemRoot':os.environ['SystemRoot'],'TEMP':str(tmp_path),'TMP':str(tmp_path)})
 owned=None;pid=None;birth=None
 try:
  owned=WindowsJob(child.pid,resume_primary_thread=True);deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   if marker.exists():
    try:pid=json.loads(marker.read_text())['pid'];break
    except (OSError,ValueError):pass
   assert child.poll() is None;time.sleep(.01)
  assert pid is not None
  descendant=psutil.Process(pid);birth=descendant.create_time()
  assert pid in [p.pid for p in psutil.Process(child.pid).children(recursive=True)]
  assert owned.terminate_and_wait(5) is True and owned._job is None
  child.wait(timeout=5)
  # Windows may retain a terminated process object while a query handle exists.
  # Wait on the captured owned process identity rather than PID enumeration.
  descendant.wait(timeout=5)
 finally:
  if owned is not None:owned.close()
  if child.poll() is None:child.kill();child.wait(timeout=5)
  if pid is not None:
   try:
    process=psutil.Process(pid)
    if process.create_time()==birth:process.kill();process.wait(timeout=5)
   except psutil.NoSuchProcess:pass
