import json, os, pathlib, socket, time

STATE_NAME="connectivity_state.json"

def _data_root():
    return pathlib.Path(os.getenv("ProgramData",r"C:\ProgramData"))/"BybitClusterGrid"

def state_path():
    return _data_root()/STATE_NAME

def load_state():
    p=state_path()
    try: return json.loads(p.read_text(encoding="utf-8"))
    except Exception: return {}

def save_state(state):
    p=state_path(); p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state,sort_keys=True),encoding="utf-8")
    os.replace(tmp,p)

def mark_coordinator_success(now=None):
    now=now or time.time()
    s=load_state(); s["last_coordinator_success"]=now; s["last_internet_success"]=now
    save_state(s)

def mark_internet_success(now=None):
    s=load_state(); s["last_internet_success"]=now or time.time(); save_state(s)

def internet_available(timeout=3):
    # Connectivity check only; no application data is sent.
    for host,port in (("1.1.1.1",443),("8.8.8.8",53)):
        try:
            with socket.create_connection((host,port),timeout=timeout):
                return True
        except OSError:
            pass
    return False

def decommission_due(days=7,now=None):
    now=now or time.time()
    s=load_state()
    last_coord=float(s.get("last_coordinator_success",now))
    last_net=float(s.get("last_internet_success",now))
    threshold=days*86400
    # Destructive self-clean must fail closed on wall-clock discontinuities.
    # A Windows clock jump must never turn minutes of outage into seven days.
    if now < last_coord or now < last_net:
        return False
    coord_age=now-last_coord; net_age=now-last_net
    max_reasonable_age=max(threshold*4,31*86400)
    if coord_age>max_reasonable_age or net_age>max_reasonable_age:
        return False
    # Self-clean only after the machine itself has lacked general Internet for the full period.
    # Coordinator-only outage must never trigger destruction.
    return coord_age>=threshold and net_age>=threshold
