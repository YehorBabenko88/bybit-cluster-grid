from __future__ import annotations
import json,os,pathlib,time

MAX_ENTRIES=500

def _path():
    root=pathlib.Path(os.environ.get("ProgramData",r"C:\ProgramData"))/"BybitClusterGrid"
    return root/"command_receipts.json"

def _load():
    try:
        data=json.loads(_path().read_text(encoding="utf-8"))
        return data if isinstance(data,dict) else {}
    except Exception:
        return {}

def get(command_id):
    item=_load().get(str(command_id))
    return item if isinstance(item,dict) else None

def put(command_id,ok,result=None,error=None):
    p=_path();p.parent.mkdir(parents=True,exist_ok=True)
    data=_load()
    data[str(command_id)]={"ok":bool(ok),"result":result,"error":error,"ts":time.time()}
    if len(data)>MAX_ENTRIES:
        keep=sorted(data.items(),key=lambda kv:float((kv[1] or {}).get("ts",0)),reverse=True)[:MAX_ENTRIES]
        data=dict(keep)
    tmp=p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data,sort_keys=True,default=str),encoding="utf-8")
    os.replace(tmp,p)
