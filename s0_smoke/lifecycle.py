"""Hard deadline targets only this interpreter; never a PID or foreign process."""
import math,os,threading,time
_armed=False
_started=None

def deadline_wait(event,seconds,exit_fn):
 if not event.wait(seconds):exit_fn(124)

def arm_deadline():
 global _armed,_started
 if not _armed:
  _started=time.monotonic()
  _armed=True
  threading.Thread(target=deadline_wait,args=(threading.Event(),300,os._exit),daemon=True,name='s0-self-deadline').start()

def runtime_budget(now=None):
 if _started is None:raise ValueError('S0_DEADLINE_NOT_ARMED')
 elapsed=(time.monotonic() if now is None else now)-_started
 if not math.isfinite(elapsed) or elapsed<0:raise ValueError('S0_DEADLINE_INVALID')
 budget=math.floor(300-elapsed)-5
 if budget<245:raise ValueError('S0_STARTUP_BUDGET_EXHAUSTED')
 return budget
