import json,pytest
from s0_smoke import cli
from s0_smoke.lifecycle import deadline_wait

def test_plan_has_no_host_calls(capsys,monkeypatch):
 monkeypatch.setattr(cli,'dispatch',lambda *_: (_ for _ in ()).throw(AssertionError('dispatch called')))
 assert cli.main([])==0
 v=json.loads(capsys.readouterr().out);assert v['status']=='PLAN_ONLY' and v['g1_execute'] is False and v['command'] is None
@pytest.mark.parametrize('action',['prepare','execute','stop','evidence'])
def test_mutation_without_approval_never_dispatches(action,capsys,monkeypatch):
 monkeypatch.setattr(cli,'dispatch',lambda *_: (_ for _ in ()).throw(AssertionError('dispatch called')))
 assert cli.main(['--action',action])==1
 assert json.loads(capsys.readouterr().out)['status']=='BLOCKED'
def test_watchdog_only_own_exit_callback():
 class Event:
  def wait(self,seconds):assert seconds==300;return False
 got=[];deadline_wait(Event(),300,got.append);assert got==[124]
def test_no_watchdog_exit_when_finished():
 class Event:
  def wait(self,seconds):return True
 got=[];deadline_wait(Event(),300,got.append);assert got==[]


def test_runtime_budget_subtracts_startup_and_finish_reserve(monkeypatch):
 from s0_smoke import lifecycle
 monkeypatch.setattr(lifecycle,'_started',100.)
 assert lifecycle.runtime_budget(now=120.)==275
 with pytest.raises(ValueError):lifecycle.runtime_budget(now=400.)
