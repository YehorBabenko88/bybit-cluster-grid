"""Fault-isolated extension registry for scientific methods.

A plugin receives immutable event data and returns JSON-compatible observations.
Plugin failures are journaled and can quarantine only that plugin.
"""
from __future__ import annotations
from dataclasses import dataclass
import json,traceback

@dataclass(frozen=True)
class ScientificMethod:
    key:str
    version:str
    schema_version:int
    handler:object
    capabilities:dict
    compatible_from:tuple[int,...]=()

class ScientificMethodRegistry:
    def __init__(self,quarantine_after=5):
        self.methods={};self.quarantine_after=max(1,int(quarantine_after))
    def register(self,method:ScientificMethod):
        if not method.key or int(method.schema_version)<1:raise ValueError("invalid scientific method")
        if method.key in self.methods:raise ValueError("duplicate scientific method")
        self.methods[method.key]=method
    async def sync_db(self,pool):
        for m in self.methods.values():
            existing=await pool.fetchrow("SELECT schema_version FROM scientific_methods WHERE method_key=$1",m.key)
            if existing is not None:
                old=int(existing["schema_version"])
                if old!=int(m.schema_version) and old not in set(int(x) for x in m.compatible_from):
                    raise RuntimeError(f"scientific method {m.key} schema {old}->{m.schema_version} requires explicit compatibility")
            await pool.execute("""INSERT INTO scientific_methods(
              method_key,method_version,schema_version,capabilities)
              VALUES($1,$2,$3,$4::jsonb) ON CONFLICT(method_key) DO UPDATE SET
              method_version=EXCLUDED.method_version,schema_version=EXCLUDED.schema_version,
              capabilities=EXCLUDED.capabilities,updated_at=now()""",
              m.key,m.version,int(m.schema_version),json.dumps(m.capabilities or {},separators=(",",":")))
    async def dispatch(self,pool,event):
        results={}
        for key,m in tuple(self.methods.items()):
            status=await pool.fetchval("SELECT status FROM scientific_methods WHERE method_key=$1",key)
            if status in ("DISABLED","QUARANTINED"):continue
            try:
                value=m.handler(dict(event))
                if hasattr(value,"__await__"):value=await value
                payload=value if isinstance(value,dict) else {"result":value}
                # PostgreSQL jsonb rejects NaN/Infinity: validate before writing,
                # so malformed plugin output is quarantined as a plugin failure.
                serialized=json.dumps(payload,default=str,allow_nan=False,separators=(",",":"))
                await pool.execute("""INSERT INTO scientific_method_events(
                  method_key,event_ts,event_type,payload,schema_version,source_event_id)
                  VALUES($1,COALESCE($2,now()),$3,$4::jsonb,$5,$6)
                  ON CONFLICT (method_key,source_event_id)
                  WHERE source_event_id IS NOT NULL DO NOTHING""",
                  key,event.get("event_ts"),str(event.get("event_type") or "observation"),
                  serialized,int(m.schema_version),
                  event.get("source_event_id"))
                await pool.execute("""UPDATE scientific_methods SET failure_count=0,last_error=NULL,
                  updated_at=now() WHERE method_key=$1""",key)
                results[key]={"ok":True,"payload":payload}
            except Exception as e:
                msg=f"{type(e).__name__}: {e}"[:2000]
                await pool.execute("""INSERT INTO scientific_method_errors(
                  method_key,event_ts,error_type,error_message,context)
                  VALUES($1,$2,$3,$4,$5::jsonb)""",key,event.get("event_ts"),type(e).__name__,str(e)[:2000],
                  json.dumps({"event_type":str(event.get("event_type") or ""),
                            "symbol":str(event.get("symbol") or "")},separators=(",",":")))
                count=await pool.fetchval("""UPDATE scientific_methods SET failure_count=failure_count+1,
                  last_error=$2,status=CASE WHEN failure_count+1 >= $3 THEN 'QUARANTINED' ELSE status END,
                  updated_at=now() WHERE method_key=$1 RETURNING failure_count""",
                  key,msg,self.quarantine_after)
                results[key]={"ok":False,"error":msg,"failure_count":int(count or 0)}
        return results
