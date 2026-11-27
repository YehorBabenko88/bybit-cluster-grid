"""Bounded, fail-closed canonical Grid instrument-universe projection.

This is a pure receipt validator over a Root-managed read-only Grid source.
It does NOT infer source completeness from SQL row count, exchange status,
a digest, a locally cached symbol list, or Strattester's registry. No Bybit
transport, writer, Math implementation, or new HTTP listener is created.
"""
import hashlib
import json
import re

_SCHEMA = "market_data.instrument-universe-envelope.v1"
_SOURCE = "CANONICAL_GRID_REGISTRY_PAGINATED"
_SYMBOL = re.compile(r"[A-Z0-9]{1,36}USDT\Z")
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_MAX_SYMBOLS = 50000
_MAX_PAGES = 1000
_MAX_PAGE_SIZE = 1000


class UniverseReadError(ValueError):
    """Never expose a partial/unadmitted registry as a complete universe."""


def _need(condition, reason):
    if condition is not True:
        raise UniverseReadError(reason)


def _sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode("ascii")).hexdigest()


def qualified_universe_snapshot(pages, *, observation_ms, source_receipt):
    """Project exhaustive Grid-owned pages with explicit custody, no mutation.

    The caller MUST supply pages from one Root-authorized read-only database
    transaction and a separately verified *external* source receipt. A hash
    over stored rows proves only row integrity and does NOT establish an
    independent exchange completeness witness.
    """
    _need(type(observation_ms) is int and 0 < observation_ms < 2**63,
          "UNIVERSE_CLOCK_REQUIRED")
    _need(type(pages) in (tuple, list) and 0 < len(pages) <= _MAX_PAGES,
          "UNIVERSE_PAGE_LIMIT")
    _need(type(source_receipt) is dict
          and set(source_receipt) == {
              "schema", "producer", "venue", "market_type", "snapshot_id",
              "source_revision", "lease_epoch", "observed_at_ms",
              "page_count", "complete_count", "completeness",
              "independent_source_attestation", "admitted_by_root",
          }, "UNIVERSE_SOURCE_RECEIPT_REQUIRED")
    r = source_receipt
    _need(r["schema"] == "market_data.instrument-universe-source.v1"
          and r["producer"] == "market_data"
          and r["venue"] == "Bybit" and r["market_type"] == "linear"
          and type(r["snapshot_id"]) is str and _SHA.fullmatch(r["snapshot_id"]) is not None
          and type(r["source_revision"]) is str
          and re.fullmatch(r"[0-9a-f]{40}", r["source_revision"]) is not None
          and type(r["lease_epoch"]) is str and 0 < len(r["lease_epoch"]) <= 128
          and type(r["observed_at_ms"]) is int and r["observed_at_ms"] == observation_ms
          and type(r["page_count"]) is int and r["page_count"] == len(pages)
          and type(r["complete_count"]) is int and 0 < r["complete_count"] <= _MAX_SYMBOLS,
          "UNIVERSE_SOURCE_IDENTITY_REQUIRED")
    # A self-asserted receipt cannot authenticate its own completeness. Do
    # not trust even a caller-forged True, digest, release, or Root label.
    # Production must substitute a distinct independently verified capability
    # issued by Root before any instrument snapshot can be admitted.
    _need(False, "UNIVERSE_INDEPENDENT_ROOT_ATTESTATION_NOT_INSTALLED")
    symbols = []
    for index, page in enumerate(pages):
        _need(type(page) is dict and set(page) == {"page_index", "symbols", "page_sha256"},
              "UNIVERSE_PAGE_SCHEMA")
        values = page["symbols"]
        _need(type(page["page_index"]) is int and page["page_index"] == index
              and type(values) is list and 0 < len(values) <= _MAX_PAGE_SIZE
              and type(page["page_sha256"]) is str
              and _SHA.fullmatch(page["page_sha256"]) is not None,
              "UNIVERSE_PAGE_BOUNDS")
        _need(all(type(s) is str and _SYMBOL.fullmatch(s) is not None for s in values),
              "UNIVERSE_SYMBOL_INVALID")
        _need(values == sorted(set(values))
              and page["page_sha256"] == _sha(values),
              "UNIVERSE_PAGE_INTEGRITY")
        symbols.extend(values)
        _need(len(symbols) <= _MAX_SYMBOLS, "UNIVERSE_TOTAL_LIMIT")
    _need(len(symbols) == r["complete_count"]
          and symbols == sorted(set(symbols)),
          "UNIVERSE_PAGINATION_NOT_EXHAUSTIVE")
    receipt = {
        "schema": _SCHEMA, "api_version": {"major": 1, "minor": 0},
        "status": "PARTIAL", "reason": "GRID_SOURCE_ATTESTED_EXHAUSTIVE",
        "producer": "market_data", "venue": "Bybit", "market_type": "linear",
        "snapshot_id": r["snapshot_id"], "lease_epoch": r["lease_epoch"],
        "source_revision": r["source_revision"], "observation_ms": observation_ms,
        "source_authenticity": "EXTERNALLY_ATTESTED",
        "exchange_completeness": "EXTERNALLY_ATTESTED",
        "source_receipt_verification": "REQUIRES_ROOT_EXTERNAL_VERIFIER",
        "page_count": len(pages), "symbol_count": len(symbols),
        "symbols": symbols, "read_only": True, "execution_authority": False,
        "trading_authorized": False, "paper_admitted": False,
        "consumer_cutover_authorized": False,
    }
    return dict(receipt, dataset_fingerprint=_sha(receipt))


def unavailable_universe(reason="UNIVERSE_SOURCE_NOT_INDEPENDENTLY_ATTESTED"):
    """Public no-data response until a real Root-approved exhaustive source exists."""
    _need(reason == "UNIVERSE_SOURCE_NOT_INDEPENDENTLY_ATTESTED",
          "UNIVERSE_DENIAL_REASON")
    receipt = {
        "schema": _SCHEMA, "api_version": {"major": 1, "minor": 0},
        "status": "UNAVAILABLE", "reason": reason, "producer": "market_data",
        "venue": "Bybit", "market_type": "linear", "source_authenticity": "NOT_ATTESTED",
        "exchange_completeness": "NOT_ATTESTED", "symbols": [],
        "symbol_count": 0, "page_count": 0, "read_only": True,
        "execution_authority": False, "trading_authorized": False,
        "paper_admitted": False, "consumer_cutover_authorized": False,
    }
    return dict(receipt, dataset_fingerprint=_sha(receipt))
