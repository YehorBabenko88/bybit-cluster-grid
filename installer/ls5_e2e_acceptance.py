"""Independent fail-closed evidence inspection for a disposable E2E laboratory.

Does not launch coordinator, agents, SQL, cleanup, or rollback.
All input is untrusted. A self-consistent report never proves independent custody.
"""
import hashlib
import io
import json
import re
import zipfile

from installer.ls5_physical_acceptance import AcceptanceBlocked, require, strict_json

SHA40 = re.compile(r"[a-f0-9]{40}\\Z")
SHA64 = re.compile(r"[a-f0-9]{64}\\Z")
PHASES = ("coordinator_start", "agent_register", "assignment", "synthetic_ingest",
          "postgres_commit", "storage_readback", "shutdown", "restart",
          "recovery_readback")
FAULTS = ("crash", "timeout", "network_loss", "db_restart", "corrupted_spool",
          "duplicate_message", "invalid_configuration", "descriptor_drift",
          "interrupted_journal", "cleanup_boundary", "rollback_boundary")
REQUIRED_PRS = (238, 239, 240, 241, 242)


def verify_zip_bytes(raw, *, expected_digest, expected_files):
    """Check actual ZIP bytes, entries, sizes and supplied hashes; not origin."""
    require(type(raw) is bytes and 0 < len(raw) <= 32_000_000, "ZIP_BYTES")
    require(type(expected_digest) is str and SHA64.fullmatch(expected_digest)
            and hashlib.sha256(raw).hexdigest() == expected_digest, "ZIP_DIGEST")
    require(type(expected_files) is dict and bool(expected_files), "ZIP_MANIFEST")
    require(all(type(n) is str and n and not n.startswith("/")
                and "\\\\" not in n and ".." not in n.split("/")
                and type(h) is str and SHA64.fullmatch(h)
                for n, h in expected_files.items()), "ZIP_MANIFEST_ENTRY")
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            entries = archive.infolist()
            names = [x.filename for x in entries]
            require(len(names) == len(set(names)) and set(names) == set(expected_files),
                    "ZIP_INVENTORY")
            require(all(not x.is_dir() and x.file_size <= 4_000_000 and
                        x.compress_size <= 8_000_000 and
                        not (x.external_attr >> 16) & 0o170000 == 0o120000
                        for x in entries), "ZIP_UNSAFE_ENTRY")
            for entry in entries:
                payload = archive.read(entry)
                require(hashlib.sha256(payload).hexdigest() ==
                        expected_files[entry.filename], "ZIP_ENTRY_DIGEST")
    except (zipfile.BadZipFile, RuntimeError, OSError, EOFError, ValueError):
        raise AcceptanceBlocked("ACCEPTANCE_ZIP_INVALID") from None
    return {"zip_consistent": True, "origin_authenticated": False,
            "lab_go": False, "deployment_go": False}


def inspect_e2e(raw, *, expected_head, expected_run, expected_attempt):
    """Assess independent phase and fault evidence without accepting producer PASS."""
    require(type(expected_head) is str and SHA40.fullmatch(expected_head), "E2E_HEAD")
    require(type(expected_run) is int and expected_run > 0 and
            type(expected_attempt) is int and expected_attempt > 0, "E2E_RUN")
    x = strict_json(raw)
    require(type(x) is dict and set(x) == {
        "head", "run_id", "attempt", "phases", "faults", "environment",
        "artifact_sha256", "independent_readback"
    }, "E2E_SCHEMA")
    require(x["head"] == expected_head and type(x["head"]) is str, "E2E_HEAD_MISMATCH")
    require(type(x["run_id"]) is int and x["run_id"] == expected_run and
            type(x["attempt"]) is int and x["attempt"] == expected_attempt,
            "E2E_ATTEMPT_MISMATCH")
    require(x["environment"] == "DISPOSABLE_SYNTHETIC", "E2E_ENVIRONMENT")
    require(type(x["artifact_sha256"]) is str and
            SHA64.fullmatch(x["artifact_sha256"]), "E2E_ARTIFACT_SHA")
    require(type(x["independent_readback"]) is bool, "E2E_READBACK_TYPE")
    for key, expected in (("phases", PHASES), ("faults", FAULTS)):
        rows = x[key]
        require(type(rows) is list and len(rows) == len(expected), "E2E_COUNT")
        for row, name in zip(rows, expected):
            require(type(row) is dict and set(row) == {"name", "status", "evidence"}
                    and row["name"] == name and
                    row["status"] in ("PASS", "FAIL", "BLOCKED", "NOT_RUN")
                    and type(row["evidence"]) is str and len(row["evidence"]) <= 256,
                    "E2E_ROW")
    blockers = [row["name"] for key in ("phases", "faults") for row in x[key]
                if row["status"] != "PASS" or not row["evidence"]]
    return {"status": "BLOCKED", "unverified_or_incomplete": blockers,
            "producer_claims_complete": not blockers,
            "independent_readback_claimed": x["independent_readback"],
            "artifact_bytes_verified": False, "origin_authenticated": False,
            "lab_go": False, "deployment_go": False}


def inspect_g0_g1(prs, *, expected_heads):
    """All five PRs must have verified artifacts and contract evidence; never auto-GO."""
    require(type(expected_heads) is dict and set(expected_heads) == set(REQUIRED_PRS)
            and all(type(k) is int and type(v) is str and SHA40.fullmatch(v)
                    for k, v in expected_heads.items()), "G01_PINS")
    require(type(prs) is list, "G01_TYPE")
    seen = {}
    for row in prs:
        require(type(row) is dict and set(row) == {
            "pr", "head", "workflow", "run_id", "attempt",
            "artifact_sha256", "artifact_bytes_verified", "contract_test"
        }, "G01_SCHEMA")
        n = row["pr"]
        require(type(n) is int and n in expected_heads and n not in seen,
                "G01_PR")
        require(type(row["head"]) is str and row["head"] == expected_heads[n],
                "G01_HEAD")
        require(type(row["run_id"]) is int and row["run_id"] > 0
                and type(row["attempt"]) is int and row["attempt"] > 0, "G01_RUN")
        require(row["workflow"] in ("success", "queued", "pending", "skipped",
                                    "failure", "cancelled", "in_progress"), "G01_WORKFLOW")
        require(type(row["artifact_sha256"]) is str and
                SHA64.fullmatch(row["artifact_sha256"]), "G01_SHA")
        require(type(row["artifact_bytes_verified"]) is bool and
                type(row["contract_test"]) is bool, "G01_FLAGS")
        seen[n] = row
    missing = sorted(set(REQUIRED_PRS) - set(seen))
    blocked = sorted(n for n, row in seen.items()
                     if row["workflow"] != "success"
                     or not row["artifact_bytes_verified"]
                     or not row["contract_test"])
    return {"status": "BLOCKED", "missing_prs": missing,
            "g0_g1_unverified": blocked, "reported_complete": not missing and not blocked,
            "cross_branch_executed": False, "lab_go": False, "deployment_go": False}
