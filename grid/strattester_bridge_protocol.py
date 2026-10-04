from __future__ import annotations
import hashlib,json

PROTOCOL_VERSION=1
REQUIRED=("protocol_version","run_id","job_id","job_type","dataset_hash",
          "code_version","config_hash","input_hash","result_hash","status")


def canonical_json(value):
    return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str)


def digest(value):
    raw=value if isinstance(value,(bytes,bytearray)) else canonical_json(value).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def make_manifest(*,run_id,job_id,job_type,dataset_hash,code_version,config,input_spec,result=None,status="COMPLETE",metrics=None,artifacts=None):
    result_payload={"result":result or {},"metrics":metrics or {},"artifacts":artifacts or []}
    return {
        "protocol_version":PROTOCOL_VERSION,
        "run_id":str(run_id),"job_id":str(job_id),"job_type":str(job_type),
        "dataset_hash":str(dataset_hash),"code_version":str(code_version),
        "config_hash":digest(config or {}),"input_hash":digest(input_spec or {}),
        "result_hash":digest(result_payload),"status":str(status),
        "result":result or {},"metrics":metrics or {},"artifacts":artifacts or [],
    }


def validate_manifest(manifest,expected=None):
    if not isinstance(manifest,dict): raise ValueError("handoff manifest must be an object")
    missing=[k for k in REQUIRED if not manifest.get(k)]
    if missing: raise ValueError("handoff manifest missing: "+",".join(missing))
    if int(manifest["protocol_version"])!=PROTOCOL_VERSION:
        raise ValueError("unsupported handoff protocol version")
    if manifest["status"]!="COMPLETE": raise ValueError("research job is not complete")
    expected=expected or {}
    for key in ("run_id","job_id","job_type","dataset_hash","code_version","config_hash","input_hash"):
        if key in expected and str(manifest.get(key))!=str(expected[key]):
            raise ValueError(f"handoff {key} mismatch")
    actual=digest({"result":manifest.get("result") or {},"metrics":manifest.get("metrics") or {},"artifacts":manifest.get("artifacts") or []})
    if actual!=manifest["result_hash"]: raise ValueError("handoff result hash mismatch")
    return True


def aggregate_fingerprint(manifests):
    """Stable research fingerprint independent of worker identity/completion order."""
    pairs=[]
    for manifest in manifests:
        validate_manifest(manifest)
        pairs.append((str(manifest["job_id"]),str(manifest["result_hash"])))
    ids=[x[0] for x in pairs]
    if len(ids)!=len(set(ids)):raise ValueError("duplicate shard job_id in aggregate")
    return digest(sorted(pairs))
