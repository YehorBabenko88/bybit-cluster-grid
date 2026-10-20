"""Live pytest9.1.1 event receipt for the frozen offline inventory only."""
import json,os,pathlib
from _pytest.subtests import SubtestReport
STATE={'nodes':[],'calls':[],'subtests':[],'bad_reports':[]}
def normalize(n):
    path,sep,rest=n.partition('::');return path.replace(chr(92),'/')+sep+rest
def pytest_collection_finish(session):
    STATE['nodes']=[normalize(i.nodeid) for i in session.items]
def pytest_runtest_logreport(report):
    row={'nodeid':normalize(report.nodeid),'outcome':report.outcome,'xfail':hasattr(report,'wasxfail')}
    if isinstance(report,SubtestReport):STATE['subtests'].append(row)
    elif report.when=='call':STATE['calls'].append(row)
    if report.outcome!='passed' or row['xfail']:STATE['bad_reports'].append(row)
def pytest_sessionfinish(session,exitstatus):
    STATE['exitstatus']=int(exitstatus)
    pathlib.Path(os.environ['GRID_OFFLINE_EVENT_RECEIPT']).write_text(json.dumps(STATE,indent=2),encoding='utf8')
