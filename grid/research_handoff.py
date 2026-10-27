"""Read-only research import validation. Never issues an order or mutates research DB."""
import re
import uuid
from .provenance import digest

def accept_handoff(record, trusted_sources):
    denied = {"status":"UNAVAILABLE", "reason":"RESEARCH_HANDOFF_INVALID", "execution_authority":False}
    if not isinstance(record, dict):
        return denied
    try:
        version = record["api_version"]
        if type(version["major"]) is not int or version["major"] != 1 or type(version["minor"]) is not int or version["minor"] != 1:
            return denied
        uuid.UUID(record["run_id"])
        if record["producer"] != "strattester" or record["mode"] != "HISTORICAL" or record["execution_authority"] is not False:
            return denied
        identity, revision = record["producer_identity"], record["source_revision"]
        if (identity, revision, record.get("run_id"), record.get("completion_receipt")) not in trusted_sources:
            return {**denied,"reason":"SOURCE_IDENTITY_UNATTESTED"}
        uuid.UUID(record["producer_epoch"])
        dataset = record["dataset"]
        if not re.fullmatch(r"[0-9a-f]{64}", dataset["fingerprint"]):
            return denied
        if any(type(dataset[k]) is not int for k in ("start_ms","end_ms")) or not 0 <= dataset["start_ms"] <= dataset["end_ms"]:
            return denied
        if not all(dataset.get(k) for k in ("source_identity","market_type","symbol","timeframe","coverage")) or dataset.get("missing_data") != [] or dataset["coverage"] != "COMPLETE":
            return {**denied,"reason":"RESEARCH_DATA_INCOMPLETE"}
        if type(record["completed_at_ms"]) is not int or record["completed_at_ms"] < dataset["end_ms"]:
            return denied
        if not all(record.get(k) for k in ("strategy","model","execution_assumptions","metrics")):
            return denied
        receipt = record["completion_receipt"]
        if receipt != digest({k:v for k,v in record.items() if k != "completion_receipt"}):
            return {**denied,"reason":"RESEARCH_RECEIPT_CORRUPT"}
        return {"status":"ACCEPTED_HISTORICAL", "run_id":record["run_id"],
                "completion_receipt":receipt, "execution_authority":False,
                "trading_authorized":False}
    except (KeyError, TypeError, ValueError, AttributeError):
        return denied
