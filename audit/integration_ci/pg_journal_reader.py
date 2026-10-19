"""Strict, read-only parser for the PowerShell GridLab owner.jsonl wire format.

A canonical-byte match is only a serialization check, never native ownership
proof or execution authorization. The digest is for New-GridLabPlan, NOT the
separate PostgreSQL schema-1 plan.
"""
import json
import re

ALLOWED_STATES = (
    ("PREPARED",),
    ("PREPARED", "COMMITTED"),
    ("PREPARED", "RETIRED"),
    ("PREPARED", "COMMITTED", "RETIRED"),
)
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = ("schema", "plan_sha256", "state")
_ALLOWED = frozenset(("PREPARED", "COMMITTED", "RETIRED"))


class _RepeatedKey(ValueError):
    pass


def _unique_pairs(pairs):
    record = {}
    for key, value in pairs:
        if key in record:
            raise _RepeatedKey("duplicate JSON key")
        record[key] = value
    return record


def _reject_constant(value):
    raise ValueError("nonstandard JSON constant")


def _result(errors, states=(), canonical=False):
    return {
        "status": "BLOCKED_UNPROVEN",
        "metadata_valid": not errors,
        "byte_contract_verified": bool(canonical and not errors),
        "lifecycle_phase": states[-1] if not errors and states else "UNVERIFIED",
        "errors": list(dict.fromkeys(errors)),
        "readiness_passed": False,
        "execution_authorized": False,
        "schema_2_enabled": False,
        "physical_ownership_verified": False,
        "note": "Canonical serialization does not authenticate native physical ownership",
    }


def inspect_journal_bytes(journal_text, plan_sha256):
    """Validate exact producer serialization and lifecycle; never authorize use.

    The PowerShell producer emits compact, ordered JSON keys followed by LF,
    encoded as UTF-8 without a BOM. Both input bytes and decoded text are
    supported, but no input is accepted after lossy decoding or reserialization.
    """
    errors = []
    if type(plan_sha256) is not str or _DIGEST.fullmatch(plan_sha256) is None:
        errors.append("INVALID_PLAN_DIGEST")
    if type(journal_text) is bytes:
        try:
            raw = journal_text
            text = raw.decode("utf-8", errors="strict")
        except UnicodeError:
            return _result(errors + ["INVALID_UNICODE"])
    elif type(journal_text) is str:
        text = journal_text
        try:
            raw = text.encode("utf-8", errors="strict")
        except UnicodeError:
            return _result(errors + ["INVALID_UNICODE"])
    else:
        return _result(errors + ["INVALID_JOURNAL_INPUT"])
    if not raw or len(raw) > 4096:
        return _result(errors + ["INVALID_JOURNAL_BOUNDS"])
    if not raw.endswith(b"\n") or b"\r" in raw or raw.startswith(b"\xef\xbb\xbf"):
        errors.append("NONCANONICAL_JSONL")
    states = []
    for raw_line in raw.split(b"\n")[:-1]:
        if not raw_line:
            errors.append("NONCANONICAL_JSONL")
            continue
        try:
            record = json.loads(
                raw_line.decode("utf-8"),
                object_pairs_hook=_unique_pairs,
                parse_constant=_reject_constant,
            )
        except _RepeatedKey:
            errors.append("DUPLICATE_JSON_KEY")
            continue
        except (ValueError, TypeError, RecursionError, UnicodeError):
            errors.append("INVALID_JSONL_RECORD")
            continue
        if type(record) is not dict or tuple(record) != _FIELDS:
            errors.append("INVALID_JOURNAL_SCHEMA")
            continue
        if type(record["schema"]) is not int or record["schema"] != 1:
            errors.append("SCHEMA1_REQUIRED")
        if type(record["plan_sha256"]) is not str or record["plan_sha256"] != plan_sha256:
            errors.append("PLAN_DIGEST_MISMATCH")
        if type(record["state"]) is not str or record["state"] not in _ALLOWED:
            errors.append("INVALID_JOURNAL_STATE")
            continue
        states.append(record["state"])
        # The explicit byte comparison enforces field order, ASCII escaping,
        # whitespace, key spelling and PowerShell's terminal LF policy.
        expected = ('{"schema":1,"plan_sha256":"' + record["plan_sha256"] +
                    '","state":"' + record["state"] + '"}').encode("ascii")
        if raw_line != expected:
            errors.append("NONCANONICAL_JSONL")
    if tuple(states) not in ALLOWED_STATES:
        errors.append("ILLEGAL_JOURNAL_TRANSITION")
    return _result(errors, states, canonical=True)
